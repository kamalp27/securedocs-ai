"""Real model integration test: exercises the actual SentenceTransformer model and FAISS store."""

from pathlib import Path
import numpy as np
import pytest

from app.rag.embeddings.sentence_transformer import SentenceTransformerEmbeddingService
from app.rag.vector_store.faiss_store import FAISSVectorStore


@pytest.mark.real_model
def test_real_sentence_transformer_and_faiss_end_to_end(tmp_path: Path):
    """
    Explicit integration test utilizing the actual 'all-MiniLM-L6-v2' model.
    Verifies real embedding generation, unit normalization, dimension 384,
    and FAISS semantic nearest-neighbor retrieval.
    """
    # 1. Instantiate real model service
    real_service = SentenceTransformerEmbeddingService(model_name="all-MiniLM-L6-v2", device="cpu")
    assert real_service.dimension == 384

    # 2. Generate embeddings for semantically distinct texts
    texts = [
        "Kubernetes container orchestration and pod scaling in microservices.",
        "Deep learning transformer architectures for neural language modeling.",
        "French culinary recipes for baking traditional butter croissants.",
    ]
    embeddings = real_service.generate_embeddings(texts)

    assert embeddings.shape == (3, 384)
    # Verify strict unit normalization
    for v in embeddings:
        assert np.isclose(np.linalg.norm(v), 1.0, atol=1e-4)

    # 3. Index in real FAISS store
    index_file = tmp_path / "real_model_test.index"
    store = FAISSVectorStore(dimension=384, index_path=str(index_file), auto_load=True)

    vector_ids = [101, 202, 303]
    store.add_vectors(vector_ids, embeddings, persist=True)
    assert store.ntotal == 3

    # 4. Search query semantically close to item 2 (transformers / NLP)
    query = "Neural networks and large language model transformers"
    q_vec = real_service.generate_query_embedding(query)

    hits = store.search_prefiltered(
        query_vector=q_vec,
        top_k=3,
        allowed_vector_ids=[101, 202, 303],
        threshold=0.0,
    )

    assert len(hits) == 3
    # Nearest semantic neighbor must be item 202 (deep learning transformers)
    top_hit_id, top_hit_score = hits[0]
    assert top_hit_id == 202
    assert top_hit_score > 0.5  # Cosine similarity for semantic match
    # Other hits (Kubernetes, baking croissants) have substantially lower similarity
    assert hits[1][1] < top_hit_score - 0.2
    assert hits[2][1] < top_hit_score - 0.2
