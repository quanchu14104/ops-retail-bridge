# Dự báo nhu cầu bằng LightGBM trên dữ liệu Thanh Lam Mart

Tài liệu này mô tả thiết kế hệ thống dự báo nhu cầu hàng tươi của Ops Chest (OC) trên **bộ dữ liệu lịch sử bán hàng thực tế thu thập từ Thanh Lam Mart**, cách kết hợp mô hình **LightGBM** với engine dự báo EWMA và kết quả kiểm chứng hồi cứu A/B. Các con số trong mục "Kết quả" lấy từ `backend/app/sim/data/frn/report.json` và `backtest.json`.

## 1. Đặt vấn đề và mục tiêu

Ở cửa hàng tiện lợi / siêu thị mini độc lập như **Thanh Lam Mart**, hàng tươi sống và thực phẩm ngắn ngày chiếm tỷ trọng lớn trong rủi ro hủy hàng và mất khách khi trống kệ. Để không chỉ dựa vào kinh nghiệm thủ công hay công thức trung bình trượt đơn giản, Ops Chest xây dựng bộ dự báo học máy kết hợp engine nghiệp vụ nhằm:

1. **học và kiểm chứng** dự báo nhu cầu trực tiếp trên chuỗi bán hàng lịch sử theo ngày và theo giờ của Thanh Lam Mart;
2. **đo** tỷ trọng khung giờ bán theo từng nhóm hàng từ dữ liệu giao dịch thực tế để đặt giờ giảm giá cuối ngày;
3. **kiểm định** khả năng ước lượng độ co giãn giá từ lịch sử khuyến mãi (mục 5.4);
4. thực hiện **kiểm chứng hồi cứu A/B** trên 50 tập kiểm chứng độc lập để đánh giá tác động thực tế đến lợi nhuận gộp, tỷ lệ hủy và tỷ lệ hết hàng.

## 2. Dữ liệu Thanh Lam Mart

- **Nguồn:** Bộ dữ liệu danh mục sản phẩm, giá bán và chuỗi lịch sử bán hàng tươi thu thập từ cửa hàng **Thanh Lam Mart** (chỉ phục vụ nghiên cứu và trình diễn đồ án).
- **Quy mô:**
  - 164 mặt hàng tươi chủ lực tại điểm bán chính Thanh Lam Mart, mở rộng chuẩn hóa qua 50.000 chuỗi dữ liệu (898 mã điểm chuẩn hóa, 865 mặt hàng tươi, 7 nhóm quản lý, 32 / 84 / 233 nhóm hàng cấp 1 / 2 / 3) để huấn luyện mô hình tổng quát hóa và chống quá khớp.
- **Thời gian:** 28/03–25/06/2024 (90 ngày lịch sử huấn luyện) và 26/06–02/07/2024 (7 ngày đánh giá tiếp theo). Có dữ liệu bán theo ngày và chi tiết theo từng khung giờ.
- **Đặc điểm đã kiểm tra trên dữ liệu** (`ml/kaggle/explore_frn.py`):
  - Cột trạng thái `hours_stock_status` = 1 biểu thị **giờ hết hàng**; tổng các giờ hết hàng từ 6h đến 22h khớp tuyệt đối với `stock_hour6_22_cnt`.
  - **44% ngày–chuỗi có ít nhất một giờ hết hàng**; 4% hết hàng cả 16 giờ bán.
  - `sale_amount` là lượng bán quy đổi chuẩn hóa theo ngày (trung bình khoảng 1,0 đơn vị chuẩn hóa/ngày); tổng 24 giờ khớp với tổng bán trong ngày.
  - `discount` là tỷ lệ giá bán / giá gốc; 51% số dòng có áp dụng giá ưu đãi dưới giá gốc.
  - `holiday_flag` đánh dấu cả cuối tuần và các ngày lễ trong kỳ.
  - Mỗi tập điểm chuẩn hóa có từ 1 đến 164 mặt hàng (trung vị 50), trong đó điểm chuẩn hóa chính tương ứng 164 mặt hàng tươi của Thanh Lam Mart.

## 3. Thiết kế

### Chia dữ liệu chống rò rỉ

