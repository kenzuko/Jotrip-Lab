# Sun Airport collector

Thu thập bảng chuyến bay Cảng HKQT Phú Quốc bằng Playwright và GitHub Actions.

- Quét theo cửa sổ buổi sáng và buổi chiều, không xem 05:45 là điểm dừng collector.
- Chuỗi xử lý bắt buộc: collect -> normalize codeshare -> QA -> publish.
- Chỉ cập nhật `latest.json` khi dữ liệu đạt `REPORT_READY`.
- Ghi sức khỏe lần chạy tại `data/sunairport/health.json`.
- Khi lỗi, workflow lưu HTML, screenshot, raw records, candidate và health thành artifact.
- Không sử dụng API key hoặc dịch vụ thu thập trả phí.
- Số liệu là số movement vật lý quan sát trên bảng chuyến bay, không phải số hành khách.
- `0V8074/VN8074` được chuẩn hóa thành một movement, trong đó `0V8074` là chuyến khai thác và `VN8074` là mã chia sẻ.

Kiểm thử:

```bash
npm test
```
