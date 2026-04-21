# Individual Reflection — Pham Tran Thanh Lam

## 1. Vai trò trong nhóm
**Nhóm Data & DevOps/Analyst** — Phụ trách tạo Golden Dataset (SDG), chạy Benchmark, phân tích lỗi (Failure Clustering), và tối ưu Agent.

## 2. Những gì đã học được

### 2.1 Evaluation-Driven Development
Trước lab này, tôi chỉ đánh giá AI agent bằng cách chạy thử vài câu hỏi thủ công. Bây giờ tôi hiểu tầm quan trọng của việc xây dựng **evaluation pipeline tự động** với:
- **Golden Dataset** có ground truth IDs cho retrieval evaluation
- **Multi-Judge Consensus** (≥2 models) để tránh bias từ một model duy nhất
- **Regression Gate** tự động quyết định release/rollback

### 2.2 Root Cause Analysis thay vì Surface Fix
Phân tích 5 Whys giúp tôi hiểu rằng lỗi "Agent trả lời sai" thường không phải do LLM, mà do **Retrieval Quality kém**. Ví dụ cụ thể:
- tc_013 ("tăng lương"): Lỗi thực sự nằm ở query expansion, không phải generation.
- tc_019 ("liên lạc đồng nghiệp"): Thiếu synonym mapping, không phải prompt engineering.

### 2.3 Metrics quan trọng trong RAG
- **Hit Rate @3** quan trọng hơn Hit Rate @1 vì LLM có thể tổng hợp từ top-3 chunks.
- **MRR** cho biết tài liệu đúng nằm ở vị trí nào trong kết quả retrieval.
- **Faithfulness** kiểm tra hallucination — agent có bịa thông tin không có trong context hay không.

## 3. Khó khăn gặp phải
- **Rate limiting**: OpenAI API giới hạn concurrent requests → giải quyết bằng batch_size=5 + semaphore.
- **Tiếng Việt tokenization**: Keyword search cho tiếng Việt khó hơn tiếng Anh vì không có word boundary rõ ràng.
- **Adversarial detection**: Khó phân biệt câu hỏi off-topic vs câu hỏi hợp lệ nhưng không có trong tài liệu.

## 4. Kết quả cụ thể đã đóng góp
- Tối ưu Agent từ **62% → 87.5% pass rate** (+25.5%)
- Cải thiện Hit Rate @3 từ **57.1% → 82.1%** nhờ TF-IDF + synonym expansion
- Hard cases đạt **100% pass rate** nhờ multi-hop pattern matching
- Viết báo cáo failure analysis với 5 Whys cho 3 case tệ nhất

## 5. Đề xuất cải tiến cho lần sau
1. Sử dụng **embedding model** thực sự (VD: text-embedding-3-small) thay vì keyword search.
2. Triển khai **Hybrid Search** (BM25 + Vector) để kết hợp ưu điểm của cả hai phương pháp.
3. Thêm **Reranker** (VD: Cohere rerank-v3.5) để cải thiện precision sau retrieval.
4. Tích hợp **real LLM generation** thay vì rule-based answers để xử lý long-tail questions.
