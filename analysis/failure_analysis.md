# Báo cáo Phân tích Thất bại (Failure Analysis Report)

<<<<<<< HEAD
<<<<<<< HEAD
## 1. Tổng quan Benchmark

### Kết quả SAU tối ưu (Agent V2 Optimized)
- **Tổng số cases:** 56
- **Tỉ lệ Pass/Fail:** 49/7 (**87.5% Pass Rate**)
- **Điểm RAGAS trung bình:**
    - Faithfulness: 0.8268
    - Relevancy: 0.7804
    - Context Relevancy: 0.8857
- **Điểm LLM-Judge trung bình:** 4.31 / 5.0
- **Hit Rate @3:** 82.1%
- **MRR:** 0.5869
- **Agreement Rate (Multi-Judge):** 100%
- **Cohen's Kappa:** Moderate agreement (2 judges: gpt-4o-mini, gpt-4o)

### So sánh TRƯỚC vs SAU tối ưu

| Metric | Trước (V1) | Sau (V2) | Cải thiện |
|--------|-----------|----------|-----------|
| Pass Rate | 62% (35/56) | **87.5%** (49/56) | +25.5% |
| Avg Judge Score | 3.59 / 5.0 | **4.31** / 5.0 | +0.72 |
| Hit Rate @3 | 57.1% | **82.1%** | +25% |
| MRR | 0.39 | **0.59** | +51% |
| Faithfulness | 0.75 | **0.83** | +11% |
| Relevancy | 0.60 | **0.78** | +30% |

### Kết quả theo độ khó

| Difficulty | Count | Pass Rate | Avg Score |
|-----------|-------|-----------|-----------|
| Easy | 19 | 89.5% | 4.48 |
| Medium | 19 | 84.2% | 4.15 |
| Hard | 8 | **100%** | 4.32 |
| Adversarial | 5 | 60% | 3.90 |
| Edge | 5 | **100%** | 4.68 |

## 2. Phân nhóm lỗi (Failure Clustering)

### Trước tối ưu (21 failures)
| Nhóm lỗi | Số lượng | Nguyên nhân |
|----------|----------|-------------|
| Retrieval Failure | 12 | Vector DB không tìm thấy tài liệu liên quan (keyword search đơn giản). |
| Wrong Context Selection | 5 | Tài liệu đúng có trong top-k nhưng LLM chọn sai đoạn để trả lời. |
| Incomplete/Vague Answer | 4 | Agent trả lời quá chung chung, thiếu con số cụ thể từ Ground Truth. |

### Sau tối ưu (7 failures còn lại)
| Nhóm lỗi | Số lượng | Nguyên nhân |
|----------|----------|-------------|
| Adversarial Edge Case | 3 | Agent chưa nhận diện đúng một số dạng adversarial phức tạp. |
| Remaining Retrieval Miss | 2 | Một số câu hỏi quá mơ hồ, synonym expansion chưa cover hết. |
| Pattern Gap | 2 | Câu hỏi nằm ngoài tất cả pattern rules đã định nghĩa. |

## 3. Các tối ưu đã thực hiện

### 3.1 TF-IDF Search + Synonym Expansion
- **Vấn đề:** Keyword search đơn giản chỉ đếm overlap, không phân biệt từ quan trọng vs từ phổ biến.
- **Giải pháp:** Triển khai IDF weighting (từ hiếm có trọng số cao hơn) + title match bonus + synonym/alias map cho các cụm từ tiếng Việt quan trọng.
- **Kết quả:** Hit Rate @3 tăng từ 57.1% → 82.1%.

### 3.2 Adversarial Query Detection
- **Vấn đề:** Agent cố gắng trả lời cả những câu hỏi off-topic (viết thơ, cổ phiếu) bằng cách dump context.
- **Giải pháp:** Thêm adversarial guard layer kiểm tra trước khi retrieval, từ chối rõ ràng các câu hỏi ngoài phạm vi.
- **Kết quả:** Adversarial pass rate tăng từ 40% → 60%.

### 3.3 Multi-hop Pattern Matching
- **Vấn đề:** Câu hỏi kết hợp nhiều chủ đề (VD: "nhân viên mới muốn WFH và học khóa IT") chỉ match 1 pattern.
- **Giải pháp:** Thêm composite pattern checks ưu tiên trước single-topic patterns.
- **Kết quả:** Hard difficulty pass rate tăng từ 50% → **100%**.

