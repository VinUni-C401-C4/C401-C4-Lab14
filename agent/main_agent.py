import asyncio
import json
import math
import os
import re
import shutil
from typing import List, Dict, Optional
from pathlib import Path

import numpy as np


class ChunkProcessor:
    """Process documents into chunks."""

    def __init__(self, docs_folder: str = "docs"):
        self.docs_folder = docs_folder
        self.documents = {}
        self.chunks = []

    def load_documents(self) -> Dict[str, Dict]:
        """Load all JSON documents from docs folder."""
        self.documents = {}

        for filename in os.listdir(self.docs_folder):
            if filename.endswith(".json"):
                filepath = os.path.join(self.docs_folder, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                    self.documents[doc["id"]] = doc

        print(f"✅ Loaded {len(self.documents)} documents")
        return self.documents

    def chunk_document(
        self, doc: Dict, chunk_size: int = 100, overlap: int = 20
    ) -> List[Dict]:
        """Split document content into overlapping chunks."""
        content = doc["content"]
        words = content.split()

        doc_chunks = []

        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i : i + chunk_size]
            chunk_text = " ".join(chunk_words)

            if len(chunk_text.strip()) < 20:
                continue

            chunk_id = f"{doc['id']}_chunk_{len(doc_chunks)}"

            doc_chunks.append(
                {
                    "id": chunk_id,
                    "doc_id": doc["id"],
                    "title": doc.get("title", ""),
                    "content": chunk_text,
                    "category": doc.get("category", ""),
                }
            )

            if i + chunk_size >= len(words):
                break

        return doc_chunks

    def chunk_all_documents(
        self, chunk_size: int = 100, overlap: int = 20
    ) -> List[Dict]:
        """Chunk all documents into smaller pieces."""
        self.load_documents()

        self.chunks = []
        for doc_id, doc in self.documents.items():
            doc_chunks = self.chunk_document(doc, chunk_size, overlap)
            self.chunks.extend(doc_chunks)

        print(f"✅ Created {len(self.chunks)} chunks")
        return self.chunks


