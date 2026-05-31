"""Token 计数：优先 tiktoken，不可用时回退字符估算。"""

from __future__ import annotations

import logging

from app.config import REVIEW_USE_TIKTOKEN, TIKTOKEN_ENCODING

logger = logging.getLogger("aicr")

_FALLBACK_CHARS_PER_TOKEN = 4
_encoder = None
_encoder_failed = False


def _get_encoder():
    global _encoder, _encoder_failed
    if _encoder_failed or not REVIEW_USE_TIKTOKEN:
        return None
    if _encoder is not None:
        return _encoder
    try:
        import tiktoken

        _encoder = tiktoken.get_encoding(TIKTOKEN_ENCODING)
        return _encoder
    except Exception as e:
        logger.warning(f"tiktoken unavailable ({e}), using char/4 estimate")
        _encoder_failed = True
        return None


def count_tokens(text: str) -> int:
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(text) // _FALLBACK_CHARS_PER_TOKEN)


def reset_encoder_cache() -> None:
    """测试用：重置 tiktoken 缓存。"""
    global _encoder, _encoder_failed
    _encoder = None
    _encoder_failed = False
