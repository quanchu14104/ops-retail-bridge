# Nghiệp vụ, quy tắc và KPI

## 1. Phạm vi: cửa hàng tiện lợi độc lập

Store Manager (SM) làm việc trực tiếp với đại lý, có toàn quyền nhập hoặc ngừng nhập mặt hàng — áp dụng cho cửa hàng **Thanh Lam Mart** (nơi nhóm thu thập bộ dữ liệu danh mục sản phẩm và chuỗi bán hàng thực tế cho dự án). Mô hình này khác các chuỗi lớn (7-Eleven, FamilyMart, Circle K, GS25). Ở chuỗi, hợp đồng và danh mục hàng do tổng công ty quyết; cửa hàng chỉ đặt hàng về kho tổng (DC), hoặc đặt nhà cung cấp giao thẳng (DSD).

## 2. Các điều chỉnh so với ý tưởng ban đầu

| Ý tưởng ban đầu | Điều chỉnh trong Ops Chest | Lý do |
|---|---|---|
| "Niên hạn sản phẩm" | Quản lý theo **lô**, mỗi lô có HSD. Bước **nhận hàng bắt buộc nhập HSD**. Bán theo **FEFO** (hết hạn trước bán trước). | POS chỉ biết SKU, không biết HSD. Cùng một SKU có thể gồm nhiều lô. |
| Mọi mặt hàng như nhau | 3 nhóm vòng đời: FRESH (≤3 ngày), SHORT (≤30 ngày), LONG | Lãng phí tập trung ở hàng tươi; mỗi nhóm cần chính sách đặt hàng riêng. |
| "Quyết định abcxyz" | **Phân tích ABC-XYZ** (kỹ thuật có thật) | Ma trận 9 ô quyết định mức tồn an toàn và là cơ sở đề xuất ngừng nhập. |
| Tự động gửi "hợp đồng" | Agent chỉ soạn **đơn đặt hàng (PO)** theo mẫu cố định, kèm PDF. **Hợp đồng nguyên tắc** được lưu dưới dạng dữ liệu (chiết khấu, lead time, đơn tối thiểu, điều khoản đổi trả). | Hợp đồng ký mỗi năm một lần; đơn hàng gửi hằng ngày. LLM không nên soạn văn bản pháp lý. |
| Ngừng nhập dựa trên lịch sử bán | Chỉ xét ô C-Y/C-Z **và** (hủy ≥15% hoặc lỗ), **không bao giờ** đề xuất cắt hàng kéo khách (traffic driver), có kiểm tra hàng thay thế | Nước suối, mì gói lãi thấp nhưng thiếu là khách bỏ đi. |
| LLM "ra quyết định" | **Mọi con số do engine tất định tính.** LLM chỉ gọi tool, giải thích và trò chuyện. Yêu cầu đặt hàng bằng lời cũng thành đề xuất do engine dựng, không thành thư tự do. | LLM tính sai và không lặp lại được kết quả; cách này cũng kiểm chứng được khi bảo vệ. |

## 3. Engine (`backend/app/engines/`)

### Dự báo (`forecast.py`)

- Mức nền EWMA (half-life 14 ngày) × hệ số thứ trong tuần × hệ số Tết.
- Hệ số Tết được *học từ chính lịch sử SKU*.
- **Nhu cầu bị chặn (censored demand).** Ngày hết hàng thì doanh số bằng lượng tồn, còn nhu cầu thật lớn hơn. Nếu bỏ hẳn những ngày này thì dự báo **bị lệch thấp** (đã đo được khoảng −10% trên hàng tươi), vì đó thường là ngày bán chạy. Engine ước lượng `E[D | D ≥ doanh số]` theo phân phối chuẩn (kiểu Tobit) và lặp 3 vòng.
- **Doanh số nhờ giảm giá không phải nhu cầu.** Tính cả vào thì dự báo bị thổi lên, đặt dư, rồi lại phải giảm giá tiếp. Trong kiểm chứng hồi cứu, lượng bán giờ vàng bị bỏ khỏi chuỗi nhu cầu, lượng bán giảm giá cả ngày được chia cho `1 + co giãn × mức giảm` (`baseline_demand`). Lịch sử trong DB hiện chỉ sinh từ giai đoạn không giảm giá; khi nối POS thật, cần lấy thêm số lượng bán theo mức giảm.
- Sai số chuẩn (σ) tính trên mọi quan sát, có sàn Poisson (σ ≥ √mức nền).

