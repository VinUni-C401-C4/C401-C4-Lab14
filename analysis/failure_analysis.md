# Báo cáo Phân tích Thất bại (Failure Analysis Report)

## 1) Tổng quan benchmark (run mới nhất)
- Tổng số test cases: **56**
- Pass/Fail/Error: **35 / 21 / 0**
- Avg Judge Score: **3.5482 / 5**
- Retrieval quality:
  - **Hit@1 = 0.3036**
  - **Hit@3 = 0.6786**
  - **Hit@5 = 0.8214**
  - **MRR = 0.5030**
- RAGAS quality:
  - **Faithfulness = 0.8054**
  - **Relevancy = 0.5696**
  - **Context relevancy = 0.7929**

Nhận định nhanh:
- Faithfulness cao nhưng relevancy thấp cho thấy hệ thống thường "nói đúng theo context đang có", nhưng context hoặc lựa chọn nội dung trả lời chưa đúng trọng tâm câu hỏi.

---

## 2) Failure clustering (phân cụm lỗi)

### Cụm A - Retrieval miss hoàn toàn
- Quy tắc cụm: `hit_rate_at_5 == 0`
- Số lượng: **8/21 fails (38.1%)**
- Case IDs: `tc_019`, `tc_028`, `tc_030`, `tc_031`, `tc_043`, `tc_044`, `tc_050`, `tc_054`
- Avg final score: **2.14**
- Nơi lỗi chính: **Retrieval**

### Cụm B - Có tài liệu đúng nhưng trả lời vẫn sai trọng tâm
- Quy tắc cụm: `hit_rate_at_5 == 1` và `final_score < 3`
- Số lượng: **13/21 fails (61.9%)**
- Case IDs: `tc_010`, `tc_011`, `tc_013`, `tc_018`, `tc_020`, `tc_021`, `tc_023`, `tc_038`, `tc_040`, `tc_046`, `tc_049`, `tc_051`, `tc_055`
- Avg final score: **2.42**
- Nơi lỗi chính: **Prompting**

### Cụm C - Relevant doc có trong top-5 nhưng không lên top-1
- Quy tắc cụm: `hit_rate_at_5 == 1` và `hit_rate_at_1 == 0`
- Số lượng: **6/21 fails (28.6%)**
- Case IDs: `tc_011`, `tc_020`, `tc_038`, `tc_040`, `tc_049`, `tc_055`
- Avg final score: **2.38**
- Nơi lỗi chính: **Chunking strategy + ranking trong Retrieval**

Ghi chú về ingestion:
- Kiểm tra tất cả `expected_retrieval_ids` cho thấy **0 ID bị "never seen"** trong toàn bộ retrieved IDs.
- Kết luận: **không có bằng chứng lỗi Ingestion pipeline ở vòng benchmark này**.

---

## 3) Phân tích 5 Whys

## Case 1 - Cụm A (Retrieval miss): `tc_043` / `tc_044` kiểu adversarial
1. **Symptom:** Agent fail, không lấy được tài liệu ground truth (`Hit@5 = 0`).
2. **Why 1:** Truy vấn user bị "nhiễu" bởi nội dung adversarial (goal hijacking / out-of-context).
3. **Why 2:** Retriever truy xuất theo semantic similarity thuần, thiếu bước phân loại intent + filter an toàn.
4. **Why 3:** Pipeline retrieval không có guardrail để chặn/giảm trọng số truy vấn độc hại.
5. **Why 4:** Thiết kế benchmark pipeline ưu tiên recall chung, chưa tách riêng adversarial retrieval policy.
6. **Root cause:** **Retrieval layer** thiếu cơ chế robust query rewriting/intent filtering cho adversarial input.

## Case 2 - Cụm B (Prompting failure dù retrieval tốt): `tc_010`, `tc_013`
1. **Symptom:** `Hit@5 = 1`, `Hit@1 = 1` nhưng câu trả lời lệch hẳn câu hỏi (trả lời sang chủ đề lương/thưởng).
2. **Why 1:** LLM tạo câu trả lời dựa trên phần context "dễ lấy" thay vì bám sát intent của câu hỏi.
3. **Why 2:** Prompt chưa ép buộc mapping "question -> answer span" và chưa yêu cầu self-check theo intent.
4. **Why 3:** Không có bước verification "answer coverage vs question constraints".
5. **Why 4:** Thiếu output schema bắt buộc trích dẫn đoạn context đúng rồi mới tổng hợp trả lời.
6. **Root cause:** **Prompting** (instruction hierarchy + answer validation chưa đủ chặt).

## Case 3 - Cụm C (Ranking/chunk boundary): `tc_011`, `tc_040`
1. **Symptom:** Relevant doc có trong top-5 nhưng không đứng top-1 (`Hit@1 = 0`, `Hit@5 = 1`), câu trả lời bị lệch.
2. **Why 1:** Retriever lấy đúng tài liệu nhưng thứ hạng chưa tốt, model đọc nhầm chunk top đầu.
3. **Why 2:** Chunk hiện tại có thể quá dài/không semantic nên pha trộn nhiều ý.
4. **Why 3:** Embedding của chunk "đa ý" làm độ tương đồng với query kém sắc nét.
5. **Why 4:** Chưa có reranker hoặc chunk-level compression trước khi gửi vào prompt.
6. **Root cause:** **Chunking strategy** (và phụ trợ ranking trong Retrieval).

---

## 4) Kết luận lỗi nằm ở đâu
- **Ingestion pipeline:** Chưa thấy lỗi hệ thống trong benchmark này (0 expected ID bị mất hoàn toàn).
- **Chunking strategy:** Có vấn đề ở các case `Hit@5=1` nhưng `Hit@1=0`; chunk chưa đủ "atomic" theo ý nghĩa.
- **Retrieval:** Có lỗi rõ rệt ở cụm retrieval miss (`Hit@5=0`, 8 cases).
- **Prompting:** Là nguồn lỗi lớn nhất (13 cases retrieval tốt nhưng answer vẫn fail).

---

## 5) Action plan ưu tiên
- P1 (Prompting): thêm bước "intent locking + answer plan + citation check", fail-fast nếu không bám câu hỏi.
- P1 (Retrieval): thêm query rewriting + adversarial intent filter trước truy xuất.
- P2 (Chunking): chuyển sang semantic chunking, giảm chunk overlap mù và thêm parent-child chunk.
- P2 (Ranking): thêm reranker cho top-k trước khi đưa vào answer generation.
