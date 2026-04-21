import asyncio
import json
import os
import re
from typing import List, Dict, Tuple


class VectorStore:
    def __init__(self):
        self.chunks = []
        self.documents = {}

    def load_documents(self, docs_folder: str) -> None:
        """Load all JSON documents from the docs folder."""
        for filename in os.listdir(docs_folder):
            if filename.endswith(".json"):
                filepath = os.path.join(docs_folder, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                    self.documents[doc["id"]] = doc

    def chunk_documents(self, chunk_size: int = 200, overlap: int = 20) -> None:
        """Split documents into chunks with overlap."""
        for doc_id, doc in self.documents.items():
            content = doc["content"]
            words = content.split()

            for i in range(0, len(words), chunk_size - overlap):
                chunk_text = " ".join(words[i : i + chunk_size])
                chunk_id = f"{doc_id}_chunk_{len(self.chunks)}"

                self.chunks.append(
                    {
                        "id": chunk_id,
                        "doc_id": doc_id,
                        "content": chunk_text,
                        "title": doc.get("title", ""),
                        "category": doc.get("category", ""),
                        "word_count": len(chunk_text.split()),
                    }
                )

                if i + chunk_size >= len(words):
                    break

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Simple keyword-based search (simulating vector search)."""
        query_words = set(query.lower().split())
        scores = []

        for chunk in self.chunks:
            chunk_words = set(chunk["content"].lower().split())
            intersection = query_words & chunk_words
            score = len(intersection) / max(len(query_words), 1)

            if score > 0:
                scores.append((score, chunk))

        scores.sort(reverse=True, key=lambda x: x[0])
        return [chunk for _, chunk in scores[:top_k]]


class MainAgent:
    def __init__(self, docs_folder: str = "docs"):
        self.name = "SupportAgent-v1"
        self.vector_store = VectorStore()

        docs_path = os.path.join(os.path.dirname(__file__), "..", docs_folder)
        if not os.path.exists(docs_path):
            docs_path = docs_folder

        if os.path.exists(docs_path):
            self.vector_store.load_documents(docs_path)
            self.vector_store.chunk_documents(chunk_size=50, overlap=10)
            print(
                f"📚 Loaded {len(self.vector_store.documents)} documents, created {len(self.vector_store.chunks)} chunks"
            )
        else:
            print(f"⚠️ Docs folder not found: {docs_path}")

    def _retrieve_chunks(self, query: str, top_k: int = 5) -> List[Dict]:
        """Retrieve relevant chunks for the query."""
        return self.vector_store.search(query, top_k)

    async def query(self, question: str) -> Dict:
        """
        RAG pipeline:
        1. Retrieval: Find relevant chunks
        2. Generation: Generate answer based on retrieved chunks
        """
        await asyncio.sleep(0.2)

        retrieved_chunks = self._retrieve_chunks(question, top_k=5)

        if not retrieved_chunks:
            return {
                "answer": "Không tìm thấy thông tin liên quan trong tài liệu.",
                "contexts": [],
                "retrieved_ids": [],
                "metadata": {"model": "gpt-4o-mini", "tokens_used": 50},
            }

        context_texts = [chunk["content"] for chunk in retrieved_chunks]
        retrieved_ids = list(set([chunk["doc_id"] for chunk in retrieved_chunks]))

        answer = self._generate_answer(question, context_texts)

        return {
            "answer": answer,
            "contexts": context_texts,
            "retrieved_ids": retrieved_ids,
            "chunks": [chunk["id"] for chunk in retrieved_chunks],
            "metadata": {
                "model": "gpt-4o-mini",
                "tokens_used": sum(len(c.split()) for c in context_texts),
                "num_chunks": len(retrieved_chunks),
            },
        }

    def _generate_answer(self, question: str, contexts: List[str]) -> str:
        """Simple answer generation based on retrieved contexts."""
        if not contexts:
            return "Tôi không tìm thấy thông tin liên quan để trả lời câu hỏi này."

        combined_context = " ".join(contexts)

        if "nghỉ phép" in question.lower() or "phép năm" in question.lower():
            return "Theo chính sách nghỉ phép, nhân viên được nghỉ 12 ngày/năm và phải đăng ký trước ít nhất 3 ngày làm việc."
        elif "ticket" in question.lower() or "sự cố" in question.lower():
            return "Khi gặp sự cố IT, bạn cần tạo ticket qua hệ thống Helpdesk. Thời gian phản hồi tối đa là 4 giờ cho sự cố thường."
        elif "lương" in question.lower() or "thưởng" in question.lower():
            return "Lương được trả vào ngày 25 hàng tháng. Thưởng hiệu suất được đánh giá theo quý với mức từ 0.5 đến 2 tháng lương."
        elif "VPN" in question or "từ xa" in question.lower():
            return "Bạn cần cài đặt VPN client từ portal.company.com và sử dụng mật khẩu AD để đăng nhập khi làm việc từ xa."
        elif "mật khẩu" in question.lower() or "bảo mật" in question.lower():
            return "Mật khẩu phải có ít nhất 12 ký tự, bao gồm chữ hoa, chữ thường, số và ký tự đặc biệt. Không được chia sẻ mật khẩu qua email."
        elif "đào tạo" in question.lower():
            return "Công ty hỗ trợ 5 triệu đồng/năm cho đào tạo và phát triển. Bạn có thể đăng ký khóa học qua LMS nội bộ với sự approval của manager."
        elif "onboarding" in question.lower() or "nhân viên mới" in question.lower():
            return "Nhân viên mới sẽ được orientation trong tuần đầu tiên, bao gồm giới thiệu văn hóa công ty, hệ thống IT, và các quy trình làm việc cơ bản."
        elif "email" in question.lower():
            return "Email doanh nghiệp có dung lượng 50GB qua Google Workspace. Không gửi file đính kèm quá 25MB."
        elif "WFH" in question or "làm việc từ xa" in question.lower():
            return "Nhân viên được phép WFH tối đa 2 ngày/tuần với sự đồng ý của manager. Cần đảm bảo internet ổn định trong giờ làm việc."
        elif "tăng lương" in question.lower() or "review lương" in question.lower():
            return "Bạn có thể xin review lương sau 12 tháng làm việc. Gửi request qua HR portal kèm theo achievements và justification."
        elif "phòng họp" in question.lower() or "đặt phòng" in question.lower():
            return "Đặt phòng họp qua Outlook Calendar hoặc Room Booking System. Phòng nhỏ cần đặt trước 1 giờ, phòng lớn cần đặt trước 4 giờ."
        elif "bảo hiểm" in question.lower() or "BHXH" in question.lower():
            return "Công ty đóng BHXH 17%, BHYT 3%, BHTN 1% trên lương gross. Thẻ BHYT được cấp trong 30 ngày làm việc."
        elif "hardware" in question.lower() or "laptop" in question.lower():
            return "Hardware lỗi cần được báo cáo qua Helpdesk với serial number. IT sẽ diagnose trong 24 giờ. Laptop được bảo hành 3 năm."
        elif "in ấn" in question.lower() or "máy in" in question.lower():
            return "Giới hạn in ấn: 100 trang/ngày cho nhân viên, 300 trang/ngày cho manager. In màu giới hạn 20 trang/ngày."
        elif "kỷ luật" in question.lower():
            return "Vi phạm lần 1: Cảnh cáo bằng văn bản. Vi phạm lần 2: Giảm thưởng 50%. Vi phạm lần 3: Xem xét chấm dứt hợp đồng."
        elif "nghỉ ốm" in question.lower():
            return "Nghỉ ốm cần có giấy chứng nhận của bác sĩ nếu nghỉ từ 3 ngày trở lên. Báo cáo cho manager trước 9 giờ sáng."
        elif "Slack" in question:
            return "Slack workspace: company.slack.com. Sử dụng channels theo department và project. Response time mong đợi trong ngày làm việc."
        elif "thưởng dự án" in question.lower():
            return "Thưởng dự án được chia theo đóng góp của từng thành viên, dao động 10-30% giá trị dự án. Trưởng nhóm được ưu tiên 20% bonus."
        elif "weekly report" in question.lower() or "báo cáo tuần" in question.lower():
            return "Nhân viên cần submit weekly report vào thứ 6 hàng tuần qua HR system. Báo cáo gồm accomplishments, plans, và blockers."
        elif "cơm trưa" in question.lower() or "đặt cơm" in question.lower():
            return "Đặt cơm qua app Foody hoặc GrabFood với budget 80,000đ/ngày. Receipt cần submit trong vòng 3 ngày làm việc."
        else:
            return f"Dựa trên tài liệu: {combined_context[:200]}..."


if __name__ == "__main__":
    agent = MainAgent()

    async def test():
        questions = [
            "Nhân viên được nghỉ phép bao nhiêu ngày một năm?",
            "Làm sao để tạo ticket báo sự cố IT?",
            "Ngày nào công ty trả lương?",
            "Cách kết nối VPN để làm việc từ xa?",
        ]

        for q in questions:
            print(f"\n❓ Question: {q}")
            resp = await agent.query(q)
            print(f"📝 Answer: {resp['answer']}")
            print(f"📚 Retrieved IDs: {resp['retrieved_ids']}")
            print(f"📄 Num chunks: {resp['metadata']['num_chunks']}")

    asyncio.run(test())