### Số lượng đặt (`replenishment.py`)

Cả hai chế độ dưới đây đều:

- tính toán FEFO đến ngày hàng về, **chỉ tính phần tồn còn hạn** khi hàng mới về;
- trừ hàng đang về, kể cả đơn đã quá ngày giao. Đơn không giao nữa thì Store Manager hủy trên trang Đặt & nhận hàng; bản tin cảnh báo đơn trễ;
- bị **chặn trần theo HSD**: không đặt nhiều hơn lượng bán kịp trước khi lô mới hết hạn;
- bị **chặn theo sức chứa** kệ/tủ (`Product.max_stock_qty`): tồn lúc hàng về cộng số đặt không vượt sức chứa; thẻ đề xuất ghi nhãn "sức chứa" cho dòng bị chặn;
- có **sàn mức phục vụ** theo vai trò mặt hàng (`SERVICE_FLOOR_*` trong config): hàng kéo khách ≥ 95%, nhóm A ≥ 90%, còn lại ≥ 50%. Khách vào cửa hàng tiện lợi vì tin là có hàng; engine không được chủ động để thiếu hàng chỉ vì lãi thấp. Mức 95% cho hàng chủ lực là con số tham khảo thường gặp, cần trích nguồn nếu đưa vào báo cáo;
- tính **ngày hàng về và chu kỳ phủ theo lịch NCC**: ngày giao trong tuần (`Supplier.delivery_weekdays`) và kỳ nghỉ (`supplier_closures`, ví dụ nghỉ Tết). Chu kỳ phủ = từ lúc đơn hôm nay về đến lúc đơn kế tiếp về, nên đơn cuối trước kỳ nghỉ tự lớn lên để phủ cả kỳ nghỉ (trần HSD vẫn chặn). Ngày NCC nghỉ không đến lịch đặt; bản tin cảnh báo trước 14 ngày kèm ngày đặt đơn cuối;
- làm tròn theo quy cách đóng gói.

**Đơn dưới giá trị tối thiểu** của NCC không chỉ được cảnh báo. Engine tính sẵn hai phương án để Store Manager chọn: **bù đơn** (kéo sớm từng thùng hàng bền nhóm A/B có số ngày tồn thấp nhất, không vượt trần HSD và sức chứa) và **hoãn** (chỉ khả thi khi theo dự báo không mặt hàng nào trong đơn hết trước lần giao kế tiếp). Muốn duyệt đơn vẫn dưới mức tối thiểu thì phải đánh dấu "đã thỏa thuận với NCC"; không đánh dấu thì việc thực thi bị từ chối. Dòng Store Manager tự thêm vào đơn được áp chiết khấu của thỏa thuận như dòng do engine tạo.

**Hàng dễ hư** (HSD ≤ chu kỳ đặt + 7 ngày) dùng mô hình **newsvendor**:

```
mức phục vụ tối ưu = (giá − vốn + chi phí mất khách) / (giá − giá trị thu hồi + chi phí mất khách)
```

- *Chi phí mất khách* ("chance loss", khái niệm 7-Eleven Nhật hay nhấn mạnh) = 30% giá bán, và 100% với hàng kéo khách.
- *Giá trị thu hồi* = tiền kỳ vọng thu lại khi giảm giá giờ vàng hoặc trả nhà cung cấp.
- Kết quả bị kẹp trong 30–98% rồi nâng lên sàn mức phục vụ của mặt hàng. Trước đây sàn 30% cho phép engine để một số SKU thiếu hàng 7 trên 10 ngày.

**Hàng bền** dùng **order-up-to**, với tồn an toàn `z·σ·√(L+R)` (z không thấp hơn mức ứng với sàn mức phục vụ, và tồn an toàn không thấp hơn tồn trưng bày tối thiểu `Product.min_display_qty`, vì kệ trống một nửa bán kém hơn kệ đầy) và z theo ô ABC-XYZ:

| | X | Y | Z |
|---|---|---|---|
| **A** | 2,05 | 1,65 | 1,28 |
| **B** | 1,65 | 1,28 | 1,04 |
| **C** | 1,28 | 1,04 | 0,84 |

### Rủi ro hết hạn và xử lý cận date (`expiry.py`, `disposition.py`)

Engine tính toán bán FEFO theo dự báo để ra **số lượng dự kiến hủy** của từng lô, rồi so sánh **tiền thu hồi kỳ vọng** của các phương án:

