"""The three network tools (AD-14, AD-15): what they send is exactly their `preview`.

Each tool builds its request with `preview(**args) -> {method, url, body}`; `run`
sends that very preview through the traced factory, which refuses any host
outside `allowed_hosts` and re-checks every redirect hop.
"""

from __future__ import annotations

from collections.abc import Callable
from html.parser import HTMLParser
from urllib.parse import quote

import httpx

from wavestack import config
from wavestack.messages import Message, msg
from wavestack.net.factory import create_client
from wavestack.net.guard import NetworkBlocked
from wavestack.tools.registry import ToolError, ToolSpec, Unreachable


def send(
    preview: dict[str, str],
    not_found_text: Message | None = None,
    check: Callable[[str], None] | None = None,
) -> httpx.Response:
    """Send `preview` as is; the service answered (even with an error) unless `Unreachable`.

    `check(url)` runs on every hop, redirects included, before the factory traces and sends it.
    """
    try:
        with create_client() as client:
            if check is not None:
                client.event_hooks["request"].insert(0, lambda request: check(str(request.url)))
            response = client.request(
                preview["method"],
                preview["url"],
                content=preview["body"] or None,
                follow_redirects=True,  # the factory hook runs again on every hop
            )
    except NetworkBlocked as exc:
        raise Unreachable("tools.network.blocked", cause=exc) from None
    except httpx.RequestError as exc:
        raise Unreachable(
            "tools.network.unreachable",
            kind=type(exc).__name__,
            host=httpx.URL(preview["url"]).host,
        ) from None
    if response.status_code == 404 and not_found_text:
        raise ToolError(not_found_text)
    if response.status_code >= 400:
        raise ToolError(
            "tools.network.http_error",
            status=response.status_code,
            reason=response.reason_phrase,
        )
    return response


def _get(url: str) -> dict[str, str]:
    return {"method": "GET", "url": str(httpx.URL(url)), "body": ""}


# ---------- HTML to text (stdlib) ----------


_SKIPPED = {"script", "style", "nav", "header", "footer", "noscript", "svg"}
_BLOCKS = {"p", "li", "div", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED:
            self._skipping += 1
        elif tag in _BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED and self._skipping:
            self._skipping -= 1
        elif tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


# ---------- the tools, closed over the configuration ----------


def network_tools(
    cfg: config.Config, language: Callable[[], str] = lambda: config.DEFAULT_LANGUAGE
) -> list[ToolSpec]:
    """The network tools; `language` is the session's (languages 5/5), read at each call
    for the texts a result carries (`fetch_page`'s cut)."""

    def holidays_preview(year: int) -> dict[str, str]:
        if not 1900 <= year <= 2100:
            raise ToolError("tools.network.year", year=year)
        return _get(f"https://calendrier.api.gouv.fr/jours-feries/metropole/{year}.json")

    def public_holidays(year: int) -> str:
        days = send(holidays_preview(year)).json()
        return "\n".join(f"{date} : {name}" for date, name in days.items())

    def wikipedia_preview(title: str) -> dict[str, str]:
        if not title.strip():
            raise ToolError("tools.network.empty_title")
        path = quote(title.strip().replace(" ", "_"), safe="")
        return _get(f"https://fr.wikipedia.org/api/rest_v1/page/summary/{path}")

    def wikipedia_summary(title: str) -> str:
        absent = Message("tools.network.page_absent", title=title)
        summary = send(wikipedia_preview(title), not_found_text=absent).json()
        return f"{summary.get('title') or title}\n{summary.get('extract') or ''}".strip()

    def check_page_url(url: str) -> None:
        hosts = cfg.fetch_page_hosts
        try:
            target = httpx.URL(url)
        except httpx.InvalidURL:
            target = None
        if target is None or target.scheme != "https" or target.host not in hosts:
            raise ToolError("tools.network.url_refused", url=url, hosts=", ".join(hosts))

    def page_preview(url: str) -> dict[str, str]:
        check_page_url(url)
        return _get(url)

    def fetch_page(url: str) -> str:
        response = send(page_preview(url), check=check_page_url)  # redirects checked too
        text = response.text
        if "html" in response.headers.get("content-type", "").lower():
            text = html_to_text(text)
        limit = cfg.fetch_page_max_chars
        if len(text) > limit:
            cut = msg("tools.network.cut", language(), limit=limit, total=len(text))
            text = f"{text[:limit]}\n{cut}"
        return text

    def spec(name: str, run, preview, params: dict[str, str]) -> ToolSpec:
        return ToolSpec(
            name=name,
            run=run,
            params=params,
            component=f"tools.{name}",
            hosting="network_service",
            network=True,
            preview=preview,
        )

    return [
        spec("public_holidays", public_holidays, holidays_preview, {"year": "integer"}),
        spec("wikipedia_summary", wikipedia_summary, wikipedia_preview, {"title": "string"}),
        spec("fetch_page", fetch_page, page_preview, {"url": "string"}),
    ]