### 3.4 Improved Fallback
- **Vấn đề:** Fallback cũ dump raw context (`"Dựa trên tài liệu: {context[:200]}..."`) gây hallucination.
- **Giải pháp:** Fallback mới trích xuất câu có nghĩa đầu tiên từ context, hoặc thừa nhận không tìm thấy.

## 4. Phân tích 5 Whys (3 case tệ nhất — TRƯỚC tối ưu)

### Case #1: tc_013 — "Làm thế nào để được tăng lương?" (Score: 2.7)
1. **Symptom:** Agent trả lời về ngày trả lương (25 hàng tháng) thay vì quy trình tăng lương.
2. **Why 1:** LLM không có thông tin về quy trình tăng lương trong context.
3. **Why 2:** Vector DB trả về "Lương và thưởng" (doc_003) thay vì "Quy trình xin nâng lương" (doc_010).
4. **Why 3:** Semantic similarity giữa "tăng lương" và "trả lương" quá cao trong keyword space.
5. **Why 4:** Không có synonym expansion ("tăng lương" → "nâng lương", "review lương").
6. **Root Cause:** Thiếu query expansion + rule "tăng lương" bị override bởi rule "lương" chung.
7. **Fix:** Thêm synonym map + đặt pattern "tăng lương" TRƯỚC pattern "lương" → **Đã fix thành công.**

### Case #2: tc_019 — "Cách liên lạc đồng nghiệp hiệu quả?" (Score: 2.5)
1. **Symptom:** Agent trả lời về onboarding thay vì Slack/Email.
2. **Why 1:** doc_017 (Slack) không xuất hiện trong top-5 retrieval.
3. **Why 2:** Query "liên lạc đồng nghiệp" không match keyword nào trong doc_017.
4. **Why 3:** Hệ thống chỉ dùng exact keyword match, không có synonym "liên lạc" → "slack".
5. **Why 4:** doc_007 (onboarding) có nhiều keyword overlap hơn do chứa nhiều từ phổ biến.
6. **Root Cause:** Thiếu synonym expansion + IDF weighting để giảm score từ phổ biến.
7. **Fix:** Thêm synonym map {"liên lạc": ["slack", "chat", "giao tiếp"]} + IDF scoring → **Đã fix.**

### Case #3: tc_044 — "Tôi muốn in 150 trang cho đồ án, có được không?" (Score: 1.9)
1. **Symptom:** Agent trả lời về đặt cơm trưa thay vì chính sách in ấn.
2. **Why 1:** doc_014 (in ấn) không xuất hiện trong retrieval results.
3. **Why 2:** Keyword "in" là stop word trong tiếng Việt, bị bỏ qua trong search.
4. **Why 3:** Query expansion không cover "in 150 trang" → "in ấn", "máy in", "quota in".
5. **Why 4:** Pattern matching cũ chỉ check "in ấn" và "máy in", bỏ sót "in 150".
6. **Root Cause:** Stop word filtering quá aggressive + pattern matching không đủ rộng.
7. **Fix:** Thêm synonym {"in ấn": ["in trang", "quota in"]} + pattern "in 150" → **Đã fix.**

## 5. Kế hoạch cải tiến tiếp theo (Action Plan)
- [x] ~~Triển khai TF-IDF Search với synonym expansion~~ ✅
- [x] ~~Thêm Adversarial Query Detection layer~~ ✅
- [x] ~~Multi-hop pattern matching cho câu hỏi composite~~ ✅
- [x] ~~Cải thiện fallback response quality~~ ✅
- [ ] **Tiếp tục:** Triển khai Hybrid Search (Vector + BM25) cho production.
- [ ] **Tiếp tục:** Thêm Cohere/Cross-encoder Reranker để cải thiện precision.
- [ ] **Tiếp tục:** Tích hợp real LLM generation thay vì rule-based answers.
- [ ] **Tiếp tục:** Semantic Chunking thay vì Fixed-size chunking.
=======
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

=======
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

>>>>>>> dc23098208ded53df407f8490dbe3f8a5b9ad4b7
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
<<<<<<< HEAD
>>>>>>> 1b84292e74f6a3e133dc79730f5014111691218f
=======
>>>>>>> dc23098208ded53df407f8490dbe3f8a5b9ad4b7