- **Giữ nguyên:** phần dư bị hủy, tốn thêm chi phí xử lý khoảng 500đ/đơn vị.
- **Giảm giá 20/30/50%.** Hệ số co giãn cấu hình mặc định: FRESH 3,0, SHORT 2,0, LONG 1,2. Đây là tham số cần hiệu chỉnh thêm bằng thử nghiệm giá tại cửa hàng.
  - Lô hết hạn trong ngày: chỉ **giảm giá giờ vàng cho phần còn dư, bắt đầu sau khung bán đỉnh của nhóm hàng**. Mỗi nhóm có bảng tỷ trọng bán theo khung giờ (sáng 6–11h, trưa 11–14h, chiều 14–17h, tối 17–22h) trong `category_policies`: nhóm bán đỉnh trưa giảm từ 14h, nhóm bán đỉnh sáng giảm từ 11h, các nhóm khác từ 18h. Engine dùng "tỷ trọng nhu cầu còn lại sau giờ giảm" thay cho hằng số 30% cũ. Khách sau giờ giảm vốn sẽ trả giá gốc cũng được hưởng giá giảm; engine và bộ kiểm chứng hồi cứu đều trừ phần này. Bảng tỷ trọng trong kiểm chứng hồi cứu dùng bảng khung giờ độc lập theo từng điểm để kết quả không tự chứng minh.
  - **Ràng buộc giảm giá theo nhóm hàng** (`category_policies`): được giảm giá hay không (`markdown_allowed`) và trần mức giảm (`max_markdown_pct`, mặc định 50% cho mọi nhóm). Engine không đề xuất mức vượt trần; Store Manager sửa hoặc agent sửa vượt trần bị chặn; lúc thực thi kiểm tra lại. Đây là **cấu hình của cửa hàng**: trần mức giảm và danh mục hàng không được khuyến mại phải đối chiếu Nghị định 81/2018/NĐ-CP (và văn bản sửa đổi, hướng dẫn) trước khi dùng chính thức. Danh mục Thanh Lam Mart hiện chưa có nhóm hàng nào cần cấm.
  - Lô còn vài ngày: giảm giá cả lô; engine tính cả phần doanh thu giá gốc bị mất.
  - Lô đang giảm giá: chỉ xét mức sâu hơn, so với phương án giữ mức hiện tại. Hệ thống không tăng giá trở lại, vì tem đã dán.
- **Trả nhà cung cấp:** chỉ khi thỏa thuận **còn hiệu lực** cho phép và lô còn ≥ N ngày trước HSD; hoàn x% giá vốn hoặc đổi hàng mới (`SupplierAgreement.return_mode`: `CREDIT` mặc định, `EXCHANGE` đổi date). Thỏa thuận hết hiệu lực thì đơn hàng không được chiết khấu và có cảnh báo.
- Một lô đang nằm trong đề xuất trả hoặc ghi hủy còn mở thì không được đề xuất lại cho đến khi đề xuất đó đóng.

### Giả thuyết của Store Manager (`services/hypotheses.py`)

Dự báo từ lịch sử không biết tuần này có trận bóng. Cách làm của 7-Eleven Nhật là để người bán đặt giả thuyết rồi kiểm chứng; đây cũng là việc chat làm tốt hơn dashboard.

- Store Manager nói trong chat, agent tạo đề xuất với **đúng hệ số và ngày người dùng nêu**. Thiếu thì agent phải hỏi, không tự chọn.
- Giới hạn bằng code: hệ số 0,3–3, tối đa 14 ngày, không trùng khoảng ngày cùng phạm vi.
- Dự báo chỉ đổi sau khi duyệt. Những ngày có sự kiện không được dùng để ước lượng mức nền, giống cách xử lý Tết.
- Hết khoảng ngày, hệ thống so lượng bán thực tế với dự báo nền đã lưu. **Đúng** nếu nhu cầu đi được ≥50% quãng đường dự đoán, **sai** nếu ≤25%, còn lại là đúng một phần. Dùng lượng bán vì cửa hàng thật không biết nhu cầu bị hụt. Khi từ 20% số SKU-ngày bị hết hàng, lượng bán chỉ là cận dưới của nhu cầu, nên hệ thống chỉ giữ kết luận mà cận dưới chứng minh được: giả thuyết tăng là "đúng", giả thuyết giảm là "sai". Các trường hợp còn lại chấm **chưa đủ căn cứ**, tránh việc nhập ít, bán ít rồi tự xác nhận là nhu cầu đã giảm.

