import json
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone

from src.agent.context import build_context
from src.canonical.model import ScheduleItem
from src.workflows.model import ControlFinding


class AgentContextTest(unittest.TestCase):
    def setUp(self):
        self.root = ScheduleItem(
            id="497f6e0f-556b-4c17-ad87-bdd032df8420",
            code="100",
            name="Фаза",
            type="work",
            parent_id=None,
            level=0,
            start=None,
            finish=datetime(2026, 11, 12, 18, tzinfo=timezone.utc),
            progress=75,
            status="in_progress",
            predecessors=None,
            successors=None,
        )
        self.child = replace(
            self.root,
            id="f492b913-d083-4ab9-a94c-5335f4cd28e9",
            code="101",
            parent_id=self.root.id,
            level=1,
            start=datetime(2026, 11, 10, 9, tzinfo=timezone.utc),
            target_start=datetime(2026, 11, 9, 9, tzinfo=timezone.utc),
            target_finish=datetime(2026, 11, 11, 18, tzinfo=timezone.utc),
        )
        self.orphan = replace(self.child, id="orphan", code="102", parent_id="missing")
        self.finding = ControlFinding(
            rule_id="OVERDUE_INCOMPLETE",
            item_id=self.root.id,
            code=self.root.code,
            name=self.root.name,
            type=self.root.type,
            finish=self.root.finish,
            progress=75,
            status=self.root.status,
            days_overdue=2,
            message="Срок истёк.",
        )
        self.raw = build_context(
            [self.child, self.root, self.orphan], [self.finding], date(2026, 11, 14)
        )
        self.context = json.loads(self.raw)

    def test_schedule_contains_all_items_with_parent_codes(self):
        schedule = self.context["schedule"]
        self.assertEqual([item["code"] for item in schedule], ["101", "100", "102"])
        self.assertEqual([item["parent_code"] for item in schedule], ["100", None, None])

    def test_context_excludes_technical_ids(self):
        for item in self.context["schedule"]:
            self.assertNotIn("id", item)
            self.assertNotIn("parent_id", item)
        self.assertNotIn("item_id", self.context["findings"][0])
        self.assertNotIn(self.root.id, self.raw)
        self.assertNotIn(self.child.id, self.raw)

    def test_findings_are_serialized(self):
        self.assertEqual(self.context["findings"], [{
            "rule_id": "OVERDUE_INCOMPLETE",
            "code": "100",
            "name": "Фаза",
            "finish": "2026-11-12T18:00:00+00:00",
            "progress": 75,
            "status": "in_progress",
            "days_overdue": 2,
            "message": "Срок истёк.",
        }])

    def test_dates_are_iso_and_missing_dates_are_null(self):
        self.assertEqual(self.context["as_of_date"], "2026-11-14")
        child, root, _ = self.context["schedule"]
        self.assertEqual(child["start"], "2026-11-10T09:00:00+00:00")
        self.assertEqual(root["finish"], "2026-11-12T18:00:00+00:00")
        self.assertIsNone(root["start"])
        self.assertEqual(child["target_start"], "2026-11-09T09:00:00+00:00")
        self.assertEqual(child["target_finish"], "2026-11-11T18:00:00+00:00")
        self.assertIsNone(root["target_start"])
        self.assertIsNone(root["target_finish"])
