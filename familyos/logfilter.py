"""Keep credentials out of uvicorn's logs.

Sign-in links (`?link=`), socket tickets (`?ticket=`) and the session token the
iOS driver still puts in a socket URL (`?token=`) travel in query strings, and
uvicorn prints the whole request line. The filter blanks those values.
"""
from __future__ import annotations

import logging
import re

_SECRET = re.compile(r"(?i)([?&;](?:token|ticket|link)=)[^&\s\"']*")


def redact(text: str) -> str:
    return _SECRET.sub(r"\1[redacted]", text)


class RedactQuerySecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
        return True


def install() -> None:
    """Idempotent. uvicorn logs HTTP lines on uvicorn.access and websocket
    lines on uvicorn.error."""
    for name in ("uvicorn.access", "uvicorn.error", "uvicorn"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, RedactQuerySecrets) for f in lg.filters):
            lg.addFilter(RedactQuerySecrets())