### Học từ phần sửa (`engines/edit_learning.py`)

Chỉ gợi ý khi có ít nhất 5 lần sửa trên 3 đơn đã duyệt, trung vị lệch từ 15% và 70% số lần cùng chiều. Hệ số do code tính (làm tròn 0,05, trong khoảng 0,5–1,5), agent không chọn được. Áp dụng phải qua duyệt, tắt được bất cứ lúc nào. Hệ số tăng vẫn không vượt trần HSD.

### Ngừng nhập và hàng mới

- `Product.listed_date`: mặt hàng bán chưa đủ 8 tuần là **hàng mới**, hiện nhãn "hàng mới" thay cho phân loại bán và không bị xét ngừng nhập (ít lịch sử nên dễ rơi vào nhóm bán chậm).
- Thẻ đề xuất ngừng nhập kèm **kế hoạch xả tồn**: tồn còn lại, đơn đang về, số ngày dự kiến bán hết, số đơn vị không bán kịp trước HSD. Có phần không kịp thì gợi ý xả hàng (giảm giá) và cân nhắc huỷ đơn đang về. Ngừng nhập vẫn chỉ đổi trạng thái; đơn đang mở không tự huỷ.
- Chưa có luồng thêm mặt hàng mới với "SKU tham chiếu" để mượn dự báo (xem mục 7).

### Kiểm kê theo SKU (`services/stockcount.py`)

Đếm **mù**: phiếu không hiện số trên sổ, vì người đếm thấy số sẽ có xu hướng đếm cho khớp. Nhân viên gửi số đếm; chênh lệch thành đề xuất cho Store Manager duyệt. Thiếu thì trừ lô gần hết hạn trước (không biết mất ở lô nào), dư thì cộng vào lô mới nhất. Nếu tồn đã thay đổi giữa lúc đếm và lúc duyệt, đề xuất thất bại và phải đếm lại, thay vì ghi đè bằng số cũ. Cách đếm này chủ yếu dùng cho hàng dài ngày còn xa hạn.

- **Lịch đếm theo ABC**: nhóm A mỗi tuần, B hai tuần, C mỗi tháng, tính từ lần đếm gần nhất (kiểm kê hoặc kiểm date, kể cả khi khớp sổ). Bản tin nhắc số mặt hàng đến lịch; phiếu "Đến lịch đếm" chỉ gồm các mặt hàng này.
- **Tồn ảo**: mặt hàng bán đều (trung bình ≥ 1/ngày, có bán ≥ 60% số ngày trong 4 tuần) mà 3 ngày liền không bán trong khi sổ còn hàng được đưa vào phiếu đếm, kèm lý do. Đây thường là kệ đã trống mà sổ chưa biết; để lâu thì dự báo giảm dần và mặt hàng không được đặt lại.
- Lưu ý: cờ "hết hàng" trong `DailySales` của bộ dữ liệu Thanh Lam Mart lấy từ ghi nhận giờ hết hàng lịch sử. Khi vận hành trực tiếp tại cửa hàng chưa có cảm biến kệ, hệ thống suy cờ này từ sổ tồn bằng 0, nên việc kiểm kê phát hiện tồn ảo và kiểm date là cách giữ sổ đúng để bước hiệu chỉnh nhu cầu bị chặn hoạt động chính xác.

### Kiểm date theo lô (`services/datecheck.py`)

POS chỉ biết SKU, và khách hay với tay lấy lô mới ở phía trong kệ. Sổ ghi lô cũ đã bán hết trong khi lô cũ vẫn nằm trên kệ, nên lô sắp hết hạn không hiện trong báo cáo cận date và quá hạn ngay trên kệ mà sổ không biết.

- **Phiếu kiểm date** liệt kê các mặt hàng có lô sắp tới ngày bán cuối (hàng tươi ≤ 2 ngày, ngắn ngày ≤ 7, dài ngày ≤ 30), kèm các HSD sổ đang có nhưng **không kèm số lượng** (vẫn đếm mù). Nhân viên đếm theo từng HSD in trên bao bì và thêm được HSD mà sổ chưa có.
- Lịch: hàng tươi mỗi ngày, hàng ngắn ngày thứ Hai, hàng dài ngày ngày 1 hằng tháng; bản tin nhắc khi đến lịch.
- Mặt hàng đã nhập số thì HSD trên sổ mà phiếu để trống được tính là 0: người đếm đã xem hết kệ của mặt hàng đó.
- Chênh lệch thành đề xuất `STOCK_ADJUST` **cấp lô**. Duyệt thì sổ ghi đúng số của từng HSD; lô đã đóng trên sổ được mở lại, HSD chưa từng có thì tạo lô mới. Chuyển số giữa các lô cùng mặt hàng trong một phiếu không bị tính là hao hụt.

