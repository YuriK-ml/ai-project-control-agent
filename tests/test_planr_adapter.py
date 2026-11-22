import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.planr.adapter import load_project_schedule, load_schedule, load_schedule_names
from src.canonical.model import DependencyType, ScheduleDependency


class PlanrAdapterTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        keys = ["code", "target-start", "target-finish", "relation-in", "relation-out"]
        self.write_json("common/wbs-attributes.json", [{"id": key, "key": key} for key in keys])
        self.rows = [
            self.row("a", "10", **{"target-start": 0, "relation-out": "20;30"}),
            self.row("b", "20", **{"target-finish": 86400000, "relation-in": "10"}),
            self.row("c", "30", **{"relation-in": "10"}),
        ]
        self.write_json("schedule_01/wbs.json", self.rows)
        self.write_json("schedule_02/wbs.json", [self.row("d", "40"), self.row("e", "50")])
        self.write_json("schedule_01/relations.json", [
            self.relation("b", "a", "fs", 0, "v1"),
            self.relation("c", "a", "ss", -12, "v1"),
        ])
        self.write_json("schedule_02/relations.json", [
            self.relation("d", "e", "ff", 2.5, "v2"),
            self.relation("e", "d", "sf", 4, "v2"),
        ])
        self.eps = [
            {"id": "schedule-y", "type": "schedule", "name": "Север"},
            {"id": "v1", "type": "version", "parentId": "schedule-y", "name": "Версия 1"},
            {"id": "v2", "type": "version", "parentId": "schedule-x", "name": "Версия 2"},
            {"id": "schedule-x", "type": "schedule", "name": "Юг"},
        ]
        self.write_json("common/eps.json", self.eps)

    def write_json(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8-sig")

    @staticmethod
    def row(item_id, code, **values):
        return {
            "id": item_id, "type": "work", "level": 0, "parentId": None,
            "values": {"code": code, **values},
        }

    @staticmethod
    def relation(wbs_id, linked_id, kind, lag, version):
        return {"wbsId": wbs_id, "linkedWbsId": linked_id, "type": kind,
                "lag": lag, "versionId": version}

    def test_wbs_dates_and_raw_links_are_preserved(self):
        self.write_json("project_01/wbs.json", self.rows)
        attributes = (self.root / "common/wbs-attributes.json").read_bytes()
        (self.root / "project_01/wbs-attributes.json").write_bytes(attributes)
        items = load_schedule(self.root / "project_01")
        self.assertEqual(items, load_project_schedule(self.root / "schedule_01").items)
        first, second, _ = items
        self.assertEqual(first.target_start, datetime(1970, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(second.target_finish, datetime(1970, 1, 2, tzinfo=timezone.utc))
        self.assertIsNone(second.target_start)
        self.assertIsNone(first.target_finish)
        self.assertEqual(first.successors, "20;30")

    def test_loads_only_selected_schedule_and_maps_typed_relations(self):
        first = load_project_schedule(self.root / "schedule_01")
        second = load_project_schedule(self.root / "schedule_02")
        self.assertEqual((first.version_id, first.name), ("v1", "Север"))
        self.assertEqual((second.version_id, second.name), ("v2", "Юг"))
        self.assertEqual([item.id for item in first.items], ["a", "b", "c"])
        self.assertEqual([item.id for item in second.items], ["d", "e"])
        self.assertEqual(first.dependencies, [
            ScheduleDependency("a", "b", DependencyType.FINISH_TO_START, 0, "v1", True),
            ScheduleDependency("a", "c", DependencyType.START_TO_START, -12, "v1", True),
        ])
        self.assertEqual(second.dependencies, [
            ScheduleDependency("d", "e", DependencyType.FINISH_TO_FINISH, 2.5, "v2", False),
            ScheduleDependency("e", "d", DependencyType.START_TO_FINISH, 4, "v2", False),
        ])

    def test_relations_file_is_required_for_new_schedule(self):
        (self.root / "schedule_02/relations.json").unlink()
        with self.assertRaises(FileNotFoundError):
            load_project_schedule(self.root / "schedule_02")

    def test_empty_or_ambiguous_relations_are_rejected(self):
        for relations, message in (
            ([], "Ограничение MVP"),
            ([self.relation("a", "b", "fs", 0, "v1"),
              self.relation("b", "a", "fs", 0, "v2")], "Неоднозначность"),
        ):
            with self.subTest(relations=relations):
                self.write_json("schedule_01/relations.json", relations)
                with self.assertRaisesRegex(ValueError, message):
                    load_project_schedule(self.root / "schedule_01")

    def test_schedule_names_use_eps_parent_of_each_relations_version(self):
        self.assertEqual(load_schedule_names(self.root), {
            "schedule_01": "Север",
            "schedule_02": "Юг",
            "schedule_03": "График 03",
        })

    def test_schedule_name_falls_back_when_version_or_parent_is_unknown(self):
        for missing_id, expected in (
            ("v1", {"schedule_01": "График 01", "schedule_02": "Юг"}),
            ("schedule-x", {"schedule_01": "Север", "schedule_02": "График 02"}),
        ):
            with self.subTest(missing_id=missing_id):
                self.write_json("common/eps.json", [
                    node for node in self.eps if node["id"] != missing_id
                ])
                self.assertEqual(load_schedule_names(self.root), {
                    **expected, "schedule_03": "График 03",
                })
