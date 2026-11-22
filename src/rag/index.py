import json
import os
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from src.rag.loader import load_directory


EMBEDDING_MODEL = "text-embedding-3-small"


def openai_embeddings(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("Укажите OPENAI_API_KEY в .env в корне проекта.")
    with OpenAI(max_retries=0) as client:
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


class VectorIndex:
    def __init__(
        self, directory: Path,
        embed: Optional[Callable[[list[str]], list[list[float]]]] = None,
    ):
        self.directory = Path(directory)
        self.embed = embed or openai_embeddings

    def _client(self):
        import chromadb
        from chromadb.config import Settings

        return chromadb.PersistentClient(
            path=str(self.directory),
            settings=Settings(anonymized_telemetry=False),
        )

    def _active_name(self):
        manifest = self.directory / "active.json"
        if not manifest.exists():
            return None
        return json.loads(manifest.read_text(encoding="utf-8"))["collection"]

    def collection(self):
        name = self._active_name()
        if name is None:
            raise ValueError("Индекс отсутствует. Нажмите «Построить индекс».")
        return self._client().get_collection(name, embedding_function=None)

    def stats(self) -> dict:
        if self._active_name() is None:
            return {"available": False, "chunks": 0, "documents": 0}
        collection = self.collection()
        count = collection.count()
        return {
            "available": count > 0,
            "chunks": count,
            "documents": collection.metadata["documents"],
        }

    def build(self, documents: Path) -> dict:
        self.directory.mkdir(parents=True, exist_ok=True)
        lock = self.directory / "build.lock"
        try:
            handle = lock.open("x")
        except FileExistsError:
            raise RuntimeError("Индексация уже выполняется. Дождитесь её завершения.") from None
        name = "methodology_" + uuid4().hex
        client = None
        created = False
        manifest_temp = self.directory / (name + ".json.tmp")
        try:
            chunks = load_directory(documents)
            previous = self._active_name()
            client = self._client()
            collection = client.create_collection(
                name, embedding_function=None,
                metadata={
                    "documents": len({chunk.source for chunk in chunks}),
                    "embedding_model": EMBEDDING_MODEL,
                    "hnsw:space": "cosine",
                },
            )
            created = True
            for start in range(0, len(chunks), 64):
                batch = chunks[start:start + 64]
                texts = [chunk.text for chunk in batch]
                collection.add(
                    ids=[str(start + number) for number in range(len(batch))],
                    documents=texts,
                    metadatas=[{"source": chunk.source, "chunk": chunk.number} for chunk in batch],
                    embeddings=self.embed(texts),
                )
            if collection.count() != len(chunks):
                raise RuntimeError("Количество сохранённых фрагментов не совпадает с исходным.")
            manifest_temp.write_text(json.dumps({"collection": name}), encoding="utf-8")
            manifest_temp.replace(self.directory / "active.json")
        except Exception:
            if client is not None and created:
                client.delete_collection(name)
            raise
        finally:
            manifest_temp.unlink(missing_ok=True)
            handle.close()
            lock.unlink()
        # Publication succeeded. An old collection cannot affect search or statistics.
        if previous:
            try:
                client.delete_collection(previous)
            except Exception:
                pass
        return {
            "available": True, "chunks": len(chunks),
            "documents": len({chunk.source for chunk in chunks}),
        }
