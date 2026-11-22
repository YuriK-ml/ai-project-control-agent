import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from docx import Document

from src.rag.index import VectorIndex
from src.rag.loader import load_directory, load_document, split_text
from src.rag.search import search


def fake_embeddings(texts):
    return [[1.0, float("deadline" in text.lower()), 0.5] for text in texts]


class RagTest(unittest.TestCase):
    def setUp(self):
        # Chroma can retain open handles on Windows.
        self.root = Path(tempfile.mkdtemp(prefix="rag-test-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.documents = self.root / "documents"
        self.documents.mkdir()
        document = Document()
        document.add_heading("1. Requirements", level=1)
        document.add_paragraph("Before table.")
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Owner"
        table.cell(0, 1).text = "Deadline"
        table.cell(0, 1).add_table(rows=1, cols=1).cell(0, 0).text = "Nested rule"
        document.add_paragraph("After table.")
        document.save(self.documents / "rules.docx")
        self.embed = Mock(side_effect=fake_embeddings)
        self.index = VectorIndex(self.root / "index", self.embed)

    def test_paragraphs_tables_order_and_source(self):
        chunks = load_document(self.documents / "rules.docx")
        text = chunks[0].text
        self.assertEqual(text, (
            "1. Requirements\n\nBefore table.\n\nOwner\n\nDeadline"
            "\n\nNested rule\n\nAfter table."
        ))
        self.assertEqual(chunks[0].source, "rules.docx")
        self.assertEqual(load_directory(self.documents), chunks)

    def test_split_size_overlap_and_no_text_loss(self):
        text = "0123456789" * 235
        chunks = split_text(text)
        self.assertEqual([len(chunk) for chunk in chunks], [1000, 1000, 750])
        self.assertEqual(chunks[0][-200:], chunks[1][:200])
        self.assertEqual(chunks[0] + "".join(chunk[200:] for chunk in chunks[1:]), text)
        self.assertEqual(split_text(""), [])
        with self.assertRaises(ValueError):
            split_text("text", 10, 10)

    def test_build_reload_replace_and_search_without_reembedding_on_load(self):
        stats = self.index.build(self.documents)
        self.assertEqual(stats, {"available": True, "chunks": 1, "documents": 1})
        self.embed.reset_mock()
        loaded = VectorIndex(self.root / "index", self.embed)
        self.assertEqual(loaded.stats(), stats)
        self.embed.assert_not_called()
        results = search(loaded, "deadline")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "rules.docx")
        self.assertIn("Deadline", results[0]["text"])
        self.embed.assert_called_once_with(["deadline"])
        original = loaded._active_name()
        self.assertEqual(loaded.build(self.documents), stats)
        self.assertNotEqual(loaded._active_name(), original)
        self.assertEqual(len(loaded._client().list_collections()), 1)
        code = (
            "import sys; from pathlib import Path; from src.rag.index import VectorIndex; "
            "s=VectorIndex(Path(sys.argv[1])).stats(); "
            "assert s == {'available': True, 'chunks': 1, 'documents': 1}"
        )
        subprocess.run([sys.executable, "-c", code, str(self.root / "index")], check=True)

    def test_rebuild_replaces_sources(self):
        self.index.build(self.documents)
        (self.documents / "rules.docx").rename(self.documents / "replacement.docx")
        self.index.build(self.documents)
        self.assertEqual(self.index.stats()["chunks"], 1)
        self.assertEqual(search(self.index, "deadline")[0]["source"], "replacement.docx")

    def test_failed_rebuild_preserves_saved_index(self):
        self.index.build(self.documents)
        original = self.index._active_name()
        self.embed.side_effect = RuntimeError("embedding unavailable")
        with self.assertRaises(RuntimeError):
            self.index.build(self.documents)
        self.assertEqual(self.index._active_name(), original)
        self.assertEqual(self.index.stats()["chunks"], 1)
        self.assertEqual(len(self.index._client().list_collections()), 1)
        self.assertFalse((self.root / "index/build.lock").exists())

    def test_missing_empty_index_and_query(self):
        self.assertEqual(self.index.stats(), {"available": False, "chunks": 0, "documents": 0})
        self.assertFalse(self.index.directory.exists())
        with self.assertRaisesRegex(ValueError, "отсутствует"):
            search(self.index, "deadline")
        self.embed.assert_not_called()
        self.index.build(self.documents)
        self.index.collection().delete(ids=["0"])
        with self.assertRaisesRegex(ValueError, "пуст"):
            search(self.index, "deadline")
        with self.assertRaises(ValueError):
            search(self.index, " ")

    def test_bad_or_empty_document_is_not_silently_skipped(self):
        (self.documents / "bad.docx").write_bytes(b"invalid")
        with self.assertRaises(Exception):
            self.index.build(self.documents)
        self.embed.assert_not_called()
        self.assertFalse(self.index.stats()["available"])

    def test_streamlit_rag_actions_are_explicit_and_failure_is_reported(self):
        st = MagicMock()
        spec = importlib.util.spec_from_file_location(
            "rag_ui_test", Path(__file__).resolve().parents[1] / "streamlit_app.py"
        )
        ui = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"streamlit": st}):
            spec.loader.exec_module(ui)
        with patch("src.rag.index.VectorIndex") as factory, patch(
            "src.rag.search.search"
        ) as retrieve:
            index = factory.return_value
            index.stats.return_value = {"available": False, "chunks": 0, "documents": 0}
            st.button.return_value = False
            ui.render_knowledge_base(self.root)
            index.build.assert_not_called()
            retrieve.assert_not_called()
            st.button.side_effect = lambda label, **kwargs: kwargs["key"] == "rag_build"
            index.build.side_effect = RuntimeError("offline")
            ui.render_knowledge_base(self.root)
            st.error.assert_called()
            st.success.assert_not_called()
            index.build.side_effect = None
            index.build.return_value = {"available": True, "chunks": 7, "documents": 3}
            ui.render_knowledge_base(self.root)
            st.success.assert_called_once()
            st.button.side_effect = lambda label, **kwargs: kwargs["key"] == "rag_search"
            st.text_input.return_value = "deadline"
            retrieve.return_value = [{"text": "Synthetic rule.", "source": "test.docx"}]
            ui.render_knowledge_base(self.root)
            retrieve.assert_called_once_with(index, "deadline")
            st.text.assert_called_once_with("Synthetic rule.")
            st.caption.assert_any_call("test.docx")
