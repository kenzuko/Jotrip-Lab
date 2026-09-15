# PHÚ QUỐC WEATHER & MARINE DECISION INTELLIGENCE

## MASTER LOCK V5.1 - LAB-FIRST, REALITY-FIRST, RESILIENT DIRECT-MODEL

Ngày khóa: 15/09/2026  
Thay thế: MASTER V5.0, V4.9 và các bản trước  
Múi giờ vận hành: UTC+7  
Lịch báo cáo: 06:00 và 18:00 hằng ngày  
Phạm vi: Phú Quốc, vùng biển lân cận, các điểm và tuyến vận hành JoTrip

## 1. MỤC TIÊU

Tạo báo cáo ra quyết định sát điều kiện JoTrip thực sự gặp tại điểm và trên tuyến. Hệ thống phải xác định:

- điều kiện có khả năng xảy ra nhất;
- cửa vận hành tốt nhất và cửa cần tránh;
- hazard tail còn đáng kể;
- trigger làm thay đổi quyết định;
- độ đầy đủ, ổn định và tin cậy của dữ liệu;
- xu hướng cải thiện hoặc xấu đi giữa các model run.

Không dự báo xấu nhất có thể. Không hạ chuẩn an toàn. Không biến thiếu dữ liệu thành thời tiết xấu.

## 2. LAB-FIRST EXECUTION LOCK

JoTrip-Lab là Data Plane. MASTER là Decision Plane.

JoTrip-Lab chịu trách nhiệm:

- direct ingest;
- run/member/grid/valid-time metadata;
- chuẩn hóa đơn vị và QC;
- point/route extraction;
- land/sea validation;
- model lineage;
- ensemble, quantile và exceedance probability;
- route metrics;
- forecast drift;
- archive và snapshot bất biến.

MASTER chịu trách nhiệm:

- xác thực snapshot;
- đọc số Lab, không tự sửa số;
- áp actual, local truth và official/operational gate;
- tách base state và hazard tail;
- chọn weather window;
- áp Product-Class Risk Envelope;
- ra quyết định và viết Human Report.

Đầu vào số production duy nhất là `LAB_SNAPSHOT_V1` hợp lệ. MASTER không tự lấy chart, screenshot, snippet hoặc số từ website dự báo để thay Lab.

## 3. SNAPSHOT PREFLIGHT

Trước báo cáo phải kiểm tra:

```text
snapshot_id
schema_version
cutoff_time
generated_at
payload_hash
data_mode
direct_ingest_status
git_commit_sha
formula_bundle_version
critical_data_gaps
```

Snapshot phải đúng schema, đúng hash, đúng cycle và chưa vượt `max_age_minutes` trong config. Dữ liệu đến sau cutoff tạo snapshot mới, không sửa ngầm snapshot đã phát.

Nếu snapshot unavailable, invalid hoặc stale:

```text
LAB DATA PLANE DEGRADED
MODE C
NUMERICAL MODEL LAYER UNAVAILABLE
```

Sau đó dùng official restriction, official local, VISHIPEL, raw actual và verified local truth. Không dùng news/SEO/aggregator thay numerical layer.

## 4. NO-NEWS NUMERICS

Báo chí, trang tin, trang SEO thời tiết, search snippet, repost, blog và forecast tiêu dùng không có model/run/grid provenance:

```text
NUMERIC_RISK_WEIGHT = 0
PROBABILITY_WEIGHT = 0
BLEND_WEIGHT = 0
```

Chúng chỉ dùng discovery/context. Nếu dẫn nguồn chính thức phải truy bản gốc. Không truy được bản gốc thì không đưa claim vào công thức.

Nguồn chính thức Việt Nam không phải nguồn yếu. VISHIPEL, bản tin An Thới và Cảng vụ vẫn có quyền cao trong đúng phạm vi, đúng thời hạn.

## 5. DATA MODE

MODE A - đủ direct atmosphere, direct marine, member-level ensemble, point/route extraction và lớp actual/official cần thiết. Cho phép q50/q90/q95, exceedance probability và P_operational_window khi coherence gate đạt.

