# Individual Reflection — Tín Dương (Tin Duong)

## 1. Vai trò trong nhóm
**Nhóm RAG Optimization & Metrics** — Phụ trách triển khai RAGAS metrics và đánh giá Retrieval Quality.

## 2. Những gì đã học được

### 2.1 RAGAS Metrics
Tôi đã hiểu sâu về 3 trụ cột của RAGAS:
- **Faithfulness**: Đo lường sự trung thành của câu trả lời với context.
- **Answer Relevancy**: Độ liên quan của câu trả lời với câu hỏi.
- **Context Relevancy**: Chất lượng của các chunks được retrieve.
Tôi đã học cách cài đặt fallback logic sử dụng Heuristic scoring khi API gặp sự cố.

### 2.2 Retrieval Evaluation (Hit Rate & MRR)
Tôi đã học cách tính toán các chỉ số search chuyên sâu:
- **Hit Rate @K**: Tỷ lệ tìm thấy tài liệu đúng trong top K.
- **MRR (Mean Reciprocal Rank)**: Đánh giá vị trí của tài liệu đúng (càng cao càng tốt).
Việc tối ưu Hit Rate từ 57% lên 82% sau khi thêm TF-IDF và synonym expansion là một trải nghiệm rất giá trị.

## 3. Khó khăn gặp phải
- Việc định nghĩa Ground Truth IDs cho hàng chục test cases tốn rất nhiều thời gian và cần sự tỉ mỉ để kết quả eval chính xác.
- Cân bằng giữa chi phí API và độ chính xác của metrics: Phải chọn model phù hợp (gpt-4o-mini) cho các tác vụ eval đơn giản.

## 4. Kết quả cụ thể đã đóng góp
- Triển khai module `engine/ragas_metrics.py` và `engine/retrieval_eval.py`.
- Thiết lập hệ thống logging chi tiết cho quá trình đánh giá retrieval.
- Phân tích và chỉ ra các case "Retrieval Miss" dẫn đến lỗi hệ thống trong báo cáo Failure Analysis.
