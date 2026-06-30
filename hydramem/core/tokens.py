"""Token counting — single responsibility: count tokens in text."""
from __future__ import annotations

import tiktoken

_ENC_CACHE: dict[str, tiktoken.Encoding] = {}


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Return the number of tokens in *text* using tiktoken."""
    if encoding_name not in _ENC_CACHE:
        _ENC_CACHE[encoding_name] = tiktoken.get_encoding(encoding_name)
    return len(_ENC_CACHE[encoding_name].encode(text))