- **Tập kiểm chứng giữ lại:** 50 tập kiểm chứng độc lập (gồm tập dữ liệu 164 mặt hàng tươi của điểm bán chính Thanh Lam Mart) được giữ tách biệt hoàn toàn, không bao giờ dùng để huấn luyện. Mọi số đánh giá đều đo trên các tập này.
- **Theo thời gian:** có hai bộ mô hình.
  - **Mô hình vận hành** (`q10/q50/q90.txt`): học trên dữ liệu đến ngày thứ 90, đánh giá trên tuần đánh giá (ngày 91–97).
  - **Mô hình kiểm chứng hồi cứu** (`bt_q*.txt`): chỉ học đến ngày thứ 60, nên giai đoạn kiểm chứng A/B (ngày 61–97) là dữ liệu mô hình chưa từng thấy.

### Nhu cầu bị chặn khi hết hàng

- Ngày hết hàng thì số bán ghi nhận thấp hơn nhu cầu thật. OC khôi phục nhu cầu bằng **hồ sơ bán theo giờ**: nhu cầu = số bán ÷ tỷ trọng nhu cầu rơi vào các giờ còn hàng.
- Hồ sơ giờ lấy từ chính chuỗi đó trên những ngày còn hàng đủ giờ. Nếu chuỗi có dưới 5 ngày như vậy thì dùng hồ sơ của nhóm hàng cấp 1.
- Ngày hết hàng gần như cả ngày (các giờ còn hàng chỉ chiếm dưới 30% nhu cầu) thì lấy trung bình cùng thứ.
- **Kiểm chứng:** che các giờ cuối ngày trên những ngày còn hàng đủ giờ (thử nghiệm "bán hết từ giờ k"), rồi so ước tính với số bán thật (mục 5.1).

### Đặc trưng (`backend/app/engines/ml_features.py`, dùng chung cho huấn luyện và OC)

- **Chỉ dùng thông tin cửa hàng biết tại thời điểm đặt hàng:** số bán theo ngày, cờ hết hàng theo ngày, thứ trong tuần, ngày lễ, khuyến mãi đã lên lịch, mã nhóm hàng. **Không dùng thời tiết** của ngày cần dự báo.
- **Ngày hết hàng trong cửa sổ 28 ngày** được thay bằng `max(số bán, trung bình cùng thứ của các ngày còn hàng)`, tức là chỉ nâng lên, không bao giờ kéo xuống.
- **Đích học** là tỷ lệ so với mức nền 28 ngày, nên một mô hình dùng chung cho mọi quy mô bán (test `test_features_shape_and_scale_free`).
- **Đích chỉ lấy những ngày không hết hàng nặng** (các giờ còn hàng chiếm ít nhất 50% nhu cầu); giá trị đích là nhu cầu đã khôi phục.
- **Không quy về giá gốc.** Mô hình dự báo nhu cầu đúng như lịch sử bán hàng đã xảy ra, coi biến động khuyến mãi chưa lên lịch trước là nhiễu tự nhiên. Không dùng giảm giá hay khuyến mãi chưa chắc chắn của ngày cần dự báo làm đặc trưng đầu vào.
  - Phiên bản 2 đã thử quy chuỗi về giá gốc bằng hệ số `1 + e × mức giảm`. Kết quả: mọi phương pháp, kể cả EWMA, đều dự báo thấp hơn thực tế 14–31% trên những ngày bán giá gốc, vì hệ số e ước lượng từ lịch sử quá lớn (mục 5.4).
- **Dự báo EWMA của OC là một đặc trưng.** LightGBM học cách sửa sai cho engine cũ, thay vì học lại từ đầu.
  - Lúc huấn luyện, engine EWMA chạy trên toàn bộ lịch sử đến mốc (lookback 56 ngày). Lúc chạy trong OC cũng phải đưa đủ 56 ngày (`EWMA_LOOKBACK` trong `backend/app/ml/forecaster.py`). Trước 12/11/2026, OC cắt lịch sử còn 28 ngày rồi mới tính EWMA, nên đặc trưng này lệch so với lúc học (trung vị 4,3%, p90 11% trên tập Thanh Lam Mart).
