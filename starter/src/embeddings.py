"""Plain-text MiniLM embeddings; fixed revision, 384 dimensions, no task prefix."""
from pathlib import Path


class SentenceTransformerEmbedder:
    dimensions = 384
    model_id = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, model_name: str, revision: str, cache_dir: Path, batch_size: int = 16) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        if model_name != self.model_id or len(revision) != 40:
            raise ValueError("Use the selected MiniLM model with a pinned commit revision")
        self.model_name, self.revision, self.batch_size = model_name, revision, batch_size
        self.token_counts: dict[str, list[int]] = {"document": [], "query": []}
        torch.set_num_threads(4)
        self.model = SentenceTransformer(model_name, revision=revision, cache_folder=str(cache_dir),
                                        device="cpu", trust_remote_code=False,
                                        model_kwargs={"dtype": torch.float32})
        if self.model.get_embedding_dimension() != self.dimensions or self.model.max_seq_length != 128:
            raise ValueError("Unexpected MiniLM dimensions or sequence limit")
        self.parameter_count = sum(p.numel() for p in self.model.parameters())
        if any(p.dtype != torch.float32 for p in self.model.parameters()):
            raise ValueError("Expected float32 parameters")
        self.model.eval()

    def _encode(self, texts: list[str], kind: str) -> list[list[float]]:
        import numpy as np

        if not texts:
            return []
        if any(not isinstance(t, str) or not t.strip() for t in texts):
            raise ValueError("Embedding inputs must be nonempty text")
        counts = [len(ids) for ids in self.model.tokenizer(texts, truncation=False,
                  padding=False, add_special_tokens=True)["input_ids"]]
        if max(counts) > self.model.max_seq_length:
            raise ValueError("Input exceeds MiniLM's 128-token limit; split chunks before embedding")
        self.token_counts[kind].extend(counts)
        vectors = self.model.encode(texts, prompt="", batch_size=self.batch_size,
                                    normalize_embeddings=True, convert_to_numpy=True,
                                    show_progress_bar=len(texts) > self.batch_size)
        if vectors.shape != (len(texts), self.dimensions) or not np.isfinite(vectors).all():
            raise ValueError("Invalid embedding shape or nonfinite values")
        if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4):
            raise ValueError("Embeddings are not L2-normalized")
        return vectors.astype("float32").tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts, "document")

    def embed_query(self, question: str) -> list[float]:
        return self._encode([question], "query")[0]
