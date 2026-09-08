"""Google ID-token verification via the tokeninfo endpoint.

Kept behind the :class:`GoogleTokenVerifier` port so the auth flow can be tested
with a stub and so the network dependency is isolated to infrastructure.
"""

from __future__ import annotations

import httpx

from tender_intel.domain.exceptions import InvalidTokenError
from tender_intel.domain.interfaces.providers import GoogleIdentity

_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


class GoogleTokenVerifierImpl:
    def __init__(self, client_id: str | None, http_client: httpx.AsyncClient | None = None) -> None:
        self._client_id = client_id
        self._http = http_client

    async def verify(self, id_token: str) -> GoogleIdentity:
        client = self._http or httpx.AsyncClient(timeout=10.0)
        try:
            resp = await client.get(_TOKENINFO_URL, params={"id_token": id_token})
        finally:
            if self._http is None:
                await client.aclose()

        if resp.status_code != httpx.codes.OK:
            raise InvalidTokenError("Google token verification failed")
        data = resp.json()

        # Audience must match our client id (prevents token substitution).
        if self._client_id and data.get("aud") != self._client_id:
            raise InvalidTokenError("Google token audience mismatch")
        # An unverified address proves only that someone typed it into a Google
        # account, so it can never be trusted for admission.
        if data.get("email_verified") not in ("true", True):
            raise InvalidTokenError("Google email not verified")

        sub = data.get("sub")
        email = data.get("email")
        if not sub or not email:
            raise InvalidTokenError("Google token missing subject/email")
        hosted_domain = data.get("hd")
        return GoogleIdentity(
            subject=sub,
            email=email,
            full_name=data.get("name") or email.split("@")[0],
            hosted_domain=hosted_domain.strip().lower() if hosted_domain else None,
        )