MODE B - có đủ operational evidence nhưng thiếu một số lớp nâng cao. Cho phép deterministic range, model comparison, drift định tính/định lượng hợp lệ, weather window và quyết định có confidence penalty. Không tạo ensemble giả.

MODE C - Lab hỏng đáng kể. Dùng official/local/actual/operational evidence. Báo cáo vẫn hoàn thành nhưng không tạo số model giả.

## 6. MISSING TAXONOMY

Chỉ dùng các trạng thái:

```text
AVAILABLE
ACTIVE-VALID
STALE-BUT-VALID
FALLBACK-USABLE
RAW-NOT-PARSED
PARTIAL
NOT-YET-ISSUED
RETRIEVAL-FAILED
AUTH-REQUIRED
NOT-COMPUTABLE
REJECTED-QC
TRUE-MISSING
NOT-APPLICABLE
```

`TRUE-MISSING` chỉ dùng sau khi decision fallback thất bại. `NOT-COMPUTABLE` cho một phép tính không đồng nghĩa biến thời tiết đang missing. Freshness và validity phải tách riêng.

## 7. DECISION FALLBACK

```text
LAB DIRECT MODEL/API/RAW
-> OFFICIAL LOCAL/ROUTE
-> LATEST COMPLETED DIRECT MODEL RUN
-> DIRECT TECHNICAL ARCHIVE
-> OFFICIAL REGIONAL
-> QUALIFIED MODEL PLATFORM WITH LINEAGE
-> NOT-COMPUTABLE
```

Search fallback là nhánh discovery riêng, không được quay vào risk engine.

## 8. SPATIAL AUTHORITY

Khi chất lượng và thời gian tương đương:

```text
ACTUAL/VERIFIED LOCAL TRUTH
> OFFICIAL LOCAL/ROUTE BULLETIN
> POINT/ROUTE MODEL
> REGIONAL ENVELOPE
> SYNOPTIC BACKGROUND
```

Điểm bắt buộc:

- Dương Đông: 10.2172N, 103.9593E;
- An Thới: 10.0191N, 104.0150E;
- Gành Dầu: 10.3759N, khoảng 103.9000E.

Hòn Dăm, Vịnh Đầm, Hòn Thơm, Mây Rút, Gầm Ghì và route geometry chỉ được production-eligible sau khi xác minh GPS.

Regional hazard không được tự nâng local D0 risk nếu thiếu causal bridge. Causal bridge gồm route intersection, point concurrence, actual deterioration, local official warning hoặc restriction.

## 9. POINT VÀ ROUTE

Không lấy một point đại diện toàn tuyến. Sampling theo native grid, turning point, hướng phơi nhiễm, bathymetric transition và known hazard zone. Không nội suy chi tiết giả hơn native resolution.

Mỗi sample lưu requested coordinate, sampled coordinate, grid resolution, displacement, sea/land status và QC.

Marine grid trên đất:

```text
REJECTED-LAND-GRID
```

Sau đó tìm sea grid hợp lệ trong displacement limit của model.

Route output tối thiểu:

```text
ROUTE TYPICAL
ROUTE MAX
ROUTE UPPER PERCENTILE
WORST SEGMENT
EXPOSURE DURATION
WAVE ANGLE
```

## 10. DIRECT-MODEL COMPLETENESS GATE

Trước khi dùng các từ ensemble, q50, q90, q95, probability, calibrated blend, consensus hoặc disagreement, phải có:

```text
source/model/system
run
member
valid time
grid
variable
completion
lineage
```

Không đạt gate thì `NOT-COMPUTABLE`. Windy và technical viewer có underlying model rõ chỉ là cross-check, không thay direct ingest và không được double-count với model gốc.

Các family như GFS deterministic, GEFS control, GEFS mean và GEFS members không phải các model độc lập. Blend ở system level trước, sau đó mới cross-center.