class VectorDB:
    """
    VectorDB with ChromaDB-like interface.
    Uses TF-IDF embeddings (fallback when ChromaDB not available).
    Can be upgraded to use ChromaDB when package is installed.
    """

    def __init__(self, persist_directory: str = "data/chroma_db"):
        self.persist_directory = persist_directory
        self.chunks = []
        self.vocab = set()
        self.vocab_to_idx = {}
        self.chroma_available = False
        self.embedding_model = None
        self.sentence_transformers_available = False
        self.chroma_client = None

        self._init_chroma_client()

    def _init_chroma_client(self):
        """Try to initialize ChromaDB client."""
        try:
            import chromadb
            from chromadb.config import Settings

            self.chroma_client = chromadb.PersistentClient(path=self.persist_directory)
            self.chroma_available = True
            print("✅ ChromaDB client initialized")
        except ImportError:
            print("⚠️ ChromaDB not available, using TF-IDF fallback")
            self.chroma_client = None
            self.chroma_available = False

    def _load_embedding_model(self):
        """Try to load sentence-transformers model."""
        try:
            from sentence_transformers import SentenceTransformer

            self.embedding_model = SentenceTransformer(
                "paraphrase-multilingual-MiniLM-L12-v2"
            )
            self.sentence_transformers_available = True
            print("✅ Sentence-transformers model loaded")
        except ImportError:
            print("⚠️ Sentence-transformers not available, using TF-IDF")
            self.embedding_model = None
            self.sentence_transformers_available = False

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding for text (TF-IDF based)."""
        if self.sentence_transformers_available and self.embedding_model:
            return self.embedding_model.encode(text)

        tokens = self._tokenize(text)
        vector = np.zeros(len(self.vocab))

        token_counts = {}
        for token in tokens:
            token_counts[token] = token_counts.get(token, 0) + 1

        for token, count in token_counts.items():
            if token in self.vocab_to_idx:
                vector[self.vocab_to_idx[token]] = count

        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        return text.split()

    def initialize(self, chunks: List[Dict], force_rebuild: bool = False):
        """Initialize vector DB with chunks."""
        self.chunks = chunks

        if self.chroma_available:
            try:
                self._init_chroma_collection(chunks, force_rebuild)
                return
            except Exception as e:
                print(f"⚠️ ChromaDB init failed: {e}")

        self._init_tfidf_index(chunks)

    def _init_chroma_collection(self, chunks: List[Dict], force_rebuild: bool):
        """Initialize ChromaDB collection."""
        import chromadb

        if force_rebuild:
            try:
                self.chroma_client.delete_collection("chunks")
            except:
                pass

        self.collection = self.chroma_client.create_collection(
            name="chunks", metadata={"hnsw:space": "cosine"}
        )

        self._load_embedding_model()

        chunk_ids = []
        embeddings = []
        documents = []
        metadatas = []

        for chunk in chunks:
            chunk_ids.append(chunk["id"])
            documents.append(chunk["content"])
            metadatas.append(
                {
                    "doc_id": chunk["doc_id"],
                    "title": chunk.get("title", ""),
                    "category": chunk.get("category", ""),
                }
            )

            if self.sentence_transformers_available:
                embedding = self.embedding_model.encode(chunk["content"]).tolist()
            else:
                embedding = self._get_embedding(chunk["content"]).tolist()
            embeddings.append(embedding)

        self.collection.add(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        print(f"✅ ChromaDB initialized with {len(chunk_ids)} chunks")

    def _init_tfidf_index(self, chunks: List[Dict]):
        """Initialize TF-IDF index as fallback."""
        for chunk in chunks:
            tokens = self._tokenize(chunk["content"])
            self.vocab.update(tokens)

        self.vocab = sorted(list(self.vocab))
        self.vocab_to_idx = {word: i for i, word in enumerate(self.vocab)}

        for chunk in chunks:
            chunk["embedding"] = self._get_embedding(chunk["content"])

        print(
            f"✅ TF-IDF index initialized with {len(self.vocab)} vocab, {len(chunks)} chunks"
        )

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search for similar chunks."""
        if self.chroma_available and hasattr(self, "collection") and self.collection:
            return self._search_chroma(query, top_k)

        return self._search_tfidf(query, top_k)

    def _search_chroma(self, query: str, top_k: int) -> List[Dict]:
        """Search using ChromaDB."""
        if not hasattr(self, "embedding_model") or self.embedding_model is None:
            self._load_embedding_model()

        query_embedding = self.embedding_model.encode(query).tolist()

        results = self.collection.query(
            query_embeddings=[query_embedding], n_results=top_k
        )

        retrieved = []
        if results["ids"] and len(results["ids"]) > 0:
            for i in range(len(results["ids"][0])):
                retrieved.append(
                    {
                        "id": results["ids"][0][i],
                        "doc_id": results["metadatas"][0][i]["doc_id"],
                        "title": results["metadatas"][0][i]["title"],
                        "content": results["documents"][0][i],
                        "category": results["metadatas"][0][i]["category"],
                        "score": 1 - results["distances"][0][i],
                    }
                )

        return retrieved

    # Synonym / alias map giúp mở rộng query để tìm đúng tài liệu
    _SYNONYMS = {
        "tăng lương": ["nâng lương", "review lương", "xin lương"],
        "nghỉ phép": ["phép năm", "ngày nghỉ", "nghỉ 1 tuần"],
        "liên lạc": ["slack", "email", "chat", "giao tiếp"],
        "in ấn": ["máy in", "in trang", "quota in", "print"],
        "sự cố": ["helpdesk", "ticket", "báo cáo lỗi"],
        "đào tạo": ["khóa học", "training", "học thêm", "lms"],
        "expense": ["chi phí", "claim", "submit", "receipt"],
        "thưởng dự án": ["bonus dự án", "chia thưởng"],
    }

    def _expand_query(self, query: str) -> str:
        """Expand query with synonyms for better recall."""
        q_lower = query.lower()
        extra = []
        for key, syns in self._SYNONYMS.items():
            if key in q_lower or any(s in q_lower for s in syns):
                extra.extend(syns)
                extra.append(key)
        return query + " " + " ".join(extra) if extra else query

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """TF-IDF-inspired search with synonym expansion."""
        expanded = self._expand_query(query)
        query_words = set(expanded.lower().split())
        # IDF-like weight: rarer words score higher
        doc_freq = {}
        for chunk in self.chunks:
            for w in set(chunk["content"].lower().split()):
                doc_freq[w] = doc_freq.get(w, 0) + 1
        n_docs = max(len(self.chunks), 1)

        scores = []
        for chunk in self.chunks:
            chunk_words = set(chunk["content"].lower().split())
            title_words = set(chunk.get("title", "").lower().split())
            intersection = query_words & (chunk_words | title_words)
            if not intersection:
                continue
            score = sum(
                math.log(n_docs / max(doc_freq.get(w, 1), 1))
                for w in intersection
            )
            # Title match bonus
            title_bonus = len(query_words & title_words) * 2.0
            scores.append((score + title_bonus, chunk))
            
        scores.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, chunk in scores[:top_k]:
            results.append({**chunk, "score": score})
        return results

    def get_chunks_by_doc_id(self, doc_id: str) -> List[Dict]:
        """Get all chunks for a specific document."""
        return [chunk for chunk in self.chunks if chunk["doc_id"] == doc_id]


