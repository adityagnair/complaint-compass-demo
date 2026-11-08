import os
from functools import lru_cache
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
MODEL_CACHE = Path(os.getenv("SENTENCE_TRANSFORMERS_HOME", BACKEND_DIR / "data" / "model-cache"))
if not MODEL_CACHE.is_absolute():
    MODEL_CACHE = BACKEND_DIR / MODEL_CACHE
EMBEDDING_DIMENSIONS = 384


class EmbeddingModelUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _load_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME, cache_folder=str(MODEL_CACHE), device="cpu")


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 384), dtype=np.float32)
    try:
        model = _load_model()
        vectors = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
    except Exception as exc:
        raise EmbeddingModelUnavailable(
            f"Could not load {MODEL_NAME}. Check the model cache or allow its first-run download."
        ) from exc
    return np.asarray(vectors, dtype=np.float32)
