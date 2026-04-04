"""
Data models dùng chung trong toàn bộ pipeline.

Tất cả dataclasses ở đây đều serializable cho JSON evidence export.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
from enum import Enum


# =============================================================================
# CONFIG
# =============================================================================

@dataclass
class Config:
    """
    Tất cả parameters ảnh hưởng đến kết quả tính giờ.
    Lưu vào evidence report dưới dạng config_snapshot.
    """
    # Session detection
    default_threshold_sec: int = 1800
    media_threshold_sec: int = 3600
    max_bonus_sec: int = 300
    min_session_sec: int = 60
    min_events_per_session: int = 2

    # Anomaly detection
    max_events_per_hour: int = 200
    min_gap_std_threshold: float = 1.5
    auto_refresh_tolerance_sec: float = 2.0
    max_ips_per_session: int = 3

    # Content classification
    media_components: tuple = ('H5P', 'Page', 'URL', 'File')
    exclude_event_names: tuple = (
        'User login failed',
        'Log report viewed',
        'Live logs',
    )

    # Reporting
    moodle_base_url: str = ''

    def to_dict(self) -> dict:
        d = asdict(self)
        d['media_components'] = list(d['media_components'])
        d['exclude_event_names'] = list(d['exclude_event_names'])
        return d

    @classmethod
    def from_yaml(cls, path: str) -> 'Config':
        """Load config từ YAML file."""
        try:
            import yaml
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
            session = data.get('session', {})
            anomaly = data.get('anomaly', {})
            content = data.get('content', {})
            return cls(
                default_threshold_sec=session.get('default_threshold_sec', 1800),
                media_threshold_sec=session.get('media_threshold_sec', 3600),
                max_bonus_sec=session.get('max_bonus_sec', 300),
                min_session_sec=session.get('min_session_sec', 60),
                min_events_per_session=session.get('min_events_per_session', 2),
                max_events_per_hour=anomaly.get('max_events_per_hour', 200),
                min_gap_std_threshold=anomaly.get('min_gap_std_threshold', 1.5),
                auto_refresh_tolerance_sec=anomaly.get('auto_refresh_tolerance_sec', 2.0),
                max_ips_per_session=anomaly.get('max_ips_per_session', 3),
                media_components=tuple(content.get('media_components', ['H5P', 'Page', 'URL', 'File'])),
                exclude_event_names=tuple(content.get('exclude_event_names', [])),
                moodle_base_url=(
                    data.get('reporting', {}).get('moodle_base_url')
                    or data.get('moodle', {}).get('base_url', '')
                ),
            )
        except ImportError:
            raise ImportError("pip install pyyaml to use YAML config")


# =============================================================================
# LOG ENTRY
# =============================================================================

@dataclass
class LogEntry:
    """1 dòng log đã parse từ CSV — đơn vị nhỏ nhất."""
    timestamp: datetime
    unix_ts: float
    user_id: str
    user_name: str
    event_context: str
    component: str
    event_name: str
    description: str
    origin: str
    ip_address: str
    course_id: Optional[str] = None
    course_name: Optional[str] = None
    course_module_id: Optional[str] = None
    is_media: bool = False


# =============================================================================
# ANOMALY
# =============================================================================

class AnomalyType(Enum):
    AUTO_REFRESH = "auto_refresh"
    BOT_PATTERN = "bot_pattern"
    EXCESSIVE_EVENTS = "excessive_events"
    MULTI_IP = "multi_ip"
    SINGLE_ACTIVITY_LOOP = "single_activity_loop"
    SESSION_TOO_LONG = "session_too_long"


# =============================================================================
# SESSION
# =============================================================================

@dataclass
class Session:
    """1 session hoàn chỉnh sau detection + enrichment."""
    session_id: int
    user_id: str
    user_name: str
    start_time: datetime
    end_time: datetime
    raw_duration_sec: float
    bonus_sec: float
    total_duration_sec: float
    event_count: int
    events: list                        # List[LogEntry]
    ips: set                            # Unique IPs
    confidence_score: float = 0.5
    threshold_used_sec: int = 0
    anomaly_flags: list = field(default_factory=list)
    course_breakdown: dict = field(default_factory=dict)


# =============================================================================
# AGGREGATION OUTPUT
# =============================================================================

@dataclass
class CourseTime:
    """Thời gian 1 user × 1 course (aggregated từ nhiều sessions)."""
    user_id: str
    user_name: str
    course_name: str
    total_sec: float
    session_count: int
    event_count: int
    avg_confidence: float
    anomaly_count: int
