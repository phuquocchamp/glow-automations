# Moodle Time Tracking Engine

Calculates student study hours from Moodle site-level logs, with adaptive thresholds, anomaly detection, cross-validation, and a full audit trail.

## Directory Structure

```
glow-automation/
│
├── README.md                       # This file
├── requirements.txt                # Python dependencies
├── setup.py                        # Package setup (optional)
├── run.py                          # Main entry point
│
├── config/
│   └── default.yaml                # Default config (thresholds, bonus, filters)
│
├── src/
│   └── moodle_tracker/
│       ├── __init__.py
│       │
│       ├── core/                   # Core business logic
│       │   ├── __init__.py
│       │   ├── parser.py           # Phase 1: Parse CSV logs → LogEntry objects
│       │   ├── session_detector.py # Phase 2: Site-level session detection
│       │   ├── anomaly_detector.py # Phase 3: Detect suspicious patterns
│       │   ├── course_attributor.py# Phase 4: Map session time → courses
│       │   └── cross_validator.py  # Phase 5: Quiz/SCORM cross-validation
│       │
│       ├── reports/                # Output generation
│       │   ├── __init__.py
│       │   ├── aggregator.py       # Phase 6: Aggregate sessions → summaries
│       │   └── exporter.py         # Export CSV reports and evidence
│       │
│       ├── utils/                  # Shared utilities
│       │   ├── __init__.py
│       │   └── models.py           # Data models (LogEntry, Session, Config, etc.)
│       │
│       └── engine.py               # Main orchestrator — runs the full pipeline
│
├── data/
│   ├── input/                      # Place CSV log files here
│   │   └── .gitkeep
│   └── output/                     # Generated reports are saved here
│       └── .gitkeep
│
└── docs/
    └── architecture.md             # Detailed architecture documentation
```

## Requirements

- Python >= 3.10
- No database required — fully file-based CSV processing
- No internet required — offline processing

## Installation

### Option 1: Direct install (simplest)

```bash
git clone <repo-url> glow-automation
cd glow-automation

python3 -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
pip install pyyaml              # Required for --config flag
```

Create a `.env` file for Moodle credentials:

```env
GLOW_USERNAME=your_username
GLOW_PASSWORD=your_password
```

### Option 2: Install as package (for integration)

```bash
pip install -e .
```

## Usage

### 1. Prepare data

Credentials for `crawl.py` are read from `.env` (`GLOW_USERNAME`, `GLOW_PASSWORD`).
All other settings (base URL, timezone, year/month, thresholds, anomalies, reporting) are read from `config/default.yaml`.

Download logs from Moodle:

- Go to **Site administration → Reports → Logs**
- Select **All participants**, **All days**, **All activities**, **All actions**
- Important: select **Site logs** (not course-level logs)
- Click **Get these logs** → Download CSV
- Name the file `YYYY-MM-DD.csv` and place it in `data/input/`

### 2. Run with default config

```bash
python run.py data/input/2026-03-29.csv
```

Output is saved to `data/output/`:

```
data/output/
├── report_per_user.csv            # Total hours per student
├── report_per_user_course.csv     # Hours per student × course
├── report_sessions.csv            # Individual session details
├── report_anomalies.csv           # Flagged sessions
└── evidence_audit_trail.csv       # Full audit trail for compliance
```

### 3. Run with custom config

```bash
# Edit config/default.yaml then run
python run.py data/input/2026-03-29.csv --config config/default.yaml

# Or override individual values via CLI
python run.py data/input/2026-03-29.csv \
    --threshold 1800 \
    --media-threshold 3600 \
    --max-bonus 300 \
    --min-session 60 \
    --output data/output
```

### 4. Batch mode — process a full month

```bash
python run.py --dir data/input/2026/03 --config config/default.yaml
```

Processes all `*.csv` files in the directory and automatically generates:

- `data/output/2026/03/detail_2026-03.csv` — detailed session rows
- `data/output/2026/03/monthly_summary_2026-03.csv` — aggregated by user

User identity handling:

- `User full name` is split into `PALS_ID` (first token) + `Fullname`.
- `PALS_ID` is uppercased, validated against `reporting.PALS_REGEX` in `config/default.yaml`.
- Rows with invalid `PALS_ID` are filtered out before session/report generation.

### 5. Programmatic usage

```python
from src.moodle_tracker.engine import MoodleTimeTracker
from src.moodle_tracker.utils.models import Config

config = Config(
    default_threshold_sec=1800,   # 30 min gap threshold
    media_threshold_sec=3600,     # 60 min for H5P/video content
    max_bonus_sec=300,            # 5 min bonus cap per session
    min_session_sec=60,           # Drop sessions shorter than 1 min
    min_events_per_session=2,     # Drop single-click sessions
)

tracker = MoodleTimeTracker(config)
result = tracker.process('data/input/logs.csv')

# result['by_user']         → dict of per-user summaries
# result['by_user_course']  → list of per-user-course breakdowns
# result['sessions']        → list of Session objects
# result['evidence']        → list of audit trail dicts
# result['summary']         → overall stats
```

## Config Parameters

| Parameter                    | Default              | Description                                          |
| ---------------------------- | -------------------- | ---------------------------------------------------- |
| `default_threshold_sec`      | 900 (15m)            | Max gap between two events to be in the same session |
| `media_threshold_sec`        | 1200 (20m)           | Higher threshold for H5P/Page/Video content          |
| `max_bonus_sec`              | 600 (10m)            | Max bonus added to the end of each session           |
| `min_session_sec`            | 180 (3m)             | Sessions shorter than this are discarded             |
| `min_events_per_session`     | 2                    | Sessions with fewer events are discarded             |
| `max_events_per_hour`        | 600                  | Flag anomaly if exceeded                             |
| `min_gap_std_threshold`      | 1.5                  | Flag auto-refresh if std(gaps) < X seconds           |
| `auto_refresh_tolerance_sec` | 2.0                  | Tolerance window for regularity check                |
| `max_ips_per_session`        | 3                    | Flag if session has too many unique IPs              |
| `max_session_hours`          | 8                    | Flag session as `session_too_long` if exceeded       |
| `media_components`           | H5P, Page, URL, File | Components that use `media_threshold`                |

## Reading Output Reports

### report_per_user.csv

One row per student. **Status** column values:

- `CLEAN` — no anomalies detected
- `HAS ANOMALIES` — flags present but confidence is acceptable
- `REVIEW REQUIRED` — low confidence score, needs teacher verification

### report_anomalies.csv

Contains only flagged sessions. Anomaly types:

- `auto_refresh` — abnormally regular gaps (bot/auto-reload pattern)
- `excessive_events` — too many events per hour
- `single_activity_loop` — >90% of events on the same activity
- `multi_ip` — multiple IP addresses within one session
- `session_too_long` — single session exceeds `max_session_hours` (default 8h)

### evidence_audit_trail.csv

Full evidence for auditing: each session includes a config snapshot, first/last event, course breakdown, and confidence score. Used for compliance reporting.
