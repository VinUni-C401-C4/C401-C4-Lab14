from typing import List, Dict
import asyncio
from collections import defaultdict


class RetrievalEvaluator:
    def __init__(self, top_k_values: List[int] = None):
        self.top_k_values = top_k_values or [1, 3, 5, 10]

    def calculate_hit_rate(
        self, expected_ids: List[str], retrieved_ids: List[str], top_k: int = 3
    ) -> float:
        """
        Hit Rate@K: Kiểm tra xem ít nhất 1 expected_id có nằm trong top_k retrieved_ids không.
        Returns 1.0 nếu có hit, 0.0 nếu không.
        """
        if not expected_ids or not retrieved_ids:
            return 0.0
        top_retrieved = retrieved_ids[:top_k]
        hit = any(doc_id in top_retrieved for doc_id in expected_ids)
        return 1.0 if hit else 0.0

    def calculate_hit_rate_at_k(
        self, expected_ids: List[str], retrieved_ids: List[str], k: int
    ) -> float:
        """Hit Rate tại một giá trị k cụ thể."""
        return self.calculate_hit_rate(expected_ids, retrieved_ids, k)

    def calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        """
        Mean Reciprocal Rank (MRR):
        MRR = 1 / rank_of_first_hit
        rank là 1-indexed. Nếu không tìm thấy trong danh sách, trả về 0.
        """
        if not expected_ids or not retrieved_ids:
            return 0.0
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected_ids:
                return 1.0 / (i + 1)
        return 0.0

    def calculate_precision_at_k(
        self, expected_ids: List[str], retrieved_ids: List[str], k: int
    ) -> float:
        """
        Precision@K: Tỷ lệ documents liên quan trong top_k.
        """
        if not retrieved_ids:
            return 0.0
        top_retrieved = set(retrieved_ids[:k])
        expected_set = set(expected_ids)
        relevant_retrieved = len(top_retrieved & expected_set)
        return relevant_retrieved / k

    def calculate_recall_at_k(
        self, expected_ids: List[str], retrieved_ids: List[str], k: int
    ) -> float:
        """
        Recall@K: Tỷ lệ documents liên quan đã được retrieve trong top_k.
        """
        if not expected_ids:
            return 0.0
        top_retrieved = set(retrieved_ids[:k])
        expected_set = set(expected_ids)
        relevant_retrieved = len(top_retrieved & expected_set)
        return relevant_retrieved / len(expected_set)

    def calculate_ndcg(
        self, expected_ids: List[str], retrieved_ids: List[str], k: int = 10
    ) -> float:
        """
        Normalized Discounted Cumulative Gain (NDCG@K).
        """
        if not expected_ids or not retrieved_ids:
            return 0.0
        expected_set = set(expected_ids)

        def dcg(relevance_list):
            return sum((2**rel - 1) / (i + 1) for i, rel in enumerate(relevance_list))

        relevance = [
            1.0 if doc_id in expected_set else 0.0 for doc_id in retrieved_ids[:k]
        ]
        actual_dcg = dcg(relevance)

        ideal_relevance = [1.0] * min(len(expected_ids), k)
        ideal_dcg = dcg(ideal_relevance)

        return actual_dcg / ideal_dcg if ideal_dcg > 0 else 0.0

    async def evaluate_single(self, test_case: Dict, agent_response: Dict) -> Dict:
        """
        Evaluate một test case đơn lẻ.
        test_case phải có: expected_retrieval_ids, question
        agent_response phải có: retrieved_ids
        """
        expected_ids = test_case.get("expected_retrieval_ids", [])
        retrieved_ids = agent_response.get("retrieved_ids", [])

        if not expected_ids:
            return {
                "hit_rate_at_1": 0.0,
                "hit_rate_at_3": 0.0,
                "hit_rate_at_5": 0.0,
                "mrr": 0.0,
                "precision_at_5": 0.0,
                "recall_at_5": 0.0,
                "ndcg_at_10": 0.0,
            }

        return {
            "hit_rate_at_1": self.calculate_hit_rate_at_k(
                expected_ids, retrieved_ids, 1
            ),
            "hit_rate_at_3": self.calculate_hit_rate_at_k(
                expected_ids, retrieved_ids, 3
            ),
            "hit_rate_at_5": self.calculate_hit_rate_at_k(
                expected_ids, retrieved_ids, 5
            ),
            "mrr": self.calculate_mrr(expected_ids, retrieved_ids),
            "precision_at_5": self.calculate_precision_at_k(
                expected_ids, retrieved_ids, 5
            ),
            "recall_at_5": self.calculate_recall_at_k(expected_ids, retrieved_ids, 5),
            "ndcg_at_10": self.calculate_ndcg(expected_ids, retrieved_ids, 10),
        }

    async def evaluate_batch(
        self, dataset: List[Dict], agent_responses: List[Dict] = None
    ) -> Dict:
        """
        Chạy eval cho toàn bộ bộ dữ liệu.
        Dataset cần có: expected_retrieval_ids
        agent_responses cần có: retrieved_ids

        Hoặc dataset đã chứa đầy đủ thông tin (hybrid mode).
        """
        results = []

        for i, test_case in enumerate(dataset):
            if agent_responses and i < len(agent_responses):
                response = agent_responses[i]
            elif "retrieved_ids" in test_case:
                response = test_case
            else:
                continue

            eval_result = await self.evaluate_single(test_case, response)
            eval_result["question"] = test_case.get("question", "")
            eval_result["expected_ids"] = test_case.get("expected_retrieval_ids", [])
            eval_result["retrieved_ids"] = response.get("retrieved_ids", [])
            results.append(eval_result)

        if not results:
            return {
                "avg_hit_rate_at_1": 0.0,
                "avg_hit_rate_at_3": 0.0,
                "avg_hit_rate_at_5": 0.0,
                "avg_mrr": 0.0,
                "avg_precision_at_5": 0.0,
                "avg_recall_at_5": 0.0,
                "avg_ndcg_at_10": 0.0,
                "total_cases": 0,
            }

        n = len(results)
        summary = {
            "avg_hit_rate_at_1": sum(r["hit_rate_at_1"] for r in results) / n,
            "avg_hit_rate_at_3": sum(r["hit_rate_at_3"] for r in results) / n,
            "avg_hit_rate_at_5": sum(r["hit_rate_at_5"] for r in results) / n,
            "avg_mrr": sum(r["mrr"] for r in results) / n,
            "avg_precision_at_5": sum(r["precision_at_5"] for r in results) / n,
            "avg_recall_at_5": sum(r["recall_at_5"] for r in results) / n,
            "avg_ndcg_at_10": sum(r["ndcg_at_10"] for r in results) / n,
            "total_cases": n,
            "per_case_results": results,
        }

        return summary

    def get_failure_analysis(self, results: List[Dict]) -> Dict:
        """
        Phân tích các trường hợp thất bại (Hit Rate = 0).
        """
        failures = [r for r in results if r["hit_rate_at_3"] == 0.0]

        return {
            "total_failures": len(failures),
            "failure_rate": len(failures) / len(results) if results else 0.0,
            "failure_cases": [
                {
                    "question": f["question"],
                    "expected_ids": f["expected_ids"],
                    "retrieved_ids": f["retrieved_ids"],
                    "mrr": f["mrr"],
                }
                for f in failures
            ],
        }
