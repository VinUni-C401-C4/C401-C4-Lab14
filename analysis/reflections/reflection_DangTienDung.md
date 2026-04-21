# Báo cáo Cá nhân — Reflection Report

**Họ và tên:** Đặng Tiến Dũng  
**Mã sinh viên:** 2A202600024  
**Lab:** Day 14 — AI Evaluation Factory  
**Ngày nộp:** 21/04/2026  

---

## 1. Đóng góp Kỹ thuật (Engineering Contribution)

### 1.1 Tổng quan đóng góp

Trong dự án Lab 14, tôi đảm nhận **Giai đoạn 1** — Retrieval Evaluation & SDG (Synthetic Data Generation). Đây là nền tảng quan trọng để chứng minh Retrieval stage hoạt động tốt trước khi đánh giá Generation.

**Các thành phần đã phát triển:**
1. **Retrieval Evaluator** (`engine/retrieval_eval.py`) - Tính toán Hit Rate, MRR, Precision, Recall, NDCG
2. **Synthetic Data Generator** (`data/synthetic_gen.py`) - Tạo 50+ test cases với Ground Truth IDs
3. **Document Processing** (`docs/`) - 20 policy documents được xử lý và chunking
4. **RAG System** (`agent/main_agent.py`) - VectorDB với ChromaDB/TF-IDF, answer generation từ chunks

---

### 1.2 Module 1: Retrieval Evaluator (`engine/retrieval_eval.py`)

**Vấn đề cần giải quyết:** Theo rubric, cần chứng minh Retrieval stage hoạt động tốt trước khi đánh giá Generation. Cần tính Hit Rate và MRR với Ground Truth document IDs.

**Giải pháp triển khai:**

```python
def calculate_hit_rate(self, expected_ids: List[str], retrieved_ids: List[str], top_k: int = 3) -> float:
    """Hit Rate@K: Kiểm tra ít nhất 1 expected_id có trong top_k retrieved_ids"""
    top_retrieved = retrieved_ids[:top_k]
    hit = any(doc_id in top_retrieved for doc_id in expected_ids)
    return 1.0 if hit else 0.0

def calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
    """MRR = 1 / rank_of_first_hit (1-indexed)"""
    for i, doc_id in enumerate(retrieved_ids):
        if doc_id in expected_ids:
            return 1.0 / (i + 1)
    return 0.0
```

**Metrics bổ sung đã triển khai:**
- `calculate_precision_at_k()` - Tỷ lệ documents liên quan trong top_k
- `calculate_recall_at_k()` - Tỷ lệ documents liên quan đã được retrieve
- `calculate_ndcg()` - Normalized Discounted Cumulative Gain
- `get_failure_analysis()` - Phân tích các trường hợp thất bại

**Kết quả benchmark:**
```
Hit Rate @1: 32.1%
Hit Rate @3: 75.0%
Hit Rate @5: 91.1%
MRR:         54.2%
```

---

### 1.3 Module 2: Synthetic Data Generator (`data/synthetic_gen.py`)

**Vấn đề cần giải quyết:** Tạo 50+ test cases với Ground Truth document IDs để đánh giá retrieval.

**Giải pháp triển khai:**

```python
def generate_test_cases() -> List[Dict]:
    """Tạo 56 test cases với Ground Truth document IDs"""
    # 19 easy: Fact lookup trực tiếp từ nội dung docs
    # 19 medium: Reasoning, procedure, kết hợp 2+ docs
    # 8 hard: Multi-hop, complex reasoning  
    # 5 adversarial: Prompt injection, goal hijacking, out-of-context
    # 5 edge: Boundary conditions
```

**Cấu trúc test case:**
```json
{
    "id": "tc_001",
    "question": "Nhân viên được nghỉ phép bao nhiêu ngày một năm?",
    "expected_answer": "12 ngày/năm theo quy định công ty",
    "expected_retrieval_ids": ["doc_001"],
    "metadata": {"difficulty": "easy", "type": "fact_lookup"}
}
```

**Kết quả:** 56 test cases với đầy đủ Ground Truth IDs