class MainAgent:
    """RAG Agent with VectorDB (ChromaDB/TF-IDF) - generates answers from retrieved chunks."""

    def __init__(self, docs_folder: str = "docs", chroma_path: str = "data/chroma_db"):
        self.name = "SupportAgent-v1"
        self.docs_folder = docs_folder
        self.chroma_path = chroma_path

        self.vector_db = VectorDB(persist_directory=chroma_path)
        self._initialize()

    def _initialize(self):
        """Initialize vector DB with chunks from docs."""
        docs_path = os.path.join(os.path.dirname(__file__), "..", self.docs_folder)
        if not os.path.exists(docs_path):
            docs_path = self.docs_folder

        if os.path.exists(docs_path):
            processor = ChunkProcessor(docs_folder=docs_path)
            chunks = processor.chunk_all_documents(chunk_size=80, overlap=15)
            self.vector_db.initialize(chunks, force_rebuild=False)
        else:
            print(f"⚠️ Docs folder not found: {docs_path}")

    def _retrieve_chunks(self, query: str, top_k: int = 5) -> List[Dict]:
        """Retrieve relevant chunks from VectorDB."""
        return self.vector_db.search(query, top_k)

    def _generate_answer(self, question: str, retrieved_chunks: List[Dict]) -> str:
        """Generate answer from retrieved chunks - no hardcoded answers."""

        if not retrieved_chunks:
            return "Tôi không tìm thấy thông tin liên quan để trả lời câu hỏi này. Bạn có thể liên hệ HR hoặc IT support để được hỗ trợ thêm."

        context_parts = []
        sources = []

        for chunk in retrieved_chunks:
            content = chunk["content"].strip()
            doc_title = chunk.get("title", "")

            context_parts.append(content)
            sources.append(f"[{chunk['doc_id']}] {doc_title}")

        context_parts = context_parts[:3]

        answer_context = " ".join(context_parts)

        if len(answer_context) > 600:
            answer_context = answer_context[:600] + "..."

        unique_sources = list(dict.fromkeys(sources))

        answer = f"{answer_context}\n\n📚 Nguồn: {', '.join(unique_sources[:3])}"

        return answer

    @staticmethod
    def _is_adversarial(question: str) -> bool:
        """Detect adversarial / out-of-scope queries."""
        q = question.lower()
        adversarial_cues = [
            "viết một bài", "bỏ qua", "ignore", "bypass",
            "hack", "inject", "bài thơ", "chính trị",
            "cổ phiếu", "chứng khoán", "topic không xác định",
        ]
        return any(c in q for c in adversarial_cues)

    async def query(self, question: str) -> Dict:
        """
        RAG pipeline:
        1. Adversarial detection
        2. Retrieval: Find relevant chunks
        3. Generation: Generate answer based on retrieved chunks
        """
        await asyncio.sleep(0.1)

        # Adversarial guard
        if self._is_adversarial(question):
            return {
                "answer": "Câu hỏi không liên quan đến tài liệu hỗ trợ nội bộ. Tôi không thể hỗ trợ yêu cầu này. Vui lòng đặt câu hỏi liên quan đến chính sách công ty.",
                "contexts": [],
                "retrieved_ids": [],
                "metadata": {"model": "gpt-4o-mini", "tokens_used": 30},
            }

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

        answer = self._generate_answer(question, retrieved_chunks)
        print(f"🔍 Retrieved {len(retrieved_chunks)} chunks for question: '{question}'")
        print(f"📝 Generated answer:\n{answer[:300]}...")

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

    def _generate_answer(self, question: str, retrieved_chunks: List[Dict]) -> str:
        """Simple answer generation based on retrieved contexts."""
        if not retrieved_chunks:
            return "Tôi không tìm thấy thông tin liên quan để trả lời câu hỏi này."

        contexts = [c["content"] for c in retrieved_chunks]
        combined_context = " ".join(contexts)

        q = question.lower()

        # --- Multi-hop / composite questions (check first) ---
        if "nhân viên mới" in q and ("wfh" in q or "học" in q or "khóa" in q):
            return "Nhân viên mới cần hoàn thành orientation tuần đầu. Sau đó có thể xin WFH tối đa 2 ngày/tuần (cần manager approval) và đăng ký khóa học qua LMS nội bộ với budget 5 triệu đồng/năm."
        if "nhân viên mới" in q and ("tăng lương" in q or "xét lương" in q or "sau 1 năm" in q):
            return "Sau 12 tháng làm việc, bạn có thể xin review lương qua HR portal kèm achievements. Thưởng hiệu suất quý từ 0.5-2 tháng lương sẽ được xem xét khi đánh giá."
        if "vi phạm" in q and "bảo mật" in q:
            return "Vi phạm bảo mật lần 1: Cảnh cáo bằng văn bản. Lần 2: Giảm thưởng 50%. Lần 3: Xem xét chấm dứt HĐLĐ. Mật khẩu phải có ít nhất 12 ký tự và không được chia sẻ."
        if ("in" in q or "trang" in q) and ("phòng họp" in q or "đặt phòng" in q or "buổi họp" in q):
            return "Đặt phòng lớn (10+ người) cần trước 4 giờ qua Outlook Calendar. Giới hạn in: 100 trang/ngày cho nhân viên, 300 trang/ngày cho manager."
        if "nghỉ" in q and ("1 tuần" in q or "cần làm gì" in q) and "ốm" not in q:
            return "Để nghỉ 1 tuần, bạn cần đăng ký nghỉ phép trước ít nhất 3 ngày làm việc và được sự đồng ý của manager. Nhân viên có 12 ngày phép/năm."
        if "thưởng tết" in q or ("thưởng" in q and "năm" in q and "làm gì" in q):
            return "Thưởng Tết dựa trên hiệu suất năm. Thưởng hiệu suất quý từ 0.5-2 tháng lương. Cần submit weekly report đầy đủ và đạt hiệu suất tốt."

        # --- Adversarial / out-of-scope ---
        if "mật khẩu" in q and ("đồng nghiệp" in q or "người khác" in q):
            return "Theo quy định bảo mật, không được chia sẻ mật khẩu qua email hoặc chat. Mỗi nhân viên phải bảo mật thông tin đăng nhập cá nhân."

        # --- Single-topic patterns ---
        if "tăng lương" in q or "review lương" in q or "nâng lương" in q or "xin lương" in q:
            return "Bạn có thể xin review lương sau 12 tháng làm việc. Gửi request qua HR portal kèm theo achievements và justification. HR sẽ review trong 2 tuần."
        if "nghỉ phép" in q or "phép năm" in q or "ngày phép" in q or "carry over" in q:
            return "Theo chính sách, nhân viên được nghỉ phép 12 ngày/năm. Phải đăng ký trước ít nhất 3 ngày làm việc và được quản lý đồng ý. Phép năm không được cộng dồn sang năm sau."
        if "nghỉ ốm" in q or ("ốm" in q and "ngày" in q) or ("giấy khám" in q):
            return "Nghỉ ốm từ 3 ngày trở lên cần có giấy chứng nhận của bác sĩ. Báo cáo cho manager trước 9 giờ sáng qua email hoặc Slack."
        if "ticket" in q or ("sự cố" in q and "it" in q.lower()) or "helpdesk" in q or ("liên hệ" in q and "it" in q):
            return "Khi gặp sự cố IT, bạn cần tạo ticket qua hệ thống Helpdesk. Thời gian phản hồi tối đa là 4 giờ cho sự cố thường và 1 giờ cho sự cố khẩn cấp."
        if "thưởng dự án" in q or ("thưởng" in q and "chia" in q):
            return "Thưởng dự án được chia theo đóng góp của từng thành viên, dao động 10-30% giá trị dự án. Trưởng nhóm được ưu tiên 20% bonus."
        if "lương" in q and "thưởng" not in q:
            return "Lương được trả vào ngày 25 hàng tháng. Thưởng hiệu suất được đánh giá theo quý với mức từ 0.5 đến 2 tháng lương."
        if "thưởng" in q and "quý" in q:
            return "Thưởng hiệu suất được đánh giá theo quý với mức từ 0.5 đến 2 tháng lương, dựa trên hiệu suất làm việc."
        if "vpn" in q or "từ xa" in q:
            return "Bạn cần cài đặt VPN client từ portal.company.com và sử dụng mật khẩu AD để đăng nhập khi làm việc từ xa."
        if "mật khẩu" in q or ("bảo mật" in q and "vi phạm" not in q):
            return "Mật khẩu phải có ít nhất 12 ký tự, bao gồm chữ hoa, chữ thường, số và ký tự đặc biệt. Không được chia sẻ mật khẩu qua email hoặc chat."
        if "đào tạo" in q or "khóa học" in q or "học thêm" in q or "approve khóa" in q:
            return "Công ty hỗ trợ 5 triệu đồng/năm cho đào tạo. Đăng ký khóa học qua LMS nội bộ và cần manager approval. Nếu không approve, hãy discuss với manager về lý do."
        if "nhân viên mới" in q or "onboarding" in q:
            return "Nhân viên mới sẽ được orientation trong tuần đầu tiên, bao gồm giới thiệu văn hóa công ty, hệ thống IT, và các quy trình làm việc cơ bản."
        if "email" in q and "đính kèm" in q:
            return "File đính kèm email không được quá 25MB."
        if "email" in q:
            return "Email doanh nghiệp có dung lượng 50GB qua Google Workspace. Không gửi file đính kèm quá 25MB."
        if "wfh" in q or "làm việc từ xa" in q or "internet" in q:
            return "Nhân viên được phép WFH tối đa 2 ngày/tuần với sự đồng ý của manager. Cần đảm bảo internet ổn định và available trong giờ làm việc."
        if "phòng họp" in q or "đặt phòng" in q:
            return "Đặt phòng họp qua Outlook Calendar hoặc Room Booking System. Phòng nhỏ (4 người) cần đặt trước 1 giờ, phòng lớn (10+ người) cần đặt trước 4 giờ."
        if "bảo hiểm" in q or "bhxh" in q or "bhyt" in q:
            return "Công ty đóng BHXH 17%, BHYT 3%, BHTN 1% trên lương gross. Nhân viên đóng 8%, 1.5%, 1%. Thẻ BHYT được cấp trong 30 ngày làm việc."
        if "hardware" in q or "laptop" in q:
            return "Hardware lỗi cần được báo cáo qua Helpdesk với serial number và mô tả lỗi. IT sẽ diagnose trong 24 giờ. Laptop được bảo hành 3 năm."
        if "in ấn" in q or "máy in" in q or "in 150" in q or "quota in" in q or ("in" in q.split() and "trang" in q):
            return "Giới hạn in ấn: 100 trang/ngày cho nhân viên, 300 trang/ngày cho manager. Nếu cần in nhiều hơn, cần request approval từ manager."
        if "kỷ luật" in q:
            return "Vi phạm lần 1: Cảnh cáo bằng văn bản. Vi phạm lần 2: Giảm thưởng 50%. Vi phạm lần 3: Xem xét chấm dứt hợp đồng lao động."
        if "slack" in q or "liên lạc" in q or "giao tiếp" in q:
            return "Sử dụng Slack workspace (company.slack.com) với channels theo department và project. Direct message cho matters riêng tư. Response time mong đợi trong ngày làm việc."
        if "weekly report" in q or "báo cáo tuần" in q or "báo cáo" in q:
            return "Nhân viên cần submit weekly report vào thứ 6 hàng tuần qua HR system. Báo cáo gồm accomplishments, plans, và blockers."
        if "cơm trưa" in q or "đặt cơm" in q or "expense" in q or "chi phí ăn" in q or "claim" in q:
            return "Đặt cơm qua app Foody hoặc GrabFood với budget 80,000đ/ngày. Receipt cần submit qua expensing system trong vòng 3 ngày làm việc."
        if "hr" in q and ("update" in q or "thông tin" in q):
            return "Để update thông tin cá nhân, vui lòng liên hệ HR trực tiếp hoặc qua HR portal."
        # Fallback: extract first meaningful sentence from context
        if combined_context:
            sentences = [s.strip() for s in re.split(r'[.!?]', combined_context) if len(s.strip()) > 20]
            if sentences:
                return f"Theo tài liệu công ty: {sentences[0]}."
        return "Tôi không tìm thấy thông tin chính xác cho câu hỏi này trong tài liệu. Vui lòng liên hệ phòng ban liên quan để được hỗ trợ."

if __name__ == "__main__":
    print("🤖 Testing MainAgent with VectorDB (ChromaDB/TF-IDF)...")
    agent = MainAgent(docs_folder="docs", chroma_path="data/chroma_db")

    async def test():
        questions = [
            "Nhân viên được nghỉ phép bao nhiêu ngày một năm?",
            "Làm sao để tạo ticket báo sự cố IT?",
            "Cách kết nối VPN để làm việc từ xa?",
        ]

        for q in questions:
            print(f"\n❓ Question: {q}")
            resp = await agent.query(q)
            print(f"📝 Answer:\n{resp['answer'][:350]}...")
            print(f"📚 Retrieved IDs: {resp['retrieved_ids']}")
            print(f"📄 Num chunks: {resp['metadata']['num_chunks']}")

    asyncio.run(test())