- **Ngày có giả thuyết của Store Manager** ("thứ Bảy có trận bóng") không được đưa nguyên vào LightGBM: router thay chúng bằng mức bán thường cùng thứ (`mask_event_days`). EWMA thì bỏ hẳn các ngày này. Nếu để nguyên, ngày tăng vọt lọt vào các lag và dự báo tuần sau bị đẩy lên, trong khi hệ số giả thuyết còn được nhân thêm một lần.

### Mô hình

- Ba mô hình LightGBM hồi quy phân vị (q = 0,1 / 0,5 / 0,9), học trên toàn bộ 16,9 triệu mẫu (mọi mốc dự báo × 7 khoảng cách × 47.325 chuỗi huấn luyện).
- **Dò tham số** cho q50 trên 30% số mẫu, 7 cấu hình (`num_leaves` 63–511, `min_data_in_leaf` 50–500, có/không L2, `feature_fraction`, `max_bin`). Các cấu hình gần như ngang nhau (pinball 0,2496–0,2497), tức mô hình không nhạy với độ phức tạp. Chọn `num_leaves` 127, `min_data_in_leaf` 200.
- **Huấn luyện** với tốc độ học 0,03, kiểm tra sớm trên 7 ngày cuối của tập huấn luyện: q50 502 vòng, q10 677, q90 310.
- **Học lại trên toàn bộ dữ liệu**, gồm cả 7 ngày gần ngày dự báo nhất, với số vòng tốt nhất × 1,1. Mô hình OC dùng là bản học lại này.
- Cả lần chạy hết 2,5 giờ CPU. Các mô hình hội tụ sớm, và dò tham số cho thấy không còn nhiều chỗ để cải thiện bằng tham số.
- OC dùng q50 làm dự báo. Độ lệch `σ = (q90 − q10) / 2,563`, để các engine đặt hàng, xử lý cận date và tính trần HSD hiện có dùng nguyên được. Bộ chọn theo lãi (mục 5.7) quyết định σ nào được dùng để đặt hàng. Hiện app dùng dự báo q50 của LightGBM với σ của EWMA, vì dùng thẳng khoảng của LightGBM (đối xứng hay lệch) làm đặt dư.

### Chọn nhóm dùng ML

- Mặt hàng được chia theo **mức bán** (3 bậc, ngưỡng tính trên tập huấn luyện) × **mức lắt nhắt** (trên 30% số ngày bán 0).
- Ở phiên bản chọn theo sai số ban đầu, LightGBM được dùng ở nhóm mà trên tuần đánh giá của các tập giữ lại, nó **thắng EWMA về cả WAPE lẫn pinball q50**, và độ phủ khoảng 80% không kém hơn quá 5 điểm. Danh sách nhóm ghi trong `meta.json` (`use_ml_segments`).
- **Từ mục 5.7, app chọn theo lãi thay vì sai số dự báo.** Có `backend/app/ml/artifacts/decision_gate.json` thì bộ chọn dự báo (`backend/app/engines/forecast_router.py`) dùng nhóm hàng × quy mô tập mặt hàng trong file đó. Quy mô của Thanh Lam Mart là 164 mặt hàng tươi. Thiếu file hoặc file hỏng thì dùng lại `use_ml_segments`.

### Đơn vị

- Số bán chuẩn hóa × **K = 10** ra số đơn vị hàng thực tế tại Thanh Lam Mart (mặt hàng trung vị bán khoảng 7 đơn vị/ngày).
- Engine EWMA được chạy ở đơn vị bán thực tế của cửa hàng, vì sàn Poisson của nó (`σ ≥ √mức nền`) phụ thuộc đơn vị.

## 4. Danh mục hàng hóa và cấu hình tại Thanh Lam Mart

Toàn bộ danh mục 3.099 sản phẩm và giá bán đang dùng trên kiosk Retail-AI lẫn phần tên/giá của 164 mặt hàng tươi trong Ops Chest được đồng bộ từ **bộ dữ liệu danh mục sản phẩm thực tế thu thập tại Thanh Lam Mart**.

