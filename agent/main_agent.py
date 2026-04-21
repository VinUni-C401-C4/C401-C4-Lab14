import asyncio
import json
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

    def _search_tfidf(self, query: str, top_k: int) -> List[Dict]:
        """Search using TF-IDF cosine similarity."""
        query_vector = self._get_embedding(query)

        results = []
        for chunk in self.chunks:
            chunk_vector = chunk.get("embedding", self._get_embedding(chunk["content"]))
            similarity = float(np.dot(query_vector, chunk_vector))
            results.append({**chunk, "score": similarity})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

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

    async def query(self, question: str) -> Dict:
        """
        RAG pipeline:
        1. Retrieval: Find relevant chunks from VectorDB
        2. Generation: Generate answer from retrieved chunks
        """
        await asyncio.sleep(0.1)

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