### 10.1 NUMERICAL READINESS GATE

Không dùng HTTP 200 làm bằng chứng data-ready. Mỗi nguồn đi qua các mức:

```text
ENDPOINT-REACHABLE
-> OBJECT-RETRIEVED
-> FIELD-DECODED
-> POINT/ROUTE-EXTRACTED
-> MEMBER-COMPLETE
-> DECISION-ELIGIBLE
```

Chỉ `POINT/ROUTE-EXTRACTED` mới được đưa số điểm/tuyến vào snapshot. Chỉ `MEMBER-COMPLETE` mới được tính ensemble probability. GRIB tải được nhưng chưa giải mã là `RAW-NOT-PARSED`. Trường ICON giải mã được nhưng chưa ghép tọa độ lưới phi cấu trúc là `FIELD-NUMERIC-READY / POINT-NOT-COMPUTABLE`.

### 10.2 SOURCE FAILOVER LOCK

Failover chỉ dùng hạ tầng chính thức hoặc mirror do chính bên phát hành công bố:

```text
ECMWF: ECMWF Open Data -> AWS -> Google
GEFS/GEFS Wave: NOAA NOMADS -> NOAA NODD AWS
ICON: DWD Open Data -> latest active-valid DWD run trong archive
Copernicus: official Toolbox/API -> latest active-valid Lab subset
```

Mỗi attempt lưu endpoint, thời gian, HTTP/error class, retry count và fallback level. Dùng exponential backoff có jitter, timeout riêng cho connect/read, circuit breaker và giới hạn tổng thời gian theo cycle.

Không được dùng GEFS để giả là ECMWF fallback hoặc ngược lại. Nếu một family hỏng, giữ family khác là bằng chứng độc lập, giảm completeness và ghi gap. Nếu live run hỏng, chỉ được dùng latest completed run cùng family còn trong age limit cấu hình; không kéo valid time sang ngày khác.

Source health và numeric readiness là hai lớp riêng. Production report không được nhận source là healthy nếu live smoke chỉ mở được directory nhưng không tải và giải mã được field.

### 10.3 CURRENT VERIFIED ACCESS STATE

Kiểm thử ngoài môi trường proxy ngày 15/09/2026 đã xác nhận:

```text
ECMWF 10u: direct retrieve + GRIB decode + Phú Quốc point PASS
GEFS control 10u: indexed byte-range + decode + Phú Quốc point PASS
GEFS Wave Hs: indexed byte-range + decode + Phú Quốc point PASS
ICON 10u: direct BZ2/GRIB decode PASS; point extraction PENDING grid join
Copernicus Marine: AUTH-REQUIRED, không tự kích hoạt
```

Đây là smoke evidence, chưa phải bằng chứng đủ 72h variables/members. MODE A chỉ bật sau khi collector đầy đủ biến, lead, member và route gate đạt.

## 11. ENSEMBLE VÀ CALIBRATION

Mỗi system khai báo expected members và minimum completion ratio trong config.

Nguyên tắc ban đầu:

```text
>= 90%: ELIGIBLE
75-89%: PARTIAL-ENSEMBLE + confidence penalty
< 75%: NOT-ELIGIBLE
```

Chưa đủ mẫu calibration thì không bias-correct và không gọi calibrated blend. Hiển thị từng model family, consensus range, most likely range và disagreement.

Historical bias/adaptive weight chỉ bật khi đủ minimum sample cho cùng model family, point/route, lead bucket và regime.

## 12. FORECAST DRIFT VÀ PUSHBACK

Chỉ so các run có cùng model/system, variable, point/route, valid window và extraction method.

Tính:

```text
ONSET_DRIFT_HOURS
PEAK_DRIFT_HOURS
AMPLITUDE_DRIFT
PROBABILITY_DRIFT
OPERATIONAL_WINDOW_DRIFT
```

Risk-First phải ghi trend `IMPROVING`, `STABLE`, `DETERIORATING` hoặc `HIGH-VOLATILITY`, cùng thay đổi từ báo cáo trước. Forecast cũ không được đè forecast mới đã cải thiện liên tiếp.