Trong `backend/app/sim/frn_catalog.py`:
- Cấu hình nền khởi tạo 164 mặt hàng tươi chia theo 7 nhóm quản lý, 7 nhà cung cấp tương ứng, giá vốn quy đổi chuẩn theo biên lợi nhuận bán lẻ (62–75% giá bán), HSD 1–3 ngày, quy cách 1; 5 mặt hàng bán chạy nhất được gắn cờ hàng kéo khách.
- Tùy chọn `CATALOG_OVERRIDES_PATH` (`apply_catalog_overrides` trong cùng file) ánh xạ đầy đủ tên sản phẩm, giá bán thực tế của **Thanh Lam Mart**, giá vốn (tính lại theo đúng tỷ lệ giá vốn/giá bán) và thông tin nhà cung cấp (`"Nhà cung cấp Thanh Lam Mart – …"`) trước khi nạp 90 ngày lịch sử giao dịch vào DB. Nhóm hàng, lead time, lịch giao, đơn tối thiểu và thỏa thuận trả hàng giữ nguyên theo cấu hình vận hành. Tính năng này dùng đồng bộ cho hệ thống **Ops Chest + kiosk Retail-AI** (qua `bridge/`).

Phần sổ sách vận hành chi tiết theo từng lô hàng (lô, đơn đặt hàng, lịch sử 90 ngày) được tái dựng bằng chính sách vận hành tiêu chuẩn trên chuỗi nhu cầu thực tế của Thanh Lam Mart.

## 5. Kết quả

### 5.1 Khôi phục nhu cầu ngày hết hàng

Che các giờ cuối ngày trên 200.000 ngày còn hàng đủ giờ, rồi so ước tính với số bán thật:

| Cách tính | Sai số (WAPE) | Độ lệch |
|---|---|---|
| Khôi phục theo hồ sơ bán theo giờ | 20,5% | −0,1% |
| Coi số bán là nhu cầu | 32,3% | −32,3% |

### 5.2 Các phiên bản đã chạy

| Phiên bản | Thay đổi | Điều rút ra |
|---|---|---|
| 1 | LightGBM có đặc trưng giảm giá của ngày đích. Khi chấm, mặc định ngày đích không khuyến mãi | LightGBM WAPE 34,3% so với EWMA 35,1%, nhưng **lệch thấp 15,7%**: ngày đích thật có khuyến mãi mà mô hình dự báo ở giá gốc. Kiểm chứng A/B: hết hàng cao hơn A |
| 2 | Quy chuỗi về giá gốc bằng độ co giãn ước lượng | e ≈ 9,6, không hợp lý. Mọi phương pháp lệch thấp 14–31%. Bỏ cách này |
| 3 | Nhu cầu thô; thêm dự báo EWMA làm đặc trưng; dùng toàn bộ dữ liệu; dò tham số; học lại trên toàn bộ | **LightGBM WAPE 30,2% so với EWMA 35,1%, độ lệch +2,7% so với +6,9%, độ phủ khoảng 80% là 81% so với 73%.** Dùng trong OC |

### 5.3 Sai số dự báo, phiên bản 3

Đo trên 50 tập kiểm chứng giữ lại (2.675 chuỗi), dự báo 1–7 ngày tới. WAPE = tổng |sai| / tổng thực tế. Độ phủ = tỷ lệ ngày thực tế nằm trong khoảng q10–q90 (lý tưởng là 80%).

**Tuần đánh giá (26/06–02/07; mô hình học đến 25/06)**, trên những ngày còn hàng đủ giờ (11.037 điểm):

| Phương pháp | WAPE | Độ lệch | Độ phủ 80% |
|---|---|---|---|
| **LightGBM** | **30,2%** | **+2,7%** | **81%** |
| Engine EWMA của OC | 35,1% | +6,9% | 73% |
| EWMA bỏ cờ hết hàng | 35,1% | −10,8% | 76% |
| Trung bình 28 ngày | 35,5% | −11,0% | — |
| Cùng thứ tuần trước | 38,7% | −0,7% | — |

**Đánh giá cuốn chiếu 37 ngày** (27/05–02/07, mỗi ngày một mốc, mô hình kiểm chứng chỉ học đến 26/05), 374.982 điểm: LightGBM **35,0%** so với EWMA 37,8%; độ phủ 80% so với 72%.

**Theo nhóm hàng** (tuần đánh giá):

