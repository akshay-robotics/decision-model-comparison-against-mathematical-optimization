"""Small network guards for the local research tools."""

from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener


class NoCredentialRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        # Never forward an authenticated request to a redirect target.
        raise HTTPError(request.full_url, code, "API redirects are disabled", headers, fp)


def open_api_request(request, timeout):
    target = urlsplit(request.full_url)
    if target.scheme != "https" or target.netloc != "openrouter.ai":
        raise ValueError("API requests require the configured HTTPS provider")
    return build_opener(NoCredentialRedirect()).open(request, timeout=timeout)


def trusted_browser_request(headers, port):
    """Reject DNS rebinding and cross-origin access to the loopback server."""
    hosts = headers.get_all("Host", [])
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if port == 80:
        allowed.update({"127.0.0.1", "localhost"})
    if len(hosts) != 1 or hosts[0].lower() not in allowed:
        return False
    origins = headers.get_all("Origin", [])
    if origins and (len(origins) != 1 or origins[0] != "http://" + hosts[0].lower()):
        return False
    return headers.get("Sec-Fetch-Site", "none") != "cross-site"
