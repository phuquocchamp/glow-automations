#!/usr/bin/env python3
"""
Crawl Moodle log CSV theo tháng, lưu vào data/input/{year}/{mm}/{yyyy-mm-dd}.csv

Usage:
    python crawl.py                               # dùng year/month từ config
    python crawl.py --year 2026 --month 3         # override năm/tháng
    python crawl.py --force                       # re-download ngay cả khi đã có file
    python crawl.py --delay 2.0                   # delay 2s giữa mỗi request
    python crawl.py --config config/default.yaml  # chỉ định config file khác
    python crawl.py --output data/input           # chỉ định thư mục output khác
"""

import argparse
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def load_yaml(path: str) -> dict:
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        raise ImportError("pip install pyyaml")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Crawl Moodle site logs theo tháng → data/input/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crawl.py
  python crawl.py --year 2026 --month 3
  python crawl.py --force --delay 2.0
        """,
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config/default.yaml",
        help="Path to YAML config (default: config/default.yaml)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="data/input",
        help="Output directory (default: data/input)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Năm cần crawl (default: lấy từ config general.year)",
    )
    parser.add_argument(
        "--month",
        type=int,
        default=None,
        help="Tháng cần crawl (default: lấy từ config general.month)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download ngay cả khi file đã tồn tại",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay (giây) giữa mỗi request (default: 1.0)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    load_dotenv()

    if not os.path.isfile(args.config):
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)

    cfg = load_yaml(args.config)

    # --- Resolve year / month ---
    year = args.year or cfg.get("general", {}).get("year")
    month = args.month or cfg.get("general", {}).get("month")

    if not year or not month:
        print(
            "Error: Không tìm được year/month — khai báo trong config general.year/month hoặc dùng --year/--month."
        )
        sys.exit(1)

    year = int(year)
    month = int(month)

    # --- Moodle credentials ---
    moodle_cfg = cfg.get("moodle", {})
    base_url = moodle_cfg.get("base_url", "").strip()
    username = os.getenv("GLOW_USERNAME").strip()
    password = os.getenv("GLOW_PASSWORD").strip()
    tz_offset = int(moodle_cfg.get("timezone_offset", 7))

    if not base_url or not username or not password:
        print(
            "Error: Thiếu thông tin kết nối Moodle.\n"
            "Kiểm tra config moodle.base_url và .env (GLOW_USERNAME/GLOW_PASSWORD) "
            "hoặc fallback config moodle.username/moodle.password."
        )
        sys.exit(1)

    # --- Run ---
    from moodle_tracker.crawler import MoodleCrawler

    crawler = MoodleCrawler(base_url, username, password, tz_offset)
    crawler.login()
    crawler.crawl_month(
        year, month, args.output, force=args.force, delay_sec=args.delay
    )

    print(f"\nFiles saved to: {os.path.abspath(args.output)}/{year}/{month:02d}/")


if __name__ == "__main__":
    main()
