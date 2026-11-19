"""Cầu nối một chiều Ops Chest → Retail-AI (giai đoạn 1, demo).

Bridge không import code của Ops Chest hay Retail-AI: nó đọc REST của Ops Chest, đọc file catalog WinMart và
file FRN (chỉ đọc), rồi ghi file `ops_feed.json` theo hợp đồng v1 và các bảng feed có sẵn của Retail-AI.
"""

__version__ = "0.1.0"
