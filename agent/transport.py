"""HTTP requests to the organisation's server, shared by the agent, the desktop control and the gateway.

An office server has its own certificate that no certificate authority signed (desktop/tls.py).
When WORKTRACK_SERVER_PIN holds that certificate's SHA-256 fingerprint, HTTPS connections accept
exactly that certificate and nothing else. Without a pin the normal certificate checks apply.
The launcher sets the variable, so the agent it starts inherits it.

On macOS the trusted root certificates come from the system keychains: an installed app cannot
rely on the certificate file of the Python it was built with (it is missing on other Macs).
"""

import functools
import hashlib
import hmac
import http.client
import os
import ssl
import subprocess
import sys
from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener

MAC_KEYCHAINS = ('/System/Library/Keychains/SystemRootCertificates.keychain', '/Library/Keychains/System.keychain')

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


def mac_roots():
    """PEM text of the certificates macOS trusts for everyone (Apple's roots and ones the IT added)."""
    try:
        result = subprocess.run(
            ['/usr/bin/security', 'find-certificate', '-a', '-p', *MAC_KEYCHAINS],
            capture_output=True,
            timeout=15,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ''
    return result.stdout.decode('ascii', 'ignore')


@functools.lru_cache(maxsize=1)
def trusted_context():
    context = ssl.create_default_context()
    if sys.platform == 'darwin':
        pem = mac_roots()
        if pem:
            try:
                context.load_verify_locations(cadata=pem)
            except (ssl.SSLError, ValueError):
                pass  # Keep Python's own defaults.
    return context


def opener(follow_redirects=False, pin=None):
    handlers = [] if follow_redirects else [NoRedirect()]
    pin = pin or os.environ.get(PIN_ENV)
    handlers.append(PinnedHTTPSHandler(pin.lower()) if pin else HTTPSHandler(context=trusted_context()))
    return build_opener(*handlers)


def open_url(request, timeout, follow_redirects=False, pin=None):
    return opener(follow_redirects, pin).open(request, timeout=timeout)
