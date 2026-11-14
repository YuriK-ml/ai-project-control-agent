import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.adapters.planr.adapter import load_schedule


class PlanrAdapterTest(unittest.TestCase):
    def test_target_dates_from_project_fixture(self):
        fixture = Path(__file__).resolve().parents[1] / "data/fixtures/planr/project_01"
        items = {item.code: item for item in load_schedule(fixture)}

        self.assertEqual(items["431"].target_start, datetime(2024, 3, 25, 9, tzinfo=timezone.utc))
        self.assertEqual(items["431"].target_finish, datetime(2027, 9, 15, 18, tzinfo=timezone.utc))
        self.assertIsNone(items["404"].target_start)
        self.assertIsNone(items["270"].target_finish)