### Ngày bán cuối và rút kệ (`services/shelf.py`)

- Mỗi mặt hàng có `pull_days_before_expiry` (cấu hình: tươi 0, ngắn ngày 1, dài ngày 7). **Ngày bán cuối** = HSD − số ngày này. Báo cáo cận date, đề xuất giảm giá, số lượng đặt (tồn còn bán được, trần HSD) đều tính theo ngày bán cuối; điều khoản trả NCC vẫn tính theo HSD in trên bao bì.
- Bán hàng quá hạn là vi phạm an toàn thực phẩm, nên **gỡ kệ là việc bắt buộc của ca làm, không chờ duyệt**. Cửa hàng có giờ đóng cửa (`CLOSING_HOUR`, mặc định 22h): sau giờ này có **danh sách rút kệ** cho các lô hết ngày bán. Nhân viên ghi **số thực gỡ** (phiếu không hiện số trên sổ). Xác nhận xong lô chuyển `PULLED`: không còn là tồn bán được, không tính vào đơn đặt hàng, có ghi nhật ký.
- Store Manager duyệt **bút toán ghi hủy** (`DISPOSE`) theo số thực gỡ. Phần chênh với sổ ghi `ADJUST` lý do hao hụt, lô đóng hẳn. Lô quá ngày bán cuối mà chưa ai xác nhận gỡ vẫn được đề xuất ghi hủy (theo số sổ, có cảnh báo); SM sửa số nhỏ hơn thì phần còn lại cũng ghi hao hụt, không còn nằm trên sổ để bị đề xuất lại mãi.

### Trả nhà cung cấp: vòng đời phiếu trả (`services/returns.py`)

Tiền chỉ có khi đối tác xác nhận. Phiếu trả đi qua `REQUESTED → CONFIRMED → PICKED_UP → CREDITED`, hoặc `REFUSED`.

- **Duyệt đề xuất trả hàng**: phần hàng trả được tách thành lô `RETURN_PENDING` (không bán, không tính tồn), email gửi NCC. **Chưa ghi tiền**: lợi nhuận gộp không đổi tại thời điểm duyệt.
- **NCC đã lấy hàng**: Store Manager nhập số NCC thực nhận. Lúc này mới ghi `RETURN`. Với `CREDIT` là tiền hoàn theo tỷ lệ thỏa thuận (chờ NCC trả hoặc trừ vào đơn sau, SM đánh dấu "đã nhận tiền" để đóng phiếu). Với `EXCHANGE` là lô hàng đổi giá vốn 0, HSD mới; phiếu đóng ngay. Phần NCC không nhận quay lại bán.
- **NCC từ chối**: lô quay lại bán và hệ thống xét lại phương án giảm giá (tạo đề xuất nếu có lợi).
- Bản tin nhắc phiếu đã gửi từ 5 ngày mà NCC chưa lấy hàng: trong lúc đó hàng vẫn nằm ở cửa hàng.
- Đây là thao tác của Store Manager (có nhật ký), không phải của agent; agent chỉ xem được trạng thái phiếu.

### Hủy có lý do

Mọi bút toán hủy có `reason`: `EXPIRED` (hết hạn), `DAMAGED` (vỡ, móp), `SPOILED` (hỏng do bảo quản, tủ mát), `SUPPLIER_DEFECT` (lỗi NCC), `OTHER`. Nhân viên báo hủy hàng vỡ, hỏng theo lô kèm lý do (trang Hàng cận date hoặc chat); đây là đề xuất, SM duyệt mới trừ tồn. Báo cáo chi phí tách hủy theo lý do: tủ mát hỏng và đặt dư là hai vấn đề khác nhau.

### Nhận hàng (`services/receiving.py`)

