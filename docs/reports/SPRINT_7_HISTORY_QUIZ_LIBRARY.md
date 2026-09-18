# Sprint 7 - Chat History và Quiz Library

Run date: 2026-09-17

## Kết quả

- Conversation API hỗ trợ list, load messages, rename và delete.
- Production FE khôi phục thread đang chọn sau reload và cho phép chuyển thread.
- Quiz được lưu thành entity riêng, liên kết với assistant run và conversation.
- Mỗi quiz hỗ trợ nhiều attempt, backend xác thực đủ câu và tự chấm điểm.
- Quiz Library hiển thị số câu, số attempt, best score, nội dung quiz và citations.
- Xóa conversation xóa cascade messages, assistant runs, quizzes và quiz attempts.

## Database

Migration `20260917_0005` tạo:

- `quizzes`: title, questions JSON có schema, run và conversation nguồn;
- `quiz_attempts`: answers, correct count, total questions và timestamp.

Migration tự backfill các quiz cũ đang nằm trong `assistant_runs.quiz`. Quiz mới
được thêm vào thư viện trong cùng transaction với conversation, messages và run audit.

## API

```text
GET    /api/v1/conversations
GET    /api/v1/conversations/{id}/messages
PATCH  /api/v1/conversations/{id}
DELETE /api/v1/conversations/{id}

GET    /api/v1/quizzes
GET    /api/v1/quizzes/{id}
POST   /api/v1/quizzes/{id}/attempts
GET    /api/v1/quizzes/{id}/attempts
DELETE /api/v1/quizzes/{id}
```

## Kiểm chứng

- Backend: 97 tests PASS.
- Frontend strict TypeScript production build: PASS.
- Alembic: `20260917_0005 (head)`.
- Conversation và quiz list API: HTTP 200.
- Production UI: HTTP 200 tại `http://localhost:3000`.

## Phạm vi

Đây là history cho single-user deployment. Multi-user production cần authentication,
`user_id`, authorization filter và retention policy trước khi expose dữ liệu giữa tài khoản.

## Cập nhật tích hợp (2026-09-18)

- New Thread chỉ tạo conversation khi người dùng gửi message đầu tiên, tránh gọi
  `/messages` với một UUID chưa tồn tại và loại bỏ lỗi 404 trước đây.
- History có thể tải lại message sau refresh; rename/delete tiếp tục đi qua API.
- Quiz tạo từ Auto hoặc tab Quiz đều được lưu vào cùng Quiz Library, kèm attempt và best score.
