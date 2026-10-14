"""
Fetching one page a person added. Polite and narrow: Bridge says who it is, obeys
robots.txt, follows at most three redirects, reads at most 2 MB, accepts only HTML and
PDF, and never follows a link on the page.
"""

import hashlib
import io
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "BridgeSourceReader/1.0 (sandbox student-payment demo; reads only pages a person adds)"
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 15
HTML_TYPES = ("text/html", "application/xhtml+xml")
PDF_TYPE = "application/pdf"


class FetchError(ValueError):
    """The page cannot be used. The message is shown to the person who added it."""


@dataclass(frozen=True)
class Page:
    url: str  # after redirects
    title: str
    text: str  # the readable text, one block per line
    content_hash: str


def text_hash(text: str) -> str:
    """A hash of the readable text: markup that changes on every load does not count as a change."""
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def domain_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").casefold()
    return host.removeprefix("www.")


# ---------------------------------------------------------------- reading HTML and PDF

_SKIP = {"script", "style", "noscript", "template", "svg", "head", "nav", "footer", "form", "button"}
_BLOCK = {
    "p", "div", "section", "article", "main", "header", "li", "ul", "ol", "table", "tr", "td", "th",
    "h1", "h2", "h3", "h4", "h5", "h6", "br", "blockquote", "dd", "dt", "figcaption",
}  # fmt: skip


class _Reader(HTMLParser):
    """Visible text, line by line. The page's <main> is preferred when it has one."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.body: list[str] = []
        self.main: list[str] = []
        self._skipping = 0
        self._in_title = False
        self._in_main = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        elif tag in _SKIP:
            self._skipping += 1
        elif tag == "main":
            self._in_main += 1
        if tag in _BLOCK:
            self._add("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag in _SKIP:
            self._skipping = max(0, self._skipping - 1)
        elif tag == "main":
            self._in_main = max(0, self._in_main - 1)
        if tag in _BLOCK:
            self._add("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title.append(data)
        elif not self._skipping:
            self._add(data)

    def _add(self, text: str) -> None:
        self.body.append(text)
        if self._in_main:
            self.main.append(text)


def _lines(parts: list[str]) -> str:
    lines = (" ".join(line.split()) for line in "".join(parts).split("\n"))
    return "\n".join(line for line in lines if line)


def read_html(data: bytes, charset: str | None) -> tuple[str, str]:
    """(title, text) of an HTML page."""
    reader = _Reader()
    reader.feed(data.decode(charset or "utf-8", errors="replace"))
    reader.close()
    text = _lines(reader.main) or _lines(reader.body)
    return " ".join("".join(reader.title).split()), text


def read_pdf_text(data: bytes) -> tuple[str, str]:
    """(title, text) of a PDF."""
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            title = str((pdf.metadata or {}).get("Title") or "").strip()
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as error:  # pdfplumber raises several kinds for a broken file
        raise FetchError("The PDF could not be read.") from error
    return title, _lines([text])


# ---------------------------------------------------------------- fetching


def _robots_allow(client: httpx.Client, url: str) -> bool:
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        response = client.get(robots_url, follow_redirects=True)
    except httpx.HTTPError as error:
        raise FetchError("Could not read the site's robots.txt, so the page was not fetched.") from error
    # The same reading as urllib.robotparser: 401 and 403 forbid everything; other 4xx allow everything.
    if response.status_code in (401, 403):
        return False
    if 400 <= response.status_code < 500:
        return True
    if response.status_code != 200:
        raise FetchError("Could not read the site's robots.txt, so the page was not fetched.")
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def _get(client: httpx.Client, url: str) -> tuple[httpx.Response, bytes]:
    with client.stream("GET", url) as response:
        if response.is_redirect:
            return response, b""
        if response.status_code != 200:
            raise FetchError(f"The page answered with HTTP {response.status_code}.")
        kind = response.headers.get("content-type", "").split(";")[0].strip().casefold()
        if kind not in (*HTML_TYPES, PDF_TYPE):
            raise FetchError("Only HTML pages and PDF files can be added.")
        data = bytearray()
        for chunk in response.iter_bytes():
            data += chunk
            if len(data) > MAX_BYTES:
                raise FetchError("The page is larger than 2 MB.")
        return response, bytes(data)


def fetch(url: str, client: httpx.Client | None = None) -> Page:
    """Fetch exactly this page (and at most three redirects). Raises FetchError."""
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
        raise FetchError("Enter a full web address that starts with https://.")
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    client.headers["User-Agent"] = USER_AGENT
    try:
        for _ in range(MAX_REDIRECTS + 1):
            if not _robots_allow(client, url):
                raise FetchError("The site's robots.txt does not allow this page to be fetched.")
            try:
                response, data = _get(client, url)
            except httpx.HTTPError as error:
                raise FetchError("The page could not be reached.") from error
            if response.is_redirect:
                url = urljoin(url, response.headers.get("location", ""))
                continue
            kind = response.headers.get("content-type", "").split(";")[0].strip().casefold()
            if kind == PDF_TYPE:
                title, text = read_pdf_text(data)
            else:
                title, text = read_html(data, response.charset_encoding)
            if not text:
                raise FetchError("The page has no readable text.")
            return Page(url=url, title=title or domain_of(url), text=text, content_hash=text_hash(text))
        raise FetchError("The page redirects more than three times.")
    finally:
        if own:
            client.close()
