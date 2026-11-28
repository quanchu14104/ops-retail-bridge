# Kịch bản trình diễn (khoảng 12 phút)

Hệ thống vận hành cho cửa hàng **Thanh Lam Mart** với **164 mặt hàng tươi chủ lực**, 7 nhà cung cấp và **90 ngày dữ liệu bán hàng lịch sử** (28/03–25/06/2024). Ngày nghiệp vụ hiện tại của hệ thống là **26/06/2024** (xem thêm cấu trúc dữ liệu và mô hình tại [du-bao-ml.md](du-bao-ml.md), mục 4).

## Chuẩn bị

1. Điền `.env` (khóa LLM), rồi chạy lệnh dưới. Lần đầu, backend tự nạp 90 ngày dữ liệu lịch sử Thanh Lam Mart, mất khoảng 10 giây.

   ```bash
   docker compose up -d --build
   ```

2. Mở http://localhost:5173 và đăng nhập tài khoản Store Manager trong `.env.example`.
3. Mở thêm tab http://localhost:8025 (Mailpit).
4. Muốn nạp lại trạng thái ban đầu của dữ liệu (sau khi tiến ngày nghiệp vụ), dùng lệnh:

   ```bash
   docker compose exec backend python -m app.sim.seed --reset
   ```

5. Nếu cấu hình `CATALOG_OVERRIDES_PATH` (khi chạy đồng bộ cùng kiosk Retail-AI qua `bridge/`), tên hàng và giá bán lấy đầy đủ từ bảng ánh xạ danh mục **Thanh Lam Mart**, tên nhà cung cấp hiển thị theo dạng `"Nhà cung cấp Thanh Lam Mart – …"`.

## 1. Buổi sáng của Store Manager (2 phút)

- Trang chủ **Trợ lý** hiện **bản tin đầu ngày**, chia ba nhóm *Cần quyết*, *Cần để ý*, *Việc trong ngày*: đề xuất chờ duyệt, lô cận date, nhà cung cấp đến lịch đặt, đơn đang chờ giao, hàng hết… Nhấn mạnh: bản tin dựng trực tiếp từ dữ liệu thực tế trong DB, **không qua LLM**, nên không thể bịa số.
- Bấm một dòng của bản tin, ví dụ *lô cận date*: việc đó mở trong popup (không qua LLM). Thẻ lô cận date cho tick chọn lô rồi bấm Giảm giá / Trả NCC / Ghi hủy để tạo đề xuất. Nút bong bóng chat ở cuối dòng thì hỏi Ops Chest về mục đó.
- Bấm nút **Công việc** cạnh ô chat: lưới việc của ca (Chờ duyệt, Cận date, Rút kệ, Kiểm date, Kiểm kê, Nhận hàng, Trả NCC, Hàng hết, KPI) kèm số đếm. Đây là cách làm việc hằng ngày, không cần vào các trang trong nhóm *Tra cứu*.
- Trong menu **Công việc**, bấm **Quét đề xuất** (chỉ Store Manager thấy; ô **Quét giảm giá** cạnh đó chạy việc của job 17:00). Đây là việc job 06:30 làm mỗi sáng: đề xuất đặt hàng cho nhà cung cấp đến lịch, giảm giá hàng cận date, ghi hủy hàng quá hạn.
- Nhấn mạnh: **chưa có gì được gửi đi.**
- Nếu hỏi về dòng "… mặt hàng đang hết hàng" (con số lớn): đây là tồn **buổi sáng trước khi nhận hàng**. Hàng tươi HSD 1–2 ngày bán gần hết trong ngày, và hàng mới đang trên đường giao (dòng "đơn hàng đang chờ giao"). Lịch sử 90 ngày ban đầu được vận hành theo chính sách kinh nghiệm thủ công, nên có nhiều mặt hàng tươi hết hàng vào cuối ngày.

## 2. Dự báo bằng mô hình học máy (2 phút)

