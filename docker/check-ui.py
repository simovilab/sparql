"""Check Django through Gunicorn with the configured public host."""

import os
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# The default backend may redirect "/" to its slug; check that slug directly.
request = Request(
    f"http://127.0.0.1:7000/{os.environ['QLEVERUI_BACKEND']}/",
    headers={
        "Host": os.environ["QLEVERUI_ALLOWED_HOSTS"],
        "X-Forwarded-Proto": "https",
    },
)
with build_opener(NoRedirect).open(request, timeout=5) as response:
    if response.status != 200:
        raise RuntimeError(f"Unexpected UI status: {response.status}")
