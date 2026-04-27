#!/usr/bin/env python3
"""
Entry point — process Moodle logs for a full month.

Usage:
    python run.py --dir data/input/2026/03
    python run.py --dir data/input/2026/03 --config config/default.yaml
"""

import argparse
import os
import re
import sys

# Add src/ to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from moodle_tracker.engine import MoodleTimeTracker
from moodle_tracker.utils.models import Config


def parse_args():
    parser = argparse.ArgumentParser(
        description='Moodle Time Tracking Engine — calculate student study hours from site logs.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py --dir data/input/2026/03
  python run.py --dir data/input/2026/03 --config config/default.yaml
  python run.py --dir data/input/2026/03 --threshold 1800 --media-threshold 3600
        """,
    )

    parser.add_argument(
        '--dir', '-d',
        metavar='DIR',
        required=True,
        help='Directory containing *.csv log files for a month (e.g. data/input/2026/03)',
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


def process_one(csv_path: str, tracker: MoodleTimeTracker, output_dir: str):
    date_str = extract_date(csv_path)
    result = tracker.process(csv_path)
    tracker.export(result, output_dir, date_str=date_str, skip_global=True)
    return date_str


def main():
    args = parse_args()
    config = build_config(args)
    tracker = MoodleTimeTracker(config)

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

    # Clear existing detail file so re-runs don't double-append sessions
    first_date = extract_date(csv_files[0])
    if first_date:
        _year, _month, _ = first_date.split('-')
        detail_path = os.path.join(
            args.output, _year, _month, f'detail_{_year}-{_month}.csv'
        )
        if os.path.isfile(detail_path):
            os.remove(detail_path)
            print(f"  Cleared existing detail file: {detail_path}")

    print(f"\n{'='*60}")
    print(f"BATCH MODE — {len(csv_files)} files in {args.dir}")
    print(f"{'='*60}")

    last_date_str = None
    for i, csv_path in enumerate(csv_files, 1):
        print(f"\n[{i}/{len(csv_files)}] {os.path.basename(csv_path)}")
        print("-" * 60)
        try:
            date_str = process_one(csv_path, tracker, args.output)
            if date_str:
                last_date_str = date_str
        except Exception as e:
            print(f"  ✗ Error: {e}")

    # Sort combined detail rows and generate monthly summary
    if last_date_str:
        year, month, _ = last_date_str.split('-')
        print(f"\n{'='*60}")
        print(f"FINALIZING — {year}-{month}")
        print(f"{'='*60}")
        tracker.finalize_detail(year, month, args.output)
        tracker.export_monthly_summary(year, month, args.output)

    print(f"\nAll reports saved to: {os.path.abspath(args.output)}/")


if __name__ == '__main__':
    main()