- Một dòng PO nhận được nhiều cặp (số lượng, HSD); mỗi cặp thành một lô.
- **Từ chối tại cửa** (`rejected_qty` + lý do: móp, date ngắn, sai hàng). Sau khi ký nhận, rủi ro thuộc về cửa hàng.
- **Chuẩn nhận hàng**: lô phải còn ≥ 2/3 vòng đời (`RECEIVE_MIN_REMAINING_LIFE_PCT`). Dưới chuẩn thì mặc định bị chặn; chỉ Store Manager nhận được (tick xác nhận, có ghi nhật ký).
- **Giao thiếu** được lưu theo dòng (`short_qty`), hiện trong bản tin. Không tạo đơn bù; lần đặt sau engine tự tính lại.
- **Giao dư** quá 10% hoặc quá một quy cách (lấy mức lớn hơn) cần Store Manager xác nhận.
- **Giá hóa đơn** khác PO: nhập `actual_unit_cost`, lô dùng giá thực và hệ thống cảnh báo chênh lệch.
- Chưa hỗ trợ nhận hàng ngoài đơn.

### Đọc ảnh tem HSD (`agent/vision.py`)

Model chỉ đọc chữ in trên bao bì; việc hiểu ngày (ngày trước tháng, chỉ có tháng/năm thì lấy cuối tháng) do code tất định làm. Không đọc được HSD thì trả rỗng và không bao giờ lấy NSX thay thế. Kết quả chỉ điền sẵn ô HSD, người nhận hàng vẫn phải đối chiếu và xác nhận; ảnh không được lưu. Đã thử trên ảnh tem chụp thử, cần kiểm tra thêm với nhiều loại bao bì thực tế.

### Bản tin đầu ngày theo vai trò (`services/briefing.py`)

Bản tin dựng thẳng từ DB, không qua LLM. Mỗi mục có mức `action` (cần quyết), `warn` (cần để ý) hoặc `info` (việc trong ngày).

- **Phân vai:** chỉ Store Manager được duyệt, nên với nhân viên mục đề xuất chờ duyệt là `info` ("đang chờ Store Manager duyệt"), không phải việc của họ. Các việc của ca (rút kệ, kiểm date, kiểm kê, nhận hàng) giữ nguyên cho mọi vai trò.
- **Nhà cung cấp đến lịch đặt:** một NCC thì ghi tên; nhiều NCC thì gộp thành "N nhà cung cấp đến lịch đặt hàng hôm nay", danh sách tên để ở phần chi tiết.
- **Lô có nguy cơ hủy trong 3 ngày:** giá vốn rủi ro chỉ cộng đúng các lô được đếm (không lẫn lô trạng thái OK), để số lô và số tiền cùng một tập.

### Việc làm trong chat

Chat là nơi làm việc chính; người dùng chỉ tự thao tác những việc bắt buộc phải do người làm (duyệt, đếm, nhập HSD, xác nhận gỡ kệ).

- Khi người dùng muốn **làm** một việc (duyệt, xử lý cận date, nhận hàng, trả NCC, đếm, kiểm date, rút kệ), agent mở **thẻ việc** tương ứng thay vì mô tả. Thẻ tự tải số liệu hiện tại; mọi nút trên thẻ đi qua REST có kiểm quyền, giống các trang dữ liệu.
- **Đặt hàng theo lời** ("đặt thêm 50…", "soạn tờ trình đặt…", "gửi email bảo NCC giao thêm") luôn thành đề xuất đặt hàng thật: thêm vào đơn chờ duyệt của NCC đó nếu có, không thì tạo đơn mới rồi sửa. Agent không viết đơn hay email dạng văn bản tự do, không bịa địa chỉ, ngày, và không bảo Store Manager tự liên hệ NCC: đơn chỉ gửi đi sau khi duyệt.
- **"Hôm nay nên đặt gì":** agent liệt kê mọi đơn đặt hàng đang chờ duyệt trước, chỉ tạo đơn cho NCC đến lịch mà chưa có đơn.
- **Tồn sau khi hàng về** = các lô còn bán được vào ngày hàng về + số đặt. Lô hết ngày bán trước ngày hàng về (ví dụ hết hôm nay, hàng về mai) không được cộng.
- **Đơn vị:** danh mục không có đơn vị tính, nên agent ghi số kèm "sản phẩm", không tự đặt ra "thùng", "gói".

## 4. Định nghĩa KPI (`kpi.py`)

