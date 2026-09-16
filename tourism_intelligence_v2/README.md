# Tourism Decision Intelligence V2 - safe extensions

Mục tiêu của package này là bổ sung các lớp dữ liệu còn thiếu cho MASTER V2.1 mà không sửa lõi đang chạy.

## Khóa an toàn

- Không ghi vào `weather/**`.
- Không thay `LAB_SNAPSHOT_V1`.
- Không sửa `tools/sunairport-collector/**` hoặc workflow Sun Airport.
- Không sửa `index.html`, `app.js`, `style.css`, `weather-dashboard.*`.
- Dữ liệu sinh tự động của từng collector phải đi vào branch dữ liệu riêng sau khi collector được duyệt production.
- Module mới chỉ được báo `REPORT_READY` khi chính collector/parser/QA của module đó đạt. `REPORT_READY` không có nghĩa thị trường đang hoạt động.
- Thiếu dữ liệu phải giữ `UNKNOWN`, không dùng D-1 thay D0 và không nội suy giả.

## Trạng thái 0.1.0

- Source Registry: triển khai và kiểm tra TTL/freshness.
- Marine Operations: collector miễn phí từ cổng Giấy phép rời cảng + fallback operator Thạnh Thới, lọc D0 nghiêm ngặt.
- Hotel Forward: basket V1 + bộ xử lý coverage/availability/rate; adapter Booking chưa bật production.
- Airfare: basket V1 + bộ xử lý comparability/coverage; adapter hãng bay chưa bật production.
- Forward Airlift: contract + processor, chưa tự động thu lịch bay.
- Social Intent: schema đa thị trường/ngôn ngữ/nền tảng.
- JoTrip Internal: schema tối thiểu.

Không có dịch vụ trả phí nào được kích hoạt.
