"""
RAGAS-style Metrics Evaluator for AI Agent Benchmark.

Computes Faithfulness, Answer Relevancy, and Context Relevancy
alongside retrieval metrics (Hit Rate, MRR, Precision, Recall, NDCG).

Supports LLM-based evaluation via OpenAI API with an automatic
fallback to NLP-heuristic scoring when the API is unavailable.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from engine.retrieval_eval import RetrievalEvaluator

load_dotenv()
logger = logging.getLogger(__name__)

# Danh sách từ dừng tiếng Việt — loại bỏ khi tính keyword overlap
# để chỉ giữ lại các từ có ý nghĩa nội dung (content words)
_STOP_WORDS = frozenset({
    "là", "và", "của", "cho", "có", "không", "được", "với", "các",
    "một", "trong", "từ", "đến", "theo", "để", "hoặc", "hay", "cần",
    "phải", "nếu", "thì", "bạn", "tôi", "về", "này", "đó", "khi",
    "như", "mà", "còn", "nhưng", "vì", "do", "nên", "tại", "rất",
    "cũng", "đã", "sẽ", "đang", "hãy", "xin", "ở", "ra", "lên",
    "đi", "đây", "kia", "nào", "gì", "sao", "thế", "ai",
})


def _keywords(text: str) -> set:
    """Return meaningful keywords from Vietnamese text."""
    return set(text.lower().split()) - _STOP_WORDS


def _split_sentences(text: str) -> List[str]:
    """Split Vietnamese/mixed text into sentences."""
    parts = re.split(r"[.!?;]\s*", text)
    return [s.strip() for s in parts if len(s.strip()) > 5]


# ─── LLM evaluation prompts ──────────────────────────────────────────────────

_FAITHFULNESS_PROMPT = (
    "Bạn là chuyên gia đánh giá AI. Hãy kiểm tra xem câu trả lời dưới đây "
    "có TRUNG THÀNH (faithful) với ngữ cảnh (context) được cung cấp không.\n\n"
    "Context:\n{context}\n\n"
    "Câu trả lời:\n{answer}\n\n"
    "Trả lời JSON: {{\"score\": <0.0-1.0>, \"reasoning\": \"<giải thích>\"}}"
)

_RELEVANCY_PROMPT = (
    "Bạn là chuyên gia đánh giá AI. Hãy đánh giá mức độ LIÊN QUAN "
    "(relevancy) của câu trả lời so với câu hỏi.\n\n"
    "Câu hỏi:\n{question}\n\n"
    "Câu trả lời:\n{answer}\n\n"
    "Ground Truth:\n{ground_truth}\n\n"
    "Trả lời JSON: {{\"score\": <0.0-1.0>, \"reasoning\": \"<giải thích>\"}}"
)

# ──────────────────────────────────────────────────────────────────────────────


class RAGASEvaluator:
    """
    Computes RAGAS-style metrics + retrieval quality for each test case.

    Metrics produced:
        - faithfulness    (0–1): Is the answer grounded in the retrieved context?
        - relevancy       (0–1): Does the answer address the question?
        - context_relevancy (0–1): Are the retrieved chunks relevant to the query?
        - retrieval.*     : Hit Rate@K, MRR, Precision@K, Recall@K, NDCG@K
    """

    def __init__(self, use_llm: bool = True):
        # Sử dụng RetrievalEvaluator có sẵn cho Hit Rate, MRR, Precision, Recall, NDCG
        self.retrieval_evaluator = RetrievalEvaluator()
        self._client = None
        self._api_available = False

        # Theo dõi token và chi phí API cho RAGAS metrics
        self.total_tokens: Dict[str, int] = {"prompt": 0, "completion": 0}
        self.total_cost: float = 0.0
        self.eval_count: int = 0

        # Khởi tạo OpenAI client nếu được bật và có API key
        if use_llm:
            self._init_client()

    def _init_client(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if api_key and len(api_key) > 10:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=api_key)
                self._api_available = True
                logger.info("✅ OpenAI API initialised for RAGAS metrics")
            except ImportError:
                logger.warning("⚠️ openai not installed — using heuristic RAGAS")
        else:
            logger.info("ℹ️ OPENAI_API_KEY not set — using heuristic RAGAS metrics")

    # ── Public interface ──────────────────────────────────────────────────

    async def score(
        self, test_case: Dict[str, Any], agent_response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate a single (test_case, agent_response) pair.

        Returns:
            dict with faithfulness, relevancy, context_relevancy,
            and retrieval sub-dict.
        """
        self.eval_count += 1

        question = test_case.get("question", "")
        ground_truth = test_case.get("expected_answer", "")
        answer = agent_response.get("answer", "")
        contexts = agent_response.get("contexts", [])

        # Chạy đồng thời 3 async metrics + 1 sync metric để tối ưu thời gian
        faith_task = self._compute_faithfulness(answer, contexts)
        rel_task = self._compute_relevancy(question, answer, ground_truth)
        # Context relevancy là heuristic thuần (sync) — không cần await
        ctx_rel = self._compute_context_relevancy(question, contexts)
        retrieval_task = self.retrieval_evaluator.evaluate_single(test_case, agent_response)

        # asyncio.gather chạy song song faithfulness + relevancy + retrieval eval
        faithfulness, relevancy, retrieval = await asyncio.gather(
            faith_task, rel_task, retrieval_task
        )

        return {
            "faithfulness": round(faithfulness, 4),
            "relevancy": round(relevancy, 4),
            "context_relevancy": round(ctx_rel, 4),
            "retrieval": {
                "hit_rate_at_1": retrieval["hit_rate_at_1"],
                "hit_rate_at_3": retrieval["hit_rate_at_3"],
                "hit_rate_at_5": retrieval["hit_rate_at_5"],
                "mrr": retrieval["mrr"],
                "precision_at_5": retrieval["precision_at_5"],
                "recall_at_5": retrieval["recall_at_5"],
                "ndcg_at_10": retrieval["ndcg_at_10"],
            },
        }

    # ── Faithfulness ──────────────────────────────────────────────────────

    async def _compute_faithfulness(
        self, answer: str, contexts: List[str]
    ) -> float:
        """Faithfulness: is the answer grounded in the retrieved context?"""
        if not answer or not contexts:
            return 0.0

        combined_context = " ".join(contexts)

        if self._api_available:
            try:
                return await self._faithfulness_llm(answer, combined_context)
            except Exception as exc:
                logger.warning("LLM faithfulness failed: %s — fallback", exc)

        return self._faithfulness_heuristic(answer, combined_context)

    async def _faithfulness_llm(self, answer: str, context: str) -> float:
        """Use LLM to evaluate faithfulness."""
        prompt = _FAITHFULNESS_PROMPT.format(
            context=context[:3000], answer=answer[:1000]
        )
        result = await self._call_llm(prompt)
        return max(0.0, min(1.0, result.get("score", 0.5)))

    @staticmethod
    def _faithfulness_heuristic(answer: str, context: str) -> float:
        """
        Heuristic faithfulness: fraction of answer sentences whose
        keywords overlap with the context.
        """
        sentences = _split_sentences(answer)
        if not sentences:
            return 0.5

        ctx_kw = _keywords(context)
        if not ctx_kw:
            return 0.5

        # Với mỗi câu trong answer, kiểm tra keyword overlap với context
        # overlap ≥ 30% → hoàn toàn supported (1.0)
        # overlap 15-30% → partially supported (0.5)
        # overlap < 15% → not supported (0.0)
        supported = 0
        for sent in sentences:
            s_kw = _keywords(sent)
            if not s_kw:
                supported += 0.5  # Câu quá ngắn → không đánh giá được
                continue
            overlap = len(s_kw & ctx_kw) / len(s_kw)
            if overlap >= 0.3:
                supported += 1.0
            elif overlap >= 0.15:
                supported += 0.5

        # Tỷ lệ câu được support / tổng số câu
        return round(supported / len(sentences), 4)

    # ── Answer Relevancy ──────────────────────────────────────────────────

    async def _compute_relevancy(
        self, question: str, answer: str, ground_truth: str
    ) -> float:
        """Relevancy: does the answer address the question?"""
        if not answer:
            return 0.0

        if self._api_available:
            try:
                return await self._relevancy_llm(question, answer, ground_truth)
            except Exception as exc:
                logger.warning("LLM relevancy failed: %s — fallback", exc)

        return self._relevancy_heuristic(question, answer, ground_truth)

    async def _relevancy_llm(
        self, question: str, answer: str, ground_truth: str
    ) -> float:
        prompt = _RELEVANCY_PROMPT.format(
            question=question[:500],
            answer=answer[:1000],
            ground_truth=ground_truth[:500],
        )
        result = await self._call_llm(prompt)
        return max(0.0, min(1.0, result.get("score", 0.5)))

    @staticmethod
    def _relevancy_heuristic(
        question: str, answer: str, ground_truth: str
    ) -> float:
        """
        Heuristic relevancy:
        1) Keyword overlap between question and answer (topic alignment)
        2) Keyword overlap between answer and ground truth (correctness)
        """
        q_kw = _keywords(question)
        a_kw = _keywords(answer)
        gt_kw = _keywords(ground_truth)

        if not q_kw:
            return 0.5

        # 1) Topic alignment: answer có chứa keywords từ question không (30%)
        q_overlap = len(q_kw & a_kw) / len(q_kw) if q_kw else 0
        # 2) Correctness: answer khớp với ground truth không (50%)
        gt_overlap = len(gt_kw & a_kw) / max(len(gt_kw), 1) if gt_kw else 0.5

        # 3) Number matching: số liệu trong answer có đúng không (20%)
        # Quan trọng cho fact_lookup (VD: "12 ngày", "25MB", "80,000đ")
        q_nums = set(re.findall(r"\d+", question))
        a_nums = set(re.findall(r"\d+", answer))
        gt_nums = set(re.findall(r"\d+", ground_truth))
        num_match = len(gt_nums & a_nums) / max(len(gt_nums), 1) if gt_nums else 0.5

        # Weighted combination: correctness quan trọng nhất (50%)
        score = q_overlap * 0.3 + gt_overlap * 0.5 + num_match * 0.2
        return round(max(0.0, min(1.0, score)), 4)

    # ── Context Relevancy ─────────────────────────────────────────────────

    @staticmethod
    def _compute_context_relevancy(
        question: str, contexts: List[str]
    ) -> float:
        """
        Context relevancy: how many retrieved chunks are topically
        related to the question?
        """
        if not contexts:
            return 0.0

        q_kw = _keywords(question)
        if not q_kw:
            return 0.5

        relevant_count = 0
        for ctx in contexts:
            c_kw = _keywords(ctx)
            if not c_kw:
                continue
            overlap = len(q_kw & c_kw) / len(q_kw)
            if overlap >= 0.2:
                relevant_count += 1

        return round(relevant_count / len(contexts), 4)

    # ── LLM helper ────────────────────────────────────────────────────────

    async def _call_llm(self, user_prompt: str) -> Dict[str, Any]:
        """Call GPT-4o-mini for metric evaluation and track cost."""
        model = "gpt-4o-mini"
        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0.0,
                    max_tokens=200,
                    response_format={"type": "json_object"},
                ),
                timeout=20.0,
            )

            usage = response.usage
            if usage:
                self.total_tokens["prompt"] += usage.prompt_tokens
                self.total_tokens["completion"] += usage.completion_tokens
                cost = (
                    usage.prompt_tokens * 0.15 / 1_000_000
                    + usage.completion_tokens * 0.60 / 1_000_000
                )
                self.total_cost += cost

            content = response.choices[0].message.content
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                match = re.search(r"\{[^{}]+\}", content, re.DOTALL)
                if match:
                    return json.loads(match.group())
                return {"score": 0.5}

        except Exception as exc:
            logger.warning("RAGAS LLM call failed: %s", exc)
            raise

    # ── Cost summary ──────────────────────────────────────────────────────

    def get_cost_summary(self) -> Dict[str, Any]:
        """Trả về thống kê token và chi phí USD tích lũy."""
        total_tok = self.total_tokens["prompt"] + self.total_tokens["completion"]
        return {
            "total_tokens": {
                "prompt": self.total_tokens["prompt"],
                "completion": self.total_tokens["completion"],
                "total": total_tok,
            },
            "total_cost_usd": round(self.total_cost, 6),
            "avg_cost_per_eval": round(self.total_cost / max(self.eval_count, 1), 6),
            "total_evaluations": self.eval_count,
            "api_available": self._api_available,
        }