---

### 1.4 Module 3: Document Processing & VectorDB (`agent/main_agent.py`)

**Vấn đề cần giải quyết:** 
1. Load documents từ `docs/` folder
2. Chunk documents thành smaller pieces
3. Embedding vào VectorDB (ChromaDB với TF-IDF fallback)
4. Search và generate answer từ retrieved chunks

**Giải pháp triển khai:**

```python
class ChunkProcessor:
    def chunk_document(self, doc: Dict, chunk_size: int = 80, overlap: int = 15) -> List[Dict]:
        """Split document content thành overlapping chunks"""
        words = doc['content'].split()
        for i in range(0, len(words), chunk_size - overlap):
            chunk_text = ' '.join(words[i:i + chunk_size])
            # Tạo chunk với id, doc_id, title, content, category
```

```python
class VectorDB:
    def initialize(self, chunks: List[Dict]):
        """Initialize ChromaDB hoặc TF-IDF fallback"""
        if chromadb_available:
            self._init_chroma_collection(chunks)
        else:
            self._init_tfidf_index(chunks)
    
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Cosine similarity search"""
```

**Kết quả:**
- 20 documents đã được xử lý
- 37 chunks được tạo (chunk_size=80, overlap=15)
- Vector index với 589 vocabulary words

---

### 1.5 Module 4: Answer Generation from Chunks

**Vấn đề cần giải quyết:** Generate answer từ retrieved chunks thay vì hardcoded answers.

**Giải pháp triển khai:**

```python
def _generate_answer(self, question: str, retrieved_chunks: List[Dict]) -> str:
    """Generate answer từ retrieved chunks - KHÔNG hardcoded"""
    if not retrieved_chunks:
        return "Tôi không tìm thấy thông tin liên quan..."
    
    context_parts = []
    sources = []
    
    for chunk in retrieved_chunks:
        context_parts.append(chunk['content'].strip())
        sources.append(f"[{chunk['doc_id']}] {chunk.get('title', '')}")
    
    answer_context = " ".join(context_parts[:3])
    unique_sources = list(dict.fromkeys(sources))
    
    answer = f"{answer_context}\n\n📚 Nguồn: {', '.join(unique_sources[:3])}"
    return answer
```

**Ví dụ output:**
```
❓ Question: Nhân viên được nghỉ phép bao nhiêu ngày một năm?

📝 Answer:
Theo quy định của công ty, nhân viên được nghỉ phép 12 ngày/năm. 
Nghỉ phép phải được đăng ký trước ít nhất 3 ngày làm việc...

📚 Nguồn: [doc_001] Chính sách nghỉ phép năm 2024, [doc_016] Quy trình xin nghỉ ốm
```

---

## 2. Hiểu biết Kỹ thuật Sâu (Technical Depth)

### 2.1 Hit Rate vs MRR

**Hit Rate@K:** Tỷ lệ queries có ít nhất 1 relevant document trong top K kết quả.
- Hit Rate@1 = 32.1%: ~1/3 queries có document đúng ở vị trí đầu tiên
- Hit Rate@3 = 75.0%: 3/4 queries tìm được document đúng trong top 3
- Hit Rate@5 = 91.1%: Hầu hết queries đều tìm được document đúng

**MRR (Mean Reciprocal Rank):** Trung bình cộng của 1/rank của document đúng đầu tiên.
- MRR = 54.2% có nghĩa là: trung bình document đúng xuất hiện ở rank ~1.85

**Phân tích:** Hit Rate@3 cao (75%) nhưng Hit Rate@1 thấp (32%) → Retrieval hoạt động nhưng ranking chưa tốt. Cần cải thiện thuật toán xếp hạng hoặc thêm reranking step.

---

### 2.2 Chunking Strategy

**Fixed-size Chunking:** 
- Chunk size = 80 words, overlap = 15 words
- Tạo 37 chunks từ 20 documents
- Ưu điểm: Đơn giản, nhanh
- Nhược điểm: Có thể split context ở vị trí không tự nhiên

