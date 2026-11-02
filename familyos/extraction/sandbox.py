"""Parsing, in a process that holds nothing worth stealing.

`parse()` runs PyMuPDF, Pillow and Tesseract over bytes a stranger sent us.
Those are large C libraries with a long history of memory-safety bugs, and the
bytes arrive by email -- anyone who learns a household's inbound address can
post a crafted PDF. Until now that ran inside the API process, which holds the
database pool and, moment to moment, unwrapped household keys. `to_thread`
kept it off the event loop, which is latency isolation and not security
isolation: a thread shares the address space it was spawned from.

So parsing moves out. The child is this module run as `python -m`: bytes in on
stdin, JSON out on stdout, and an environment with **no FAMILYOS_ variables at
all**. Code execution in there is not handed the master key, the database
address or a way to write a file: the environment is empty of them, the
working directory is the temp directory and writes are limited to zero bytes.

What this stops, and what it does not
-------------------------------------
Stops: being handed our secrets through the environment, writing to disk,
dumping core (a core file would contain the document), running away with
memory or CPU, and hanging the worker.

Does not stop: the child reading a file by absolute path as the same user
(the project's `.env` is one, and so is anything else this account can read),
a kernel escape, or outbound network from the child. A plain process cannot
close those; they need a boundary around it. `bubblewrap` with `--unshare-net`
and only the interpreter, the libraries and the temp directory mounted is the
cheap step and a microVM the thorough one. `FAMILYOS_SANDBOX_CMD` puts either in
front of this without touching the caller. Until one is set, treat the child as
"cannot be handed secrets", not as "cannot reach them".

Fails closed. A crash, a timeout, or output that will not parse means the
extraction fails and the notice is left unread, which is visible. The
alternative -- treating a crashed parser as an empty document -- would read as
"this notice says nothing", which is the failure we would never notice.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import resource
import sys
import tempfile
import weakref

from familyos.extraction.parse import Page, ParsedDocument, Word, parse
from familyos.settings import settings

logger = logging.getLogger(__name__)

# The child is handed the media type on argv and the bytes on stdin, so no
# part of the document ever appears in a process listing.
MODULE = "familyos.extraction.sandbox"


class ParseFailed(RuntimeError):
    """The sandbox did not return a document. Never treated as an empty one."""


# ----------------------------------------------------------------------------
# the child
# ----------------------------------------------------------------------------

def _limits(memory_mb: int, cpu_seconds: int) -> None:
    """Applied in the child before it imports a parser or reads a byte."""
    soft = memory_mb * 1024 * 1024
    for what, limit in (
        (resource.RLIMIT_AS, soft),          # address space
        (resource.RLIMIT_CPU, cpu_seconds),  # SIGXCPU, then SIGKILL
        (resource.RLIMIT_FSIZE, 0),          # cannot write a file of any size
        (resource.RLIMIT_CORE, 0),           # a core dump would hold the document
        (resource.RLIMIT_NOFILE, 64),
    ):
        try:
            resource.setrlimit(what, (limit, limit))
        except (ValueError, OSError):  # noqa: PERF203 - a refused limit is not fatal
            logger.warning("could not set rlimit %s in the parse sandbox", what)


def _as_json(doc: ParsedDocument) -> dict:
    return {
        "media_type": doc.media_type,
        "notes": list(doc.notes),
        "parser_version": doc.parser_version,
        "pages": [{"number": p.number, "text": p.text, "width": p.width, "height": p.height,
                   "source": p.source,
                   # A word is a character span into the page text plus an
                   # optional box, which is what grounding draws from.
                   "words": [[w.start, w.end, list(w.box) if w.box else None] for w in p.words]}
                  for p in doc.pages],
    }


def _from_json(raw: dict) -> ParsedDocument:
    pages = [Page(number=p["number"], text=p["text"], width=p.get("width"), height=p.get("height"),
                  source=p.get("source", "text"),
                  words=[Word(start=w[0], end=w[1], box=tuple(w[2]) if w[2] else None)
                         for w in p.get("words") or []])
             for p in raw.get("pages") or []]
    return ParsedDocument(media_type=raw["media_type"], pages=pages,
                          notes=list(raw.get("notes") or []),
                          parser_version=raw.get("parser_version", ""))


MAX_PIXELS = 50_000_000     # refused above this; Pillow's own default is about 179M (two-thirds of a GB of RGB at 1 GB of memory)


def _op(name: str, data: bytes, args: dict) -> dict:
    """The other things done to a stranger's bytes: a picture for the browser or the model, the verdict on a
    picture, the QR codes on a PDF. Each is a library call that parses the file, so each runs here."""
    if name == "jpeg":
        import io

        from PIL import Image, ImageOps

        from familyos.extraction.parse import _heif
        _heif()
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            if args.get("side"):
                im.thumbnail((int(args["side"]), int(args["side"])))
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=85, optimize=True)
        import base64
        return {"jpeg": base64.b64encode(out.getvalue()).decode("ascii")}
    if name == "kind":
        from familyos import pictures
        return {"kind": pictures.kind_of(data, ocr_chars=int(args.get("ocr_chars") or 0))}
    if name == "pdfqr":
        from familyos import paylinks
        return {"codes": paylinks.from_pdf_qr(data)}
    raise ValueError(f"unknown sandbox op {name}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (3, 4):
        print("usage: python -m familyos.extraction.sandbox <media_type> <memory_mb> <cpu_seconds> [<op json>]",
              file=sys.stderr)
        return 2
    media_type, memory_mb, cpu_seconds = argv[0], int(argv[1]), int(argv[2])
    _limits(memory_mb, cpu_seconds)
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS // 2      # Pillow only warns at the limit and refuses at twice it
    except ImportError:
        pass
    data = sys.stdin.buffer.read()
    if len(argv) == 4:
        task = json.loads(argv[3])
        sys.stdout.write(json.dumps(_op(task["op"], data, task.get("args") or {})))
    else:
        doc = parse(data, media_type)
        sys.stdout.write(json.dumps(_as_json(doc)))
    sys.stdout.flush()
    return 0


# ----------------------------------------------------------------------------
# the parent
# ----------------------------------------------------------------------------

def child_env() -> dict[str, str]:
    """What the child is allowed to know.

    Everything is dropped except the few variables a parser genuinely needs.
    No FAMILYOS_ variable survives, so the child has no master key, no database
    URL, no object-store credentials and no inbound secret -- there is nothing
    in there for a compromised parser to take.
    """
    keep = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
            "TESSDATA_PREFIX", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")
    env = {k: v for k, v in os.environ.items() if k in keep}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    # Parsers that look for a network proxy should find a dead one rather than
    # the host's.
    env["no_proxy"] = "*"
    return env


def _command(media_type: str, task: dict | None = None) -> list[str]:
    """The child, optionally wrapped. FAMILYOS_SANDBOX_CMD is the seam where a
    stronger boundary goes -- `bwrap --unshare-net --unshare-pid --ro-bind / /`
    or a container runtime -- without the caller knowing."""
    inner = [sys.executable, "-I", "-m", MODULE, media_type,
             str(settings.parse_memory_mb), str(settings.parse_cpu_seconds)]
    if task is not None:
        inner.append(json.dumps(task))
    wrapper = (settings.sandbox_cmd or "").strip()
    return (wrapper.split() + inner) if wrapper else inner


_slots: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _slot() -> asyncio.Semaphore:
    """At most `parse_concurrency` children at once, per event loop. A page of thumbnails is a page of requests, and each child may take a
    gigabyte; the rest wait their turn (the timeout below counts only the child's own time)."""
    loop = asyncio.get_running_loop()
    size = max(1, settings.parse_concurrency)
    held = _slots.get(loop)
    if held is None or held[0] != size:          # a changed setting takes effect for what starts next
        held = _slots[loop] = (size, asyncio.Semaphore(size))
    return held[1]


async def _child(data: bytes, media_type: str, task: dict | None = None) -> bytes:
    async with _slot():
        return await _spawn(data, media_type, task)


async def _spawn(data: bytes, media_type: str, task: dict | None) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *_command(media_type, task),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=child_env(),
        cwd=tempfile.gettempdir(),      # not the project directory, where .env sits (-I keeps the working directory off sys.path)
        close_fds=True,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(data), timeout=settings.parse_timeout_seconds)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ParseFailed(f"parsing {media_type} took longer than "
                          f"{settings.parse_timeout_seconds}s and was killed") from None

    if proc.returncode != 0:
        detail = (err or b"")[-400:].decode("utf-8", "replace").strip()
        # A negative return code is a signal: a segfault in a parser, or the
        # CPU limit firing. Both are the interesting case.
        raise ParseFailed(f"the parse sandbox exited {proc.returncode}: {detail or 'no output'}")
    if len(out) > settings.parse_max_output_bytes:
        raise ParseFailed(f"the parse sandbox returned {len(out)} bytes, over the "
                          f"{settings.parse_max_output_bytes} limit")
    return out


