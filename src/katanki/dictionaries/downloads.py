"""Bounded HTTPS downloads shared by pack builds and dictionary updates."""

from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def https_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Dictionary downloads require HTTPS without credentials.")
    return url


class HttpsRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        https_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def download(url: str, *, limit: int) -> bytes:
    request = Request(https_url(url), headers={"User-Agent": "Kanji-Katanki/1 dictionary-updater"})
    with build_opener(HttpsRedirect()).open(request, timeout=30) as response:
        https_url(response.url)
        chunks, size = [], 0
        while chunk := response.read(min(1024 * 1024, limit + 1 - size)):
            size += len(chunk)
            if size > limit:
                raise ValueError("Dictionary download exceeds its size limit.")
            chunks.append(chunk)
    return b"".join(chunks)