- Mở một đề xuất **Đặt hàng** của một nhà cung cấp hàng tươi. Các dòng có nhãn **LightGBM**: dự báo do mô hình học máy huấn luyện trên chuỗi dữ liệu lịch sử bán hàng tính ra, kết hợp với engine EWMA.
- Nhấn mạnh hai điều:
  - **Mô hình chỉ dự báo, không quyết định.** Số lượng đặt vẫn do engine tất định tính, với trần HSD, sức chứa và sàn mức phục vụ (nhãn *trần HSD*, *giữ ≥95%*). Mô hình không thể đề xuất vượt các giới hạn này (có test kiểm).
  - **Mô hình được chọn theo lãi, không chỉ theo độ chính xác.** Bộ chọn (`decision_gate.json`) học từ kiểm chứng hồi cứu A/B hai việc:
    - nhóm hàng × quy mô danh mục nào dùng LightGBM;
    - độ bất định nào dùng để đặt hàng.
  - Tại Thanh Lam Mart, **127/164 mặt hàng** (bán chạy và bán vừa) dùng **dự báo điểm của LightGBM**, nhưng tồn an toàn tính theo **σ của engine EWMA**. Lý do: khoảng dự báo của LightGBM rộng hơn, đi qua sàn mức phục vụ 90–95% thì thành đặt dư. 37 mặt hàng bán ít giữ engine EWMA, vì ở nhóm này LightGBM không lãi hơn.
- Vào **Menu tài khoản (góc phải trên) → Cài đặt → Báo cáo mô hình** (`/model`):
  - bảng 5 phương pháp: LightGBM WAPE 30,2% so với EWMA 35,1%, độ phủ khoảng 80% là 81% so với 73%;
  - bảng theo nhóm hàng, có nhãn "Dùng ML" / "Giữ engine cũ" theo sai số dự báo. Đây là bộ chọn cũ; app nay chọn theo lãi (mục 7);
  - kiểm tra khôi phục nhu cầu ngày hết hàng (sai số 20,5% so với 32,3% nếu coi số bán là nhu cầu).
- Nói thẳng kết quả âm: **dữ liệu lịch sử khuyến mãi không cho ước lượng tin cậy độ co giãn khi giảm giá** (ra con số phi lý e ≈ 9,6 vì giá khuyến mãi nội sinh theo nhu cầu), nên OC giữ giả định bảo thủ 3,0. Bảng ước lượng có trên trang để hội đồng thấy.

## 3. Hộp duyệt: HITL (2 phút)

- Mở **Hộp duyệt** (ngăn kéo bên phải: bấm nút Hộp duyệt ở thanh trên, hoặc nói *"cho tôi xem các đề xuất chờ duyệt"* để agent mở thẻ hộp duyệt ngay trong chat).
- Trong thẻ đặt hàng: cột *Dự báo phủ*, *Đề xuất*, phân loại mức bán (Chủ lực / Bán vừa / Bán chậm) của từng dòng. Đơn dài mặc định lọc còn các dòng cần chú ý (bộ lọc *Cần xem / Đã sửa / Tất cả*, kèm ô tìm SKU).
- **Sửa bằng lời:** nói với agent *"giảm mỗi món còn một nửa"* hoặc *"đặt thêm 50 <tên hàng>"*, hoặc bấm **Hỏi lại** trên thẻ. Agent tạo đề xuất **mới** chờ duyệt, bản cũ chuyển sang "Đã có bản sửa". Agent không tự duyệt.
- **Sửa bằng tay:** đổi số lượng một dòng bằng nút +/− (dòng được tô vàng, tổng tiền ở đầu thẻ cập nhật theo), rồi bấm **Duyệt (đã sửa)** trên thanh duyệt ở cuối thẻ. Sang Mailpit xem email đơn hàng kèm **PDF** (font tiếng Việt), ghi rõ người duyệt.
- Thẻ giảm giá: kéo thanh trượt mức giảm. Nếu mức đó thu về ít hơn giữ giá, thẻ cảnh báo và phải bấm duyệt hai lần. Từ chối thì chọn lý do bằng chip.
- Mở **Tra cứu → Nhật ký**: các bước tạo → sửa → duyệt → thực thi, mỗi bước có người làm và thời điểm.
- Đăng nhập tài khoản **nhân viên**: bản tin ghi đề xuất "đang chờ Store Manager duyệt" ở dạng thông tin; thẻ đề xuất không có nút duyệt, menu Công việc không có Quét đề xuất; gọi API duyệt nhận lỗi 403.

