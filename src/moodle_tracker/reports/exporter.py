"""
Export kết quả thành CSV reports.

Output files (batch --dir mode):
  - {year}/{mm}/detail_{year}-{mm}.csv          ← combined all-days, sorted
  - {year}/{mm}/monthly_summary_{year}-{mm}.csv ← aggregated by user + Log URL

Output files (single-file mode, thêm):
  - report_per_user.csv
  - report_per_user_course.csv
  - report_sessions.csv
  - report_anomalies.csv
  - evidence_audit_trail.csv
"""

import csv
import os
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from ..utils.models import Config, Session


class ReportExporter:

    def __init__(self, output_dir: str = 'data/output'):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def export_all(
        self,
        result: dict,
        config: Config,
        date_str: str = None,
        skip_global: bool = False,
    ):
        """Export reports từ pipeline result cho 1 ngày."""
        if not skip_global:
            print(f"\n[Exporter] Writing reports to {self.output_dir}/")
            self._export_per_user(result)
            self._export_per_user_course(result)
            self._export_sessions(result['sessions'])
            self._export_anomalies(result['sessions'])
            self._export_evidence(result, config)

        self._export_daily_detail(result['sessions'], config, date_str)

    # -------------------------------------------------------------------------
    # Global flat reports (single-file mode only)
    # -------------------------------------------------------------------------

    def _export_per_user(self, result: dict):
        path = os.path.join(self.output_dir, 'report_per_user.csv')
        sessions = result['sessions']
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow([
                'User ID', 'User Name', 'Total Hours', 'Total Minutes',
                'Sessions', 'Events', 'Avg Confidence', 'Anomaly Count',
                'Clean Hours', 'Status',
            ])
            for uid, d in result['by_user'].items():
                user_sess = [s for s in sessions if s.user_id == uid]
                clean_hrs = sum(
                    s.total_duration_sec for s in user_sess if not s.anomaly_flags
                ) / 3600
                status = _status(d['anomaly_count'], d['avg_confidence'])
                w.writerow([
                    uid, d['user_name'], d['total_hours'], d['total_minutes'],
                    d['session_count'], d['event_count'], d['avg_confidence'],
                    d['anomaly_count'], round(clean_hrs, 2), status,
                ])
        print(f"  → {path}")

    def _export_per_user_course(self, result: dict):
        path = os.path.join(self.output_dir, 'report_per_user_course.csv')
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow([
                'User ID', 'User Name', 'Course / Activity',
                'Total Minutes', 'Sessions', 'Avg Confidence', 'Anomaly Count',
            ])
            for item in result['by_user_course']:
                w.writerow([
                    item['user_id'], item['user_name'], item['course_name'],
                    item['total_minutes'], item['session_count'],
                    item['avg_confidence'], item['anomaly_count'],
                ])
        print(f"  → {path}")

    def _export_sessions(self, sessions: list):
        path = os.path.join(self.output_dir, 'report_sessions.csv')
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow([
                'Session ID', 'User ID', 'User Name',
                'Start Time', 'End Time',
                'Raw Duration (min)', 'Bonus (min)', 'Total Duration (min)',
                'Events', 'Confidence', 'Threshold (min)',
                'IPs', 'Anomaly Flags', 'Course Breakdown',
            ])
            for s in sessions:
                course_str = '; '.join(
                    f"{k}: {v/60:.1f}m" for k, v in s.course_breakdown.items()
                )
                flags_str = '; '.join(
                    f['type'] for f in s.anomaly_flags
                ) if s.anomaly_flags else 'none'
                w.writerow([
                    s.session_id, s.user_id, s.user_name,
                    s.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                    s.end_time.strftime('%Y-%m-%d %H:%M:%S'),
                    round(s.raw_duration_sec / 60, 1),
                    round(s.bonus_sec / 60, 1),
                    round(s.total_duration_sec / 60, 1),
                    s.event_count, s.confidence_score,
                    s.threshold_used_sec // 60,
                    ', '.join(s.ips), flags_str, course_str,
                ])
        print(f"  → {path}")

    def _export_anomalies(self, sessions: list):
        path = os.path.join(self.output_dir, 'report_anomalies.csv')
        flagged = [s for s in sessions if s.anomaly_flags]
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow([
                'Session ID', 'User ID', 'User Name', 'Duration (min)',
                'Events', 'Confidence', 'Anomaly Type', 'Severity', 'Detail',
            ])
            for s in flagged:
                for fl in s.anomaly_flags:
                    w.writerow([
                        s.session_id, s.user_id, s.user_name,
                        round(s.total_duration_sec / 60, 1),
                        s.event_count, s.confidence_score,
                        fl['type'], fl.get('severity', ''), fl.get('detail', ''),
                    ])
        print(f"  → {path}")

    def _export_evidence(self, result: dict, config: Config):
        path = os.path.join(self.output_dir, 'evidence_audit_trail.csv')
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow([
                'Session ID', 'User ID', 'User Name',
                'Start Time', 'End Time',
                'Raw Duration (min)', 'Bonus (min)', 'Total Duration (min)',
                'Events', 'Confidence', 'Threshold (min)',
                'IP Addresses', 'Anomaly Flags', 'Course Breakdown',
                'First Event Time', 'First Event Context', 'First Event Name',
                'Last Event Time', 'Last Event Context', 'Last Event Name',
                'Generated At',
            ])
            generated_at = datetime.now().isoformat()
            for ev in result['evidence']:
                flags_str = '; '.join(
                    f"{fl['type']}({fl.get('severity', '')}): {fl.get('detail', '')}"
                    for fl in ev['anomaly_flags']
                ) if ev['anomaly_flags'] else 'none'
                course_str = '; '.join(
                    f"{k}: {v}m" for k, v in ev['course_breakdown'].items()
                )
                fe = ev.get('first_event', {})
                le = ev.get('last_event', {})
                w.writerow([
                    ev['session_id'], ev['user_id'], ev['user_name'],
                    ev['start_time'], ev['end_time'],
                    ev['raw_duration_min'], ev['bonus_min'], ev['total_duration_min'],
                    ev['event_count'], ev['confidence_score'], ev['threshold_used_min'],
                    ', '.join(ev['ip_addresses']), flags_str, course_str,
                    fe.get('time', ''), fe.get('context', ''), fe.get('event', ''),
                    le.get('time', ''), le.get('context', ''), le.get('event', ''),
                    generated_at,
                ])
        print(f"  → {path}")

    # -------------------------------------------------------------------------
    # Daily detail — append to combined monthly file
    # -------------------------------------------------------------------------

    _DETAIL_HEADER = [
        'Date', 'User ID', 'User Name',
        'Session Start', 'Session End',
        'Total Hours', 'Events',
        'Confidence', 'Anomaly Count', 'Clean Hours', 'Status',
        'Anomaly Types', 'Severity', 'Details', 'Log URL',
    ]

    _SEV_RANK = {'high': 3, 'medium': 2, 'low': 1, '': 0}

    def _export_daily_detail(
        self,
        sessions: list,
        config: Config,
        date_str: str = None,
    ):
        """
        Append one row per session to the combined file `detail_{year}-{mm}.csv`.
        Header is only written when creating a new file.
        """
        if not date_str:
            date_str = (
                sessions[0].start_time.strftime('%Y-%m-%d')
                if sessions else datetime.now().strftime('%Y-%m-%d')
            )

        year, month, _ = date_str.split('-')
        out_dir = os.path.join(self.output_dir, year, month)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f'detail_{year}-{month}.csv')

        file_exists = os.path.isfile(path)
        mode = 'a' if file_exists else 'w'

        # Unix timestamp for start-of-day UTC (for log URL)
        day_start_ts = int(
            datetime.strptime(date_str, '%Y-%m-%d')
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )

        sorted_sessions = sorted(sessions, key=lambda s: (s.user_id, s.start_time))

        rows = [
            self._build_detail_row(s, date_str, day_start_ts, config)
            for s in sorted_sessions
        ]

        with open(path, mode, newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            if not file_exists:
                w.writerow(self._DETAIL_HEADER)
            w.writerows(rows)

    def _build_detail_row(
        self,
        s,
        date_str: str,
        day_start_ts: int,
        config: Config,
    ) -> list:
        """Build one CSV row for a single session."""
        total_hours = round(s.total_duration_sec / 3600, 2)
        confidence = round(s.confidence_score, 2)
        anomaly_count = len(s.anomaly_flags)
        clean_hours = round(s.total_duration_sec / 3600, 2) if not s.anomaly_flags else 0.0
        status = _status(anomaly_count, confidence)

        # Collect anomaly type → highest severity for this session
        type_severity: dict = {}
        for fl in s.anomaly_flags:
            t = fl['type']
            sev = fl.get('severity', '')
            if self._SEV_RANK.get(sev, 0) > self._SEV_RANK.get(type_severity.get(t, ''), 0):
                type_severity[t] = sev

        detail = '; '.join(
            f"{fl['type']} - {fl.get('detail', '')}" for fl in s.anomaly_flags
        )

        log_url = _build_log_url(config.moodle_base_url, s.user_id, day_start_ts)

        return [
            date_str, s.user_id, s.user_name,
            s.start_time.strftime('%H:%M'), s.end_time.strftime('%H:%M'),
            total_hours, s.event_count,
            confidence, anomaly_count, clean_hours, status,
            '; '.join(type_severity.keys()),
            '; '.join(type_severity.values()),
            detail,
            log_url,
        ]

    def finalize_detail(self, year: str, month: str):
        """
        Sort combined detail file: User Name asc → Date asc → Session Start asc.
        """
        path = os.path.join(self.output_dir, year, month, f'detail_{year}-{month}.csv')
        if not os.path.isfile(path):
            return

        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        has_session_start = 'Session Start' in (rows[0] if rows else {})
        if has_session_start:
            rows.sort(key=lambda r: (r['User Name'], r['Date'], r['Session Start']))
        else:
            rows.sort(key=lambda r: (r['User Name'], r['Date']))

        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=self._DETAIL_HEADER, extrasaction='ignore')
            w.writeheader()
            w.writerows(rows)

        print(f"[Exporter] Detail sorted → {path}  ({len(rows)} rows)")

    # -------------------------------------------------------------------------
    # Monthly summary
    # -------------------------------------------------------------------------

    _MONTHLY_HEADER = [
        'Month', 'User ID', 'User Name',
        'Total Hours', 'Days Active',
        'Sessions', 'Events',
        'Avg Confidence', 'Anomaly Count', 'Clean Hours', 'Status',
        'Log URL',
    ]

    def export_monthly_summary(self, year: str, month: str, config: Config = None):
        """
        Đọc combined detail file và tổng hợp theo user.
        Output: {output_dir}/{year}/{month}/monthly_summary_{year}-{month}.csv
        """
        detail_path = os.path.join(
            self.output_dir, year, month, f'detail_{year}-{month}.csv'
        )
        if not os.path.isfile(detail_path):
            print(f"[Exporter] Detail file not found: {detail_path}")
            return

        user_data: dict = defaultdict(lambda: {
            'user_name': '',
            'total_hours': 0.0,
            'days': set(),
            'sessions': 0,
            'events': 0,
            'confidences': [],
            'anomaly_count': 0,
            'clean_hours': 0.0,
        })

        with open(detail_path, newline='', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                uid = row['User ID']
                d = user_data[uid]
                d['user_name'] = row['User Name']
                d['total_hours'] += float(row['Total Hours'])
                d['days'].add(row['Date'])
                d['sessions'] += 1  # one row = one session
                d['events'] += int(row['Events'])
                d['confidences'].append(float(row['Confidence']))
                d['anomaly_count'] += int(row['Anomaly Count'])
                d['clean_hours'] += float(row['Clean Hours'])

        base_url = config.moodle_base_url if config else ''

        rows = []
        for uid, d in user_data.items():
            avg_conf = round(statistics.mean(d['confidences']), 2) if d['confidences'] else 0.0
            log_url = _build_log_url(base_url, uid) if base_url else ''
            rows.append([
                f"{year}-{month}", uid, d['user_name'],
                round(d['total_hours'], 2), len(d['days']),
                d['sessions'], d['events'],
                avg_conf, d['anomaly_count'], round(d['clean_hours'], 2),
                _status(d['anomaly_count'], avg_conf),
                log_url,
            ])

        rows.sort(key=lambda r: -r[3])

        out_path = os.path.join(
            self.output_dir, year, month, f'monthly_summary_{year}-{month}.csv'
        )
        with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(self._MONTHLY_HEADER)
            w.writerows(rows)

        print(f"[Exporter] Monthly summary → {out_path}  ({len(rows)} users)")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _status(anomaly_count: int, avg_confidence: float) -> str:
    if anomaly_count > 0 and avg_confidence < 0.4:
        return 'REVIEW REQUIRED'
    if anomaly_count > 0:
        return 'HAS ANOMALIES'
    return 'CLEAN'


def _build_log_url(base_url: str, user_id: str, date_ts: int = None) -> str:
    """
    Build a Moodle log URL for a user.
    date_ts=None  → no date filter (show all logs)
    date_ts=int   → filter to a specific day
    """
    if not base_url:
        return ''
    url = (
        f"{base_url.rstrip('/')}/report/log/index.php"
        f"?chooselog=1&logreader=logstore_standard&id=0&user={user_id}"
    )
    if date_ts is not None:
        url += f"&date={date_ts}"
    return url
