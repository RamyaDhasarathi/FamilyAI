"""HTML from strangers, read in time that grows with its length and not with its length squared.

A pattern like `<script.*?</script>` run over a mail's HTML is quadratic when the tag is opened and never closed: every opener scans to the
end of the text looking for a closer that is not there, so a megabyte of `<script>` held the worker (and its event loop) for minutes. These
helpers do the same jobs with `str.find` and the standard parser, each of which reads the text once.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

MAX_HTML = 2_000_000          # characters of one HTML part that anything here will look at

_OPEN = {t: re.compile(rf"<{t}\b", re.I) for t in ("script", "style", "noscript")}


def strip_blocks(html: str, tags: tuple[str, ...] = ("script", "style")) -> str:
    """The text with each `<tag ...>...</tag>` block (those tags only) replaced by a space. A block that is opened and never closed
    swallows the rest of the text, as a browser reads it; and once one closer is missing, none after it can be found, so the scan stops."""
    html = html[:MAX_HTML]
    for tag in tags:
        opener = _OPEN[tag]
        closer = re.compile(rf"</{tag}\b[^>]*>?", re.I)
        out: list[str] = []
        at = 0
        while True:
            m = opener.search(html, at)
            if m is None:
                out.append(html[at:])
                break
            out.append(html[at:m.start()])
            out.append(" ")
            gt = html.find(">", m.end())              # the opener's own end; none, and the tag never ends
            if gt < 0:
                break
            end = closer.search(html, gt + 1)
            if end is None:
                break                                 # never closed: the rest is inside the block
            at = end.end()
        html = "".join(out)
    return html


class _Text(HTMLParser):
    BREAKS = frozenset({"br", "p", "div", "li", "tr"})
    SKIP = frozenset({"script", "style", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._size = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "br":
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip and self._size < MAX_HTML:
            self._size += len(data)
            self.parts.append(data)
            self.parts.append(" ")


def text_of(html: str) -> str:
    """The readable words of an HTML part: tags dropped, script and style content dropped, line breaks at paragraph ends. Linear in the
    text; an unclosed tag at the end is read as the words it is."""
    parser = _Text()
    try:
        parser.feed(html[:MAX_HTML])
        parser.close()
    except Exception:  # noqa: BLE001 - HTML that will not parse has the words it has given so far
        pass
    return "".join(parser.parts)


class _Anchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, str]] = []
        self._href: str | None = None
        self._words: list[str] = []
        self._alt: str = ""

    def _close(self) -> None:
        if self._href is not None and len(self.found) < 200:
            anchor = " ".join(" ".join(self._words).split())[:80]
            self.found.append((anchor or self._alt, self._href.strip()))
        self._href, self._words, self._alt = None, [], ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a":
            self._close()                             # an unclosed anchor ends where the next begins
            if a.get("href"):
                self._href = a["href"]
        elif tag == "img" and self._href is not None and not self._alt:
            self._alt = a.get("alt") or ""

    def handle_endtag(self, tag):
        if tag == "a":
            self._close()

    def handle_data(self, data):
        if self._href is not None and len(self._words) < 400:
            self._words.append(data)


def anchors(html: str) -> list[tuple[str, str]]:
    """Every link with a href in the HTML, with the words it was hung on (or its image's alt text), at most 200."""
    parser = _Anchors()
    try:
        parser.feed(html[:MAX_HTML])
        parser.close()
    except Exception:  # noqa: BLE001 - HTML that will not parse has the links it has given so far
        pass
    return parser.found