## 4. Trò chuyện với Ops Chest (2 phút)

Hỏi lần lượt:
- *"Tổng quan tồn kho hiện giờ"*: thẻ KPI và bảng theo nhóm hàng hiện trong chat.
- *"Món nào đang hết?"*: bảng tên các mặt hàng đang hết, bán chạy 28 ngày qua lên trước.
- *"Hôm nay nên đặt gì?"*: agent liệt kê mọi đơn đặt hàng đang chờ duyệt (NCC, số mặt hàng, tổng tiền) trước, chỉ tạo đơn cho NCC đến lịch mà chưa có đơn.
- *"Soạn tờ trình đặt thêm 50 <tên hàng>"*: agent không viết thư; nó sửa đơn chờ duyệt của NCC đó (hoặc tạo đơn mới) thành một đề xuất thật để duyệt.
- *"Vẽ biểu đồ nhập/xuất kho Nhóm tươi 6 30 ngày qua theo tuần"*: biểu đồ hiện ngay trong khung chat.
- *"Có mặt hàng nào nên ngừng nhập không?"*: agent đưa ra các mặt hàng bán chậm, hủy nhiều (nhóm C-Y/C-Z, tỷ lệ hủy cao).
- *"Ngừng nhập <mặt hàng bán chạy nhất> đi"*: với mặt hàng kéo khách (thuộc 5 mặt hàng bán nhiều nhất của Thanh Lam Mart), `propose_delist` **không tạo đề xuất**. Chặn bằng code, không phụ thuộc LLM.
- *"Duyệt luôn đơn hàng và gửi email giúp tôi"*: agent chỉ tạo đề xuất và giải thích quyết định thuộc về Store Manager.

**Mẹo khi LLM chậm hoặc lỗi:** bản tin, menu **Công việc** và gợi ý nhanh có đường dự phòng không cần LLM. Lỗi của dịch vụ AI hiện thành một câu tiếng Việt dễ hiểu, không lộ thông báo của provider.

## 5. Nhận hàng, rút kệ, kiểm date (2 phút)

- Nói trong chat *"Có đơn nào đang chờ giao không?"*: agent mở thẻ đơn chờ giao, bấm nhận hàng hoặc huỷ đơn ngay trên thẻ. *"Nhận đơn PO-…"* thì agent **chỉ mở form**; nhân viên điền số thực nhận và HSD rồi tự bấm xác nhận.
- Trang **Tra cứu → Đặt & nhận hàng**: form đầy đủ (tách dòng thành nhiều HSD, số từ chối kèm lý do, giá hóa đơn, ô ngày dd/mm/yyyy). HSD còn dưới 2/3 vòng đời thì tài khoản nhân viên bị chặn.
- **Công việc → Rút kệ** (hoặc trang *Hàng cận date → Rút kệ cuối ngày*): ghi số thực gỡ rồi xác nhận (không cần duyệt). Store Manager chỉ duyệt bút toán ghi hủy.
- Giờ giảm giá cuối ngày lấy theo **khung giờ bán thực tế của từng nhóm hàng trong dữ liệu Thanh Lam Mart**: nhóm bán đỉnh buổi sáng giảm từ 11h, nhóm bán đỉnh buổi tối giảm từ 18h.

## 6. Tua ngày nghiệp vụ và giả thuyết (1 phút, tùy chọn)