async def parse_isolated(data: bytes, media_type: str) -> ParsedDocument:
    """Parse in a child process. Raises ParseFailed rather than returning an
    empty document, because an empty document reads as "this notice says
    nothing" and that is the failure nobody would notice."""
    if not settings.parse_sandbox:
        # Development escape hatch. The boot log says when it is off.
        return await asyncio.to_thread(parse, data, media_type)
    out = await _child(data, media_type)
    try:
        return _from_json(json.loads(out))
    except (ValueError, KeyError, TypeError) as exc:
        raise ParseFailed(f"the parse sandbox returned something unreadable: {exc}") from exc


async def run_op(op: str, data: bytes, **args) -> dict:
    """One of the child's other jobs on a stranger's bytes (a JPEG of a picture, a picture's verdict, a PDF's QR
    codes). Raises ParseFailed like parse_isolated; the caller decides what a failure means."""
    if not settings.parse_sandbox:
        return await asyncio.to_thread(_op, op, data, args)
    out = await _child(data, "application/octet-stream", {"op": op, "args": args})
    try:
        return json.loads(out)
    except ValueError as exc:
        raise ParseFailed(f"the parse sandbox returned something unreadable: {exc}") from exc


async def jpeg(data: bytes, side: int | None = None) -> bytes:
    import base64
    return base64.b64decode((await run_op("jpeg", data, side=side))["jpeg"])


def describe() -> str:
    if not settings.parse_sandbox:
        return ("Parsing is NOT sandboxed (FAMILYOS_PARSE_SANDBOX=false): PDFs and images are "
                "parsed in this process, which holds the database pool and household keys.")
    where = (settings.sandbox_cmd or "").strip()
    return (f"Parsing is sandboxed in a child process with no FAMILYOS_ environment, "
            f"{settings.parse_memory_mb}MB and {settings.parse_cpu_seconds}s CPU, "
            f"killed after {settings.parse_timeout_seconds}s"
            + (f", wrapped in: {where}" if where else ", unwrapped (no network namespace, and files this account can read, such as .env, are still readable by path)"))


if __name__ == "__main__":
    raise SystemExit(main())
