# Báo cáo Cá nhân — Reflection Report

**Họ và tên:** Phạm Việt Cường  
**Lab:** Day 14 — AI Evaluation Factory  
**Ngày nộp:** 21/04/2026

---

## 1. Vai trò và phạm vi đóng góp

Trong Lab 14, tôi tập trung vào 3 nhiệm vụ chính:
- Chạy benchmark end-to-end để tạo `reports/summary.json` và `reports/benchmark_results.json`
- Phân cụm lỗi (Failure Clustering) dựa trên tín hiệu retrieval + judge score
- Thực hiện phân tích **5 Whys** để chỉ ra lỗi nằm ở **Ingestion pipeline / Chunking strategy / Retrieval / Prompting**

Đây là phần giúp nhóm chuyển từ “đoán lỗi” sang “định vị lỗi có bằng chứng”.

---

## 2. Kết quả benchmark tôi đã chạy

Từ lần chạy benchmark mới nhất:
- Tổng số test cases: **56**
- Pass/Fail/Error: **35 / 21 / 0**
- Avg Judge Score: **3.5482 / 5**
- Retrieval metrics:
  - Hit@1 = **0.3036**
  - Hit@3 = **0.6786**
  - Hit@5 = **0.8214**
  - MRR = **0.5030**
- RAGAS:
  - Faithfulness = **0.8054**
  - Relevancy = **0.5696**
  - Context Relevancy = **0.7929**

Điều tôi rút ra: hệ thống có xu hướng “trả lời bám context đang có” (faithfulness cao), nhưng còn trả lời **chưa đúng trọng tâm câu hỏi** (relevancy thấp).

---

## 3. Failure Clustering — cách tôi phân cụm lỗi

Tôi dùng chính `reports/benchmark_results.json` để tách fail cases thành cụm có tính hành động:

### Cụm A — Retrieval miss hoàn toàn
- Tiêu chí: `hit_rate_at_5 == 0`
- Số lượng: **8/21 fails**
- Ý nghĩa: không lấy được tài liệu ground truth trong top-5
- Kết luận kỹ thuật: lỗi chính nằm ở **Retrieval**

### Cụm B — Retrieval tốt nhưng answer vẫn fail
- Tiêu chí: `hit_rate_at_5 == 1` và `judge final_score < 3`
- Số lượng: **13/21 fails**
- Ý nghĩa: tài liệu đúng đã có, nhưng câu trả lời vẫn lệch intent
- Kết luận kỹ thuật: lỗi chính nằm ở **Prompting**

### Cụm C — Có đúng trong top-5 nhưng không lên top-1
- Tiêu chí: `hit_rate_at_5 == 1` và `hit_rate_at_1 == 0`
- Số lượng: **6/21 fails**
- Ý nghĩa: ranking/chunk quality chưa tốt, mô hình dễ đọc nhầm chunk đứng đầu
- Kết luận kỹ thuật: lỗi chính nằm ở **Chunking strategy** (và ranking trong retrieval)

---

## 4. 5 Whys — những gì tôi học được từ root-cause analysis

### Case đại diện 1: Retrieval miss (Cụm A)
1. Symptom: fail do không retrieve được ground truth.
2. Why 1: query bị nhiễu bởi input adversarial/out-of-context.
3. Why 2: retrieval thiếu bước intent filtering trước search.
4. Why 3: pipeline chưa có robust query rewriting cho truy vấn nhiễu.
5. Why 4: thiết kế hiện tại ưu tiên recall chung, chưa tách policy cho adversarial.
6. **Root cause:** **Retrieval**.

### Case đại diện 2: Retrieval tốt nhưng trả lời sai (Cụm B)
1. Symptom: hit@5 = 1 nhưng final score thấp.
2. Why 1: model trả lời theo đoạn context “dễ dùng” thay vì bám intent câu hỏi.
3. Why 2: prompt chưa có cơ chế khóa intent và tự kiểm tra trước khi trả lời.
4. Why 3: chưa có bước kiểm tra coverage giữa câu hỏi và câu trả lời.
5. Why 4: chưa ép output trích dẫn đúng evidence trước khi tổng hợp.
6. **Root cause:** **Prompting**.

### Case đại diện 3: Hit@5 tốt, Hit@1 thấp (Cụm C)
1. Symptom: có tài liệu đúng trong top-5 nhưng không top-1.
2. Why 1: chunk đứng đầu chưa phải chunk chứa thông tin quyết định.
3. Why 2: chunk hiện tại còn “đa ý”, làm embedding không sắc theo intent.
4. Why 3: chưa có semantic chunking + reranking.
5. Why 4: pipeline đang dựa nhiều vào retrieval score gốc.
6. **Root cause:** **Chunking strategy**.

---

## 5. Trả lời trực tiếp câu hỏi “lỗi nằm ở đâu?”

Sau benchmark + failure clustering + 5 Whys, kết luận của tôi:
- **Ingestion pipeline:** chưa có bằng chứng lỗi hệ thống ở run này (không có expected retrieval id nào bị “never seen”).
- **Chunking strategy:** có lỗi ở nhóm Hit@5=1 nhưng Hit@1=0.
- **Retrieval:** có lỗi rõ ở nhóm retrieval miss (8 cases).
- **Prompting:** là bottleneck lớn nhất trong run hiện tại (13 cases retrieval tốt nhưng vẫn fail).

---

## 6. Kế hoạch cải tiến cá nhân cho vòng tiếp theo

1. Thêm bước **intent locking** trong prompt (ép trả lời theo đúng intent câu hỏi).
2. Bổ sung **query rewriting + adversarial filter** trước retrieval.
3. Chuyển sang **semantic chunking** thay cho fixed-size thuần.
4. Thêm **reranker** cho top-k trước khi gửi vào answer generation.
5. Theo dõi thêm metric mới: tỉ lệ “retrieval-good-but-answer-fail” để đo đúng bottleneck Prompting.

---

*Phạm Việt Cường*  
*Lab Day 14 — AI Evaluation Factory*