**Cải tiến tiềm năng:**
- Semantic Chunking: Split theo câu/đoạn văn có nghĩa
- Hybrid: Kết hợp fixed-size với sentence boundaries

---

### 2.3 ChromaDB vs TF-IDF Fallback

**ChromaDB:**
- Ưu điểm: Sentence embeddings chất lượng cao (paraphrase-multilingual-MiniLM-L12-v2)
- Nhược địa: Cần cài đặt package, tài nguyên tính toán lớn hơn

**TF-IDF Fallback:**
- Ưu điểm: Không cần thêm package, nhanh
- Nhược điểm: Chỉ matching từ khóa, không hiểu semantic

**Hiện tại:** System tự động detect và dùng TF-IDF khi ChromaDB không available.

---

### 2.4 Trade-off: Retrieval vs Generation

**Retrieval Metrics đã chứng minh:**
- 75% queries tìm được document đúng trong top 3
- 91% queries tìm được document đúng trong top 5

**Điều này có nghĩa:**
- Generation stage có đủ context để trả lời (91% cases)
- Nếu answer sai, nguyên nhân chính là ở Generation, không phải Retrieval
- Cần tập trung cải thiện prompt/LLM generation thay vì retrieval

---

## 3. Giải quyết Vấn đề Phát sinh (Problem Solving)

### 3.1 Vấn đề: ChromaDB not available

**Triệu chứng:** ImportError khi chạy với ChromaDB

**Giải pháp:** 
```python
try:
    import chromadb
    self.chroma_available = True
except ImportError:
    print("⚠️ ChromaDB not available, using TF-IDF fallback")
    self.chroma_available = False
```

**Bài học:** Luôn có fallback plan khi dependencies không available.

---

### 3.2 Vấn đề: Hardcoded answers

**Triệu chứng:** `_generate_answer()` trả về câu trả lời hardcoded thay vì từ retrieved chunks

**Giải pháp:** 
- Tách riêng context extraction từ chunks
- Merge multiple chunks' content
- Trích xuất sources từ metadata

**Bài học:** RAG pipeline phải use retrieved context, không phải memorized answers.

---

### 3.3 Vấn đề: Answer quá dài

**Triệu chứng:** Kết hợp nhiều chunks tạo answer > 600 characters

**Giải pháp:**
```python
if len(answer_context) > 600:
    answer_context = answer_context[:600] + "..."
```

**Bài học:** Cần có truncation logic để control output size.

---

## 4. Kết quả Benchmark

### 4.1 Retrieval Metrics

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Hit Rate @1 | 32.1% | Document đúng ở rank 1 |
| Hit Rate @3 | 75.0% | Document đúng trong top 3 |
| Hit Rate @5 | 91.1% | Document đúng trong top 5 |
| MRR | 54.2% | Avg 1/rank của document đúng |

### 4.2 Test Case Distribution

| Difficulty | Count | Examples |
|------------|-------|----------|
| Easy | 19 | Fact lookup từ 1 doc |
| Medium | 19 | Reasoning, kết hợp 2+ docs |
| Hard | 8 | Multi-hop queries |
| Adversarial | 5 | Prompt injection, out-of-context |
| Edge | 5 | Boundary conditions |

---

## 5. Tổng kết

Qua Lab 14, tôi đã học được:

| Kỹ năng | Ứng dụng |
|---------|----------|
| **Retrieval Evaluation** | Hit Rate, MRR, NDCG để đo lường RAG quality |
| **Data Engineering** | Tạo golden dataset với Ground Truth IDs |
| **Document Processing** | Chunking, embedding, vector search |
| **RAG Pipeline** | End-to-end: retrieval → generation from chunks |
| **System Design** | Fallback chains, graceful degradation |

**Điều quan trọng nhất:** "Không thể cải thiện điều không đo được." 
- Retrieval đã proven working với Hit Rate@3 = 75%
- Generation sẽ được đánh giá với context đã được verify
- Failure analysis sẽ xác định chính xác bottleneck ở đâu

---

*Đặng Tiến Dũng*  
*Lab Day 14 — AI Evaluation Factory*