"""
MoodleCrawler — tải log CSV từ Moodle theo từng ngày trong tháng.

Flow:
  1. Login vào Moodle → lấy sesskey
  2. Với mỗi ngày trong tháng, tính unix timestamp cho 00:00:00 theo timezone server
  3. Download CSV log, lưu vào data/input/{year}/{mm:02d}/{yyyy}-{mm:02d}-{dd:02d}.csv
  4. Bỏ qua ngày đã có file (trừ khi --force)

Requirements: pip install requests
"""

import calendar
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

try:
    import requests
except ImportError:
    raise ImportError("pip install requests")


class MoodleCrawler:

    _DEFAULT_HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/131.0.0.0 Safari/537.36'
        ),
        'Accept-Language': 'en-US,en;q=0.9',
    }

    # Moodle log report params — lấy toàn bộ site log, tất cả user
    _LOG_PARAMS = {
        'chooselog': '1',
        'showusers': '0',
        'showcourses': '0',
        'id': '1',          # 1 = site level
        'user': '0',        # 0 = all users
        'modid': '',
        'modaction': '',
        'origin': '',
        'edulevel': '-1',
        'logreader': 'logstore_standard',
    }

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timezone_offset: int = 7,
    ):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.tz = timezone(timedelta(hours=timezone_offset))
        self._session = requests.Session()
        self._session.headers.update(self._DEFAULT_HEADERS)
        self._sesskey: Optional[str] = None

    # -------------------------------------------------------------------------
    # Auth
    # -------------------------------------------------------------------------

    def login(self):
        """Login vào Moodle và lưu sesskey. Gọi 1 lần trước khi download."""
        print(f"[Crawler] Logging in to {self.base_url} as '{self.username}'...")

        # Step 1: GET login page → logintoken
        login_page = self._session.get(f'{self.base_url}/login/index.php', timeout=30)
        login_page.raise_for_status()

        token_match = re.search(r'name="logintoken"\s+value="([^"]+)"', login_page.text)
        logintoken = token_match.group(1) if token_match else ''

        # Step 2: POST credentials
        resp = self._session.post(
            f'{self.base_url}/login/index.php',
            data={
                'username': self.username,
                'password': self.password,
                'logintoken': logintoken,
                'anchor': '',
            },
            allow_redirects=True,
            timeout=30,
        )
        resp.raise_for_status()

        if 'loginerrormessage' in resp.text or 'Invalid login' in resp.text:
            raise ValueError("Login thất bại — kiểm tra username/password trong config.")

        # Step 3: GET log report page → sesskey
        log_page = self._session.get(
            f'{self.base_url}/report/log/index.php',
            params={**self._LOG_PARAMS, 'date': '0'},
            timeout=30,
        )
        log_page.raise_for_status()

        self._sesskey = self._extract_sesskey(log_page.text)
        print(f"[Crawler] Login OK | sesskey: {self._sesskey}")

    @staticmethod
    def _extract_sesskey(html: str) -> str:
        m = re.search(r'"sesskey"\s*:\s*"([^"]+)"', html)
        if m:
            return m.group(1)
        m = re.search(
            r'<input[^>]+name=["\']sesskey["\'][^>]+value=["\']([^"\']+)["\']', html
        )
        if m:
            return m.group(1)
        raise ValueError("Không tìm được sesskey — kiểm tra lại login.")

    # -------------------------------------------------------------------------
    # Download
    # -------------------------------------------------------------------------

    def _day_unix_ts(self, year: int, month: int, day: int) -> int:
        """Unix timestamp cho 00:00:00 ngày đó theo timezone của server."""
        dt = datetime(year, month, day, 0, 0, 0, tzinfo=self.tz)
        return int(dt.timestamp())

    def download_day(
        self,
        year: int,
        month: int,
        day: int,
        output_dir: str = 'data/input',
        force: bool = False,
    ) -> Optional[Path]:
        """
        Tải CSV log cho 1 ngày.
        Trả về Path của file đã lưu, hoặc None nếu bỏ qua.
        """
        if self._sesskey is None:
            raise RuntimeError("Chưa login — gọi crawler.login() trước.")

        out_dir = Path(output_dir) / str(year) / f'{month:02d}'
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f'{year}-{month:02d}-{day:02d}.csv'

        if out_path.exists() and not force:
            print(f"  [skip] {out_path.name} đã tồn tại")
            return None

        unix_ts = self._day_unix_ts(year, month, day)
        params = {
            **self._LOG_PARAMS,
            'date': str(unix_ts),
            'sesskey': self._sesskey,
            'download': 'csv',
        }

        resp = self._session.get(
            f'{self.base_url}/report/log/index.php',
            params=params,
            stream=True,
            timeout=60,
        )
        resp.raise_for_status()

        # Kiểm tra content-type — đôi khi Moodle trả HTML thay vì CSV (session hết hạn)
        ct = resp.headers.get('Content-Type', '')
        if 'text/html' in ct:
            raise RuntimeError(
                f"Server trả HTML thay vì CSV cho ngày {year}-{month:02d}-{day:02d}. "
                "Session có thể đã hết — thử chạy lại."
            )

        with open(out_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_kb = out_path.stat().st_size / 1024
        print(f"  ✓ {out_path.name}  ({size_kb:.1f} KB)")
        return out_path

    # -------------------------------------------------------------------------
    # Month crawl
    # -------------------------------------------------------------------------

    def crawl_month(
        self,
        year: int,
        month: int,
        output_dir: str = 'data/input',
        force: bool = False,
        delay_sec: float = 1.0,
    ) -> List[Path]:
        """
        Tải toàn bộ log của tháng `month` năm `year`.

        Args:
            force:      Re-download ngay cả khi file đã tồn tại.
            delay_sec:  Độ trễ giữa mỗi request (tránh quá tải server).

        Returns:
            Danh sách Path các file đã tải được.
        """
        _, num_days = calendar.monthrange(year, month)
        print(
            f"\n[Crawler] Crawling {year}-{month:02d} "
            f"({num_days} days) → {output_dir}/{year}/{month:02d}/"
        )

        downloaded = []
        for day in range(1, num_days + 1):
            try:
                path = self.download_day(year, month, day, output_dir, force)
                if path:
                    downloaded.append(path)
            except Exception as e:
                print(f"  ✗ {year}-{month:02d}-{day:02d}: {e}")

            if day < num_days:
                time.sleep(delay_sec)

        print(
            f"\n[Crawler] Done — {len(downloaded)} file(s) downloaded, "
            f"{num_days - len(downloaded)} skipped/failed."
        )
        return downloaded
