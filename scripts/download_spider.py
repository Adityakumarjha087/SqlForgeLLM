"""Download Spider (questions, gold SQL, SQLite databases) into data/raw.

Primary source is a Hugging Face mirror of the official ``spider_data.zip``.
If it is unavailable, download manually from the official site
(https://yale-lily.github.io/spider -> Google Drive link), place the zip at
data/raw/spider_data.zip and re-run this script to extract it.

Usage: uv run python scripts/download_spider.py
"""

import sys
import zipfile
from pathlib import Path

from huggingface_hub import hf_hub_download
from pydantic import BaseModel

from sqlforge.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


class DataConfig(BaseModel):
    hf_repo: str
    zip_name: str
    raw_dir: str
    processed_dir: str
    include_train_others: bool
    max_schema_chars: int
    exec_timeout_s: float
    exec_row_limit: int
    seed: int


def main() -> None:
    cfg = load_config(REPO_ROOT / "configs" / "data.yaml", DataConfig)
    raw_dir = REPO_ROOT / cfg.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / cfg.zip_name
    extracted_marker = raw_dir / "spider_data" / "dev.json"

    if extracted_marker.exists():
        print(f"Already extracted at {extracted_marker.parent}")
        return

    if not zip_path.exists():
        print(f"Downloading {cfg.zip_name} from {cfg.hf_repo} ...")
        try:
            downloaded = hf_hub_download(
                repo_id=cfg.hf_repo,
                filename=cfg.zip_name,
                repo_type="dataset",
                local_dir=raw_dir,
            )
            zip_path = Path(downloaded)
        except Exception as err:  # noqa: BLE001 - we want a helpful exit, whatever failed
            sys.exit(
                f"Download failed ({err}).\n"
                "Manual fallback: get spider_data.zip from the official site "
                "(https://yale-lily.github.io/spider), place it at "
                f"{zip_path}, then re-run this script."
            )

    print(f"Extracting {zip_path} ...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(raw_dir)
    if not extracted_marker.exists():
        sys.exit(f"Extraction finished but {extracted_marker} is missing - unexpected zip layout.")
    n_dbs = len(list((raw_dir / "spider_data" / "database").iterdir()))
    print(f"Done: {extracted_marker.parent} ({n_dbs} databases)")


if __name__ == "__main__":
    main()
