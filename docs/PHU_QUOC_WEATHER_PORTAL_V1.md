# PHÚ QUỐC WEATHER PORTAL - OBSERVATION + LOCAL ANALYSIS + ENSEMBLE V1

Cập nhật: 18/09/2026

## 1. Mục tiêu

Weather Lab được nâng từ dashboard model thành một hệ khí tượng chuyên biệt cho Phú Quốc.

Ba lớp bắt buộc phải tách rõ:

1. ACTUAL - số đo máy/trạm có timestamp và provenance.
2. PQ LOCAL NOW - ESTIMATED - phân tích địa phương được neo bằng observation, dùng khi không có trạm ngay tại điểm.
3. PQ ENSEMBLE LOCAL - FUTURE - ensemble tương lai, chỉ được hiệu chỉnh bằng lịch sử observation thật khi đủ mẫu.

Remote sensing như Himawari/radar là REMOTE OBSERVED, không phải trạm mặt đất.

## 2. Ground truth đã khóa

### VVPQ

- Production actual qua Aviation Weather Center METAR JSON.
- Dùng temperature, dewpoint, wind, pressure, visibility, present weather, cloud/CB/TCU.
- Không dùng METAR làm rain gauge tích lũy.

### VRain Phú Quốc

Production actual cho precipitation accumulation:
- Cửa Cạn - 10.292693, 103.914799
- Bãi Thơm - 10.411765, 104.031055
- An Thới - 10.018482, 104.014900

Weather Lab snapshot public feed mỗi 15 phút. Increment chỉ được tạo khi period_start không đổi, previous sample cùng station, delta không âm ngoài tolerance và khoảng cách sample <=120 phút.

### KT Hải văn Phú Quốc 60018

Deep probe đã bắt XHR thật, thử 6/24/72 giờ và tải official Excel 16-18/09/2026. Workbook có schema 10 phút nhưng observation cells đều rỗng, numeric observation cells = 0.

Status: FEED_EMPTY. Không dùng làm ACTUAL cho tới khi public feed có numeric trở lại.

### Rạch Giá 089907

Endpoint/export hoạt động nhưng numeric public observation hiện zero/rỗng. Không dùng để giả actual.

### An Thới 408

Station tồn tại trong mạng quốc gia, public machine-readable feed chưa tìm được. Status: FEED_UNRESOLVED.

## 3. PQ LOCAL NOW V1

Internal engine: PQ_LOCAL_NOW_V1

### Nhiệt độ

T_local = T_model_local + alpha_T * (T_vvpq_obs - T_model_anchor_proxy)

alpha_T = exp(-distance_to_VVPQ / 45 km) * freshness * source_quality

### Gió

Ưu tiên U/V residual khi pipeline có direction tại cả anchor và local point. Khi direction model chưa có, V1 chỉ scale tốc độ:

ratio = clamp(V_vvpq_obs / V_anchor_model, 0.35, 2.2)

V_local = V_model_local * [1 + alpha_W * (ratio - 1)]

alpha_W = exp(-distance_to_VVPQ / 38 km) * freshness * source_quality

Không truyền direction VVPQ thành direction local.

### Mưa

Mưa đối lưu không được nội suy như trường trơn.

Nếu có gauge increment fresh:

rate_i = increment_i / window_i
w_i = exp(-distance_i / 28 km) * freshness_i
gauge_rate = sum(w_i * rate_i) / sum(w_i)

PQ_rain_rate = 0.80 * gauge_rate + 0.20 * model_satellite_signal

Confidence giảm khi gauge gần nhất ở xa hoặc convection score cao.

Nếu chưa có gauge increment: dùng model + Himawari signal, confidence thấp.

### Biển

Cho tới khi có numeric 60018/phao usable, Hs/Hmax/period/current đều là MODEL_ONLY.

## 4. Field feedback

UI hỏi người dùng: Khớp, Mưa nhiều hơn, Mưa ít hơn, Gió mạnh hơn, Gió yếu hơn, Có dông.

Mỗi feedback giữ time, point_id, engine/version, estimate lúc feedback và category.

Feedback là FIELD_EVIDENCE, không phải numeric ground truth và không dùng trực tiếp để tính MAE/RMSE.

Hiện client lưu queue local. Nếu JOTRIP_WEATHER_FEEDBACK_ENDPOINT được cấu hình, client POST JSON sang collector trung tâm.

## 5. PQ ENSEMBLE LOCAL V1

Internal engine: PQ_ENSEMBLE_LOCAL_V1

Chỉ học từ observation_class = ACTUAL. Mặc định minimum matched samples = 30, shrink K = 30.

lambda = n / (n + K)

Khi n < 30: status = LEARNING, không sửa ensemble.

Smooth variables:
bias_raw = median(observed - forecast)
bias_applied = lambda * bias_raw
member_corrected = member_raw + bias_applied

Rain:
r = median[log((obs + eps)/(fcst + eps))]
factor = exp(lambda * r)
rain_member_corrected = max(0, rain_member_raw * factor)

Bắt buộc correct từng member trước rồi mới recompute q50/q90/q95/spread/exceedance.

## 6. Future ensemble transport

Ưu tiên NOAA GEFS official qua NOMADS GRIB Filter, cắt một hộp nhỏ quanh Phú Quốc trước khi download. Không dùng free Open-Meteo production vì free API không cấp commercial use.

## 7. Weather map

Không dùng RainViewer làm dependency hoặc embed chính.

Lớp visual độc lập:
- Windy Radar
- Windy wind
- Windy rain forecast
- JMA Himawari B13 direct image
- NCHMF radar official link

Map chỉ giúp nhìn spatial structure. Quyết định số học không phụ thuộc iframe.

## 8. Archive

Ground truth chạy mỗi 15 phút và lưu vào data-weather để tự xây time series calibration.

## 9. Semantic safety gates

- Không gọi PQ Local Now là actual.
- Không gọi Himawari score là station observation.
- Không gọi model wave là measured wave.
- Không train ensemble correction bằng ESTIMATED_NOW.
- Không dùng accumulated rain như instantaneous rate nếu chưa có increment.
- Không propagate airport wind direction thành local direction khi local U/V chưa có.
