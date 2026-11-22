import json
import importlib.util
import os
import sys
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from src.agent.analyzer import SECTION_FIELDS, analyze_project
from src.agent.context import build_context
from src.agent.model import format_references
from src.canonical.model import DependencyType, ProjectSchedule, ScheduleDependency, ScheduleItem
from src.workflows.schedule_actuality import check_schedule_actuality


class MultiScheduleTest(unittest.TestCase):
    def setUp(self):
        self.date = date(2026, 11, 14)
        item = ScheduleItem(
            id="same-id", code="10", name="Work", type="work", parent_id=None,
            level=0, start=None, finish=datetime(2026, 11, 12, tzinfo=timezone.utc),
            progress=50, status="in_progress", predecessors=None, successors=None,
        )
        self.schedules = [
            ProjectSchedule("v1", "Север", [item], []),
            ProjectSchedule("v2", "Юг", [
                replace(item, progress=100),
                replace(item, id="other", parent_id="same-id", code="20"),
            ], [ScheduleDependency("same-id", "other", DependencyType.START_TO_START,
                                   -3, "v2", True)]),
        ]
        self.findings = {
            schedule.version_id: check_schedule_actuality(schedule.items, self.date)
            for schedule in self.schedules
        }
        self.sdk = ModuleType("openai")
        self.sdk.APIError = RuntimeError
        self.sdk.OpenAI = MagicMock()
        self.create = self.sdk.OpenAI.return_value.__enter__.return_value.responses.create

    def report(self, references):
        report = {section: [] for section in SECTION_FIELDS}
        report["analysis"] = [{"references": references, "conclusion": "Проверить данные."}]
        return report

    def invoke(self, report, schedules=None, normative_context=None):
        self.create.return_value = SimpleNamespace(
            status="completed", output_text=json.dumps(report)
        )
        with patch.dict(sys.modules, {"openai": self.sdk}), patch.dict(
            os.environ, {"OPENAI_API_KEY": "test"}
        ):
            return analyze_project(
                self.schedules if schedules is None else schedules, self.findings, self.date,
                normative_context=normative_context,
            )

    def test_optional_rag_preserves_base_request_and_report_schema(self):
        report = {section: [] for section in SECTION_FIELDS}
        with patch("src.rag.search.search") as retrieve:
            self.invoke(report)
            baseline = self.create.call_args.kwargs
            self.assertEqual(
                baseline["input"], build_context(self.schedules, self.findings, self.date)
            )
            prompt = Path("src/agent/prompts/project_analysis.txt").read_text(encoding="utf-8")
            self.assertEqual(baseline["instructions"], prompt)
            self.create.reset_mock()
            normative = "Источник: Порядок.docx\n7. Синтетическое нормативное требование."
            self.invoke(report, normative_context=normative)
            self.create.assert_called_once()
            enriched = self.create.call_args.kwargs
            context = json.loads(enriched["input"])
            self.assertEqual(context.pop("normative_context"), normative)
            self.assertEqual(context, json.loads(baseline["input"]))
            self.assertTrue(enriched["instructions"].startswith(prompt))
            self.assertIn("not an exhaustive list", enriched["instructions"])
            self.assertEqual(enriched["text"], baseline["text"])
            self.assertEqual(enriched["model"], baseline["model"])
            retrieve.assert_not_called()
            self.create.reset_mock()
            with self.assertRaises(ValueError):
                self.invoke(report, normative_context=" ")
            self.create.assert_not_called()

    def test_independent_checks_and_context_with_colliding_ids_and_codes(self):
        self.assertEqual(len(self.findings["v1"]), 1)
        self.assertEqual(len(self.findings["v2"]), 1)
        context = json.loads(build_context(self.schedules, self.findings, self.date))
        first, second = context["schedules"]
        self.assertIsNone(first["schedule"][0]["parent_code"])
        self.assertEqual(second["schedule"][1]["parent_code"], "10")
        self.assertEqual(first["dependencies"], [])
        self.assertEqual(second["dependencies"][0]["lag"], -3)
        self.assertEqual(second["dependencies"][0]["first_item_id"], "same-id")
        self.assertEqual(first["findings"][0]["item_id"], "same-id")
        self.assertEqual(second["findings"][0]["item_id"], "other")

    def test_one_request_and_unified_report_with_cross_schedule_and_whole_schedule_refs(self):
        references = [
            {"version_id": "v1", "item_id": "same-id", "code": "10"},
            {"version_id": "v2", "item_id": "same-id", "code": "10"},
            {"version_id": "v2", "item_id": None, "code": None},
        ]
        result = self.invoke(self.report(references))
        self.create.assert_called_once()
        context = json.loads(self.create.call_args.kwargs["input"])
        self.assertEqual([s["version_id"] for s in context["schedules"]], ["v1", "v2"])
        self.assertEqual(result.analysis[0]["references"], references)
        self.assertEqual(format_references(references, self.schedules),
                         "Север — работы 10\nЮг")
        schema = self.create.call_args.kwargs["text"]["format"]
        self.assertTrue(schema["strict"])
        self.assertEqual(set(schema["schema"]["properties"]), set(SECTION_FIELDS))

    def test_single_schedule_uses_same_request_path(self):
        result = self.invoke(self.report([
            {"version_id": "v1", "item_id": "same-id", "code": "10"}
        ]), self.schedules[:1])
        self.create.assert_called_once()
        self.assertEqual(len(json.loads(self.create.call_args.kwargs["input"])["schedules"]), 1)
        self.assertEqual(len(result.analysis), 1)

    def test_reference_formatting_groups_schedules_and_preserves_order(self):
        cases = [
            ([("v1", "a", "311")], "Север — работы 311"),
            ([("v1", "a", "311"), ("v1", "b", "313"), ("v1", "c", "419")],
             "Север — работы 311, 313, 419"),
            ([("v1", "a", "311"), ("v2", "b", "10"), ("v1", "c", "419")],
             "Север — работы 311, 419\nЮг — работы 10"),
            ([("v2", None, None)], "Юг"),
            ([("v1", "a", None)], "Север — работы без кода"),
        ]
        for values, expected in cases:
            references = [
                {"version_id": version, "item_id": item, "code": code}
                for version, item, code in values
            ]
            with self.subTest(values=values):
                self.assertEqual(format_references(references, self.schedules), expected)

    def test_invalid_version_item_or_code_is_rejected(self):
        for reference in (
            {"version_id": "unknown", "item_id": None, "code": None},
            {"version_id": "v1", "item_id": "other", "code": "20"},
            {"version_id": "v1", "item_id": "same-id", "code": "wrong"},
            {"version_id": "v1", "item_id": None, "code": "10"},
        ):
            with self.subTest(reference=reference):
                with self.assertRaisesRegex(RuntimeError, "ссылки"):
                    self.invoke(self.report([reference]))

    def test_empty_or_duplicate_selection_fails_before_request(self):
        for schedules in ([], [self.schedules[0], self.schedules[0]]):
            with self.subTest(schedules=schedules):
                with self.assertRaises(ValueError):
                    self.invoke({}, schedules)
        self.create.assert_not_called()

    def test_parent_and_dependency_codes_do_not_resolve_from_another_schedule(self):
        first = replace(self.schedules[0], items=[
            replace(self.schedules[0].items[0], parent_id="other")
        ], dependencies=[
            ScheduleDependency("same-id", "other", DependencyType.FINISH_TO_START, 0,
                               "v1", False)
        ])
        context = json.loads(build_context(
            [first, self.schedules[1]], self.findings, self.date
        ))["schedules"][0]
        self.assertIsNone(context["schedule"][0]["parent_code"])
        self.assertIsNone(context["dependencies"][0]["second_code"])

    def test_streamlit_selection_runs_one_common_analysis_and_blocks_empty_selection(self):
        st = MagicMock()
        spec = importlib.util.spec_from_file_location(
            "multi_schedule_ui_test", Path(__file__).resolve().parents[1] / "streamlit_app.py"
        )
        ui = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"streamlit": st}):
            spec.loader.exec_module(ui)
        st.button.side_effect = lambda label, **kwargs: label == "Провести анализ"
        st.session_state = {}
        st.checkbox.return_value = False
        st.columns.return_value = [MagicMock(), MagicMock()]
        st.date_input.return_value = self.date
        names = {"schedule_01": "Север", "schedule_02": "Юг", "schedule_03": "Вендоры"}
        self.schedules.append(ProjectSchedule(
            "v3", "Вендоры",
            [replace(self.schedules[0].items[0], id="vendor", code="A100")], [],
        ))
        report = {
            section: [{
                "references": [
                    {"version_id": "v1", "item_id": "same-id", "code": "10"}
                ],
                field: "Полный текст " + section + "\nВторая строка без сокращений.",
            }]
            for section, field in SECTION_FIELDS.items()
        }
        self.create.return_value = SimpleNamespace(
            status="completed", output_text=json.dumps(report)
        )
        with patch.dict(sys.modules, {"openai": self.sdk}), patch.dict(
            os.environ, {"OPENAI_API_KEY": "test"}
        ), patch.object(ui, "load_dotenv"), patch.object(ui, "render_knowledge_base"), patch.object(
            ui, "load_schedule_names", return_value=names
        ), patch.object(ui, "load_project_schedule") as load, patch.object(
            Path, "is_dir", return_value=True
        ), patch("src.rag.search.search") as retrieve, patch(
            "src.rag.index.VectorIndex"
        ) as vector_index:
            load.side_effect = lambda path: self.schedules[list(names).index(path.name)]
            for selection in (["schedule_01"], ["schedule_01", "schedule_02"], list(names)):
                with self.subTest(selection=selection):
                    st.reset_mock()
                    self.create.reset_mock()
                    st.multiselect.return_value = selection
                    ui.main()
                    st.error.assert_not_called()
                    self.create.assert_called_once()
                    retrieve.assert_not_called()
                    vector_index.assert_not_called()
                    self.assertFalse(st.checkbox.call_args.kwargs["value"])
                    context = json.loads(self.create.call_args.kwargs["input"])
                    self.assertEqual(len(context["schedules"]), len(selection))
                    self.assertEqual(st.dataframe.call_count, len(selection))
                    for key, table in zip(selection, st.dataframe.call_args_list):
                        schedule = self.schedules[list(names).index(key)]
                        rows = table.args[0]
                        self.assertEqual({row["График"] for row in rows}, {names[key]})
                        self.assertEqual(
                            [row["Код"] for row in rows],
                            [finding.code for finding in check_schedule_actuality(
                                schedule.items, self.date
                            )],
                        )
                        self.assertEqual(table.kwargs["column_config"], {"График": None})
                    self.assertEqual(
                        [call.args[0] for call in st.text.call_args_list],
                        [
                            value
                            for section, field in SECTION_FIELDS.items()
                            for value in (
                                "Работы 10" if len(selection) == 1 else "Север — работы 10",
                                report[section][0][field],
                            )
                        ],
                    )
                    self.assertEqual(
                        [call.args[0] for call in st.subheader.call_args_list],
                        ([names[key] for key in selection] if len(selection) > 1 else [])
                        + list(ui.SECTION_LABELS.values()),
                    )
            st.checkbox.return_value = True
            st.multiselect.return_value = list(names)
            fragments = [
                {"source": f"Регламент {number}.docx", "text": f"Требование {number}."}
                for number in range(3)
            ]
            retrieve.return_value = fragments
            self.create.reset_mock()
            ui.main()
            self.create.assert_called_once()
            retrieve.assert_called_once()
            self.assertEqual(retrieve.call_args.kwargs, {"top_k": 3})
            query = retrieve.call_args.args[1]
            self.assertIn("базовые и целевые сроки", query)
            self.assertIn("Незавершённые работы", query)
            context = json.loads(self.create.call_args.kwargs["input"])
            self.assertEqual(len(context["schedules"]), 3)
            for fragment in fragments:
                self.assertIn(fragment["source"], context["normative_context"])
                self.assertIn(fragment["text"], context["normative_context"])
            vector_index.return_value.build.assert_not_called()
            for error in (ValueError("Индекс отсутствует"), RuntimeError("Ошибка поиска")):
                self.create.reset_mock()
                retrieve.side_effect = error
                ui.main()
                self.create.assert_not_called()
                self.assertIn("Анализ с RAG невозможен", st.error.call_args.args[0])
            retrieve.side_effect = None
            retrieve.return_value = []
            ui.main()
            self.create.assert_not_called()
            st.checkbox.return_value = False
            st.reset_mock()
            st.multiselect.return_value = list(names)
            st.date_input.return_value = date(1970, 1, 1)
            ui.main()
            st.dataframe.assert_not_called()
            st.info.assert_called_with("Контрольные отклонения не выявлены.")
            self.assertEqual(
                [call.args[0] for call in st.subheader.call_args_list],
                list(ui.SECTION_LABELS.values()),
            )
            st.date_input.return_value = self.date
            st.reset_mock()
            st.multiselect.return_value = ["schedule_01"]
            whole_schedule_report = {
                section: [{
                    "references": [{"version_id": "v1", "item_id": None, "code": None}],
                    field: report[section][0][field],
                }]
                for section, field in SECTION_FIELDS.items()
            }
            self.create.return_value.output_text = json.dumps(whole_schedule_report)
            ui.main()
            st.error.assert_not_called()
            self.assertEqual(
                [call.args[0] for call in st.text.call_args_list],
                [report[section][0][field] for section, field in SECTION_FIELDS.items()],
            )
            self.create.reset_mock()
            load.reset_mock()
            st.multiselect.return_value = []
            ui.main()
            self.assertTrue(st.button.call_args.kwargs["disabled"])
            load.assert_not_called()
            self.create.assert_not_called()
            for message in ("Ограничение MVP", "Неоднозначность"):
                st.multiselect.return_value = ["schedule_01"]
                load.side_effect = ValueError(message)
                ui.main()
                st.error.assert_called_with(message)
                self.create.assert_not_called()
