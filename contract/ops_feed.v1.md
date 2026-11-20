# Hợp đồng `ops-feed` v1

File JSON một chiều **Ops Chest → kiosk Retail-AI**, do `bridge sync` ghi (mặc định `bridge/out/ops_feed.json`) và
`OpsOverlayRepository` của Retail-AI đọc. Ví dụ đầy đủ: [`ops_feed.example.json`](ops_feed.example.json).

## Nguyên tắc

- **Một chủ cho mỗi trường.** Tồn bán được, HSD theo lô, giá bán thường và giảm giá cận date của 164 mặt hàng đã
  ánh xạ thuộc Ops Chest. Danh tính sản phẩm (tên, ảnh, barcode, danh mục) và vị trí kệ vẫn thuộc catalog WinMart
  và planogram của Retail-AI; feed không chứa các trường đó.
- **Danh sách trường là tuyệt đối.** Bên ghi dựng từng phần tử từ đúng các khoá dưới đây, theo đúng thứ tự, và
  kiểm tra lại trước khi ghi. Không bao giờ xuất: `unit_cost`, nguồn hàng (`supplier`), `value_at_risk`,
  `expected_*` (dự báo), `options` (phương án xử lý), thỏa thuận với nguồn hàng.
- **Ghi atomic.** Ghi file tạm cùng thư mục rồi `os.replace`. Bên đọc không bao giờ thấy file dở dang. Trên Windows,
  `os.replace` thất bại khi bên đọc đang mở file, nên bên ghi thử lại vài lần; vẫn thất bại thì giữ feed cũ.
- **Ops Chest không phản hồi** thì bridge không ghi đè feed cũ và trả exit code khác 0. Bên đọc vẫn áp feed cũ;
  `published_at` để lộ tuổi dữ liệu.
- Bên đọc gặp `contract`/`version` lạ hoặc JSON hỏng thì giữ feed hợp lệ gần nhất và ghi log.

## Phần đầu

| Khoá | Kiểu | Ý nghĩa |
|---|---|---|
| `contract` | `"ops-feed"` | Tên hợp đồng |
| `version` | `1` | Phiên bản. Đổi nghĩa trường thì tăng phiên bản |
| `published_at` | ISO 8601 có múi giờ | Thời điểm xuất (giờ thật, Asia/Ho_Chi_Minh) |
| `ops_business_date` | `YYYY-MM-DD` | Ngày nghiệp vụ của Ops Chest (đồng hồ giả lập) lúc xuất |
| `date_shift_days` | số nguyên | `shift` = ngày thật − `ops_business_date`. Mọi ngày trong feed đã cộng `shift` |
| `store_name` | chuỗi | Tên cửa hàng theo `/api/meta` của Ops Chest |
| `items` | mảng | Mỗi mặt hàng đã ánh xạ có trong Ops Chest, sắp theo `ops_sku` |

## Phần tử `items[]`

| Khoá | Kiểu | Cách tính |
|---|---|---|
| `product_id` | chuỗi | Mã WinMart (`WIN_…`) theo crosswalk |
| `ops_sku` | chuỗi | SKU Ops Chest (`F0412`) |
| `status` | `IN_STOCK` \| `OUT_OF_STOCK` \| `INACTIVE` | `INACTIVE` khi mặt hàng không còn ACTIVE trong Ops Chest. Khi đó `sellable_qty=0`, `lots=[]`, `earliest_expiry=null`, `promotion_text=null`, `sale_price_vnd=unit_price_vnd` |
| `sellable_qty` | số nguyên ≥ 0 | Tổng lô có `days_left ≥ 0`. Nếu `coverage_complete=false`: `on_hand` − lô đã quá ngày bán cuối |
| `earliest_expiry` | `YYYY-MM-DD` \| null | HSD nhỏ nhất trong các lô bán được, đã dời ngày |
| `unit_price_vnd` | số nguyên | Giá bán thường trong Ops Chest (= giá WinMart nạp lúc seed) |
| `sale_price_vnd` | số nguyên | Giá thấp nhất đang áp dụng: `unit_price × (1 − markdown)`, làm tròn 100 đồng (từ 50 đồng trở lên làm tròn lên) |
| `promotion_text` | chuỗi \| null | Vd `"Giảm 30% cho 5 sản phẩm HSD 20/11"`; nhiều mức nối bằng `"; "`, mức sâu trước |
| `coverage_complete` | bool | `false` khi tổng lô Ops Chest liệt kê (kể cả lô quá hạn) khác `on_hand` |
| `lots` | mảng | Các lô bán được, sắp theo HSD |

## Phần tử `lots[]`

| Khoá | Kiểu | Ý nghĩa |
|---|---|---|
| `qty` | số nguyên > 0 | Số lượng còn |
| `expiry` | `YYYY-MM-DD` | HSD đã dời ngày |
| `markdown_pct` | 0…1 | Mức giảm có hiệu lực lúc xuất. Ngày bán cuối và đã qua `markdown_hour` thì lấy `max(markdown_pct, evening_markdown_pct)`; ngược lại lấy `markdown_pct`. Ops Chest bản hiện tại chưa có `evening_markdown_pct` thì coi là 0 |

## Dời trục thời gian

Ops Chest chạy đồng hồ giả lập (vd 26/06/2024), kiosk dùng ngày thật. Nếu chuyển HSD nguyên gốc, kiosk coi mọi lô
là hết hạn. Bridge cộng `date_shift_days` vào mọi ngày lấy từ Ops Chest. Mốc sự kiện đã xảy ra (giờ nhận hàng) bị
chặn ở thời điểm hiện tại. Tua nhanh Ops Chest 1 ngày thì `date_shift_days` giảm 1; HSD sau khi dời vẫn nhất quán.

## Bên đọc (Retail-AI `OpsOverlayRepository`)

| Trường ProductSnapshot | Lấy từ feed |
|---|---|
| `stock` | `sellable_qty` (trừ thêm lô đã quá HSD nếu feed cũ) |
| `expiry_at` | `earliest_expiry` (bỏ lô đã quá HSD nếu feed cũ) |
| `price_vnd` | `min(unit_price_vnd, sale_price_vnd)`: giá người mua trả lúc này, cùng quy ước với hàng WinMart thường |
| `list_price_vnd` | `unit_price_vnd` (giá thường) |
| `sale_price_vnd` | `sale_price_vnd` |
| `promotion` | `promotion_text` |
| `price_quality_status` | `SALE` nếu `sale_price_vnd < unit_price_vnd`, ngược lại `NORMAL` |
| `data_timestamp` | `published_at` |
