# Phú Quốc Inbound Intelligence V1.1 - Lab

Lớp thử nghiệm cho MASTER LOCK 06:00. Mục tiêu: đưa trí nhớ bằng chứng, nhận diện case, sổ tín hiệu, phản chứng, sổ độ phủ và so sánh lịch sử ra khỏi phần viết báo cáo.

## Luồng
Collector -> Raw Evidence -> Dedup -> Case Resolver -> Observation Coding -> Signal Engine -> Historical Comparison -> Report Generator -> Run Archive

Report Generator không tự tìm dữ liệu.

## Lịch chuẩn
- 05:20 bắt đầu collector
- 05:45 chốt dữ liệu
- 05:50 bắt đầu tổng hợp
- 06:00 mục tiêu xuất báo cáo

## Nguyên tắc V1.1
- Một traveller/thread giữ cùng `case_id` qua nhiều ngày.
- Lỗi collector không được diễn giải thành không có tín hiệu.
- Tín hiệu lưu cả bằng chứng ủng hộ và phản chứng.
- 5 case cùng một họ nguồn không đủ để nâng thành `ĐÃ CÓ CƠ SỞ`.
- So sánh D-1/D-7/14d/30d chỉ được phép khi record lịch sử thật có thể truy xuất.
- Rổ truy vấn gồm 70-80% truy vấn cố định và 20-30% truy vấn khám phá.

## Kiểm thử
```bash
python -m unittest discover -s inbound_intelligence/tests -v
```

Không có dependency ngoài Python standard library.
