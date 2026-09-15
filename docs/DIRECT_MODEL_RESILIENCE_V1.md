# DIRECT MODEL RESILIENCE V1

Ngày kiểm thử: 15/09/2026

## Kết luận

Timeout quan sát trong Codex runtime là lỗi proxy của môi trường thử, không phải ECMWF, NOAA hoặc DWD ngừng phát dữ liệu. GitHub Actions đã xác nhận cả bốn endpoint credential-free đều reachable và tải/giải mã được field thật.

## Bằng chứng live

| Nguồn | Run/field đã thử | Kết quả |
|---|---|---|
| ECMWF Open Data | IFS 18Z, 10u, step 0 | Giải mã point 10.00N 104.00E, PASS |
| NOAA GEFS | control 00Z, 10u, f003 | Byte-range từ index, giải mã point, PASS |
| NOAA GEFS Wave | control 00Z, Hs, f003 | Byte-range từ index, giải mã point, PASS |
| DWD ICON | 00Z, 10u, step 0m | BZ2 + GRIB decode, PASS field-level |
| Copernicus Marine | Wave/current | AUTH-REQUIRED |

ICON chưa được point-eligible vì GRIB dùng `unstructured_grid`. Cần ghép cell index với grid-coordinate chính thức hoặc remap bằng bộ weight chính thức của DWD. Không tải grid 938 MB ở mỗi cycle. Grid/remap asset phải cache theo version và kiểm checksum.

## Failover được duyệt

- ECMWF: server chính -> AWS mirror -> Google mirror.
- GEFS và GEFS Wave: NOMADS -> NOAA NODD S3.
- ICON: DWD live -> run DWD gần nhất còn active-valid trong archive.
- Copernicus: official Toolbox/API -> subset archive còn active-valid.

Không thay một model family bằng family khác dưới cùng tên. Không dùng Windy, news hoặc aggregator làm numeric fallback.

## Kiểm soát vận hành

1. Probe directory/endpoint.
2. Discover latest completed run.
3. Tải index hoặc object nhỏ nhất chứa biến cần dùng.
4. Kiểm GRIB framing và checksum.
5. Decode metadata, valid time, unit và numeric range.
6. Extract point/route đúng grid.
7. Kiểm member completion.
8. Chỉ sau đó đặt `DECISION-ELIGIBLE`.

## Nguồn kỹ thuật chính thức

- ECMWF Open Data client: https://github.com/ecmwf/ecmwf-opendata
- NOAA GEFS Registry: https://registry.opendata.aws/noaa-gefs/
- NOAA GEFS AWS layout: https://github.com/awslabs/open-data-docs/tree/main/docs/noaa/noaa-gefs-pds
- DWD ICON Open Data: https://opendata.dwd.de/weather/nwp/icon/grib/
- DWD ICON remap/grid assets: https://opendata.dwd.de/weather/lib/cdo/
- Copernicus Marine subset API: https://help.marine.copernicus.eu/en/articles/8283072-copernicus-marine-toolbox-api-subset
