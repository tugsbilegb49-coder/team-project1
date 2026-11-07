"""HTTP requests to the organisation's server, shared by the agent, the desktop control and the gateway."""

from urllib.request import HTTPRedirectHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # A redirect is answered as it is; never follow it with the user's token.


def opener(follow_redirects=False):
    return build_opener() if follow_redirects else build_opener(NoRedirect())


def open_url(request, timeout, follow_redirects=False):
    return opener(follow_redirects).open(request, timeout=timeout)
