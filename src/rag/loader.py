from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


@dataclass(frozen=True)
class Chunk:
    text: str
    source: str
    number: int


def _blocks(container):
    for block in container.iter_inner_content():
        if isinstance(block, Paragraph):
            if block.text.strip():
                yield block.text.strip()
        elif isinstance(block, Table):
            for row in block.rows:
                seen = set()
                for cell in row.cells:
                    # Merged cells may appear more than once in a row.
                    if cell._tc not in seen:
                        seen.add(cell._tc)
                        yield from _blocks(cell)


def split_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("Некорректные параметры разбиения текста.")
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Prefer a paragraph or word boundary without producing tiny fragments.
        if end < len(text):
            boundary = text.rfind("\n", start + chunk_size // 2, end)
            if boundary < 0:
                boundary = text.rfind(" ", start + chunk_size // 2, end)
            if boundary > start + chunk_overlap:
                end = boundary
        fragment = text[start:end]
        if fragment.strip():
            chunks.append(fragment)
        if end == len(text):
            break
        start = end - chunk_overlap
    return chunks


def load_document(path: Path) -> list[Chunk]:
    path = Path(path)
    text = "\n\n".join(_blocks(Document(str(path))))
    return [
        Chunk(fragment, path.name, number)
        for number, fragment in enumerate(split_text(text))
    ]


def load_directory(directory: Path) -> list[Chunk]:
    paths = sorted(
        path for path in Path(directory).iterdir()
        if path.is_file() and path.suffix.lower() == ".docx" and not path.name.startswith("~$")
    )
    if not paths:
        raise ValueError("В data/documents/ не найдены DOCX-документы.")
    chunks = []
    for path in paths:
        fragments = load_document(path)
        if not fragments:
            raise ValueError(f"Документ {path.name} не содержит извлекаемого текста.")
        chunks.extend(fragments)
    return chunks
