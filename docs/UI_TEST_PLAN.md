# UI Test Plan - Multi-Agent Document Assistant

Kế hoạch này chỉ sử dụng giao diện thật tại `http://localhost:3000`. Không cần
chạy lệnh terminal trong quá trình test.

## 1. Chuẩn bị phiên test

1. Mở `http://localhost:3000`.
2. Nhấn `Ctrl + F5` để tải phiên bản FE mới nhất.
3. Nếu đang có hội thoại cũ, nhấn **New thread**.
4. Bỏ chọn tất cả tài liệu trước khi bắt đầu.
5. Có thể mở DevTools bằng `F12` để theo dõi tab **Console** và **Network**.

Giao diện phải hiển thị đúng 5 tài liệu:

| Tài liệu | Số chunks |
|---|---:|
| Enterprise Security, Access & Identity | 19 |
| Workflow Builder Fundamentals | 11 |
| Retrieval, Chunking & Embeddings | 10 |
| Knowledge Bases | 19 |
| Human in the Loop | 6 |

## 2. UI-01 - Chọn tài liệu và kiểm tra phạm vi

1. Nhấn vào `Enterprise Security, Access & Identity`.
2. Kiểm tra card có trạng thái được chọn.
3. Kiểm tra phía dưới composer hiển thị `1 document in scope`.
4. Nhấn lại card và xác nhận tài liệu được bỏ chọn.
5. Chọn lại tài liệu Security để tiếp tục.

Kết quả đạt: chỉ tài liệu được nhấn mới thay đổi trạng thái; nút gửi bị khóa khi
không có tài liệu nào được chọn.

## 3. UI-02 - Kiểm tra lựa chọn model

1. Nhấn nút **Models** trên thanh phía trên.
2. Kiểm tra có thể chọn OpenRouter, OpenAI, Gemini hoặc Ollama cho chat và embedding.
3. Kiểm tra có ô nhập/chọn custom **Chat model** và **Embedding model**.
4. Giữ nguyên model hiện tại rồi nhấn **Apply & test**.
5. Chờ kết quả kiểm tra riêng cho chat và embedding.
6. Thử một model ID không tồn tại và xác nhận cấu hình cũ vẫn được giữ.

Kết quả đạt: modal không hiển thị API key; lựa chọn chỉ được áp dụng khi backend gọi
thử thành công. Nếu đổi embedding khi đã có tài liệu, UI phải cảnh báo cần re-index.

## 4. UI-03 - Ask trên một tài liệu

Chỉ chọn `Enterprise Security, Access & Identity`, chọn tab **Ask** và gửi:

```text
According to the selected documentation, how do Role-Based Access Controls,
Workspace and Folder Access, and Project Controls differ?
```

Kiểm tra kết quả:

- Có câu trả lời thay vì `Request failed`.
- Có ít nhất một citation.
- Mọi citation đều có tên `Enterprise Security, Access & Identity`.
- Mở **Agent Trace** và xác nhận bước cuối là `PASS`.
- Trace có các bước retrieve, answer, validate, review và finalize.

Thời gian tham khảo: khoảng 10-25 giây tùy cloud provider.

## 5. UI-04 - Follow-up và lịch sử hội thoại

Không tạo thread mới, giữ tài liệu Security và gửi tiếp:

```text
How does Authentication and MFA complement those controls?
```

Kiểm tra kết quả:

- Câu trả lời hiểu được `those controls` từ message trước.
- Citation vẫn chỉ thuộc tài liệu Security.
- Agent Trace có bước query rewrite sử dụng conversation history.
- Refresh trình duyệt và xác nhận hai lượt hỏi đáp vẫn còn.
- Mở **History**, chọn đúng thread và đổi tên thành `Stack AI Security UI Test`.

Kết quả đạt: refresh không mất message và không xuất hiện thông báo request failed.

## 6. UI-05 - Tóm tắt tài liệu được chọn

1. Nhấn **New thread**.
2. Chỉ chọn `Enterprise Security, Access & Identity`.
3. Chọn tab **Summarize**.
4. Gửi prompt:

```text
Summarize the selected security documentation into five practical controls for
an enterprise deployment.
```

Kiểm tra kết quả:

- Reviewer là `PASS`.
- Có citations và tất cả đều thuộc tài liệu Security.
- Trace `Full document load` ghi đã đọc đủ `19 indexed chunks`.
- Trace có map, reduce, validate, review và finalize.
- Không có dấu hiệu hệ thống đọc 65 chunks của cả knowledge base.

Thời gian tham khảo gần nhất: khoảng 18 giây. Request có thể chậm hơn tùy model
nhưng không được trả `504 Gateway Time-out`.

## 7. UI-06 - Tạo và quản lý quiz

1. Nhấn **New thread**.
2. Chỉ chọn tài liệu `Knowledge Bases`.
3. Chọn tab **Quiz**.
4. Gửi prompt:

```text
Create a 2-question quiz about creating and using a Knowledge Base using only the selected documentation.
```

Kiểm tra kết quả:

