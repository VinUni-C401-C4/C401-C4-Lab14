"""
Async Benchmark Runner for AI Evaluation Factory.

Orchestrates the full evaluation pipeline:
    Agent query → RAGAS scoring → Multi-Judge evaluation
with concurrency control, retry logic, cost tracking, and progress reporting.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """
    High-performance async benchmark runner.

    Features:
        - Semaphore-based concurrency control (prevents rate limiting)
        - Exponential-backoff retry on transient failures
        - Per-case and aggregate latency tracking
        - Token & cost accumulation
        - Structured progress reporting
    """

    def __init__(
        self,
        agent,
        evaluator,
        judge,
        concurrency: int = 5,
        max_retries: int = 3,
        timeout: float = 60.0,
    ):
        self.agent = agent
        self.evaluator = evaluator
        self.judge = judge
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.timeout = timeout

        # Semaphore giới hạn số lượng API calls đồng thời
        # Tránh bị rate-limit khi gọi OpenAI API song song
        self.semaphore = asyncio.Semaphore(concurrency)

        # Theo dõi hiệu suất và lỗi
        self._start_time: Optional[float] = None
        self._errors: List[Dict[str, Any]] = []

    # ── Single test case ──────────────────────────────────────────────────

    async def run_single_test(
        self, test_case: Dict[str, Any], case_index: int = 0
    ) -> Dict[str, Any]:
        """
        Execute one test case through the full pipeline:
        1. Agent query  2. RAGAS scoring  3. Multi-Judge evaluation

        Uses a semaphore to cap concurrent API calls and retries
        on transient failures with exponential backoff.
        """
        case_id = test_case.get("id", f"tc_{case_index:03d}")

        # Semaphore đảm bảo chỉ có tối đa `concurrency` tasks chạy cùng lúc
        async with self.semaphore:
            start = time.perf_counter()

            # Retry với exponential backoff: 2s, 4s, 8s (tối đa max_retries lần)
            for attempt in range(1, self.max_retries + 1):
                try:
                    # ── Step 1: Agent query ───────────────────────────
                    agent_start = time.perf_counter()
                    response = await asyncio.wait_for(
                        self.agent.query(test_case["question"]),
                        timeout=self.timeout,
                    )
                    agent_ms = (time.perf_counter() - agent_start) * 1000

                    # ── Step 2: RAGAS metrics ─────────────────────────
                    eval_start = time.perf_counter()
                    ragas_scores = await self.evaluator.score(test_case, response)
                    eval_ms = (time.perf_counter() - eval_start) * 1000

                    # ── Step 3: Multi-Judge ───────────────────────────
                    judge_start = time.perf_counter()
                    judge_result = await self.judge.evaluate_multi_judge(
                        test_case["question"],
                        response["answer"],
                        test_case["expected_answer"],
                    )
                    judge_ms = (time.perf_counter() - judge_start) * 1000

                    total_ms = (time.perf_counter() - start) * 1000

                    # ── Assemble result ───────────────────────────────
                    agent_tokens = response.get("metadata", {}).get("tokens_used", 0)
                    final_score = judge_result.get("final_score", 0)

                    return {
                        "id": case_id,
                        "test_case": test_case["question"],
                        "expected_answer": test_case["expected_answer"],
                        "agent_response": response["answer"],
                        "retrieved_ids": response.get("retrieved_ids", []),
                        "expected_retrieval_ids": test_case.get(
                            "expected_retrieval_ids", []
                        ),
                        "latency": {
                            "agent_ms": round(agent_ms, 2),
                            "eval_ms": round(eval_ms, 2),
                            "judge_ms": round(judge_ms, 2),
                            "total_ms": round(total_ms, 2),
                        },
                        "ragas": ragas_scores,
                        "judge": judge_result,
                        "tokens_used": agent_tokens,
                        "status": "pass" if final_score >= 3 else "fail",
                        "metadata": {
                            "difficulty": test_case.get("metadata", {}).get(
                                "difficulty", "unknown"
                            ),
                            "type": test_case.get("metadata", {}).get(
                                "type", "unknown"
                            ),
                            "attempt": attempt,
                        },
                    }

                except asyncio.TimeoutError:
                    logger.warning(
                        "Timeout for %s (attempt %d/%d)",
                        case_id, attempt, self.max_retries,
                    )
                except Exception as exc:
                    logger.warning(
                        "Error for %s (attempt %d/%d): %s",
                        case_id, attempt, self.max_retries, exc,
                    )

                # Back off trước khi retry (exponential: 2s, 4s, max 8s)
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 8))

            # Hết số lần retry → ghi nhận error và trả về kết quả lỗi
            total_ms = (time.perf_counter() - start) * 1000
            error_info = {"case_id": case_id, "error": "Max retries exceeded"}
            self._errors.append(error_info)

            return {
                "id": case_id,
                "test_case": test_case["question"],
                "expected_answer": test_case.get("expected_answer", ""),
                "agent_response": "ERROR: evaluation failed after retries",
                "retrieved_ids": [],
                "expected_retrieval_ids": test_case.get("expected_retrieval_ids", []),
                "latency": {"total_ms": round(total_ms, 2)},
                "ragas": {},
                "judge": {"final_score": 0, "agreement_rate": 0},
                "tokens_used": 0,
                "status": "error",
                "metadata": {
                    "difficulty": test_case.get("metadata", {}).get(
                        "difficulty", "unknown"
                    ),
                    "type": test_case.get("metadata", {}).get("type", "unknown"),
                    "attempt": self.max_retries,
                    "error": "Max retries exceeded",
                },
            }

    # ── Batch execution ───────────────────────────────────────────────────

    async def run_all(
        self, dataset: List[Dict[str, Any]], batch_size: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Run all test cases in batches with progress reporting.

        Uses asyncio.gather within each batch for parallelism,
        and processes batches sequentially to avoid rate-limit bursts.
        """
        self._start_time = time.perf_counter()
        self._errors = []
        total_cases = len(dataset)
        total_batches = (total_cases + batch_size - 1) // batch_size

        print(f"\n{'='*60}")
        print(f"🚀 Benchmark Runner — {total_cases} cases, "
              f"concurrency={self.concurrency}, batch_size={batch_size}")
        print(f"{'='*60}")

        results: List[Dict[str, Any]] = []

        for batch_idx in range(0, total_cases, batch_size):
            batch = dataset[batch_idx: batch_idx + batch_size]
            batch_num = batch_idx // batch_size + 1

            print(f"\n  📦 Batch {batch_num}/{total_batches}  "
                  f"[cases {batch_idx + 1}–{batch_idx + len(batch)}]")

            batch_start = time.perf_counter()
            # asyncio.gather chạy song song các test cases trong batch
            # Kết hợp với semaphore để giới hạn concurrent API calls
            tasks = [
                self.run_single_test(case, case_index=batch_idx + j)
                for j, case in enumerate(batch)
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            batch_time = time.perf_counter() - batch_start

            for i, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error("Unhandled exception in batch: %s", result)
                    results.append({
                        "id": f"tc_{batch_idx + i + 1:03d}",
                        "status": "error",
                        "error": str(result),
                        "judge": {"final_score": 0, "agreement_rate": 0},
                        "ragas": {},
                        "latency": {"total_ms": 0},
                    })
                else:
                    results.append(result)

            # Batch summary
            pass_cnt = sum(1 for r in batch_results
                          if not isinstance(r, Exception) and r.get("status") == "pass")
            fail_cnt = sum(1 for r in batch_results
                          if not isinstance(r, Exception) and r.get("status") == "fail")
            err_cnt = len(batch) - pass_cnt - fail_cnt
            print(f"     ✅ {pass_cnt} pass  ❌ {fail_cnt} fail  "
                  f"⚠️ {err_cnt} error  ⏱ {batch_time:.1f}s")

        # Final summary
        elapsed = time.perf_counter() - self._start_time
        passed = sum(1 for r in results if r.get("status") == "pass")
        failed = sum(1 for r in results if r.get("status") == "fail")
        errors = sum(1 for r in results if r.get("status") == "error")

        print(f"\n{'='*60}")
        print(f"✅ Benchmark completed in {elapsed:.1f}s")
        print(f"   Pass: {passed}/{total_cases}  ({passed/total_cases*100:.0f}%)")
        print(f"   Fail: {failed}/{total_cases}  ({failed/total_cases*100:.0f}%)")
        print(f"   Error: {errors}/{total_cases}")
        print(f"   Throughput: {total_cases / max(elapsed, 0.01):.1f} cases/s")
        print(f"{'='*60}\n")

        return results

    # ── Performance summary ───────────────────────────────────────────────

    def get_performance_summary(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute aggregate performance statistics from results."""
        elapsed = (
            time.perf_counter() - self._start_time
            if self._start_time
            else 0
        )

        latencies = [
            r["latency"]["total_ms"]
            for r in results
            if r.get("status") != "error" and "total_ms" in r.get("latency", {})
        ]
        latencies_sorted = sorted(latencies) if latencies else [0]

        return {
            "total_time_seconds": round(elapsed, 2),
            "total_cases": len(results),
            "passed": sum(1 for r in results if r.get("status") == "pass"),
            "failed": sum(1 for r in results if r.get("status") == "fail"),
            "errors": sum(1 for r in results if r.get("status") == "error"),
            "throughput_cases_per_sec": round(
                len(results) / max(elapsed, 0.001), 2
            ),
            # Latency percentiles: avg, min, max, p50 (median), p95, p99
            # p95/p99 quan trọng để đánh giá tail latency trong production
            "latency_ms": {
                "avg": round(sum(latencies) / max(len(latencies), 1), 2),
                "min": round(latencies_sorted[0], 2),
                "max": round(latencies_sorted[-1], 2),
                "p50": round(
                    latencies_sorted[len(latencies_sorted) // 2], 2
                ),
                "p95": round(
                    latencies_sorted[int(len(latencies_sorted) * 0.95)], 2
                ),
                "p99": round(
                    latencies_sorted[int(len(latencies_sorted) * 0.99)], 2
                ),
            },
            "error_details": self._errors,
        }
