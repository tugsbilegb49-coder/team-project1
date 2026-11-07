"""HTTP requests to the organisation's server, shared by the agent, the desktop control and the gateway.

An office server has its own certificate that no certificate authority signed (desktop/tls.py).
When WORKTRACK_SERVER_PIN holds that certificate's SHA-256 fingerprint, HTTPS connections accept
exactly that certificate and nothing else. Without a pin the normal certificate checks apply.
The launcher sets the variable, so the agent it starts inherits it.
"""

import functools
import hashlib
import hmac
import http.client
import os
import ssl
from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener

PIN_ENV = 'WORKTRACK_SERVER_PIN'


class PinMismatch(ssl.SSLError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # A redirect is answered as it is; never follow it with the user's token.


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, pin, **kwargs):
        context = ssl.create_default_context()
        context.check_hostname = False  # The fingerprint below identifies the server instead.
        context.verify_mode = ssl.CERT_NONE
        kwargs.pop('context', None)
        super().__init__(*args, context=context, **kwargs)
        self.pin = pin

    def connect(self):
        super().connect()
        der = self.sock.getpeercert(binary_form=True) or b''
        if not hmac.compare_digest(hashlib.sha256(der).hexdigest(), self.pin):
            self.close()
            raise PinMismatch('The server certificate changed; this is not the paired WorkTrack server.')


class PinnedHTTPSHandler(HTTPSHandler):
    def __init__(self, pin):
        super().__init__()
        self.pin = pin

    def https_open(self, req):
        return self.do_open(functools.partial(PinnedHTTPSConnection, pin=self.pin), req)


def opener(follow_redirects=False, pin=None):
    handlers = [] if follow_redirects else [NoRedirect()]
    pin = pin or os.environ.get(PIN_ENV)
    if pin:
        handlers.append(PinnedHTTPSHandler(pin.lower()))
    return build_opener(*handlers)


def open_url(request, timeout, follow_redirects=False, pin=None):
    return opener(follow_redirects, pin).open(request, timeout=timeout)
