# Individual Reflection — Hoàng Hiệp (hoanghiepbk)

## 1. Vai trò trong nhóm
**Nhóm Engineering & AI Research** — Phụ trách phát triển module Multi-Judge Consensus và logic xử lý xung đột tự động.

## 2. Những gì đã học được

### 2.1 Multi-Judge Consensus
Tôi đã học cách triển khai hệ thống đánh giá sử dụng nhiều model LLM khác nhau (GPT-4o và GPT-4o-mini). Việc này giúp giảm thiểu "Position Bias" và "Self-preference Bias" của LLM. Tôi đã hiểu cách tính toán **Cohen's Kappa** để đo lường độ đồng thuận giữa các Judge, một kỹ thuật quan trọng trong AI Engineering chuyên nghiệp.

### 2.2 Async Programming in Python
Việc chạy benchmark cho 50+ cases yêu cầu xử lý bất đồng bộ (asyncio). Tôi đã học cách sử dụng `asyncio.Semaphore` để kiểm soát concurrency, tránh bị rate-limit bởi OpenAI API trong khi vẫn duy trì hiệu suất cao (toàn bộ pipeline chạy dưới 2 phút).

## 3. Khó khăn gặp phải
- Xử lý các phản hồi JSON không hợp lệ từ LLM Judge: Phải viết thêm logic regex để parse kết quả khi LLM không tuân thủ format JSON 100%.
- Đồng bộ hóa dữ liệu giữa các Judge khi có sự chênh lệch điểm số lớn: Phải thiết lập logic lấy trung bình trọng số hoặc median.

## 4. Kết quả cụ thể đã đóng góp
- Xây dựng file `engine/llm_judge.py` hoàn chỉnh với hỗ trợ multi-model.
- Tối ưu hóa tốc độ đánh giá thông qua batching và async calls.
- Đạt được độ đồng thuận (Agreement Rate) > 95% giữa các Judge.
