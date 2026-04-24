"""
Phase 6: Aggregate sessions → per-user, per-course summaries + evidence.
"""

import statistics
from collections import defaultdict

from ..utils.models import Config, Session, CourseTime, LogEntry


class Aggregator:

    def aggregate_by_user(self, sessions: list[Session]) -> dict:
        """Per-user summary: total hours, sessions, confidence, anomalies."""
        user_data = defaultdict(
            lambda: {
                "total_sec": 0,
                "session_count": 0,
                "event_count": 0,
                "confidences": [],
                "anomaly_count": 0,
                "user_name": "",
                "pals_id": "",
                "fullname": "",
            }
        )

        for s in sessions:
            d = user_data[s.user_id]
            d["user_name"] = s.user_name
            d["pals_id"] = s.pals_id
            d["fullname"] = s.fullname
            d["total_sec"] += s.total_duration_sec
            d["session_count"] += 1
            d["event_count"] += s.event_count
            d["confidences"].append(s.confidence_score)
            d["anomaly_count"] += len(s.anomaly_flags)

        result = {}
        for uid, d in user_data.items():
            avg_conf = statistics.mean(d["confidences"]) if d["confidences"] else 0
            result[uid] = {
                "user_id": uid,
                "user_name": d["user_name"],
                "pals_id": d["pals_id"],
                "fullname": d["fullname"],
                "total_hours": round(d["total_sec"] / 3600, 2),
                "total_minutes": round(d["total_sec"] / 60, 1),
                "total_sec": d["total_sec"],
                "session_count": d["session_count"],
                "event_count": d["event_count"],
                "avg_confidence": round(avg_conf, 2),
                "anomaly_count": d["anomaly_count"],
            }

        return dict(
            sorted(result.items(), key=lambda x: x[1]["total_sec"], reverse=True)
        )

    def aggregate_by_user_course(self, sessions: list[Session]) -> list[CourseTime]:
        """Per-user × per-course breakdown."""
        key_data = defaultdict(
            lambda: {
                "total_sec": 0,
                "session_count": 0,
                "event_count": 0,
                "confidences": [],
                "anomaly_count": 0,
                "user_name": "",
                "pals_id": "",
                "fullname": "",
            }
        )

        for s in sessions:
            for course_name, duration in s.course_breakdown.items():
                key = (s.user_id, course_name)
                d = key_data[key]
                d["user_name"] = s.user_name
                d["pals_id"] = s.pals_id
                d["fullname"] = s.fullname
                d["total_sec"] += duration
                d["session_count"] += 1
                d["confidences"].append(s.confidence_score)
                d["anomaly_count"] += len(s.anomaly_flags)

        results = []
        for (uid, cname), d in key_data.items():
            avg_conf = statistics.mean(d["confidences"]) if d["confidences"] else 0
            results.append(
                CourseTime(
                    user_id=uid,
                    user_name=d["user_name"],
                    pals_id=d["pals_id"],
                    fullname=d["fullname"],
                    course_name=cname,
                    total_sec=round(d["total_sec"], 1),
                    session_count=d["session_count"],
                    event_count=0,  # simplified — count from events if needed
                    avg_confidence=round(avg_conf, 2),
                    anomaly_count=d["anomaly_count"],
                )
            )

        results.sort(key=lambda x: x.total_sec, reverse=True)
        return results

    def generate_evidence(self, sessions: list[Session], config: Config) -> list[dict]:
        """Full audit trail per session — cho minh chứng compliance."""
        evidence = []
        for s in sessions:
            evidence.append(
                {
                    "session_id": s.session_id,
                    "user_id": s.user_id,
                    "user_name": s.user_name,
                    "pals_id": s.pals_id,
                    "fullname": s.fullname,
                    "start_time": s.start_time.isoformat(),
                    "end_time": s.end_time.isoformat(),
                    "raw_duration_min": round(s.raw_duration_sec / 60, 1),
                    "bonus_min": round(s.bonus_sec / 60, 1),
                    "total_duration_min": round(s.total_duration_sec / 60, 1),
                    "event_count": s.event_count,
                    "confidence_score": s.confidence_score,
                    "threshold_used_min": s.threshold_used_sec // 60,
                    "ip_addresses": list(s.ips),
                    "anomaly_flags": s.anomaly_flags,
                    "course_breakdown": {
                        k: round(v / 60, 1) for k, v in s.course_breakdown.items()
                    },
                    "config_snapshot": config.to_dict(),
                    "first_event": {
                        "time": s.events[0].timestamp.isoformat(),
                        "context": s.events[0].event_context,
                        "event": s.events[0].event_name,
                    },
                    "last_event": {
                        "time": s.events[-1].timestamp.isoformat(),
                        "context": s.events[-1].event_context,
                        "event": s.events[-1].event_name,
                    },
                }
            )
        return evidence
