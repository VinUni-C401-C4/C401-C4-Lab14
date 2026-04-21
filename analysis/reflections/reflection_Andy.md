# Individual Reflection — Andy Dyan (andydyan20)

## 1. Vai trò trong nhóm
**Nhóm System Architecture & Integration** — Phụ trách xây dựng Benchmark Runner, Regression Analysis và Release Gate logic.

## 2. Những gì đã học được

### 2.1 Regression Testing trong AI
Tôi đã học được rằng trong phát triển AI, việc "fix một lỗi này có thể làm hỏng thứ khác". Do đó, chạy Regression Testing so sánh V1 vs V2 là bắt buộc. Tôi đã xây dựng class `ReleaseGate` để tự động hóa việc ra quyết định dựa trên độ lệch (delta) của metrics.

### 2.2 Cost & Token Management
Trong môi trường production, chi phí là một yếu tố sống còn. Tôi đã học cách tích hợp cost tracking vào pipeline để báo cáo chính xác số tiền USD đã tiêu tốn cho mỗi lần chạy benchmark, từ đó đưa ra các đề xuất tối ưu hóa (như sử dụng caching hoặc model rẻ hơn).

## 3. Khó khăn gặp phải
- Thiết kế một runner có khả năng chịu lỗi tốt (retry logic với exponential backoff) để pipeline không bị dừng giữa chừng khi gặp lỗi mạng.
- Xây dựng format báo cáo `summary.json` sao cho vừa đầy đủ thông tin kỹ thuật, vừa dễ hiểu cho các bên liên quan.

## 4. Kết quả cụ thể đã đóng góp
- Xây dựng framework `engine/runner.py` ổn định và mạnh mẽ.
- Thiết lập logic "Release Gate" tự động trong `main.py`.
- Tạo hệ thống báo cáo tự động giúp nhóm nhanh chóng nhận diện sự sụt giảm hiệu năng giữa các phiên bản.
