"""Shadow RAG estimator – calculates how many tokens a naive RAG would inject.

Does NOT call any model or network. Only counts tokens to allow comparison
against HydraMem's filtered output.

Baseline definition (audit-friendly)
------------------------------------
The "naive RAG" baseline is intentionally **simple and conservative**:

1. Sort all chunks ever ingested by their similarity score against the query
   (the score is whatever the vector store reported the last time the chunk
   was scored; for cold chunks it defaults to 0).
2. Take the top-:pyparam:`k` (default 20).
3. Concatenate the query + each chunk's full text and count tokens with
   ``tiktoken`` (encoding ``cl100k_base``).

This is the same shape as a typical RAG that does "top-k vector retrieval +
stuff into the prompt". It does **not** include any system prompt, JSON
formatting, tool descriptions, or chain-of-thought scratch tokens. Real-world
RAG stacks usually inject *more* than this baseline, so the reported savings
% should be read as a **lower bound**.

Use ``hydramem stats --raw`` to see the unaggregated baseline / injected
token counts per call.
"""

from __future__ import annotations

import tiktoken

DEFAULT_NAIVE_K: int = 20


def estimate_naive_rag_tokens(
    query: str,
    all_chunks: list,
    k: int = DEFAULT_NAIVE_K,
    encoding_name: str = "cl100k_base",
) -> int:
    """
    Estimate how many tokens a naive top-k RAG would inject.

    Parameters
    ----------
    query:      The user query string.
    all_chunks: List of Chunk objects or plain dicts with 'text' and 'similarity'.
    k:          How many chunks the naive system would take.
    encoding_name: tiktoken encoding to use.

    Returns
    -------
    int – token count for query + top-k chunk texts concatenated.
    """

    def _sim(c) -> float:
        if hasattr(c, "similarity"):
            return float(c.similarity)
        if isinstance(c, dict):
            return float(c.get("similarity", c.get("_distance", 0.0)))
        return 0.0

    def _text(c) -> str:
        if hasattr(c, "text"):
            return str(c.text)
        if isinstance(c, dict):
            return str(c.get("text", ""))
        return ""

    sorted_chunks = sorted(all_chunks, key=_sim, reverse=True)
    top_k = sorted_chunks[:k]

    parts = [query, "\n\n"]
    for chunk in top_k:
        parts.append(_text(chunk))
        parts.append("\n")

    enc = tiktoken.get_encoding(encoding_name)
    return len(enc.encode("".join(parts)))
