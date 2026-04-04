"""
Phase 4: Map session time → individual courses.

Strategy:
  - Event[i] → Event[i+1]: time assigned to course of Event[i]
  - Last event: bonus time assigned to its course
  - Events not belonging to any course → "[Platform]" bucket
"""

from collections import defaultdict

from ..utils.models import LogEntry, Session


class CourseAttributor:

    def attribute(self, sessions: list[Session]) -> list[Session]:
        """Tính course_breakdown cho mỗi session."""
        for s in sessions:
            breakdown = defaultdict(float)

            for i, event in enumerate(s.events):
                course_key = self._get_course_key(event)

                if i < len(s.events) - 1:
                    duration = s.events[i + 1].unix_ts - event.unix_ts
                else:
                    duration = s.bonus_sec  # last event gets bonus

                breakdown[course_key] += duration

            s.course_breakdown = dict(breakdown)

        return sessions

    def _get_course_key(self, event: LogEntry) -> str:
        """Xác định course label cho 1 event."""
        # Priority 1: explicit course name from "Course: X" context
        if event.course_name:
            return event.course_name

        ctx = event.event_context
        if ctx.startswith('Course:'):
            return ctx.replace('Course: ', '').strip()

        # Priority 2: activity-level context
        if ctx and ctx not in ('System', 'Site home'):
            return f"[Activity] {ctx}"

        # Priority 3: platform-level
        return "[Platform]"
