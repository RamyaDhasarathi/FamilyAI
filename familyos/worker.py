"""Which worker process this is. One name per process, made at import: what a Postgres-held row says when it names its owner (a taught lesson,
a running assistant task, the WhatsApp reader's profile) so another worker can tell "held by a live worker" from "left by a dead one"."""
from __future__ import annotations

import os
import secrets
import socket

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(3)}"
