"""
Phase 5: Cross-validation với quiz attempts → confidence scoring.

Scoring:
  Base:     0.50  (mọi session)
  +0.25     Quiz started AND submitted (strong evidence)
  +0.10     Quiz started OR submitted
  +0.10     ≥3 unique components
  +0.05     ≥2 unique components
  -0.30     High severity anomaly
  -0.15     Medium severity anomaly
"""

import re

from ..utils.models import Session


class CrossValidator:

    RE_ATTEMPT_ID = re.compile(r"attempt with id '(\d+)'")

    def validate(self, sessions: list[Session]) -> list[Session]:
        """Tính confidence score cho mỗi session."""
        for s in sessions:
            score = 0.5

            # --- Boost: quiz lifecycle evidence ---
            has_start = any(e.event_name == 'Quiz attempt started' for e in s.events)
            has_submit = any(e.event_name == 'Quiz attempt submitted' for e in s.events)

            if has_start and has_submit:
                score += 0.25
            elif has_start or has_submit:
                score += 0.10

            # --- Boost: diverse activity types ---
            components = set(e.component for e in s.events)
            if len(components) >= 3:
                score += 0.10
            elif len(components) >= 2:
                score += 0.05

            # --- Penalty: anomalies ---
            for flag in s.anomaly_flags:
                severity = flag.get('severity', '')
                if severity == 'high':
                    score -= 0.30
                elif severity == 'medium':
                    score -= 0.15

            s.confidence_score = max(0.0, min(1.0, round(score, 2)))

        return sessions