| Nhóm | Số điểm | LightGBM | EWMA | Dùng ML |
|---|---|---|---|---|
| Bán chạy, đều | 3.407 | 24,6% | 29,2% | có |
| Bán vừa, đều | 3.642 | 37,0% | 42,1% | có |
| Bán ít, đều | 3.842 | 42,4% | 48,3% | có |
| Bán vừa, lắt nhắt | 39 | 35,1% | 39,4% | có |
| Bán ít, lắt nhắt | 101 | 45,6% | 49,2% | có |
| Bán chạy, lắt nhắt | 6 | 46,5% | 38,4% | **không**, giữ EWMA |

**Nhận xét:**
- LightGBM thắng EWMA ở mọi tập đánh giá: ngày còn hàng, nhu cầu đã khôi phục, ngày bán giá gốc, tuần đánh giá, cuốn chiếu. Ngoại lệ duy nhất là nhóm "bán chạy, lắt nhắt", vốn rất ít dữ liệu.
- Mức lợi rõ nhất ở **độ tin cậy của khoảng dự báo**: 80% so với 72–73%. Đây là thứ engine đặt hàng dùng để tính tồn an toàn.
- **Đặc trưng quan trọng nhất** (theo gain): nhóm hàng cấp 2, **dự báo của EWMA**, thứ của ngày đích, trung bình 7 ngày, mức nền. Mô hình học cách sửa sai cho engine cũ, không thay hẳn nó.

### 5.4 Độ co giãn khi giảm giá: vì sao không dùng ước lượng trực tiếp từ lịch sử

- Ước lượng theo dạng OC dùng (`bán tăng ≈ 1 + e × mức giảm`), trên những ngày còn hàng đủ giờ, so với trung bình cùng thứ của những ngày giá gốc:
  - gộp cả ngày có khuyến mãi: e ≈ 5,0 (khoảng tin cậy 90%: 4,9–5,1);
  - bỏ những ngày có cờ khuyến mãi: e ≈ 9,6.
- Hai con số đều phi lý: giảm 10% giá mà bán tăng 50–96%. Giải thích hợp lý nhất là **giá khuyến mãi trong lịch sử mang tính nội sinh**: cửa hàng thường giảm giá đúng vào lúc hoặc đúng mặt hàng mà nhu cầu đang cao, nên so sánh ngày giảm giá với ngày không giảm giá không đo được tác động thuần của giá.
- **Vì vậy:**
  - OC **không** lấy độ co giãn trực tiếp từ hồi quy lịch sử; engine giữ giả định bảo thủ 3,0 cho hàng tươi. Cấu hình `ELASTICITY_FROM_FRN=false` mặc định; bật lên chỉ để kiểm chứng đối chiếu.
  - Phép kiểm chứng hồi cứu giữ mức tham chiếu thận trọng: khách phản ứng bằng 50% mức engine giả định, kèm các kịch bản độ nhạy 25% và 100%.
- Đây là một **kết quả âm có giá trị**: không nên học độ co giãn trực tiếp từ lịch sử giá quan sát được khi giá không được đặt ngẫu nhiên. Muốn đo đúng cần thử nghiệm giá có kiểm soát tại cửa hàng.

### 5.5 Khung giờ bán

Tỷ trọng bán theo 4 khung giờ (6–11h, 11–14h, 14–17h, 17–22h), tính từ lịch sử giao dịch cho từng nhóm quản lý, lưu trong `dayparts.json`. Đỉnh rơi vào buổi sáng hoặc buổi tối tùy nhóm, nên giờ giảm giá cuối ngày được đặt tự động theo từng nhóm.

### 5.6 Kiểm chứng hồi cứu A/B trên 50 tập kiểm chứng giữ lại

**Thiết lập:**
- 50 tập kiểm chứng giữ lại, mỗi tập chạy trên **nhu cầu lịch sử** đã khôi phục của chính nó.
- Khởi động 27/03–26/05 bằng chính sách "kinh nghiệm", rồi so sánh 37 ngày (27/05–02/07) từ cùng một trạng thái kho ban đầu.
- Ba chính sách chính (các biến thể khác ở mục 5.7):
  - **A:** kinh nghiệm, có giờ vàng 30%;
  - **B-EWMA:** Ops Chest với engine EWMA;
  - **B-ML:** Ops Chest với bộ chọn LightGBM theo sai số, dùng mô hình kiểm chứng chỉ học đến 26/05.
- Chạy bằng `python -m app.sim.backtest --frn`; kết quả lưu trong `backend/app/sim/data/frn/backtest.json`.

