"""
Main orchestrator — chạy full 6-phase pipeline.

Pipeline:
  Phase 1: Parse CSV → LogEntry[]
  Phase 2: Detect site-level sessions → Session[]
  Phase 3: Anomaly detection → Session[] (with flags)
  Phase 4: Course attribution → Session[] (with breakdown)
  Phase 5: Cross-validation → Session[] (with confidence)
  Phase 6: Aggregate → reports
"""

from .utils.models import Config
from .core.parser import LogParser
from .core.session_detector import SessionDetector
from .core.anomaly_detector import AnomalyDetector
from .core.course_attributor import CourseAttributor
from .core.cross_validator import CrossValidator
from .reports.aggregator import Aggregator
from .reports.exporter import ReportExporter


class MoodleTimeTracker:
    """
    Usage:
        tracker = MoodleTimeTracker(Config())
        result = tracker.process('data/input/logs.csv')
        tracker.export(result, 'data/output')
    """

    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.parser = LogParser(self.config)
        self.detector = SessionDetector(self.config)
        self.anomaly = AnomalyDetector(self.config)
        self.attributor = CourseAttributor()
        self.validator = CrossValidator()
        self.aggregator = Aggregator()

    def process(self, csv_path: str) -> dict:
        """Run full pipeline, return all results."""
        print("=" * 60)
        print("MOODLE TIME TRACKING ENGINE")
        print("=" * 60)

        # Phase 1
        print("\n[Phase 1] Extracting & parsing logs...")
        entries = self.parser.parse_csv(csv_path)

        # Phase 2
        print("\n[Phase 2] Detecting site-level sessions...")
        sessions = self.detector.detect_all(entries)

        # Phase 3
        print("\n[Phase 3] Running anomaly detection...")
        sessions = self.anomaly.analyze(sessions)

        # Phase 4
        print("\n[Phase 4] Attributing time to courses...")
        sessions = self.attributor.attribute(sessions)

        # Phase 5
        print("\n[Phase 5] Cross-validating with quiz data...")
        sessions = self.validator.validate(sessions)

        # Phase 6
        print("\n[Phase 6] Aggregating results...")
        by_user = self.aggregator.aggregate_by_user(sessions)
        by_user_course = self.aggregator.aggregate_by_user_course(sessions)
        evidence = self.aggregator.generate_evidence(sessions, self.config)

        # Summary
        total_users = len(by_user)
        total_sessions = len(sessions)
        total_hours = sum(v['total_hours'] for v in by_user.values())
        flagged = sum(1 for s in sessions if s.anomaly_flags)
        clean_hours = sum(
            s.total_duration_sec for s in sessions if not s.anomaly_flags
        ) / 3600

        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)
        print(f"  Users tracked:       {total_users}")
        print(f"  Total sessions:      {total_sessions}")
        print(f"  Total hours (all):   {total_hours:.1f}h")
        print(f"  Total hours (clean): {clean_hours:.1f}h")
        if total_sessions > 0:
            print(f"  Flagged sessions:    {flagged} ({flagged/total_sessions*100:.0f}%)")
        print(f"  Config: threshold={self.config.default_threshold_sec//60}m, "
              f"media={self.config.media_threshold_sec//60}m, "
              f"bonus_cap={self.config.max_bonus_sec//60}m")

        return {
            'config': self.config.to_dict(),
            'summary': {
                'total_users': total_users,
                'total_sessions': total_sessions,
                'total_hours': round(total_hours, 2),
                'clean_hours': round(clean_hours, 2),
                'flagged_sessions': flagged,
            },
            'by_user': by_user,
            'by_user_course': [
                {
                    'user_id': ct.user_id,
                    'user_name': ct.user_name,
                    'course_name': ct.course_name,
                    'total_minutes': round(ct.total_sec / 60, 1),
                    'session_count': ct.session_count,
                    'avg_confidence': ct.avg_confidence,
                    'anomaly_count': ct.anomaly_count,
                }
                for ct in by_user_course
            ],
            'sessions': sessions,
            'evidence': evidence,
        }

    def export(
        self,
        result: dict,
        output_dir: str = 'data/output',
        date_str: str = None,
        skip_global: bool = False,
    ):
        """Export all reports to output directory."""
        exporter = ReportExporter(output_dir)
        exporter.export_all(result, self.config, date_str=date_str, skip_global=skip_global)

    def finalize_detail(self, year: str, month: str, output_dir: str = 'data/output'):
        """Sort combined detail file after all days are processed."""
        exporter = ReportExporter(output_dir)
        exporter.finalize_detail(year, month)

    def export_monthly_summary(self, year: str, month: str, output_dir: str = 'data/output'):
        """Aggregate combined detail CSV into a monthly summary."""
        exporter = ReportExporter(output_dir)
        exporter.export_monthly_summary(year, month, config=self.config)
