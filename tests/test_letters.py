import importlib.util
import json
import os
import sys
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from src.agent.letters import generate_letters
from src.agent.model import ProjectAnalysis
from src.canonical.model import ProjectSchedule, ScheduleItem
from src.workflows.schedule_actuality import check_schedule_actuality


def synthetic_schedules():
    item = ScheduleItem(
        id="shared-id", code="A-1", name="Работа Альфа", type="work",
        parent_id=None, level=0, start=None,
        finish=datetime(2026, 11, 12, tzinfo=timezone.utc),
        progress=50, status="in_progress", predecessors=None, successors=None,
    )
    return [
        ProjectSchedule("v1", "Альфа", [item], []),
        ProjectSchedule("v2", "Бета", [replace(item, name="Работа Бета")], []),
        ProjectSchedule("v3", "Гамма", [replace(item, name="Работа Гамма")], []),
    ]


def draft(schedule):
    return {
        "version_id": schedule.version_id,
        "subject": "Уточнение состояния проекта «" + schedule.name + "»",
        "body": (
            "Добрый день!\n\n"
            "По работе A-1 просим уточнить фактическое состояние и причины отклонения "
            "от указанного срока окончания. При необходимости просим актуализировать график."
        ),
    }


class LetterGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.date = date(2026, 11, 14)
        self.schedules = synthetic_schedules()
        self.findings = {
            schedule.version_id: check_schedule_actuality(schedule.items, self.date)
            for schedule in self.schedules
        }
        self.analysis = ProjectAnalysis([], [], [], [])
        self.sdk = ModuleType("openai")
        self.sdk.APIError = RuntimeError
        self.sdk.OpenAI = MagicMock()
        self.create = self.sdk.OpenAI.return_value.__enter__.return_value.responses.create

    def invoke(self, schedules=None):
        with patch.dict(sys.modules, {"openai": self.sdk}), patch.dict(
            os.environ, {"OPENAI_API_KEY": "test"}
        ):
            return generate_letters(
                self.schedules if schedules is None else schedules,
                self.findings, self.analysis, self.date,
            )

    def test_one_or_three_letters_with_one_request_and_isolated_project_inputs(self):
        self.analysis.analysis = [
            {
                "references": [{"version_id": schedule.version_id,
                                "item_id": "shared-id", "code": "A-1"}],
                "conclusion": "Уточнить состояние проекта " + schedule.name,
            }
            for schedule in self.schedules
        ] + [{
            "references": [
                {"version_id": "v1", "item_id": None, "code": None},
                {"version_id": "v2", "item_id": None, "code": None},
            ],
            "conclusion": "Общий вывод Альфа и Бета",
        }]
        for count in (1, 3):
            schedules = self.schedules[:count]
            self.create.reset_mock()
            self.create.return_value = SimpleNamespace(
                status="completed",
                output_text=json.dumps({"letters": [draft(s) for s in reversed(schedules)]}),
            )
            with self.subTest(count=count), patch(
                "src.agent.analyzer.analyze_project"
            ) as analyze, patch(
                "src.workflows.schedule_actuality.check_schedule_actuality"
            ) as check, patch("src.rag.search.search") as retrieve:
                result = self.invoke(schedules)
                self.create.assert_called_once()
                analyze.assert_not_called()
                check.assert_not_called()
                retrieve.assert_not_called()
                self.assertEqual([letter["version_id"] for letter in result],
                                 [schedule.version_id for schedule in schedules])
                payload = json.loads(self.create.call_args.kwargs["input"])
                for schedule, project, letter in zip(schedules, payload["projects"], result):
                    self.assertEqual(project["version_id"], schedule.version_id)
                    self.assertEqual(project["referenced_items"][0]["name"],
                                     schedule.items[0].name)
                    self.assertEqual(project["findings"][0]["name"], schedule.items[0].name)
                    self.assertEqual(len(project["analysis"]["analysis"]), 1)
                    encoded = json.dumps(project, ensure_ascii=False)
                    self.assertNotIn("Общий вывод", encoded)
                    for other in self.schedules:
                        if other.version_id != schedule.version_id:
                            self.assertNotIn(other.name, encoded)
                            self.assertNotIn(other.name, letter["subject"] + letter["body"])
                options = self.create.call_args.kwargs
                self.assertFalse(options["store"])
                self.assertTrue(options["text"]["format"]["strict"])

    def test_no_findings_or_analysis_passes_no_invented_items(self):
        self.findings["v1"] = []
        self.create.return_value = SimpleNamespace(
            status="completed", output_text=json.dumps({"letters": [{
                "version_id": "v1", "subject": "Результат проверки проекта «Альфа»",
                "body": "Добрый день!\nПо представленным данным существенных замечаний не выявлено.",
            }]}),
        )
        self.invoke(self.schedules[:1])
        project = json.loads(self.create.call_args.kwargs["input"])["projects"][0]
        self.assertEqual(project["referenced_items"], [])
        self.assertEqual(project["findings"], [])
        self.assertTrue(all(not entries for entries in project["analysis"].values()))

    def test_invalid_incomplete_duplicate_or_unknown_letters_are_rejected(self):
        for letters in (
            [],
            [draft(self.schedules[0])] * 3,
            [dict(draft(s), version_id="unknown") for s in self.schedules],
            [dict(draft(s), subject="") for s in self.schedules],
            [dict(draft(s), body="Wrong greeting") for s in self.schedules],
        ):
            with self.subTest(letters=letters):
                self.create.return_value = SimpleNamespace(
                    status="completed", output_text=json.dumps({"letters": letters})
                )
                with self.assertRaises(RuntimeError):
                    self.invoke()
        self.create.return_value = SimpleNamespace(status="incomplete", output_text="")
        with self.assertRaises(RuntimeError):
            self.invoke()

    def test_api_error_is_reported(self):
        self.create.side_effect = RuntimeError("offline")
        with self.assertRaisesRegex(RuntimeError, "OpenAI"):
            self.invoke()


