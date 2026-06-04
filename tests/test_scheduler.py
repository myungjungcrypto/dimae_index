import unittest
from datetime import datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sentiment_index.pipeline import (
    _daily_checkpoint_day,
    _format_schedule_time,
    _is_daily_snapshot_time,
    _next_run_at,
)


class SchedulerTest(unittest.TestCase):
    def test_next_run_uses_given_timezone_clock(self) -> None:
        now = datetime(2026, 6, 3, 3, 30, tzinfo=ZoneInfo("Asia/Seoul"))

        next_run = _next_run_at(now, (time(4, 0),))

        self.assertEqual(next_run.isoformat(), "2026-06-03T04:00:00+09:00")

    def test_schedule_time_format_shows_kst_and_utc(self) -> None:
        next_run = datetime(2026, 6, 3, 4, 0, tzinfo=ZoneInfo("Asia/Seoul"))

        formatted = _format_schedule_time(next_run)

        self.assertIn("2026-06-03 04:00:00 KST", formatted)
        self.assertIn("2026-06-02 19:00:00 UTC", formatted)

    def test_daily_checkpoint_uses_previous_kst_day_during_midnight_hour(self) -> None:
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                return datetime(2026, 6, 5, 0, 30, tzinfo=tz)

        with patch("sentiment_index.pipeline.datetime", FixedDatetime):
            self.assertTrue(_is_daily_snapshot_time())
            self.assertEqual(_daily_checkpoint_day(), "2026-06-04")


if __name__ == "__main__":
    unittest.main()
