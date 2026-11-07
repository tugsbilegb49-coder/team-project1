"""Local queue routing only; the server always verifies JWT authentication."""

import base64
import hashlib
import json
from urllib.parse import urlsplit


def queue_identity(tokens, api_url):
    token = tokens['refresh']
    try:
        encoded = token.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        user = claims['user_id']
        if isinstance(user, bool) or not isinstance(user, (str, int)):
            raise ValueError('Invalid user claim.')
        subject = 'user:' + str(user)
    except (ValueError, KeyError, IndexError, TypeError):
        # Non-JWT test/custom credentials cannot be shared across login sessions.
        subject = 'session:' + hashlib.sha256(token.encode()).hexdigest()
    origin = urlsplit(api_url)
    namespace = origin.scheme.lower() + '://' + origin.netloc.lower() + origin.path.rstrip('/')
    return hashlib.sha256((namespace + '\0' + subject).encode()).hexdigest()[:24]
