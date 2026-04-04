"""
Phase 2: Site-level session detection with adaptive threshold.

Key innovations vs existing tools:
  - Site-level detection (not per-course) → eliminates double-counting
  - Adaptive threshold: media content → higher threshold
  - Context-aware bonus: min(median_gap, max_bonus) — not fixed ½ timeout
"""

import statistics
from collections import defaultdict
from datetime import timedelta
from typing import Optional

from ..utils.models import Config, LogEntry, Session


class SessionDetector:

    def __init__(self, config: Config):
        self.config = config
        self._session_counter = 0

    def detect_all(self, entries: list[LogEntry]) -> list[Session]:
        """Detect sessions cho tất cả users từ site-level logs."""
        user_entries = defaultdict(list)
        for e in entries:
            user_entries[e.user_id].append(e)

        all_sessions = []
        for uid, user_logs in user_entries.items():
            sessions = self._detect_user_sessions(user_logs)
            all_sessions.extend(sessions)

        print(f"[SessionDetector] {len(all_sessions)} sessions "
              f"for {len(user_entries)} users")
        return all_sessions

    def _detect_user_sessions(self, user_logs: list[LogEntry]) -> list[Session]:
        """Session detection cho 1 user — gap-based splitting."""
        if len(user_logs) < self.config.min_events_per_session:
            return []

        sessions = []
        cur_events = [user_logs[0]]
        cur_ips = {user_logs[0].ip_address}

        for i in range(1, len(user_logs)):
            prev = user_logs[i - 1]
            curr = user_logs[i]
            gap = curr.unix_ts - prev.unix_ts

            # Adaptive threshold based on last event's content type
            threshold = self._get_threshold(prev)

            if gap >= threshold:
                session = self._build_session(cur_events, cur_ips)
                if session:
                    sessions.append(session)
                cur_events = [curr]
                cur_ips = {curr.ip_address}
            else:
                cur_events.append(curr)
                cur_ips.add(curr.ip_address)

        # Close last session
        session = self._build_session(cur_events, cur_ips)
        if session:
            sessions.append(session)

        return sessions

    def _get_threshold(self, last_event: LogEntry) -> int:
        """Adaptive: media content → higher threshold."""
        if last_event.is_media:
            return self.config.media_threshold_sec
        return self.config.default_threshold_sec

    def _build_session(
        self, events: list[LogEntry], ips: set
    ) -> Optional[Session]:
        """Build Session from events, apply min filters."""
        if len(events) < self.config.min_events_per_session:
            return None

        first, last = events[0], events[-1]
        raw_duration = last.unix_ts - first.unix_ts
        bonus = self._calc_bonus(events)
        total_duration = raw_duration + bonus

        if total_duration < self.config.min_session_sec:
            return None

        self._session_counter += 1
        return Session(
            session_id=self._session_counter,
            user_id=first.user_id,
            user_name=first.user_name,
            start_time=first.timestamp,
            end_time=last.timestamp + timedelta(seconds=bonus),
            raw_duration_sec=raw_duration,
            bonus_sec=bonus,
            total_duration_sec=total_duration,
            event_count=len(events),
            events=events,
            ips=ips,
            threshold_used_sec=self._get_threshold(last),
        )

    def _calc_bonus(self, events: list[LogEntry]) -> float:
        """
        Context-aware bonus = min(median_gap, max_bonus).

        Logic:
          Student clicks every 2m → median_gap=120s → bonus=120s (2m)
          Student clicks every 8m → median_gap=480s → bonus=300s (5m, capped)
          Only 2 events, gap=30s → bonus=30s
        """
        if len(events) < 2:
            return 0.0

        gaps = [
            events[i].unix_ts - events[i - 1].unix_ts
            for i in range(1, len(events))
            if events[i].unix_ts > events[i - 1].unix_ts
        ]
        if not gaps:
            return 0.0

        median_gap = statistics.median(gaps)
        return min(median_gap, self.config.max_bonus_sec)
