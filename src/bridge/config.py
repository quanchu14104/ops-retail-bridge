"""Cấu hình bridge: biến môi trường, có thể đặt trong `bridge/.env` (biến môi trường thật được ưu tiên)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Một repo duy nhất: Ops Chest ở bridge/ops_chest/, Retail-AI ở bridge/Retail-AI-/


def load_env_file(path: Path) -> dict[str, str]:
    """Đọc file .env tối giản: KEY=VALUE, bỏ dòng trống và chú thích, bỏ ngoặc kép bao ngoài."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def _path(value: str) -> Path:
    """Đường dẫn tương đối tính từ thư mục bridge/ (vd ops_chest/... là Ops Chest trong repo)."""
    p = Path(value)
    return p if p.is_absolute() else (ROOT / p).resolve()


@dataclass(frozen=True)
class Config:
    ops_chest_url: str
    ops_chest_user: str
    ops_chest_password: str
    retail_database_url: str
    winmart_catalog_path: Path
    frn_data_path: Path
    frn_store_id: int
    store_code: str
    kiosk_id: str
    store_address: str
    store_phone: str
    ops_feed_path: Path
    overrides_path: Path
    crosswalk_path: Path
    timezone: str

    @classmethod
    def load(cls, env: dict[str, str] | None = None, env_file: Path | None = None) -> Config:
        values = load_env_file(env_file or ROOT / ".env")
        values.update(os.environ if env is None else env)

        def get(key: str, default: str) -> str:
            v = values.get(key, "")
            return v if v.strip() else default

        return cls(
            ops_chest_url=get("OPS_CHEST_URL", "http://127.0.0.1:8000").rstrip("/"),
            ops_chest_user=get("OPS_CHEST_USER", "nhanvien"),
            ops_chest_password=get("OPS_CHEST_PASSWORD", "nhanvien123"),
            retail_database_url=get("RETAIL_DATABASE_URL", "postgresql://retail:retail@localhost:5432/retail"),
            winmart_catalog_path=_path(get("WINMART_CATALOG_PATH", "Retail-AI-/data/winmart_products.json")),
            frn_data_path=_path(get("FRN_DATA_PATH", "ops_chest/backend/app/sim/data/frn/stores_daily.csv.gz")),
            frn_store_id=int(get("FRN_STORE_ID", "18")),
            store_code=get("STORE_CODE", "WMP-DEMO-01"),
            kiosk_id=get("KIOSK_ID", "kiosk-01"),
            store_address=get("STORE_ADDRESS", "12 Phố Demo, Q. Hoàn Kiếm, Hà Nội (giả định)"),
            store_phone=get("STORE_PHONE", "024 0000 0000"),
            ops_feed_path=_path(get("OPS_FEED_PATH", "out/ops_feed.json")),
            overrides_path=_path(get("OVERRIDES_PATH", "out/ops_catalog_overrides.json")),
            crosswalk_path=_path(get("CROSSWALK_PATH", "data/crosswalk.csv")),
            timezone=get("TIMEZONE", "Asia/Ho_Chi_Minh"),
        )
