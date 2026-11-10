"""Shared URL helpers."""
from urllib.parse import urlsplit


def safe_next(target):
    """Return target only if it is a path on this site, else None.

    Blocks absolute URLs, protocol-relative ones (//evil), and backslash or
    control-character tricks that browsers turn into them (/\\evil).
    """
    if not target or not isinstance(target, str):
        return None
    if "\\" in target or any(ord(c) < 32 or ord(c) == 127 for c in target):
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target