class LetterInterfaceTest(unittest.TestCase):
    def setUp(self):
        self.st = MagicMock()
        self.st.session_state = {}
        spec = importlib.util.spec_from_file_location(
            "letters_ui_test", Path(__file__).resolve().parents[1] / "streamlit_app.py"
        )
        self.ui = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"streamlit": self.st}):
            spec.loader.exec_module(self.ui)
        self.schedules = synthetic_schedules()
        self.st.multiselect.return_value = ["schedule_01", "schedule_02", "schedule_03"]
        self.st.date_input.return_value = date(2026, 11, 14)
        self.st.columns.return_value = [MagicMock(), MagicMock()]
        self.st.checkbox.return_value = False
        self.action = None
        self.st.button.side_effect = lambda label, **kwargs: label == self.action
        self.analysis = ProjectAnalysis([], [], [], [])

    def test_letter_reruns_reuse_snapshot_reset_stale_drafts_and_preserve_analysis_on_error(self):
        for use_rag in (False, True):
            with self.subTest(use_rag=use_rag), patch.dict(
                os.environ, {"OPENAI_API_KEY": "test"}
            ), patch.object(self.ui, "load_dotenv"), patch.object(
                self.ui, "render_knowledge_base"
            ), patch.object(self.ui, "load_schedule_names", return_value={
                f"schedule_0{i+1}": s.name for i, s in enumerate(self.schedules)
            }) as names, patch.object(
                self.ui, "load_project_schedule",
                side_effect=lambda p: self.schedules[int(p.name[-1]) - 1],
            ) as load, patch.object(
                self.ui, "check_schedule_actuality", wraps=check_schedule_actuality
            ) as check, patch.object(
                self.ui, "analyze_project", return_value=self.analysis
            ) as analyze, patch.object(
                self.ui, "generate_letters", return_value=[draft(s) for s in self.schedules]
            ) as letters, patch("src.rag.search.search", return_value=[
                {"source": "Synthetic.docx", "text": "Synthetic regulation."}
            ]) as retrieve, patch("src.rag.index.VectorIndex"), patch.object(
                Path, "is_dir", return_value=True
            ):
                self.st.session_state.clear()
                self.st.checkbox.return_value = use_rag
                self.st.multiselect.return_value = ["schedule_01", "schedule_02", "schedule_03"]
                self.action = None
                self.st.reset_mock()
                self.ui.main()
                letters.assert_not_called()
                self.assertNotIn("Подготовить письма",
                                 [call.args[0] for call in self.st.button.call_args_list])
                self.action = "Провести анализ"
                self.ui.main()
                analyze.assert_called_once()
                self.assertEqual(retrieve.call_count, int(use_rag))
                saved = self.st.session_state["project_analysis"]
                counts = (load.call_count, check.call_count, analyze.call_count,
                          retrieve.call_count, names.call_count)
                self.action = "Подготовить письма"
                self.ui.main()
                letters.assert_called_once_with(
                    saved["schedules"], saved["findings"], self.analysis,
                    self.st.date_input.return_value,
                )
                self.assertEqual(counts, (
                    load.call_count, check.call_count, analyze.call_count,
                    retrieve.call_count, names.call_count,
                ))
                self.assertEqual(len(self.st.session_state["project_letters"]), 3)
                self.assertIn("Добрый день!", self.st.code.call_args.args[0])
                self.action = None
                self.ui.main()
                self.assertEqual(letters.call_count, 1)
                letters.side_effect = RuntimeError("offline")
                self.action = "Подготовить письма"
                self.ui.main()
                self.assertIs(self.st.session_state["project_analysis"], saved)
                self.assertIn("Результаты анализа сохранены", self.st.error.call_args.args[0])
                letters.side_effect = None
                self.ui.main()
                self.action = "Провести анализ"
                self.ui.main()
                self.assertNotIn("project_letters", self.st.session_state)
                self.action = "Подготовить письма"
                self.ui.main()
                self.st.multiselect.return_value = ["schedule_01"]
                self.action = None
                self.st.reset_mock()
                self.ui.main()
                self.assertNotIn("project_analysis", self.st.session_state)
                self.assertNotIn("project_letters", self.st.session_state)
                self.st.code.assert_not_called()
                # Switching back cannot revive the discarded snapshot.
                self.st.multiselect.return_value = ["schedule_01", "schedule_02", "schedule_03"]
                self.ui.main()
                self.assertNotIn("project_analysis", self.st.session_state)
