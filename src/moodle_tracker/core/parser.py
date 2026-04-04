"""
Phase 1: Parse Moodle CSV log export → LogEntry objects.

Filters applied:
  - Loại user_id = 0, -1 (system/anonymous)
  - Loại user_name = '-' (system events)
  - Loại excluded event names (login failed, log report, etc.)
  - Loại origin != web/ws (nếu cần — hiện tại CSV chỉ có web)
"""

import csv
import re
from datetime import datetime
from typing import Optional

from ..utils.models import Config, LogEntry


class LogParser:

    RE_USER_ID = re.compile(r"The user with id '(\d+)'")
    RE_COURSE_ID = re.compile(r"course with id '(\d+)'")
    RE_COURSE_MODULE_ID = re.compile(r"course module id '(\d+)'")

    def __init__(self, config: Config):
        self.config = config
        self._parse_errors = 0

    def parse_csv(self, filepath: str) -> list[LogEntry]:
        """
        Parse Moodle CSV log export → sorted list of LogEntry (ascending time).

        Args:
            filepath: Path to CSV file (UTF-8 BOM encoding from Moodle).

        Returns:
            List of LogEntry sorted by timestamp ascending.
        """
        entries = []
        total_rows = 0

        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_rows += 1
                entry = self._parse_row(row)
                if entry:
                    entries.append(entry)

        # Moodle CSV is descending — sort ascending for session detection
        entries.sort(key=lambda e: e.unix_ts)

        filtered = total_rows - len(entries)
        print(f"[Parser] {total_rows} rows → {len(entries)} valid entries "
              f"({filtered} filtered, {self._parse_errors} parse errors)")

        return entries

    def _parse_row(self, row: dict) -> Optional[LogEntry]:
        """Parse + filter 1 CSV row."""

        # --- Filter: excluded event names ---
        event_name = row.get('Event name', '')
        if event_name in self.config.exclude_event_names:
            return None

        # --- Filter: extract user_id, skip system users ---
        desc = row.get('Description', '')
        uid_match = self.RE_USER_ID.search(desc)
        if not uid_match:
            return None
        user_id = uid_match.group(1)
        if user_id in ('0', '-1'):
            return None

        # --- Filter: skip anonymous rows ---
        user_name = row.get('User full name', '-')
        if user_name == '-':
            return None

        # --- Parse timestamp ---
        try:
            ts = datetime.strptime(row['Time'], "%d/%m/%y, %H:%M:%S")
        except (ValueError, KeyError):
            self._parse_errors += 1
            return None

        # --- Extract course info ---
        event_context = row.get('Event context', '')
        component = row.get('Component', '')

        course_id = None
        course_name = None
        cid_match = self.RE_COURSE_ID.search(desc)
        if cid_match:
            course_id = cid_match.group(1)
        if event_context.startswith('Course:'):
            course_name = event_context.replace('Course: ', '').strip()

        cmid_match = self.RE_COURSE_MODULE_ID.search(desc)
        course_module_id = cmid_match.group(1) if cmid_match else None

        # --- Classify media content ---
        is_media = component in self.config.media_components

        return LogEntry(
            timestamp=ts,
            unix_ts=ts.timestamp(),
            user_id=user_id,
            user_name=user_name,
            event_context=event_context,
            component=component,
            event_name=event_name,
            description=desc,
            origin=row.get('Origin', 'web'),
            ip_address=row.get('IP address', ''),
            course_id=course_id,
            course_name=course_name,
            course_module_id=course_module_id,
            is_media=is_media,
        )
