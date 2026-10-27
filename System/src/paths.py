"""Storage contract for the lightweight System/Data project layout."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]       # VnStockDesk/System
DESK_ROOT = PROJECT_ROOT.parent                         # VnStockDesk


def validate_data_root(value) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Đường dẫn Data phải là đường dẫn tuyệt đối.")
    path = path.resolve()
    if path in (Path(path.anchor), Path.home(), DESK_ROOT.parent.resolve()):
        raise ValueError("Không được chọn thư mục gốc hoặc thư mục người dùng.")
    if path == PROJECT_ROOT or path.is_relative_to(PROJECT_ROOT) or PROJECT_ROOT.is_relative_to(path):
        raise ValueError("Data phải nằm ngoài thư mục System.")
    return path


DEFAULT_DATA_ROOT = DESK_ROOT / "Data"
DATA_ROOT = validate_data_root(os.getenv("VNSTOCKDESK_DATA_ROOT", str(DEFAULT_DATA_ROOT)))
MARKET_DIR = DATA_ROOT / "market"
PRIVATE_DIR = DATA_ROOT / "private"
if os.getenv("VNSTOCKDESK_RUNTIME_DIR"):
    RUNTIME_DIR = Path(os.environ["VNSTOCKDESK_RUNTIME_DIR"]).expanduser().resolve()
elif os.name == "nt":
    RUNTIME_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "VnStockDesk" / "runtime"
elif sys.platform == "darwin":
    RUNTIME_DIR = Path.home() / "Library" / "Application Support" / "VnStockDesk" / "runtime"
else:
    RUNTIME_DIR = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")) / "VnStockDesk" / "runtime"
STATE_DIR = PRIVATE_DIR / "state"
STORAGE_CONFIG = PRIVATE_DIR / "storage.json"

try:
    _config = json.loads(STORAGE_CONFIG.read_text(encoding="utf-8"))
except (OSError, ValueError, TypeError):
    _config = {}

if os.getenv("VNSTOCKDESK_MARKET_DIR") or _config.get("market_dir"):
    MARKET_DIR = validate_data_root(os.getenv("VNSTOCKDESK_MARKET_DIR") or _config["market_dir"])

APP_DATA_DIR = DATA_ROOT
DATA_DIR = MARKET_DIR
RAW_DIR = MARKET_DIR / "raw"
PROCESSED_DIR = MARKET_DIR / "processed"
NEWS_DIR = MARKET_DIR / "news"
ENV_FILE = RUNTIME_DIR.parent / "private" / ".env"


def app_data_dir() -> Path:
    return DATA_ROOT


def state_dir(root=PROJECT_ROOT) -> Path:
    return STATE_DIR if Path(root).resolve() == PROJECT_ROOT else Path(root) / "state"


def data_dir(root=PROJECT_ROOT) -> Path:
    return MARKET_DIR if Path(root).resolve() == PROJECT_ROOT else Path(root) / "data"


for directory in (MARKET_DIR, RAW_DIR, PROCESSED_DIR, NEWS_DIR, PRIVATE_DIR, STATE_DIR, RUNTIME_DIR):
    directory.mkdir(parents=True, exist_ok=True)
