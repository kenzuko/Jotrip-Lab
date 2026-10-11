# LivingPQ R19 - Apollo Café · Walking Preview 24 giây

**[▶ XEM VIDEO 24 GIÂY (MP4, mở trên iPhone)](LIVINGPQ_R19_APOLLO_24S_WALKING_LIMITED_VISUAL_HOLD.mp4)**

[Link MP4 trực tiếp](https://raw.githubusercontent.com/kenzuko/Jotrip-Lab/livingpq-r19-apollo-walk-24s-20261011/LIVINGPQ_R19_APOLLO_24S_WALKING_LIMITED_VISUAL_HOLD.mp4)

## Kết quả đã kiểm chứng
- Quay từ **192 khung hình WebGL thật**, Microsoft Edge, PlayCanvas Gaussian Splat (.sog), 960×540, 8 FPS, video dài **24 giây**.
- Có trình điều khiển WASD và phím chạm, nút tự chạy 24 giây. Kiểm thử trên Windows: camera dịch chuyển và tour kết thúc đúng; không lỗi trang.
- Tổng quãng camera đi trong clip ≈ **1,99m**, giới hạn trong **vùng 1,04m ngang × 0,51m sâu**. Đây là mô phỏng điều khiển khuôn hình hẹp, **KHÔNG PHẢI 100m² đi bộ tự do**.
- R19 thử che người tĩnh trong ảnh nguồn bằng OpenCV inpaint và cập nhật màu cho **221.184 Gaussian** R17G. Cảnh có các mảng vỉa hè bị nhòe sau khi xóa người: **visual chưa đạt nghiệm thu**.
- Tất cả chi tiết bị khuất sau người là **dự đoán**, không phải ảnh/chụp thực địa. Splat này bắt nguồn từ **một ảnh**, không phải multiview reconstruction. Chưa có mesh va chạm thực.
- Nền ảnh thật Apollo Café: **Vivu Vietnam / Wikimedia Commons**, CC BY-SA 4.0. [Ảnh gốc](https://commons.wikimedia.org/wiki/File:Apollo_Cafe_daytime_street_view_Sunset_Town_Phu_Quoc_Vietnam.jpg) · [Giấy phép](https://creativecommons.org/licenses/by-sa/4.0/). Các thay đổi: inpaint, dùng Depth Anything V2 Small (Apache-2.0) để suy chiều sâu, Gaussian hóa, nén SOG, chụp WebGL và xuất H.264. Điều kiện CC BY-SA áp dụng cho tác phẩm phái sinh.

## So sánh với bản trước
- [Video R17G 12 giây (giữ nguyên người trong ảnh)](LIVINGPQ_APOLLO_R17G_WEBGL_MOTION_12_SECONDS.mp4)
- [Ảnh đối chiếu xử lý người R19](R19_PEOPLE_BEFORE_AFTER_REVIEW.jpg)

**Nhận xét:** R19 xác nhận luồng xóa người trước Gaussian và điều khiển camera, nhưng vết inpaint làm giảm chất lượng visual. Giữ R17G làm benchmark màu/chất ảnh; cần dữ liệu nhiều góc thật để đạt mục tiêu 100m².

Đây là nhánh GitHub công khai **chỉ chứa tư liệu nghiên cứu**, không chứa workflows, không merge, không deploy, không sửa OpenPQ Core V1.2, không API AI trả phí.
