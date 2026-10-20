"""Cấu hình dùng chung cho mọi cấu hình A, B, C: đường dẫn, bộ nhãn, seed."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "processed_v5" / "data_v1"   # bộ dữ liệu chốt 19/10/2026
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "reports"

LABELS = ["find_restaurant", "book_restaurant", "find_hotel", "book_hotel",
          "find_train", "book_train", "NONE"]
SEED = 42
