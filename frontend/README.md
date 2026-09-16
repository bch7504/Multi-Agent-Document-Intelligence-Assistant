# Frontend workspace

`mock.html` là bản mock giao diện độc lập để duyệt layout và interaction cơ bản.

- Không gọi API.
- Không cần Node.js hoặc Python.
- Không chứa dữ liệu thật.
- Có thể mở trực tiếp bằng trình duyệt.
- Nút `Local` cho phép duyệt UX chọn/tải chat và embedding models; tiến trình tải chỉ là mô phỏng.

API key không được nhập hoặc lưu trong static frontend. Người dùng copy `.env.example` thành `.env` và chỉ điền key cho provider backend đã chọn.

Frontend React/TypeScript production sẽ được tạo sau khi API contract của FastAPI ổn định. Không phát triển business logic dựa trên code JavaScript trong mock.