- Nói *"Thứ Bảy này nhóm tươi 6 bán gấp rưỡi"* (nêu rõ ngày), rồi duyệt đề xuất giả thuyết.
- **Menu tài khoản (góc phải trên) → Cài đặt → Tua ngày nghiệp vụ**: tiến được tối đa **7 ngày** (hết chuỗi dữ liệu lịch sử Thanh Lam Mart sau 02/07/2024; tiến quá sẽ báo lỗi rõ ràng). Nhu cầu trong 7 ngày này là dữ liệu thực tế giai đoạn đánh giá mà mô hình chưa từng thấy.
- Tua ngày **không tự duyệt**: không ai duyệt đơn thì kệ trống dần, lô đã rút kệ nằm chờ ghi hủy.

## 7. Chứng minh hiệu quả (1 phút)

Vào **Menu tài khoản → Cài đặt → Báo cáo mô hình** (`/model`), kéo xuống phần **Kiểm chứng hồi cứu A/B trên dữ liệu Thanh Lam Mart**. Các chính sách chạy trên **cùng nhu cầu lịch sử** của 50 tập kiểm chứng giữ lại, trong 37 ngày mà mô hình kiểm chứng chưa từng thấy:
- **A:** làm theo kinh nghiệm, có giờ vàng;
- **B-EWMA:** Ops Chest với engine EWMA;
- **B-ML:** Ops Chest với LightGBM (bộ chọn cũ, theo sai số dự báo);
- **B-gate:** Ops Chest với bộ chọn theo lãi, chọn ngoài mẫu (kiểm chéo 2 lần). Kèm các biến thể để giải thích: LightGBM với phân phối lệch q10/q50/q90, và LightGBM với σ của EWMA ở mọi mặt hàng.

Đọc trung vị và khoảng tứ phân vị qua 50 tập kiểm chứng, tỷ lệ số tập B tốt hơn A, và bảng độ nhạy (khách phản ứng yếu hơn, Store Manager chỉ duyệt 60–80%, tắt sàn mức phục vụ…). Nói rõ: nhu cầu là lịch sử thực tế, còn một số tham số vận hành (chiết khấu, HSD chuẩn hóa, phản ứng giảm giá) được cấu hình theo quy chuẩn nghiệp vụ.

Nói thẳng kết quả ([du-bao-ml.md](du-bao-ml.md), mục 5.6–5.7):
- Ops Chest lãi hơn cách làm theo kinh nghiệm khoảng **+4,9%** (trung vị với `B-gate`) và giảm hết hàng; với hàng kéo khách, hết hàng giảm từ 8,7% xuống 3,4% (và 2,7% ở `B-ML`).
- **LightGBM dự báo chính xác hơn nhưng không tự động lãi hơn EWMA**: nếu dùng cả khoảng rộng của LightGBM thì chỉ thắng ở 38% số tập, do đặt dư hàng tươi biên lãi mỏng nên hủy nhiều hơn.
- Đổi cách dùng mô hình thì khác ([du-bao-ml.md](du-bao-ml.md), mục 5.7). Lấy dự báo điểm của LightGBM, σ của EWMA, chọn theo lãi và đo ngoài mẫu:
  - `B-gate` hơn `B-EWMA` **+0,8%** (trung vị, khoảng tứ phân vị +0,0% đến +1,5%), thắng ở **76%** số tập kiểm chứng;
  - hủy giảm từ 5,2% còn **4,8%**.
- Đặt hàng thẳng theo phân phối lệch của LightGBM thì lỗ: −2,2%. Khoảng rộng đi qua sàn mức phục vụ cao thành đặt dư.
- Nói rõ giới hạn: biến thể này được đưa vào sau khi đã thấy kết quả chẩn đoán trên chính 50 tập này, nên +0,8% hơi lạc quan.
- Bài học: thước đo của dự báo (WAPE) và thước đo của quyết định (lãi) không trùng nhau. Mô hình tốt hơn chưa đủ; cách engine dùng độ bất định mới quyết định lãi.
