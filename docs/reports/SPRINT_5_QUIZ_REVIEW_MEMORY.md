# Sprint 5 - Quiz, Review, Memory và Guardrails

## Kết quả

Sprint 5 đã hoàn tất các workflow reliability còn thiếu của MVP backend:

- `task=quiz` đi qua scope → retrieval → structured quiz generation;
- mỗi câu hỏi có 2-6 lựa chọn duy nhất, đúng một đáp án, giải thích và citation;
- deterministic validation chạy trước LLM reviewer;
- reviewer trả `pass|fail`, feedback và retry target `generation|retrieval`;
- graph retry tối đa 2 lần và chặn output nếu vẫn không grounded;
- conversation, message và assistant run audit được lưu trong PostgreSQL;
- recent history được nạp lại từ PostgreSQL, nên follow-up không phụ thuộc process memory;
- input guardrail chặn control character và các mẫu instruction override phổ biến;
- prompt QA/Summary/Quiz/Reviewer đều coi evidence là dữ liệu không đáng tin cậy.

## Graph

```text
request
  → explicit route hoặc task resolver
  → QA | Summary | Quiz
  → deterministic validation
  → grounding reviewer
  → finalize

validation/reviewer fail
  → prepare retry (tối đa 2)
  → retrieval hoặc generation theo nguyên nhân
  → validation/reviewer lại
  → finalize pass hoặc block
```

`recursion_limit=40` là lớp bảo vệ bổ sung; điều kiện `retry_count < 2` mới là
giới hạn nghiệp vụ chính.

## PostgreSQL memory

Migration `20260917_0002` tạo:

- `conversations`: metadata của thread;
- `messages`: user/assistant messages dùng cho recent-window memory;
- `assistant_runs`: task, trạng thái review, retry count, document IDs, citations,
  trace và quiz JSON để audit.

`MEMORY_MAX_MESSAGES=12` là mặc định và có thể cấu hình trong `.env`.

## Kiểm chứng

- Alembic current: `20260917_0002 (head)`.
- PostgreSQL có đủ `conversations`, `messages`, `assistant_runs`.
- Toàn bộ test suite: `80 passed`.
- API readiness: `ready`.
- Prompt-injection smoke test: HTTP `400`, không khởi tạo retrieval/model trước guardrail.
- Live quiz smoke test trên collection `data_test`: 1 câu hỏi, 4 lựa chọn, đúng một
  đáp án, citation hợp lệ, reviewer `pass`, retry count `0`.

## Phạm vi memory

Sprint này hoàn thiện short-term conversational memory bền vững và run audit.
Semantic user memory/long-term preference extraction chưa được bật; phần đó chỉ
nên thêm khi có use case, consent và chính sách retention rõ ràng.

## Cập nhật hiện tại (2026-09-18)

- Quiz đọc số câu từ prompt bằng chữ số hoặc các từ số thông dụng tiếng Việt/Anh;
  mặc định 5 câu và giới hạn 20 câu.
- Validator yêu cầu output có đúng số câu đã requested trước khi reviewer chạy.
- Quiz được lưu vào Quiz Library và hỗ trợ nhiều attempt từ Sprint 7.
- Live Auto smoke test với một tài liệu `Knowledge Bases` tạo đúng 2 câu, reviewer
  `pass` và hoàn tất khoảng 8,8 giây.
- Một prompt 3 câu Security rộng đã bị chặn sau hai retry do citation của một số câu
  không khớp excerpt. Đây là fail-closed đúng thiết kế, không được ghi nhận là quiz đạt.