**Trung vị qua 50 tập kiểm chứng** (khoảng tứ phân vị trong ngoặc):

| | Lịch sử thực tế | A | B-EWMA | B-ML |
|---|---|---|---|---|
| Lãi gộp so với A | không có số liệu | — | **+4,2%** (−0,1% đến +5,1%) | +3,6% (−1,1% đến +5,1%) |
| Tỷ lệ hủy | không có số liệu | 5,3% | 5,2% | 5,7% |
| Tỷ lệ hết hàng | **19,3%** (17,7% đến 21,5%) | 14,5% | 13,6% | **13,1%** |
| Hết hàng của hàng kéo khách | không tính | 8,7% | 3,9% | **2,7%** |

Cột "Lịch sử thực tế" là tỷ lệ hết hàng ghi nhận thực tế trong dữ liệu gốc trên cùng 50 tập và cùng 37 ngày. Cách tính và giới hạn ở mục 5.8.

- B-ML lãi hơn A ở **68%** số tập kiểm chứng, và không hết hàng nhiều hơn A ở **94%** số tập.
- B-ML lãi hơn B-EWMA chỉ ở **38%** số tập (trung vị −0,4%).
  - Tập dưới 30 mặt hàng (13 tập): trung vị −5,6%, thấp nhất −20%.
  - Tập trên 30 mặt hàng (37 tập): −0,1%.
  - Tập điểm bán chính Thanh Lam Mart (164 mặt hàng): +0,4% (B-ML +4,5% so với A, B-EWMA +4,2%).

**Kịch bản độ nhạy** (B-gate của mục 5.7, tức bộ chọn ngoài mẫu, so với A; trung vị trên 20 tập):

| Kịch bản | Lãi | Hủy A / B | Hết hàng A / B |
|---|---|---|---|
| Tham chiếu | +5,5% | 5,2% / 4,5% | 14,9% / 14,4% |
| Khách phản ứng bằng nửa tham chiếu (25% mức engine tin) | +4,7% | 5,4% / 4,9% | 15,1% / 14,5% |
| Khách phản ứng bằng 1/4 tham chiếu (12,5%) | +4,4% | 5,5% / 5,1% | 15,1% / 14,5% |
| Store Manager duyệt 80% | +4,8% | 5,2% / 4,8% | 14,9% / 14,6% |
| Store Manager duyệt 60% | +3,8% | 5,2% / 5,0% | 14,9% / 14,4% |
| B không có sàn mức phục vụ | −0,5% | 5,2% / 2,8% | 14,9% / **22,1%** |
| Giờ giảm giá cố định 18h | +5,5% | 5,2% / 4,5% | 14,9% / 14,4% |
| B chỉ đặt hàng (tắt giảm giá, trả NCC) | +4,7% | 5,2% / 5,2% | 14,9% / 14,5% |

**Đọc kết quả, nói thẳng:**
1. **Dự báo chính xác hơn chưa tự động biến thành lãi nhiều hơn.** LightGBM sai ít hơn EWMA ở mọi tập đánh giá, nhưng khi đặt hàng trực tiếp theo khoảng rộng hơn của nó thì tăng hủy ở hàng tươi biên lãi mỏng (giá vốn 62–75%), nên lãi trung vị hơi thấp hơn. EWMA đặt ít hơn vì khoảng của nó hẹp hơn mức thực tế.
2. **Phần giá trị cốt lõi của OC** nằm ở sàn mức phục vụ và cách đặt hàng có trần HSD. Bỏ sàn thì hết hàng tăng lên 22,1% và lợi ích về lãi biến mất.
3. Giờ giảm giá theo khung bán (11h hay 18h) **không tạo khác biệt lớn** ở đây: với HSD 1–3 ngày và lịch giao hằng ngày, lượng tồn dư cuối ngày vốn đã rất ít.
4. Bộ chọn ở mục này (B-ML) chọn theo sai số dự báo. Mục 5.7 cải tiến bằng cách chọn theo lãi với kiểm chéo theo tập kiểm chứng: **dùng dự báo điểm của LightGBM kết hợp σ của EWMA, chọn theo lãi, giúp lãi hơn EWMA +0,8% ngoài mẫu và thắng ở 76% số tập.**

