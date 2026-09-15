REQUIRED_SECTIONS=["KẾT LUẬN ĐIỀU HÀNH","MẪU VÀ ĐỘ PHỦ","THAY ĐỔI SO VỚI TRƯỚC","BẰNG CHỨNG ĐÁNG CHÚ Ý","HÀNH TRÌNH RA QUYẾT ĐỊNH","GÓC NHÌN THEO THỊ TRƯỜNG VÀ NHÓM KHÁCH","NHỊP KHÁCH CAO CẤP","MỨC LAN CỦA CÁC NHẬN ĐỊNH LẶP LẠI","RADAR CẢNH BÁO SỚM","BẢNG GIÁ TRỊ ĐIỂM ĐẾN","HÀNH ĐỘNG JOTRIP","GIẢ THUYẾT CẦN KIỂM TRA","NGUỒN VÀ GIỚI HẠN"]
RADAR_FIELDS={"Trở ngại mới nổi","Nhu cầu mới nổi","Đối thủ mới nổi"}
def validate_report_payload(payload):
    errors=[]; sections=payload.get("sections",{}); missing=[s for s in REQUIRED_SECTIONS if s not in sections]
    if missing: errors.append("Thiếu mục: "+", ".join(missing))
    if not payload.get("cutoff_at"): errors.append("Thiếu thời điểm chốt dữ liệu")
    if set(payload.get("radar",{})) != RADAR_FIELDS: errors.append("Radar phải có đúng 3 trường bắt buộc")
    if payload.get("historical_comparison") and not payload.get("history_retrievable",False): errors.append("Không được so sánh lịch sử khi không truy xuất được dữ liệu lịch sử")
    return errors
