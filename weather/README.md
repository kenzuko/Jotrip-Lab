# JoTrip Weather Lab MVP

Data Plane độc lập cho PHÚ QUỐC WEATHER & MARINE DECISION INTELLIGENCE, theo MASTER V5.3.

## Trạng thái

- Có contract record và `LAB_SNAPSHOT_V1`.
- Có NO-NEWS NUMERICS allowlist.
- Có member completeness gate, quantile, exceedance probability.
- Có route aggregation loại land grid, current U/V và drift comparable-run gate.
- Có SQLite archive dùng local/CI. Production database chưa được kích hoạt.
- Có direct-source health probe miễn phí với failover ECMWF sang AWS/GCP và GEFS sang NOAA NODD AWS. Probe chỉ xác nhận endpoint, chưa đồng nghĩa đã tải và giải mã GRIB/NetCDF.
- Có live numeric smoke test tải và giải mã ECMWF, GEFS atmosphere và GEFS Wave.
- ECMWF IFS/Wave đã chạy D0-D3 tại 25 bước 3 giờ cho Dương Đông, An Thới và Gành Dầu.
- ICON dùng gói trọng số DWD chính thức, remap sang grid 0,25 độ và đã trích point Phú Quốc.
- GEFS/GEFS Wave đã qua completeness gate 31/31 member tại lead +3h cho 10u và Hs. Toàn bộ matrix biến x lead 0-72h chưa được chứng minh, nên chưa bật P_operational_window.
- Copernicus Marine Wave/Current đã xác thực, tải subset NetCDF quanh Phú Quốc và trích ba point thành công.
- Route Nam đảo trong config là test-only đến khi JoTrip xác minh GPS track.

## Chạy kiểm thử

```bash
python -m unittest discover -s weather/tests -v
```

## Tạo snapshot offline

```bash
python -m weather.pipeline.build_snapshot \
  --input weather/tests/fixtures/an_thoi_2026_09_14.json \
  --output data/weather/snapshots/an_thoi_2026_09_14.json \
  --cutoff 2026-09-14T22:45:00Z \
  --offline
```

## Live health probe

```bash
python -m weather.collectors.probe
```

Không có dịch vụ trả phí nào được tự động đăng ký hoặc kích hoạt.

## Copernicus Marine

Đăng ký tài khoản miễn phí tại https://data.marine.copernicus.eu/register, sau đó thêm GitHub Actions Secrets/Variables:

```text
COPERNICUSMARINE_SERVICE_USERNAME
COPERNICUSMARINE_SERVICE_PASSWORD
COPERNICUS_WAVE_DATASET_ID
COPERNICUS_CURRENT_DATASET_ID
```

Dataset ID phải lấy từ catalogue chính thức tại thời điểm cấu hình, không hard-code theo trí nhớ. Không commit credential vào repository.