- Có đúng 2 câu hỏi.
- Mỗi câu có các lựa chọn, đúng một đáp án và explanation.
- Citation của câu hỏi chỉ thuộc tài liệu `Knowledge Bases`.
- Reviewer cuối cùng là `PASS`; hệ thống có thể retry trước khi pass.
- Nhấn **Quizzes** và mở quiz vừa tạo.
- Chọn đáp án, nhấn submit và kiểm tra score.
- Đóng rồi mở lại **Quizzes**; attempt và best score vẫn còn.

Thời gian tham khảo gần nhất: khoảng 9 giây; có thể lâu hơn tùy provider và retry.

## 8. UI-07 - Kiểm tra cô lập giữa các tài liệu

1. Nhấn **New thread**.
2. Bỏ chọn Security.
3. Chỉ chọn `Knowledge Bases`.
4. Chọn **Ask** và gửi:

```text
How do I create and use a Knowledge Base?
```

Kết quả đạt:

- Câu trả lời có citation từ `Knowledge Bases`.
- Không có citation từ Security, Workflow Builder hoặc Human in the Loop.
- Composer hiển thị đúng `1 document in scope`.

## 9. UI-08 - Phạm vi nhiều tài liệu

1. Giữ `Knowledge Bases` đang được chọn.
2. Chọn thêm `Retrieval, Chunking & Embeddings`.
3. Kiểm tra composer hiển thị `2 documents in scope`.
4. Gửi:

```text
How do chunking and embeddings support a knowledge base?
```

Kết quả đạt: citations chỉ được phép thuộc hai tài liệu đang chọn.

## 10. UI-09 - New Thread và History

1. Khi đang có nội dung chat, nhấn **New thread**.
2. Kiểm tra vùng chat trở về màn hình chào mừng ngay lập tức.
3. Không gửi message và refresh trang.
4. Mở **History** rồi chọn lại thread `Stack AI Security UI Test`.
5. Kiểm tra nội dung cũ được tải lại.
6. Xóa một thread test không cần giữ và xác nhận nó biến mất.

Kết quả đạt: New Thread không tạo lỗi 404, không giữ message của thread cũ và
History vẫn tải được các thread đã lưu.

## 11. UI-10 - Kiểm tra trạng thái lỗi

Trong toàn bộ phiên test, DevTools không được xuất hiện các lỗi sau:

- `404 /conversations/{id}/messages` khi tạo thread mới;
- `500 /assistant/runs`;
- `504 Gateway Time-out`;
- lỗi JavaScript khiến nút không phản hồi.

Nếu một request thất bại, ghi lại bốn thông tin:

1. Tài liệu đang được chọn.
2. Tab đang dùng: Ask, Summarize hay Quiz.
3. Prompt vừa gửi.
4. Status code và response trong tab Network.

## 12. UI-11 - Upload PDF

1. Nhấn **Upload a PDF** và chọn một PDF dạng text nhỏ hơn 75 MB.
2. Chờ quá trình indexing hoàn tất.
3. Xác nhận tài liệu xuất hiện trong danh sách, tự động được chọn và có thông báo
   `uploaded and indexed`.
4. Chọn thử một PDF lớn hơn 75 MB.

Kết quả đạt: PDF hợp lệ được index thành công; PDF quá giới hạn không được gửi lên server và
giao diện hiển thị rõ dung lượng file cùng giới hạn 75 MB, không chỉ báo `Request failed (413)`.

## 13. UI-12 - Auto tự nhận diện tác vụ

1. Nhấn **New thread** và giữ tab **Auto**.
2. Gửi một câu hỏi thông tin; Agent Trace phải có `Resolve task` và định tuyến sang `qa`.
3. Gửi yêu cầu bắt đầu bằng `Summarize`; hệ thống phải định tuyến sang `summary`.
4. Gửi `Create a 2-question quiz`; hệ thống phải định tuyến sang `quiz` và trả đúng 2 câu.

Kết quả đạt: người dùng không phải đổi tab thủ công; Supervisor nhận diện đúng ý định. Các tab Ask,
Summarize và Quiz vẫn dùng được khi cần ép tác vụ cụ thể.

## 14. Checklist kết quả cuối

| Hạng mục | Pass |
|---|:---:|
| Hiển thị đúng 5 tài liệu và 65 chunks | ☐ |
| Model modal hoạt động và không lộ API key | ☐ |
| Ask trả citation đúng một tài liệu | ☐ |
| Follow-up sử dụng conversation history | ☐ |
| Summary đọc đủ 19 chunks của tài liệu Security | ☐ |
| Quiz tạo đúng 2 câu theo yêu cầu và lưu được attempt | ☐ |
| Không có citation ngoài tài liệu được chọn | ☐ |
| Multi-document chỉ dùng hai tài liệu đã chọn | ☐ |
| New Thread và History hoạt động sau refresh | ☐ |
| Upload PDF dưới 75 MB hoạt động và file quá lớn có thông báo rõ | ☐ |
| Auto nhận diện đúng Ask, Summarize và số câu Quiz được yêu cầu | ☐ |
| Không có lỗi 404, 500 hoặc 504 | ☐ |
