import unittest
from dataclasses import replace
from datetime import date, datetime, timezone

from src.canonical.model import ScheduleItem
from src.workflows.schedule_actuality import check_schedule_actuality


class ScheduleActualityTest(unittest.TestCase):
    def setUp(self):
        self.as_of_date = date(2026, 11, 14)
        self.item = ScheduleItem(
            id="item-1",
            code="1",
            name="Schedule item",
            type="milestone_finish",
            parent_id=None,
            level=0,
            start=None,
            finish=datetime(2026, 11, 12, 23, 59, tzinfo=timezone.utc),
            progress=75,
            status="in_progress",
            predecessors=None,
            successors=None,
        )

    def check(self, **changes):
        return check_schedule_actuality([replace(self.item, **changes)], self.as_of_date)

    def test_overdue_incomplete(self):
        finding, = self.check()
        self.assertEqual(finding.rule_id, "OVERDUE_INCOMPLETE")
        self.assertEqual(finding.days_overdue, 2)
        self.assertEqual(finding.item_id, self.item.id)

    def test_future_finish(self):
        finish = datetime(2026, 11, 15, tzinfo=timezone.utc)
        self.assertEqual(self.check(finish=finish), [])

    def test_finish_on_control_date(self):
        finish = datetime(2026, 11, 14, 18, tzinfo=timezone.utc)
        self.assertEqual(self.check(finish=finish), [])

    def test_full_progress(self):
        self.assertEqual(self.check(progress=100), [])

    def test_missing_finish(self):
        self.assertEqual(self.check(finish=None), [])

    def test_missing_progress(self):
        self.assertEqual(self.check(progress=None, status="completed"), [])

    def test_completed_with_incomplete_progress(self):
        finding, = self.check(status="completed", finish=None)
        self.assertEqual(finding.rule_id, "STATUS_PROGRESS_MISMATCH")
        self.assertIsNone(finding.days_overdue)

    def test_completed_with_full_progress(self):
        self.assertEqual(self.check(status="completed", progress=100), [])

    def test_both_rules_apply(self):
        self.assertEqual(
            [finding.rule_id for finding in self.check(status="completed")],
            ["OVERDUE_INCOMPLETE", "STATUS_PROGRESS_MISMATCH"],
        )