NCHMF forecast xa ngày là background warning một dòng, không phải nền số chính cho D2-D14. Đánh giá xa ngày ưu tiên ensemble/model quốc tế đã duyệt và direct ingest. NCHMF D0/current bulletin vẫn dùng đúng phạm vi và validity.

## 13. REALITY-FIRST

Mỗi operational window bắt buộc tách:

```text
BASE STATE
MOST LIKELY
HAZARD TAIL
TRIGGER
```

Hazard tail không phải base state. Có dông cục bộ không đồng nghĩa biển xấu cả buổi.

Nếu official local tốt, actual/local truth tốt, không restriction và không có route-intersecting convection, Reality Correction được quyền giảm D0 risk một mức hoặc đổi `HOLD-WATCH -> GO WITH WATCH`, tùy product envelope.

Benchmark bắt buộc 14/09/2026 tại An Thới:

```text
gió 3-4
Hs 0.50-1.25 m
biển bình thường
gust hazard trong dông
```

Engine không được biến case này thành biển xấu cả ngày.

## 14. WEATHER WINDOW

`WINDOW > DAILY LABEL` với tour có giờ vận hành xác định.

Không quyết định bằng daily rainfall, daily PoP, daily max wind hoặc daily max Hs riêng lẻ. Phải tìm `BEST WINDOW`, `MARGINAL WINDOW`, `AVOID WINDOW` theo độ phân giải gốc.

Mưa bắt buộc tách:

```text
DAILY RAIN TOTAL
MAX 1H/3H RAIN
OPERATIONAL-WINDOW RAIN
PoP
CONVECTIVE RAIN RISK
ROUTE INTERSECTION
EXPECTED INTERRUPTION DURATION
```

D0 0-6h ưu tiên radar/lightning/satellite, METAR/SPECI, short-range model và local truth. Thiếu radar vẫn chạy degradation path; không tự kết luận convection unknown nếu evidence khác đồng thuận.

## 15. MARINE RISK

Không dùng Hs đơn độc. Đọc tối thiểu Hs, wave direction, mean/peak period, wind-wave/swell khi có, route heading và vessel class.

Current phân loại:

```text
OBSERVED CURRENT
MODEL POINT CURRENT
MODEL REGIONAL CURRENT
QUALITATIVE PROXY
NOT AVAILABLE
```

Không suy current từ tide hoặc wind. Model current phải lưu U, V, speed, direction-toward, depth, valid time và source/run.

Ngưỡng vận hành không được quy định cứng chỉ bằng Beaufort. Theo thực tế JoTrip, cấp 4 thường vẫn vận hành; cano bắt đầu tăng rủi ro từ cấp 5 tùy gust, Hs, period, direction, convection và tuyến; tàu/phà thường chịu được mức cao hơn và cần envelope riêng. Official restriction luôn có quyền ưu tiên.

## 16. PRODUCT MINIMUM DATASET

Cano Nam đảo: restriction, wind/gust, Hs, convection indication, visibility. Current Hòn Dăm không critical.

Fishing Hòn Dăm: wind/gust, Hs/period, convection, visibility, tide; current là supporting hoặc critical tùy mục tiêu câu đã cấu hình.

Tàu cao tốc: official operating status, wind, Hs, visibility, severe convection.

Phà: envelope riêng, không dùng envelope tàu cao tốc hoặc cano.

Tour bờ: rain timing, PoP, convective intensity, visibility; marine current là N/A.

Critical Missing xác định theo `hazard x product x time window`, không xác định chung toàn hệ thống.

## 17. QUALITY, CONFIDENCE VÀ RISK

```text
data thiếu -> confidence giảm
hazard evidence -> risk
```

Chỉ chuyển HOLD-WATCH vì uncertainty khi thiếu critical safety variable đến mức không chứng minh được nằm trong operating envelope.

Completeness dùng product weight từ config:

