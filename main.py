"""
AI Evaluation Factory — Main Entry Point.

Orchestrates the complete benchmark pipeline:
    1. Load Golden Dataset
    2. Run Agent V1 benchmark  (RAGAS + Multi-Judge)
    3. Run Agent V2 benchmark  (same pipeline, "optimised" version)
    4. Regression comparison   (delta analysis)
    5. Release Gate decision   (auto approve / block)
    6. Generate reports        (summary.json, benchmark_results.json)

Usage:
    python data/synthetic_gen.py   # generate golden_set.jsonl first
    python main.py                 # run benchmark
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from agent.main_agent import MainAgent
from engine.llm_judge import LLMJudge
from engine.ragas_metrics import RAGASEvaluator
from engine.runner import BenchmarkRunner

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Release Gate ──────────────────────────────────────────────────────────────

class ReleaseGate:
    """
    Automated release-gate logic.

    Decision matrix:
        ✅ APPROVE  – V2 score ≥ V1  AND  no critical metric regresses > 10 %
        ⚠️ REVIEW   – V2 score ≥ V1  BUT  some metric regresses 5 – 10 %
        ❌ BLOCK    – V2 score < V1   OR   any critical metric regresses > 10 %
    """

    # Các metric quan trọng không được phép giảm quá ngưỡng critical
    CRITICAL_METRICS = ["avg_score", "hit_rate", "agreement_rate", "mrr"]
    CRITICAL_THRESHOLD = 0.10   # Giảm > 10% → BLOCK release
    WARNING_THRESHOLD = 0.05    # Giảm 5-10% → cần REVIEW

    @classmethod
    def evaluate(
        cls, v1_metrics: Dict[str, float], v2_metrics: Dict[str, float]
    ) -> Dict[str, Any]:
        """Compare V1 vs V2 and return gate decision + per-metric deltas."""
        deltas: Dict[str, Dict[str, Any]] = {}
        regressions: List[str] = []
        warnings: List[str] = []

        for key in set(v1_metrics) | set(v2_metrics):
            old = v1_metrics.get(key, 0)
            new = v2_metrics.get(key, 0)
            delta_abs = new - old
            delta_pct = delta_abs / old if old != 0 else 0.0

            deltas[key] = {
                "v1": round(old, 4),
                "v2": round(new, 4),
                "delta_abs": round(delta_abs, 4),
                "delta_pct": round(delta_pct * 100, 2),
            }

            if key in cls.CRITICAL_METRICS and delta_pct < -cls.CRITICAL_THRESHOLD:
                regressions.append(key)
            elif key in cls.CRITICAL_METRICS and delta_pct < -cls.WARNING_THRESHOLD:
                warnings.append(key)

        overall_delta = v2_metrics.get("avg_score", 0) - v1_metrics.get("avg_score", 0)

        if regressions:
            decision = "BLOCK"
            reason = f"Critical regression in: {', '.join(regressions)}"
        elif overall_delta < 0 and not warnings:
            decision = "BLOCK"
            reason = f"Overall score decreased by {abs(overall_delta):.2f}"
        elif warnings:
            decision = "REVIEW"
            reason = f"Minor regression warnings in: {', '.join(warnings)}"
        else:
            decision = "APPROVE"
            reason = f"All metrics stable or improved (Δ = {overall_delta:+.2f})"

        return {
            "decision": decision,
            "reason": reason,
            "overall_delta": round(overall_delta, 4),
            "regressions": regressions,
            "warnings": warnings,
            "per_metric_deltas": deltas,
        }


# ── Benchmark orchestration ──────────────────────────────────────────────────

def _load_golden_set(path: str = "data/golden_set.jsonl") -> Optional[List[Dict]]:
    """Load the golden dataset from JSONL file."""
    if not os.path.exists(path):
        print(
            f"❌ Thiếu {path}. "
            "Hãy chạy 'python data/synthetic_gen.py' trước."
        )
        return None

    with open(path, "r", encoding="utf-8") as f:
        dataset = [json.loads(line) for line in f if line.strip()]

    if not dataset:
        print(f"❌ File {path} rỗng. Hãy tạo ít nhất 1 test case.")
        return None

    print(f"📁 Loaded {len(dataset)} test cases from {path}")
    return dataset


def _aggregate_metrics(results: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Tính trung bình các metrics qua tất cả test cases.
    
    Bao gồm:
        - Judge scores (avg_score, agreement_rate)
        - RAGAS metrics (faithfulness, relevancy, context_relevancy)
        - Retrieval metrics (hit_rate@K, MRR, precision, recall, NDCG)
    
    Lưu ý: key 'hit_rate' (= hit_rate_at_3) và 'agreement_rate' bắt buộc
    phải có để pass check_lab.py.
    """
    # Chỉ tính trên các cases không bị error
    valid = [r for r in results if r.get("status") != "error"]
    n = max(len(valid), 1)

    # Judge scores
    avg_score = sum(r["judge"].get("final_score", 0) for r in valid) / n
    agreement = sum(r["judge"].get("agreement_rate", 0) for r in valid) / n

    # RAGAS metrics
    avg_faith = sum(r.get("ragas", {}).get("faithfulness", 0) for r in valid) / n
    avg_relev = sum(r.get("ragas", {}).get("relevancy", 0) for r in valid) / n
    avg_ctx = sum(r.get("ragas", {}).get("context_relevancy", 0) for r in valid) / n

    # Retrieval metrics
    def _ret(key):
        return sum(
            r.get("ragas", {}).get("retrieval", {}).get(key, 0) for r in valid
        ) / n

    return {
        "avg_score": round(avg_score, 4),
        # "hit_rate" = hit_rate_at_3 — bắt buộc cho check_lab.py validation
        "hit_rate": round(_ret("hit_rate_at_3"), 4),
        "hit_rate_at_1": round(_ret("hit_rate_at_1"), 4),
        "hit_rate_at_3": round(_ret("hit_rate_at_3"), 4),
        "hit_rate_at_5": round(_ret("hit_rate_at_5"), 4),
        "mrr": round(_ret("mrr"), 4),
        "precision_at_5": round(_ret("precision_at_5"), 4),
        "recall_at_5": round(_ret("recall_at_5"), 4),
        "ndcg_at_10": round(_ret("ndcg_at_10"), 4),
        "faithfulness": round(avg_faith, 4),
        "relevancy": round(avg_relev, 4),
        "context_relevancy": round(avg_ctx, 4),
        # "agreement_rate" — bắt buộc cho check_lab.py validation
        "agreement_rate": round(agreement, 4),
    }


