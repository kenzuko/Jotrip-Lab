# JoTrip Weather Lab MVP

Data Plane độc lập cho PHÚ QUỐC WEATHER & MARINE DECISION INTELLIGENCE.

## Trạng thái

- Có contract record và `LAB_SNAPSHOT_V1`.
- Có NO-NEWS NUMERICS allowlist.
- Có member completeness gate, quantile, exceedance probability.
- Có route aggregation loại land grid, current U/V và drift comparable-run gate.
- Có SQLite archive dùng local/CI. Production database chưa được kích hoạt.
- Có direct-source health probe miễn phí với failover ECMWF sang AWS/GCP và GEFS sang NOAA NODD AWS. Probe chỉ xác nhận endpoint, chưa đồng nghĩa đã tải và giải mã GRIB/NetCDF.
- Có live numeric smoke test tải GRIB thật và giải mã ECMWF, GEFS atmosphere, GEFS Wave và ICON. ICON chỉ đạt field-level cho đến khi ghép lưới tọa độ chính thức, nên chưa được dùng như point forecast.
- Copernicus Marine giữ `AUTH_REQUIRED` đến khi có tài khoản miễn phí do người dùng cấp.
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