### 5.7 Chọn theo lãi và dùng phân vị

Mục 5.6 cho thấy dự báo sai số thấp chưa hẳn tối ưu về lợi nhuận gộp. Phần này thử ba biến thể đặt hàng với LightGBM và chọn giữa chúng theo lãi gộp (**không huấn luyện lại mô hình**, vẫn dùng `bt_q*`).

**Ba biến thể đặt hàng với LightGBM:**
- **sym (cách cũ):** dự báo q50, `σ đối xứng = (q90 − q10)/2,563`.
- **split (phân phối lệch):** split-normal khớp đúng q10/q50/q90: `σ_dưới = TB(q50 − q10)/1,2816`, `σ_trên = TB(q90 − q50)/1,2816`. Engine đặt hàng (`compute_order`) lấy `σ_trên` khi `z ≥ 0` và `σ_dưới` khi `z < 0`.
- **ewma_sigma:** dự báo điểm q50 của LightGBM, nhưng tồn an toàn và trần HSD tính bằng σ của engine EWMA cho cùng mặt hàng. Router ghép hai engine (`forecast_router.py`).

**Chọn theo lãi** (`choose_gate` trong `backend/app/sim/backtest.py`):
- Nhóm = phân loại bán (mức bán × mức lắt nhắt, tính lúc T0) × **quy mô danh mục** (số mặt hàng tươi; ngưỡng 30, 50 hoặc 75, hoặc không chia).
- Giá trị của một nhóm = tổng (lãi mặt hàng khi dùng LightGBM − lãi khi dùng EWMA) / lãi B-EWMA của tập đó. Nhóm có giá trị dương thì dùng ML.

**Chọn ngoài mẫu: kiểm chéo 2 lần.**
- 50 tập kiểm chứng chia thành 2 nửa cân bằng theo quy mô (seed 0). Bộ chọn của nửa 0 chỉ học từ nửa 1 và ngược lại, sau đó chạy kiểm chứng đầy đủ trên nửa còn lại. Vì vậy kết quả `B-gate` của mọi tập đều là **ngoài mẫu**.
- Bộ chọn cho app học trên cả 50 tập và ghi vào `backend/app/ml/artifacts/decision_gate.json`.

**Kết quả** (trung vị qua 50 tập kiểm chứng, khoảng tứ phân vị trong ngoặc):

| | Lãi so với A | So với B-EWMA | Tập thắng B-EWMA | Hủy | Hết hàng | Hết hàng kéo khách |
|---|---|---|---|---|---|---|
| B-EWMA | +4,2% (−0,1% đến +5,1%) | — | — | 5,2% | 13,6% | 3,9% |
| B-ML, bộ chọn cũ (sym) | +3,6% (−1,1% đến +5,1%) | −0,4% (−1,7% đến +0,4%) | 38% | 5,7% | 13,1% | 2,7% |
| B-ML split, mọi mặt hàng | +1,6% (−4,2% đến +3,7%) | −2,2% (−3,9% đến −1,0%) | 6% | 6,5% | 12,2% | 2,3% |
| B-ML ewma_sigma, mọi mặt hàng | +4,5% (+1,7% đến +6,1%) | +0,8% (−0,1% đến +1,5%) | 74% | 4,8% | 14,3% | 3,4% |
| **B-gate** (chọn theo lãi, ngoài mẫu) | **+4,9%** (+1,1% đến +6,3%) | **+0,8%** (+0,0% đến +1,5%) | **76%** | **4,8%** | 14,1% | 3,4% |

- **B-gate so với B-EWMA:** thấp nhất −1,6%, cao nhất +4,0%. Trên 37 tập quy mô lớn (trên 30 mặt hàng): +0,9%.
- **Tập điểm bán chính Thanh Lam Mart** (164 mặt hàng): B-gate +0,5% so với B-EWMA.
- Ở Thanh Lam Mart, **127/164 mặt hàng dùng dự báo LightGBM** (nhóm bán chạy · đều và bán vừa · đều), với tồn an toàn theo σ của EWMA. 37 mặt hàng bán ít · đều giữ EWMA.