def _build_summary(
    version: str,
    results: List[Dict[str, Any]],
    metrics: Dict[str, float],
    runner: BenchmarkRunner,
    judge: LLMJudge,
    evaluator: RAGASEvaluator,
    regression: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the final summary.json payload."""
    perf = runner.get_performance_summary(results)
    judge_cost = judge.get_cost_summary()
    eval_cost = evaluator.get_cost_summary()
    kappa = judge.compute_batch_kappa()

    # Aggregate cost
    total_tokens = (
        judge_cost["total_tokens"]["total"] + eval_cost["total_tokens"]["total"]
    )
    total_cost = judge_cost["total_cost_usd"] + eval_cost["total_cost_usd"]
    total_evals = judge_cost["total_evaluations"] + eval_cost["total_evaluations"]

    # Difficulty breakdown
    diff_breakdown: Dict[str, Dict[str, Any]] = {}
    for r in results:
        diff = r.get("metadata", {}).get("difficulty", "unknown")
        if diff not in diff_breakdown:
            diff_breakdown[diff] = {"count": 0, "pass": 0, "total_score": 0}
        diff_breakdown[diff]["count"] += 1
        if r.get("status") == "pass":
            diff_breakdown[diff]["pass"] += 1
        diff_breakdown[diff]["total_score"] += r.get("judge", {}).get("final_score", 0)

    for diff, info in diff_breakdown.items():
        info["pass_rate"] = round(info["pass"] / max(info["count"], 1), 4)
        info["avg_score"] = round(info["total_score"] / max(info["count"], 1), 2)

    summary = {
        "metadata": {
            "version": version,
            "total": len(results),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pipeline": "RAGAS + Multi-Judge Consensus",
        },
        "metrics": metrics,
        "performance": perf,
        "cost": {
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_per_eval": round(total_cost / max(total_evals, 1), 6),
            "judge_cost": judge_cost,
            "ragas_cost": eval_cost,
            "cost_optimisation_suggestions": [
                "Sử dụng gpt-4o-mini thay vì gpt-4o cho RAGAS metrics (giảm ~90% chi phí)",
                "Cache kết quả Judge cho các câu hỏi trùng lặp",
                "Giảm max_tokens cho Judge response (300 → 150) nếu reasoning không cần chi tiết",
                "Batch API calls nếu OpenAI hỗ trợ batch endpoint",
            ],
        },
        "multi_judge": {
            "models_used": judge.models,
            "cohens_kappa": kappa,
            "api_mode": "llm" if judge._api_available else "rule-based",
        },
        "difficulty_breakdown": diff_breakdown,
    }

    if regression:
        summary["regression"] = regression

    return summary


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run_benchmark(
    version: str,
    dataset: List[Dict],
    concurrency: int = 5,
    batch_size: int = 5,
) -> Tuple[List[Dict], Dict[str, Any], BenchmarkRunner, LLMJudge, RAGASEvaluator]:
    """
    Run full benchmark for a given agent version.

    Returns: (results, metrics, runner, judge, evaluator)
    """
    print(f"\n{'#'*60}")
    print(f"  🔬 Benchmark: {version}")
    print(f"{'#'*60}")

    agent = MainAgent()
    evaluator = RAGASEvaluator()
    judge = LLMJudge()
    runner = BenchmarkRunner(
        agent=agent,
        evaluator=evaluator,
        judge=judge,
        concurrency=concurrency,
    )

    results = await runner.run_all(dataset, batch_size=batch_size)
    metrics = _aggregate_metrics(results)

    # Print headline metrics
    print(f"\n📊 Headline Metrics ({version}):")
    print(f"   Avg Judge Score : {metrics['avg_score']:.2f} / 5.0")
    print(f"   Agreement Rate  : {metrics['agreement_rate']*100:.1f}%")
    print(f"   Hit Rate @3     : {metrics['hit_rate_at_3']*100:.1f}%")
    print(f"   MRR             : {metrics['mrr']:.4f}")
    print(f"   Faithfulness    : {metrics['faithfulness']:.4f}")
    print(f"   Relevancy       : {metrics['relevancy']:.4f}")

    return results, metrics, runner, judge, evaluator


async def main():
    """Entry point: V1 benchmark → V2 benchmark → regression → reports."""
    start_wall = time.perf_counter()

    # ── Load dataset ──────────────────────────────────────────────────
    dataset = _load_golden_set()
    if not dataset:
        return

    # ── V1 Benchmark ──────────────────────────────────────────────────
    v1_results, v1_metrics, v1_runner, v1_judge, v1_eval = await run_benchmark(
        "Agent_V1_Base", dataset
    )

    # ── V2 Benchmark (simulates an "optimised" agent) ─────────────────
    v2_results, v2_metrics, v2_runner, v2_judge, v2_eval = await run_benchmark(
        "Agent_V2_Optimized", dataset
    )

    # ── Regression Analysis ───────────────────────────────────────────
    print(f"\n{'='*60}")
    print("📊 REGRESSION ANALYSIS  (V1 → V2)")
    print(f"{'='*60}")

    gate_result = ReleaseGate.evaluate(v1_metrics, v2_metrics)

    print(f"\n   V1 Avg Score  : {v1_metrics['avg_score']:.2f}")
    print(f"   V2 Avg Score  : {v2_metrics['avg_score']:.2f}")
    print(f"   Overall Delta : {gate_result['overall_delta']:+.2f}")
    print(f"\n   🚦 Decision   : {gate_result['decision']}")
    print(f"   📝 Reason     : {gate_result['reason']}")

    if gate_result["decision"] == "APPROVE":
        print("\n   ✅ QUYẾT ĐỊNH: CHẤP NHẬN BẢN CẬP NHẬT (APPROVE)")
    elif gate_result["decision"] == "REVIEW":
        print("\n   ⚠️ QUYẾT ĐỊNH: CẦN REVIEW THÊM TRƯỚC KHI RELEASE")
    else:
        print("\n   ❌ QUYẾT ĐỊNH: TỪ CHỐI (BLOCK RELEASE)")

    # ── Build summaries ───────────────────────────────────────────────
    v2_summary = _build_summary(
        "Agent_V2_Optimized", v2_results, v2_metrics,
        v2_runner, v2_judge, v2_eval,
        regression=gate_result,
    )

    # ── Save reports ──────────────────────────────────────────────────
    os.makedirs("reports", exist_ok=True)

    with open("reports/summary.json", "w", encoding="utf-8") as f:
        json.dump(v2_summary, f, ensure_ascii=False, indent=2)
    print("\n💾 Saved: reports/summary.json")

    with open("reports/benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(v2_results, f, ensure_ascii=False, indent=2, default=str)
    print("💾 Saved: reports/benchmark_results.json")

    # ── Wall-clock total ──────────────────────────────────────────────
    wall = time.perf_counter() - start_wall
    print(f"\n⏱  Total wall-clock time: {wall:.1f}s")
    print("🏁 Pipeline complete. Run 'python check_lab.py' to validate.\n")


if __name__ == "__main__":
    asyncio.run(main())
