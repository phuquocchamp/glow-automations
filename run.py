#!/usr/bin/env python3
"""
Entry point — chạy file này để process Moodle logs.

Usage:
    # 1 file
    python run.py data/input/2026/03/2026-03-29.csv
    python run.py data/input/2026/03/2026-03-29.csv --config config/default.yaml

    # Cả tháng (xử lý tất cả *.csv trong thư mục, tự tạo monthly summary)
    python run.py --dir data/input/2026/03
    python run.py --dir data/input/2026/03 --config config/default.yaml
"""

import argparse
import os
import re
import sys

# Thêm src/ vào Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from moodle_tracker.engine import MoodleTimeTracker
from moodle_tracker.utils.models import Config


def parse_args():
    parser = argparse.ArgumentParser(
        description='Moodle Time Tracking Engine — tính giờ học sinh từ site logs.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py data/input/2026/03/2026-03-29.csv
  python run.py data/input/2026/03/2026-03-29.csv --config config/default.yaml
  python run.py --dir data/input/2026/03
  python run.py --dir data/input/2026/03 --config config/default.yaml
        """,
    )

    # Input: single file OR directory
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        'csv_file',
        nargs='?',
        help='Path to a single Moodle CSV log file',
    )
    input_group.add_argument(
        '--dir', '-d',
        metavar='DIR',
        help='Process all *.csv files in this directory + generate monthly summary',
    )

    parser.add_argument(
        '--output', '-o',
        default='data/output',
        help='Output directory for reports (default: data/output)',
    )
    parser.add_argument(
        '--config', '-c',
        default=None,
        help='Path to YAML config file (requires pyyaml)',
    )
    parser.add_argument(
        '--monthly',
        action='store_true',
        help='Generate monthly summary after processing (auto-enabled with --dir)',
    )

    # Override individual config params via CLI
    group = parser.add_argument_group('Config overrides (optional)')
    group.add_argument('--threshold', type=int, default=None,
                       help='Default session gap threshold in seconds')
    group.add_argument('--media-threshold', type=int, default=None,
                       help='Threshold for media content H5P/Page/Video')
    group.add_argument('--max-bonus', type=int, default=None,
                       help='Max bonus per session in seconds')
    group.add_argument('--min-session', type=int, default=None,
                       help='Min session duration to keep in seconds')
    group.add_argument('--min-events', type=int, default=None,
                       help='Min events per session to keep')

    return parser.parse_args()


def build_config(args) -> Config:
    if args.config:
        config = Config.from_yaml(args.config)
    else:
        config = Config()

    if args.threshold is not None:
        config.default_threshold_sec = args.threshold
    if args.media_threshold is not None:
        config.media_threshold_sec = args.media_threshold
    if args.max_bonus is not None:
        config.max_bonus_sec = args.max_bonus
    if args.min_session is not None:
        config.min_session_sec = args.min_session
    if args.min_events is not None:
        config.min_events_per_session = args.min_events

    return config


def extract_date(csv_path: str):
    m = re.search(r'(\d{4}-\d{2}-\d{2})', os.path.basename(csv_path))
    return m.group(1) if m else None


def process_one(csv_path: str, tracker: MoodleTimeTracker, output_dir: str, skip_global: bool = False):
    date_str = extract_date(csv_path)
    result = tracker.process(csv_path)
    tracker.export(result, output_dir, date_str=date_str, skip_global=skip_global)
    return result, date_str


def print_top_users(result: dict, n: int = 20):
    sessions = result['sessions']
    print(f"\n{'#':<4} {'User':<45} {'Hours':>7} {'Clean':>7} "
          f"{'Sess':>5} {'Conf':>6} {'Flags':>6} {'Status':<16}")
    print("-" * 100)
    for i, (uid, data) in enumerate(result['by_user'].items()):
        if i >= n:
            break
        clean_hrs = sum(
            s.total_duration_sec for s in sessions
            if s.user_id == uid and not s.anomaly_flags
        ) / 3600
        if data['anomaly_count'] > 0 and data['avg_confidence'] < 0.4:
            status = 'REVIEW REQUIRED'
        elif data['anomaly_count'] > 0:
            status = 'HAS ANOMALIES'
        else:
            status = 'CLEAN'
        print(f"{i+1:<4} {data['user_name'][:44]:<45} "
              f"{data['total_hours']:>6.1f}h "
              f"{clean_hrs:>6.1f}h "
              f"{data['session_count']:>4} "
              f"{data['avg_confidence']:>5.2f} "
              f"{data['anomaly_count']:>5} "
              f"{status:<16}")


def main():
    args = parse_args()
    config = build_config(args)
    tracker = MoodleTimeTracker(config)

    # ── Batch mode: --dir ────────────────────────────────────────────────────
    if args.dir:
        if not os.path.isdir(args.dir):
            print(f"Error: Directory not found: {args.dir}")
            sys.exit(1)

        csv_files = sorted([
            os.path.join(args.dir, f)
            for f in os.listdir(args.dir)
            if f.endswith('.csv')
        ])

        if not csv_files:
            print(f"Error: No CSV files found in {args.dir}")
            sys.exit(1)

        print(f"\n{'='*60}")
        print(f"BATCH MODE — {len(csv_files)} files in {args.dir}")
        print(f"{'='*60}")

        last_date_str = None
        for i, csv_path in enumerate(csv_files, 1):
            print(f"\n[{i}/{len(csv_files)}] {os.path.basename(csv_path)}")
            print("-" * 60)
            try:
                result, date_str = process_one(csv_path, tracker, args.output, skip_global=True)
                if date_str:
                    last_date_str = date_str
            except Exception as e:
                print(f"  ✗ Error: {e}")

        # Sort combined detail + monthly summary — tự động sau batch
        if last_date_str:
            year, month, _ = last_date_str.split('-')
            print(f"\n{'='*60}")
            print(f"FINALIZING — {year}-{month}")
            print(f"{'='*60}")
            tracker.finalize_detail(year, month, args.output)
            tracker.export_monthly_summary(year, month, args.output)

        print(f"\nAll reports saved to: {os.path.abspath(args.output)}/")
        return

    # ── Single file mode ─────────────────────────────────────────────────────
    if not os.path.isfile(args.csv_file):
        print(f"Error: File not found: {args.csv_file}")
        sys.exit(1)

    result, date_str = process_one(args.csv_file, tracker, args.output)

    if (args.monthly or args.dir) and date_str:
        year, month, _ = date_str.split('-')
        print(f"\n[Monthly] Generating summary for {year}-{month}...")
        tracker.export_monthly_summary(year, month, args.output)

    print("\nTOP 20 USERS BY TIME:")
    print_top_users(result)
    print(f"\nReports saved to: {os.path.abspath(args.output)}/")


if __name__ == '__main__':
    main()
