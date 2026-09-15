# Lệnh hằng ngày - Sun Airport D0

## Mục tiêu

Đọc dữ liệu Sun Airport đã được collector chuẩn hóa trong `kenzuko/Jotrip-Lab` để tạo phần Hàng không D0 của báo cáo Phú Quốc. Ưu tiên data warehouse nội bộ trước, chỉ kiểm tra trang trực tiếp khi cần đối chiếu hoặc fallback.

## Lệnh thực thi

Kiểm tra theo thứ tự:

1. `data/sunairport/health.json`
2. `data/sunairport/latest.json`
3. Snapshot mới nhất trong `data/sunairport/YYYY-MM-DD/`
4. Workflow `Sun Airport flights`, log, annotation và artifact nếu health không đạt
5. Trang Sun Airport hoặc bảng bay chính thức khác chỉ để cross-check hoặc fallback có ghi evidence class

Chỉ coi dữ liệu sẵn sàng khi đồng thời thỏa:

- `health.state = REPORT_READY`
- `latest.report_state = REPORT_READY`
- `health.source_date` và `latest.source_date` là ngày D0 theo giờ Việt Nam
- `collector_completed`, `parser_passed`, `normalization_passed`, `qa_passed`, `commit_succeeded` đều là `true`
- schema, parser và normalization version tương thích với kỳ so sánh
- snapshot chưa vượt TTL được cấu hình cho bảng bay D0

Khi đạt gate, xuất ngắn gọn:

- giờ thu thập và độ mới của snapshot
- số movement vật lý đến, đi và tổng cộng
- domestic/international mix theo chiều đến và đi
- route/station nổi bật và flight bank đáng chú ý
- số chuyến trễ, hủy hoặc thay đổi nếu dữ liệu nguồn thể hiện rõ
- trạng thái `REPORT_READY`, QA result và evidence class

Quy tắc bắt buộc:

- Codeshare trong cùng một movement chỉ đếm một lần. Dùng `operating_flight_number`; các số còn lại là `marketing_flight_numbers`.
- Không được đưa flight number vào station.
- Không lấy snapshot hôm qua thay cho hôm nay.
- Không coi nguồn lỗi hoặc chưa rollover là không có chuyến bay.
- Không suy flight count thành passenger count, load factor hoặc demand thực tế.
- Không tính trend giữa hai snapshot khác schema/parser/normalization version nếu chưa reprocess.
- Không gọi module hàng không là đầy đủ nếu dependency gate không đạt.

Nếu chưa đạt gate, phân loại chính xác một trong các trạng thái:

- `WAITING_FOR_D0` hoặc `PAGE_NOT_ROLLED`: nguồn chưa rollover, không phải collector failure. Ghi trạng thái tại cutoff và cho collector tiếp tục quét.
- `COLLECTOR_FAILED` hoặc `BROWSER_FAILED`: lỗi thu thập kỹ thuật.
- `PARSE_OR_NORMALIZE_FAILED`: lỗi parser hoặc normalization.
- `QA_FAILED`: đã thu được dữ liệu nhưng không đủ chuẩn sử dụng.
- `COMMIT_FAILED`: dữ liệu đã xử lý nhưng chưa ghi thành công vào kho.
- `STALE`: snapshot vượt TTL.
- `UNKNOWN`: chưa đủ bằng chứng để xác định.

Trong mọi trạng thái không đạt, ghi:

- trạng thái hiện tại
- thành công gần nhất
- tuổi snapshot
- công đoạn lỗi
- số lần thử
- bằng chứng từ log, annotation hoặc artifact
- fallback đã dùng hay chưa
- hành động đề nghị

Không đoán nguyên nhân nếu log chưa chứng minh. Nếu D0 chưa đạt `REPORT_READY` tại cutoff 05:45 hoặc bản chiều chưa sẵn sàng tại 17:45, đánh dấu module hàng không `DEGRADED`, nhưng collector vẫn tiếp tục chạy và có thể phát hành bản cập nhật riêng khi hồi phục.

## Mẫu đầu ra

```text
HÀNG KHÔNG D0
Data state: REPORT_READY | Source date: YYYY-MM-DD | Collected: HH:MM ICT | Freshness: N phút
Evidence: DIRECT_NORMALIZED_QA_PASSED | QA: PASS | Schema: X.Y
Movements: Arrivals N | Departures N | Total N
Mix: Arrivals domestic/international N/N | Departures domestic/international N/N
Signals: [route mix, flight bank, delay/cancel nếu có]
Limits: flight movements không phải passenger count hoặc load factor.
```
