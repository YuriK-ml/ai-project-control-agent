import json
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone

from src.agent.context import build_context
from src.canonical.model import DependencyType, ProjectSchedule, ScheduleDependency, ScheduleItem
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
            [ProjectSchedule("v1", "Schedule", [self.child, self.root, self.orphan], [])],
            {"v1": [self.finding]}, date(2026, 11, 14)
        )
        self.context = json.loads(self.raw)["schedules"][0]

    def test_schedule_contains_all_items_with_parent_codes(self):
        schedule = self.context["schedule"]
        self.assertEqual([item["code"] for item in schedule], ["101", "100", "102"])
        self.assertEqual([item["parent_code"] for item in schedule], ["100", None, None])

    def test_context_preserves_identifiers(self):
        child = self.context["schedule"][0]
        self.assertEqual(child["id"], self.child.id)
        self.assertEqual(child["parent_id"], self.root.id)
        self.assertEqual(self.context["findings"][0]["item_id"], self.root.id)

    def test_findings_are_serialized(self):
        self.assertEqual(self.context["findings"], [{
            "item_id": self.root.id,
            "rule_id": "OVERDUE_INCOMPLETE",
            "code": "100",
            "name": "Фаза",
            "finish": "2026-11-12T18:00:00+00:00",
            "progress": 75,
            "status": "in_progress",
            "days_overdue": 2,
            "message": "Срок истёк.",
        }])

    def test_dependencies_include_codes_type_lag_version_and_direction(self):
        dependencies = [
            ScheduleDependency(self.root.id, self.child.id, DependencyType.START_TO_START,
                               -5, "v1", True),
            ScheduleDependency(self.child.id, self.orphan.id, DependencyType.FINISH_TO_FINISH,
                               0, "v1", False),
        ]
        context = json.loads(build_context(
            [ProjectSchedule("v1", "Schedule", [self.child, self.root, self.orphan], dependencies)],
            {"v1": [self.finding]}, date(2026, 11, 14),
        ))
        context = context["schedules"][0]
        self.assertEqual(context["dependencies"], [
            {"first_item_id": self.root.id, "second_item_id": self.child.id, "first_code": "100", "second_code": "101", "type": "ss", "lag": -5,
             "version_id": "v1", "direction_confirmed": True},
            {"first_item_id": self.child.id, "second_item_id": self.orphan.id, "first_code": "101", "second_code": "102", "type": "ff", "lag": 0,
             "version_id": "v1", "direction_confirmed": False},
        ])
        self.assertEqual(context["findings"], self.context["findings"])

    def test_dates_are_iso_and_missing_dates_are_null(self):
        self.assertEqual(json.loads(self.raw)["as_of_date"], "2026-11-14")
        child, root, _ = self.context["schedule"]
        self.assertEqual(child["start"], "2026-11-10T09:00:00+00:00")
        self.assertEqual(root["finish"], "2026-11-12T18:00:00+00:00")
        self.assertIsNone(root["start"])
        self.assertEqual(child["target_start"], "2026-11-09T09:00:00+00:00")
        self.assertEqual(child["target_finish"], "2026-11-11T18:00:00+00:00")
        self.assertIsNone(root["target_start"])
        self.assertIsNone(root["target_finish"])