```text
sum(required_weight x availability_score)
/ sum(required_weight) x 100
```

Confidence phải hiển thị Data Quality, Source Agreement, Temporal Stability, Spatial Relevance, Nowcast Support và Final Confidence. Không tự nghĩ trọng số trong lúc viết report.

## 18. RISK-FIRST OUTPUT

### A. 60-SECOND OPERATIONAL BOARD

1. Hazard chính.
2. Decision theo từng product.
3. Base State.
4. Best Window.
5. Avoid Window.
6. Restriction/operating status.
7. Forecast Trend và thay đổi từ cycle trước.
8. Critical Missing.
9. Trigger to Hold/Modify/Cancel.
10. Next Review.

### B. QUANTITATIVE BOARD

Bắt buộc có bảng mưa, PoP, gió nền, gust, Hs, hướng, chu kỳ, visibility, TS/CB, tide/current theo giờ hoặc đúng resolution gốc cho D0 và D+1. Sau đó có D+2 và D+3 theo range/spread, không tạo false precision.

D4-D7 chỉ planning outlook theo regime, spread, hazard window và confidence. D8-D14 chỉ dùng model/ensemble có horizon thật; không dùng forecast aggregator. Không đưa GO/HOLD cứng cho D4-D14.

## 19. DECISION

Các trạng thái:

```text
GO
GO WITH WATCH
MODIFY
HOLD-WATCH
CANCEL
```

Risk color và decision tách riêng. CANCEL không được tạo từ một deterministic model, một regional envelope hoặc daily icon. Official restriction/closure có thể override theo đúng route/product/thời hạn.

## 20. HUMAN REPORT VÀ MACHINE AUDIT

Human Report chỉ trình bày decision, numbers, windows, trend, confidence, important gaps và trigger.

Machine Audit lưu source, run, member, grid, variable, QC, lineage, input record IDs, formula ID/version, transformation, fallback, code/config commit và decision trace.

MASTER không sửa số Lab vì cảm giác an toàn, không blend thêm website và không tự nhân uncertainty ngoài config versioned.

## 21. LỊCH CHẠY

Không đợi đúng giờ báo cáo mới ingest.

Cycle sáng UTC+7:

```text
04:30-05:30 refresh direct/official/actual
05:30-05:45 QC + point/route + ensemble + drift
05:45 model cutoff
05:55 operational cutoff
05:57 freeze final snapshot
06:00 MASTER report
```

Cycle 18:00 áp dụng tương tự từ 16:30. Scheduler phải có manual dispatch, retry, heartbeat, missed-cycle alert và idempotency lock. Trễ scheduler không được silent.

## 22. REPORT HEADER BẮT BUỘC

```text
Snapshot ID:
Data Mode:
Cutoff:
Generated:
Direct Ingest Status:
Completeness:
Stability:
Confidence:
Critical Data Gaps:
Report Status: FULL / DEGRADED
```

## 23. KHÓA CUỐI

```text
KHÔNG BỊA.
KHÔNG NỘI SUY GIẢ.
KHÔNG TẠO XÁC SUẤT GIẢ.
KHÔNG DÙNG NEWS/SEO/AGGREGATOR LÀM SỐ.
KHÔNG DÙNG REGIONAL ENVELOPE THAY POINT/ROUTE.
KHÔNG BIẾN DATA GAP THÀNH WEATHER RISK.
KHÔNG BIẾN HAZARD TAIL THÀNH BASE STATE.
KHÔNG ĐỂ FORECAST CŨ ĐÈ REALITY MỚI.
KHÔNG CANCEL TỪ MỘT MODEL.

LAB TẠO DỮ LIỆU.
MASTER RA QUYẾT ĐỊNH.
WINDOW > DAILY LABEL.
LOCAL/ROUTE > REGIONAL KHI CHẤT LƯỢNG VÀ THỜI GIAN CHO PHÉP.
ACTUAL > FORECAST TRONG ĐÚNG KHÔNG GIAN VÀ THỜI HẠN.
```
