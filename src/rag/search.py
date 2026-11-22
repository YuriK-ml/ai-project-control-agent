from src.rag.index import EMBEDDING_MODEL, VectorIndex


def search(index: VectorIndex, query: str, top_k: int = 3) -> list[dict]:
    if not query.strip():
        raise ValueError("Введите запрос для поиска.")
    if top_k <= 0:
        raise ValueError("Число результатов должно быть положительным.")
    collection = index.collection()
    count = collection.count()
    if not count:
        raise ValueError("Индекс пуст. Нажмите «Построить индекс».")
    if collection.metadata["embedding_model"] != EMBEDDING_MODEL:
        raise ValueError("Модель embeddings изменилась. Перестройте индекс.")
    result = collection.query(
        query_embeddings=index.embed([query]),
        n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"],
    )
    return [
        {"text": text, "source": metadata["source"], "distance": distance}
        for text, metadata, distance in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    ]
