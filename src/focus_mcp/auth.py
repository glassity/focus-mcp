"""Bearer-token handling for the HTTP transport.

Tokens are JWTs signed by an OpenID Connect provider and verified here,
needing only the provider's public keys (auth extra, PyJWT). This is
optional: a server whose requests bring their own AWS keys needs no bearer,
because the keys already decide what each request may read.
"""

import logging
import time
from typing import Optional

from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)

ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]


class JwksTokenVerifier:
    """Verify JWTs against a JWKS endpoint; keys are cached and re-fetched on miss."""

    def __init__(
        self,
        jwks_url: str,
        *,
        issuer: Optional[str] = None,
        audience: Optional[str] = None,
        required_scopes: Optional[list[str]] = None,
    ):
        try:
            import jwt  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "FOCUS_JWKS_URL is set but PyJWT is not installed; "
                "install the auth extra (pip install 'focus-mcp[auth]')"
            ) from e
        from jwt import PyJWKClient

        self.issuer = issuer or None
        self.audience = audience or None
        self.required_scopes = required_scopes or []
        self._jwks = PyJWKClient(jwks_url, cache_keys=True)

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        import jwt

        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                issuer=self.issuer,
                audience=self.audience,
                options={"verify_aud": self.audience is not None},
            )
        except jwt.PyJWTError as e:
            logger.info("Rejected bearer token: %s", e)
            return None

        scopes = _scopes(claims)
        if any(scope not in scopes for scope in self.required_scopes):
            logger.info("Rejected bearer token: missing scopes %s", self.required_scopes)
            return None

        expires_at = claims.get("exp")
        if expires_at is not None and expires_at < time.time():
            return None

        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id") or claims.get("azp") or claims.get("sub") or ""),
            scopes=scopes,
            expires_at=int(expires_at) if expires_at is not None else None,
            resource=self.audience,
            subject=str(claims["sub"]) if claims.get("sub") is not None else None,
            claims=claims,
        )


def _scopes(claims: dict) -> list[str]:
    scope = claims.get("scope")
    if isinstance(scope, str):
        return scope.split()
    if isinstance(scope, list):
        return [str(s) for s in scope]
    scp = claims.get("scp")
    if isinstance(scp, list):
        return [str(s) for s in scp]
    return []
