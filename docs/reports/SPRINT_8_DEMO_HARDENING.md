# Sprint 8 - Demo Hardening và Selected-Document Workflows

Run date: 2026-09-18

## Kết quả

Sprint 8 tập trung làm cho hành vi runtime và giao diện khớp với cách người dùng
thực tế chọn tài liệu, model và tác vụ:

- dataset `stack_ai.json` được import idempotent thành 5 document records độc lập,
  tổng 65 chunks thay vì hiển thị một tài liệu aggregate;
- QA, Summary và Quiz đều bị giới hạn bởi `document_ids` đang chọn;
- Summary tải toàn bộ chunks của tài liệu được chọn theo thứ tự nguồn, sau đó dùng
  single-pass hoặc map/reduce theo kích thước context;
- Auto routing nhận diện cả `qa`, `summary` và `quiz`; frontend dùng Auto làm mặc định;
- Quiz đọc số câu từ yêu cầu, mặc định 5 và giới hạn tối đa 20;
- giới hạn upload được đồng bộ ở 75 MiB giữa frontend, FastAPI, Docker và Nginx;
- PDF không có lớp text chuyển sang `failed` với thông báo rõ ràng, không bị hiểu nhầm
  là lỗi proxy/upload;
- Model modal cho phép chọn hoặc nhập provider/model rồi dùng **Apply & test** để
  kiểm tra chat và embedding thật trước khi thay cấu hình đang chạy;
- message UI bỏ nhãn `YOU`/`ATLAS` lặp lại, giữ avatar ngắn và phân biệt hai phía;
- Nginx tắt cache SPA để bản build mới xuất hiện ngay sau refresh cứng.

## Kiểm chứng selected-document workflows

Live QA đã được chạy riêng trên cả 5 tài liệu curated. Tất cả case đều reviewer
`pass` và citation chỉ thuộc document được chọn:

| Tài liệu | Citations | Thời gian gần nhất |
|---|---:|---:|
| Enterprise Security, Access & Identity | 3 | 19,8 giây |
| Workflow Builder Fundamentals | 4 | 8,4 giây |
| Retrieval, Chunking & Embeddings | 2 | 5,9 giây |
| Knowledge Bases | 6 | 7,9 giây |
| Human in the Loop | 4 | 5,6 giây |

Một Summary trên tài liệu Security tải đủ 19 chunks, trả 17 citations đúng scope
và reviewer `pass` trong khoảng 16,5 giây.

Auto routing smoke test trên frontend/API thật:

| Prompt type | Task đã resolve | Kết quả | Thời gian gần nhất |
|---|---|---|---:|
| Câu hỏi thông tin | `qa` | PASS | 9,2 giây |
| Yêu cầu `Summarize` | `summary` | PASS | 8,4 giây |
| `Create a 2-question quiz` | `quiz` | đúng 2 câu, PASS | 8,8 giây |

## Kiểm chứng model và upload

- Live model validation pass cho cả chat và embedding của cấu hình hiện tại.
- Embedding probe trả vector 1.536 dimensions; toàn bộ validation mất khoảng 3,8 giây.
- Backend không trả API key hoặc raw provider exception về browser.
- PDF text 69,89 MiB được parser đọc thành 46 pages; 9/10 trang đầu lấy được text.
- PDF scan 51,2 MiB đi qua upload nhưng chuyển `failed` với thông báo
  `PDF does not contain extractable text`, xác nhận thiếu OCR chứ không phải giới hạn 50 MiB.

## Guardrail behavior

Một quiz Security 3 câu từng bị reviewer từ chối sau hai retry vì citation của câu
2 và 3 không khớp excerpt. Hệ thống không trả output đó như một kết quả hợp lệ.
Case này chứng minh bounded retry và fail-closed hoạt động; prompt Knowledge Bases
2 câu được dùng làm smoke case ổn định cho demo.

## Verification

- Backend unit/integration suite: 107 tests PASS.
- Python compilation: PASS.
- Frontend strict TypeScript production build: PASS.
- Docker Compose configuration: PASS.
- API, PostgreSQL, Milvus và frontend containers: healthy trong phiên live test.

## Giới hạn còn lại

- Upload/parse/embed vẫn đồng bộ; tài liệu lớn có thể giữ request vài phút.
- Chưa OCR PDF scan hoặc ảnh.
- Model validation kiểm tra khả năng gọi tại thời điểm Apply, không bảo đảm provider
  sẽ không rate-limit ở request sau.
- Dataset RAGAS có 3 cases, chỉ phù hợp smoke regression.
- Deployment hiện là single-user; chưa có authentication/authorization theo tenant.