| KPI | Công thức |
|---|---|
| Tỷ lệ hủy | giá vốn hàng hủy / (giá vốn hàng bán + giá vốn hàng hủy) |
| Tỷ lệ hết hàng | nhu cầu hụt / (đã bán + nhu cầu hụt) |
| Lợi nhuận gộp sau hủy | doanh thu − giá vốn bán − giá vốn hủy − giá vốn hàng trả + tiền NCC hoàn − hao hụt. Hàng trả và tiền hoàn chỉ tính khi NCC đã lấy hàng |
| Số ngày tồn | tồn kho trung bình (giá vốn) / giá vốn bán trung bình mỗi ngày. Tồn trung bình lấy từ **ảnh chụp tồn cuối ngày** (`inventory_snapshots`) trong đúng kỳ, nên kỳ trước không còn dùng tồn hôm nay |
| GMROI | lợi nhuận gộp / tồn kho trung bình theo giá vốn, trong kỳ: mỗi đồng vốn nằm trong hàng sinh ra bao nhiêu lãi gộp |
| Điểm NCC | trên các đơn đến hạn giao trong kỳ: tỷ lệ giao đủ, tỷ lệ đúng hẹn, số lần giao date ngắn, số đơn vị bị từ chối tại cửa |
| Mức tin cậy của agent | tỷ lệ đề xuất được duyệt, tỷ lệ bị sửa, mức sửa số lượng trung bình |
| Hao hụt | điều chỉnh âm ròng theo từng (mặt hàng, phiếu), gồm kiểm kê, kiểm date và chênh lệch khi rút kệ; chuyển số giữa các lô cùng phiếu không tính. Hiện thành dòng riêng và trừ vào lợi nhuận gộp |
| Hủy theo lý do | giá vốn hủy tách theo `EXPIRED` / `DAMAGED` / `SPOILED` / `SUPPLIER_DEFECT` / `OTHER` |

Lưu ý: trong kiểm chứng hồi cứu, "nhu cầu hụt" được tính từ nhu cầu khôi phục theo giờ hết hàng của bộ dữ liệu lịch sử Thanh Lam Mart; khi vận hành thực tế hằng ngày không có cảm biến kệ, cửa hàng ước tính nhu cầu hụt từ dự báo vào những ngày hết hàng.

## 5. Kết quả kiểm chứng hồi cứu A/B (`python -m app.sim.backtest --frn`)

Chi tiết đầy đủ về dữ liệu, phương pháp và từng kịch bản nằm tại [du-bao-ml.md](du-bao-ml.md) (mục 5.6–5.8). Dưới đây là tóm tắt kết quả trên **50 tập kiểm chứng độc lập** của bộ dữ liệu Thanh Lam Mart trong 37 ngày đánh giá (27/05–02/07/2024), sau giai đoạn khởi động 60 ngày:

- **A ("kinh nghiệm"):** mức tồn mục tiêu = trung bình doanh số 4 tuần × hệ số an toàn; cuối ngày giảm 30% hàng hết hạn hôm nay.
- **B-EWMA:** Ops Chest dùng engine dự báo EWMA kết hợp newsvendor, trần HSD và sàn mức phục vụ.
- **B-ML:** Ops Chest dùng LightGBM với bộ chọn theo sai số dự báo và σ đối xứng.
- **B-gate:** Ops Chest dùng bộ chọn theo lãi ngoài mẫu (kiểm chéo 2 lần): dự báo điểm LightGBM kết hợp σ của EWMA cho nhóm mặt hàng được chọn.

**Trung vị qua 50 tập kiểm chứng:**

| Chính sách | Lãi gộp so với A | So với B-EWMA | Tỷ lệ hủy | Tỷ lệ hết hàng | Hết hàng kéo khách |
|---|---|---|---|---|---|
| **A (kinh nghiệm)** | — | — | 5,3% | 14,5% | 8,7% |
| **B-EWMA** | +4,2% | — | 5,2% | 13,6% | 3,9% |
| **B-ML** | +3,6% | −0,4% | 5,7% | **13,1%** | **2,7%** |
| **B-gate (hiện dùng)** | **+4,9%** | **+0,8%** | **4,8%** | 14,1% | 3,4% |

- `B-gate` lãi hơn A ở **76%** số tập kiểm chứng và lãi hơn `B-EWMA` ở **76%** số tập (trung vị **+0,8%**, khoảng tứ phân vị +0,0% đến +1,5%). Tại tập điểm bán chính Thanh Lam Mart (164 mặt hàng tươi), `B-gate` lãi hơn `B-EWMA` **+0,5%**.
- **Độ nhạy trên 20 tập kiểm chứng** (`B-gate` so với A):
  - Tham chiếu (khách phản ứng 50% mức tham chiếu của engine): **+5,5%** lãi gộp, hủy 4,5% so với 5,2% của A.
  - Khách phản ứng yếu hơn (25% / 12,5%): lãi vẫn đạt **+4,7%** / **+4,4%**.
  - Store Manager chỉ duyệt 80% / 60% đề xuất: lãi còn **+4,8%** / **+3,8%**.
  - Tắt sàn mức phục vụ: hết hàng tăng vọt lên **22,1%** (so với 14,9% của A) và lợi ích về lãi biến mất (**−0,5%**).

