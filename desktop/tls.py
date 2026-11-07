"""HTTPS for an office server without a domain name or certificate authority.

The office server makes its own certificate once and keeps it (.runtime/tls/). Employee computers
do not trust it through a certificate authority. Instead the employee types the short code the
server shows ("pairing code", the start of the certificate's SHA-256 fingerprint); the team computer
then remembers the full fingerprint and talks only to a server presenting exactly that certificate.

The front end (TLSProxy) listens on the office network and forwards to Django on 127.0.0.1:8000,
adding X-Forwarded-For so login throttling still sees each computer's address.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import os
from pathlib import Path
import socket
import ssl
import threading

from desktop.gateway import Gateway, GatewayHandler

CODE_LENGTH = 12  # Hex digits of the fingerprint the employee types (48 bits).


def fingerprint(der):
    return hashlib.sha256(der).hexdigest()


def pairing_code(digest):
    value = digest[:CODE_LENGTH].upper()
    return '-'.join(value[i : i + 4] for i in range(0, CODE_LENGTH, 4))


def normalize_code(code):
    return ''.join(char for char in (code or '').upper() if char in '0123456789ABCDEF')


def ensure_certificate(directory, addresses=()):
    """(certificate path, key path, fingerprint); made on first use and kept afterwards.

    Keeping it means the code stays the same when the computer's IP address changes.
    """
    directory = Path(directory)
    cert, key = directory / 'server.crt', directory / 'server.key'
    if not (cert.exists() and key.exists()):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        directory.mkdir(parents=True, exist_ok=True)
        private = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'WorkTrack office server')])
        names = [x509.DNSName('localhost'), x509.DNSName(socket.gethostname() or 'worktrack')]
        for address in ('127.0.0.1', *addresses):
            try:
                names.append(x509.IPAddress(ipaddress.ip_address(address)))
            except ValueError:
                pass
        now = datetime.now(timezone.utc)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(private.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(names), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(private, hashes.SHA256())
        )
        key_bytes = private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        descriptor = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(key_bytes)
        cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    der = ssl.PEM_cert_to_DER_cert(cert.read_text(encoding='ascii'))
    return cert, key, fingerprint(der)


class TLSProxy(Gateway):
    """HTTPS on the office network in front of the local Django server."""

    def __init__(self, address, cert, key, upstream):
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_cert_chain(cert, key)
        self.upstream = upstream
        super().__init__(address, Path(cert).parent, upstream, upstream)

    def handler(self):
        return TLSProxyHandler

    def start(self):
        self.thread = threading.Thread(target=self.serve_forever, name='office-https', daemon=True)
        self.thread.start()

    def handle_error(self, request, client_address):
        pass  # A browser or scanner speaking plain HTTP to this port: nothing to report.


class TLSProxyHandler(GatewayHandler):
    def setup(self):
        raw = self.request
        raw.settimeout(15)
        # The handshake runs here, in this connection's own thread, so a slow client cannot stall others.
        self.request = self.server.context.wrap_socket(raw, server_side=True, do_handshake_on_connect=False)
        try:
            self.request.do_handshake()
        except (OSError, ssl.SSLError):
            self.request.close()
            raise
        super().setup()

    def finish(self):
        try:
            super().finish()
        finally:
            self.request.close()

    def _handle(self):
        self.data = self._body()
        if self.data is False:
            return self._json(413, {'detail': 'Хүсэлт хэт том байна.'})
        # Replace, never append to, forwarding headers a client sent itself.
        extra = {'X-Forwarded-For': self.client_address[0], 'X-Forwarded-Proto': 'https'}
        return self._forward(self.server.upstream, extra)
