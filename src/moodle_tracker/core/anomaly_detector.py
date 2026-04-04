"""
Phase 3: Detect suspicious patterns trong sessions.

Anomaly types:
  - auto_refresh: gaps đều đặn bất thường (H5P heartbeat, Page auto-reload)
  - excessive_events: > N events/giờ (auto-refresh, bot)
  - single_activity_loop: >90% events trên cùng 1 activity
  - multi_ip: >N unique IPs trong 1 session
"""

import statistics
from collections import Counter

from ..utils.models import Config, Session, AnomalyType


class AnomalyDetector:

    def __init__(self, config: Config):
        self.config = config

    def analyze(self, sessions: list[Session]) -> list[Session]:
        """Run tất cả anomaly checks, gắn flags vào mỗi session."""
        flagged = 0
        for s in sessions:
            flags = []
            flags.extend(self._check_session_too_long(s))
            flags.extend(self._check_auto_refresh(s))
            flags.extend(self._check_excessive_events(s))
            flags.extend(self._check_multi_ip(s))
            flags.extend(self._check_single_activity_loop(s))
            s.anomaly_flags = flags
            if flags:
                flagged += 1

        print(f"[AnomalyDetector] Flagged {flagged}/{len(sessions)} sessions")
        return sessions

    def _check_auto_refresh(self, s: Session) -> list[dict]:
        """
        Detect auto-refresh: gaps đều đặn ± tolerance.

        Phát hiện thực tế:
          - User 8054: Page module auto-reload mỗi 60.0s exact
          - User 7263: H5P heartbeat mỗi 10.0s
          - User 8527: Fast Assignment refresh mỗi 11s
        """
        if len(s.events) < 5:
            return []

        gaps = [
            s.events[i].unix_ts - s.events[i - 1].unix_ts
            for i in range(1, len(s.events))
        ]
        if len(gaps) < 3:
            return []

        std = statistics.stdev(gaps)
        mean_gap = statistics.mean(gaps)

        # Check 1: extremely low std dev (nearly identical gaps)
        if std < self.config.min_gap_std_threshold and mean_gap < 120:
            return [{
                'type': AnomalyType.AUTO_REFRESH.value,
                'severity': 'high',
                'detail': (
                    f'Gaps extremely regular: mean={mean_gap:.1f}s, '
                    f'std={std:.2f}s across {len(gaps)} gaps'
                ),
            }]

        # Check 2: high regularity ratio (>85% gaps within tolerance of mean)
        if mean_gap > 0 and len(gaps) >= 10:
            tol = self.config.auto_refresh_tolerance_sec
            regular_count = sum(1 for g in gaps if abs(g - mean_gap) <= tol)
            regularity = regular_count / len(gaps)
            if regularity > 0.85:
                return [{
                    'type': AnomalyType.AUTO_REFRESH.value,
                    'severity': 'medium',
                    'detail': (
                        f'{regularity:.0%} of gaps within '
                        f'±{tol}s of mean {mean_gap:.1f}s'
                    ),
                }]

        return []

    def _check_excessive_events(self, s: Session) -> list[dict]:
        """Flag sessions có > max_events_per_hour."""
        if s.total_duration_sec < 60:
            return []
        rate = s.event_count / (s.total_duration_sec / 3600)
        if rate > self.config.max_events_per_hour:
            return [{
                'type': AnomalyType.EXCESSIVE_EVENTS.value,
                'severity': 'medium',
                'detail': f'{rate:.0f} events/hr (max={self.config.max_events_per_hour})',
            }]
        return []

    def _check_multi_ip(self, s: Session) -> list[dict]:
        """Flag sessions với nhiều IP addresses."""
        if len(s.ips) > self.config.max_ips_per_session:
            return [{
                'type': AnomalyType.MULTI_IP.value,
                'severity': 'low',
                'detail': f'{len(s.ips)} IPs: {", ".join(list(s.ips)[:5])}',
            }]
        return []

    def _check_session_too_long(self, s: Session) -> list[dict]:
        """Flag sessions longer than 6 hours — unlikely genuine study."""
        hours = s.total_duration_sec / 3600
        if hours > 6:
            return [{
                'type': AnomalyType.SESSION_TOO_LONG.value,
                'severity': 'high',
                'detail': f'Session duration {hours:.1f}h exceeds 6h limit',
            }]
        return []

    def _check_single_activity_loop(self, s: Session) -> list[dict]:
        """Detect lặp lại cùng 1 event_context >90% (auto-reload pattern)."""
        if len(s.events) < 10:
            return []
        contexts = [e.event_context for e in s.events]
        most_common_ctx, count = Counter(contexts).most_common(1)[0]
        ratio = count / len(contexts)
        if ratio > 0.90:
            return [{
                'type': AnomalyType.SINGLE_ACTIVITY_LOOP.value,
                'severity': 'medium',
                'detail': f'{ratio:.0%} of events on "{most_common_ctx[:60]}"',
            }]
        return []
