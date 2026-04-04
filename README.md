# Moodle Time Tracking Engine

Tính giờ học sinh trên Moodle dựa trên site-level logs, với adaptive threshold,
anomaly detection, cross-validation, và full audit trail.

## Cấu trúc thư mục

```
moodle_time_tracker/
│
├── README.md                       # File này — hướng dẫn sử dụng
├── requirements.txt                # Python dependencies
├── setup.py                        # Package setup (optional)
├── run.py                          # Entry point chính — chạy file này
│
├── config/
│   └── default.yaml                # Config mặc định (threshold, bonus, filters)
│
├── src/
│   └── moodle_tracker/
│       ├── __init__.py
│       │
│       ├── core/                   # Business logic chính
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
│       │   └── exporter.py         # Export CSV, JSON evidence
│       │
│       ├── utils/                  # Shared utilities
│       │   ├── __init__.py
│       │   └── models.py           # Data models (LogEntry, Session, Config, etc.)
│       │
│       └── engine.py               # Main orchestrator — chạy full pipeline
│
├── tests/                          # Unit tests
│   ├── __init__.py
│   ├── test_parser.py
│   ├── test_session_detector.py
│   └── test_anomaly_detector.py
│
├── data/
│   ├── input/                      # Đặt file CSV logs vào đây
│   │   └── .gitkeep
│   └── output/                     # Reports được xuất ra đây
│       └── .gitkeep
│
└── docs/
    └── architecture.md             # Tài liệu kiến trúc chi tiết
```

## Yêu cầu hệ thống

- Python >= 3.10
- Không cần database — xử lý hoàn toàn trên file CSV
- Không cần internet — offline processing

## Cài đặt

### Option 1: Cài trực tiếp (đơn giản nhất)

```bash
# 1. Clone hoặc copy project
git clone <repo-url> moodle_time_tracker
cd moodle_time_tracker

# 2. Tạo virtual environment
python3 -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# 3. Cài dependencies
pip install -r requirements.txt
```

### Option 2: Cài như package (cho integration)

```bash
cd moodle_time_tracker
pip install -e .
```

## Sử dụng

### 1. Chuẩn bị data

Download logs từ Moodle:
- Vào **Site administration → Reports → Logs**
- Chọn **All participants**, **All days**, **All activities**, **All actions**
- Quan trọng: chọn **Site logs** (không phải course-level)
- Click **Get these logs** → Download CSV
- Đặt file CSV vào `data/input/`

### 2. Chạy với config mặc định

```bash
# Từ thư mục gốc project
python run.py data/input/logs.csv
```

Output sẽ được tạo trong `data/output/`:
```
data/output/
├── report_per_user.csv            # Tổng giờ mỗi student
├── report_per_user_course.csv     # Giờ mỗi student × course
├── report_sessions.csv            # Chi tiết từng session
├── report_anomalies.csv           # Danh sách sessions bất thường
└── evidence_audit_trail.json      # Full audit trail cho minh chứng
```

### 3. Chạy với custom config

```bash
# Sửa config trong config/default.yaml rồi chạy
python run.py data/input/logs.csv --config config/default.yaml

# Hoặc override trực tiếp qua CLI
python run.py data/input/logs.csv \
    --threshold 1800 \
    --media-threshold 3600 \
    --max-bonus 300 \
    --min-session 60 \
    --output data/output
```

### 4. Chạy trong Python code (programmatic)

```python
from src.moodle_tracker.engine import MoodleTimeTracker
from src.moodle_tracker.utils.models import Config

config = Config(
    default_threshold_sec=1800,     # 30 phút
    media_threshold_sec=3600,       # 60 phút cho video/H5P
    max_bonus_sec=300,              # 5 phút cap
    min_session_sec=60,             # Loại session < 1 phút
    min_events_per_session=2,       # Loại 1-click sessions
)

tracker = MoodleTimeTracker(config)
result = tracker.process('data/input/logs.csv')

# result['by_user']         → dict per-user summaries
# result['by_user_course']  → list per-user-course breakdowns
# result['sessions']        → list Session objects
# result['evidence']        → list audit trail dicts
# result['summary']         → overall stats
```

### 5. Chạy tests

```bash
python -m pytest tests/ -v
```

## Giải thích config parameters

| Parameter | Default | Ý nghĩa |
|-----------|---------|---------|
| `default_threshold_sec` | 1800 (30m) | Gap tối đa giữa 2 events để coi cùng session |
| `media_threshold_sec` | 3600 (60m) | Threshold cao hơn cho H5P/Page/Video content |
| `max_bonus_sec` | 300 (5m) | Bonus tối đa cộng vào cuối mỗi session |
| `min_session_sec` | 60 (1m) | Session ngắn hơn bị loại |
| `min_events_per_session` | 2 | Session 1-click bị loại |
| `max_events_per_hour` | 200 | Flag anomaly nếu vượt |
| `min_gap_std_threshold` | 1.5 | Flag auto-refresh nếu std(gaps) < X |
| `max_ips_per_session` | 3 | Flag nếu quá nhiều IPs |
| `media_components` | H5P, Page, URL, File | Components dùng media_threshold |

## Đọc output reports

### report_per_user.csv
Mỗi dòng = 1 student. Cột **Status**:
- `CLEAN` — không có anomaly nào
- `HAS ANOMALIES` — có flags nhưng confidence vẫn ok
- `REVIEW REQUIRED` — confidence thấp, cần teacher xác nhận

### report_anomalies.csv
Chỉ chứa sessions bị flag. Anomaly types:
- `auto_refresh` — gaps đều đặn bất thường (bot/auto-reload)
- `excessive_events` — quá nhiều events/giờ
- `single_activity_loop` — >90% events trên 1 activity
- `multi_ip` — nhiều IP trong 1 session

### evidence_audit_trail.json
Full evidence cho audit: mỗi session có config_snapshot, first/last event,
course breakdown, confidence score. Dùng cho compliance reporting.
