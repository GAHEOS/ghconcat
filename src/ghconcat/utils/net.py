from __future__ import annotations

import os
import ssl
from typing import Optional

DEFAULT_UA: str = 'ghconcat/2.0 (+https://gaheos.com)'


def ssl_context_for(url: str) -> Optional[ssl.SSLContext]:
    """Return a permissive SSL context when GHCONCAT_INSECURE_TLS=1 and the URL is HTTPS."""
    if not url.lower().startswith('https'):
        return None
    if os.getenv('GHCONCAT_INSECURE_TLS') == '1':
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None