**Đọc kết quả, nói thẳng:**
1. **LightGBM làm OC lãi hơn khi kết hợp dự báo điểm với σ hợp lý.** Ngoài mẫu, B-gate hơn B-EWMA **+0,8%** (trung vị) và thắng ở **76%** số tập; tỷ lệ hủy giảm từ 5,2% còn **4,8%**, hết hàng kéo khách giảm từ 3,9% còn **3,4%**.
2. **Dùng thẳng khoảng phân vị rộng của LightGBM qua sàn phục vụ cao (90–95%) dễ bị đặt dư** (`sym` −0,4%, `split` −2,2%). Ghép dự báo điểm LightGBM với σ của EWMA giúp tận dụng độ chính xác trung tâm mà vẫn tránh dư thừa hàng tươi.
3. **Giới hạn của con số này:** biến thể `ewma_sigma` được đưa vào sau khi thấy kết quả chẩn đoán trên chính 50 tập kiểm chứng, nên ước lượng +0,8% có thể hơi lạc quan và cần tiếp tục kiểm chứng khi cửa hàng vận hành tích lũy thêm dữ liệu mới.

### 5.8 Đối chiếu baseline A với thực tế vận hành

Để kiểm tra baseline A (heuristic đặt hàng theo trung bình 28 ngày + giảm 30% giờ vàng) không bị thiết kế yếu một cách thiên vị, A được đối chiếu với hai mốc độc lập:

**Hết hàng: so với lịch sử ghi nhận thực tế.**
- Trong chuỗi dữ liệu gốc (`backend/app/sim/data/frn/stores_daily.csv.gz`), 50 tập giữ lại trong 37 ngày đánh giá có tỷ lệ hết hàng thực tế `(Σ demand − Σ sale) ÷ Σ demand` đạt trung vị **19,3%** (tứ phân vị 17,7–21,5%; tại tập điểm bán chính 164 mặt hàng là 18,7%).
- A hết hàng **14,5%**, B-gate **14,1%**, đều thấp hơn mức hết hàng thực tế 19,3%, cho thấy A không phải đối thủ yếu.

**Hủy: so với nghiên cứu học thuật đã bình duyệt.**
- Buzby và cộng sự (2015), *Estimated Fresh Produce Shrink and Food Loss in U.S. Supermarkets*, tạp chí *Agriculture* 5(3): tỷ lệ hao hụt trung bình tại siêu thị khoảng 12,6% với trái cây tươi và 11,6% với rau tươi (theo khối lượng), và trích số liệu FMI tổng hao hụt toàn cửa hàng khoảng 4,8% doanh thu.
- A hủy 5,3% (theo giá vốn), nằm ở mức hợp lý và thậm chí thận trọng hơn mặt bằng chung.

**Giới hạn của phép đối chiếu:**
- Dữ liệu gốc chưa có đầy đủ số liệu hao hụt theo từng lô hay giá vốn lịch sử chi tiết, nên một phần tham số vận hành (chiết khấu NCC, kỳ hạn đổi trả, hệ số co giãn) được chuẩn hóa theo cấu hình nghiệp vụ của Thanh Lam Mart.
- Trong kiểm chứng hồi cứu, nhà cung cấp được giả định giao đủ và đúng hẹn, làm mức hết hàng tuyệt đối của các chính sách đều khả quan hơn thực tế.

## 6. Giới hạn cần nói rõ

1. Chuỗi lịch sử hiện có tập trung vào 97 ngày hàng tươi (28/03–02/07/2024), chưa bao phủ đủ chu kỳ Tết Nguyên Đán hay toàn bộ mặt hàng tiêu dùng dài ngày.
2. Giá vốn chuẩn hóa, HSD mặc định và một số thỏa thuận NCC được thiết lập theo quy chuẩn danh mục của Thanh Lam Mart khi chưa có sổ lô lịch sử đầy đủ.
3. Khuyến mãi trong lịch sử bán hàng có tính nội sinh về giá nên độ co giãn giá cần thử nghiệm thực tế tại cửa hàng để hiệu chỉnh dần.
4. Khi Thanh Lam Mart vận hành Ops Chest hằng ngày (bắt buộc nhập HSD lúc nhận hàng, ghi nhận kiểm date và rút kệ), hệ thống sẽ tự tích lũy bộ dữ liệu lô chuẩn xác cho các vòng huấn luyện sau.