**Giới hạn cần nói rõ khi bảo vệ:**
1. Chuỗi dữ liệu lịch sử 97 ngày tập trung vào hàng tươi; giá vốn chuẩn hóa, HSD và độ co giãn giá là tham số nghiệp vụ được thiết lập nhất quán chứ chưa có log chiết khấu theo từng lô trong quá khứ.
2. Baseline A là heuristic hợp lý (đạt tỷ lệ hết hàng 14,5%, thấp hơn mức hết hàng lịch sử thực tế 19,3%), nhưng không đại diện cho hành vi của mọi quản lý cửa hàng.
3. Kịch bản tham chiếu xét trường hợp Store Manager duyệt 100% đề xuất; nếu chỉ duyệt 60%, lợi ích giảm còn +3,8%.
4. Trong kiểm chứng hồi cứu, nhà cung cấp luôn giao đủ và đúng hạn; một số quy tắc thực thi (giá trị đơn tối thiểu, trả hàng chờ NCC xác nhận) được áp dụng đầy đủ trong ứng dụng vận hành.

## 6. Tham khảo cách làm của các chuỗi

- **7-Eleven Nhật:** quản lý từng mặt hàng (tanpin kanri). Nhân viên đặt hàng theo giả thuyết về thời tiết và sự kiện; hàng tươi được giao nhiều chuyến mỗi ngày; coi trọng "chance loss" (mất doanh thu do hết hàng) ngang với hàng hủy.
- **Lawson, FamilyMart:** hệ thống AI *gợi ý* số lượng đặt, nhân viên xác nhận hoặc chỉnh lại. Đây chính là mô hình HITL mà Ops Chest đi theo.
- **Bách Hóa Xanh, Circle K (Việt Nam):** giảm giá hàng tươi cuối ngày, là cơ sở cho tính năng "giờ vàng".

## 7. Ngoài phạm vi (hướng phát triển)

- Bổ sung mô hình hao hụt vào kiểm chứng hồi cứu.
- **Kênh đặt hàng.** Cửa hàng độc lập phần lớn đặt qua Zalo, điện thoại, hoặc nhân viên bán hàng của nhà phân phối ghé theo tuyến. Hệ thống chuẩn hóa việc gửi đơn qua email nội bộ kèm PDF để lưu vết tập trung.
- **Công nợ và ngân sách nhập hàng.** Cửa hàng nhỏ bị giới hạn bởi tiền mặt nhiều hơn bởi dự báo; engine chưa có ràng buộc ngân sách.
- **Nhiều NCC cho một SKU**, giá vốn thay đổi theo thời gian, VAT.
- **Hàng ký gửi**: NCC chịu rủi ro hủy, cách đặt hàng khác hẳn.
- **Khuyến mãi của NCC** (mua 10 tặng 1) và tác động lên nhu cầu.
- **Lịch lễ ngoài Tết** (30/4, 2/9, Trung thu): hiện dựa vào giả thuyết Store Manager nhập tay.
- **Đặt hàng theo nhóm có thay thế** cho hàng tươi (hết cơm gà thì khách lấy cơm sườn). Hiện chỉ đo hết hàng cấp nhóm, chưa đổi cách đặt.
- **Ước tính hết hàng cho cửa hàng thật** từ dự báo (xem lưu ý ở mục 4).
- **Luồng thêm mặt hàng mới** với "SKU tham chiếu" để mượn dự báo bốn tuần đầu; SKU chưa có lịch sử hiện có dự báo bằng 0 nên không được đề xuất đặt.
- **Nhận hàng ngoài đơn** và đọc hóa đơn giao hàng.
- Đọc hóa đơn giao hàng bằng ảnh (hiện chỉ đọc tem HSD từng dòng).
- Điều chuyển hàng giữa nhiều cửa hàng.
- Tích hợp POS/ERP thật.
- Tham số đặt hàng do Store Manager tự chỉnh (z, chu kỳ).
- Học hệ số co giãn từ lịch sử giảm giá có kiểm soát.
