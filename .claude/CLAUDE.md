# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install pyyaml   # required for --config flag

# Single day
python run.py data/input/2026/03/2026-03-29.csv --config config/default.yaml

# Full month (batch — processes all *.csv in dir, auto-generates monthly summary)
python run.py --dir data/input/2026/03 --config config/default.yaml

# Programmatic
from src.moodle_tracker.engine import MoodleTimeTracker
from src.moodle_tracker.utils.models import Config
tracker = MoodleTimeTracker(Config.from_yaml('config/default.yaml'))
result = tracker.process('data/input/logs.csv')
```

Input CSVs must be named `YYYY-MM-DD.csv` — the date is extracted from the filename for log URL generation and monthly grouping.

## Architecture

The engine runs a **6-phase pipeline** orchestrated by `engine.py`:

| Phase | Module                                          | Input → Output                                              |
| ----- | ----------------------------------------------- | ----------------------------------------------------------- |
| 1     | `core/parser.py`                                | CSV file → `LogEntry[]`                                     |
| 2     | `core/session_detector.py`                      | `LogEntry[]` → `Session[]` (site-level, adaptive threshold) |
| 3     | `core/anomaly_detector.py`                      | `Session[]` → `Session[]` (with `anomaly_flags`)            |
| 4     | `core/course_attributor.py`                     | `Session[]` → `Session[]` (with `course_breakdown`)         |
| 5     | `core/cross_validator.py`                       | `Session[]` → `Session[]` (with `confidence_score`)         |
| 6     | `reports/aggregator.py` + `reports/exporter.py` | `Session[]` → CSV reports                                   |

All shared data structures live in `utils/models.py`: `Config`, `LogEntry`, `Session`, `AnomalyType`.

## Key Design Decisions

**Session detection is site-level**, not per-course. A student's full day of activity is segmented into sessions by gap thresholds, then time is attributed to courses in Phase 4. This avoids double-counting cross-course activity.

**Two gap thresholds**: `default_threshold_sec` for regular content, `media_threshold_sec` (higher) for H5P/Page/URL/File components to avoid splitting sessions during long video watches.

**Bonus time**: Each session gets a bonus appended to its end — `min(median_gap_in_session, max_bonus_sec)` — self-adjusting to the student's actual click cadence rather than a fixed value.

**Anomaly flags** are dicts with `type`, `severity`, and `detail` keys, stored on `Session.anomaly_flags`. Types are defined as `AnomalyType` enum in `models.py`. Current types: `auto_refresh`, `excessive_events`, `single_activity_loop`, `multi_ip`, `session_too_long`.

**`session_too_long`** flags sessions exceeding `config.max_session_hours` (default 8h, configurable via `anomaly.max_session_hours` in YAML).

## Output Files

**Single-file mode** produces `report_per_user.csv`, `report_per_user_course.csv`, `report_sessions.csv`, `report_anomalies.csv`, `evidence_audit_trail.csv`.

**Batch `--dir` mode** (monthly workflow) only produces:

- `data/output/{year}/{mm}/detail_{year}-{mm}.csv` — one row per user per day, sorted by User Name + Date
- `data/output/{year}/{mm}/monthly_summary_{year}-{mm}.csv` — aggregated by user for the month

`skip_global=True` is passed in batch mode to suppress the per-file global reports.

## Config

`config/default.yaml` is the single source of truth. All values have defaults in `Config` dataclass (fallbacks used when no YAML is provided). CLI flags `--threshold`, `--media-threshold`, `--max-bonus`, `--min-session`, `--min-events` override individual values after YAML is loaded.

## Docs, Comments

- Use English
