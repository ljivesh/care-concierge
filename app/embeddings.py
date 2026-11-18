"""The local embedding model: text in, a list of 768 numbers out.

Runs on CPU inside the app through ONNX (the fastembed library), so it needs
no API key. The same model must embed the documents and the questions.

The model name is a constant, not an env var, on purpose: the vector size is
part of the database schema (see migration 0002). Changing the model means a
new migration and re-embedding every chunk.
"""

import asyncio

from fastembed import TextEmbedding

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
EMBEDDING_DIM = 768


class Embedder:
    def __init__(self) -> None:
        # Loads the weights from the local cache (downloaded when the image was built).
        self._model = TextEmbedding(EMBEDDING_MODEL)

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # The model is CPU-bound; run it in a thread so the server stays responsive.
        return await asyncio.to_thread(self.embed_sync, texts)


if __name__ == "__main__":
    # `python -m app.embeddings` is run by the Dockerfile to bake the weights into the image.
    print(f"{EMBEDDING_MODEL}: {len(Embedder().embed_sync(['ok'])[0])} dimensions")
