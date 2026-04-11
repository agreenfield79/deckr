import logging
import os
import time

import requests

logger = logging.getLogger("deckr.token_cache")

_IAM_URL = "https://iam.cloud.ibm.com/identity/token"


class TokenCache:
    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            logger.debug(
                "token_cache: returning cached token (expires in %.0fs)",
                self._expires_at - time.time(),
            )
            return self._token
        return self._fetch_token()

    def _fetch_token(self) -> str:
        api_key = os.getenv("IBMCLOUD_API_KEY")
        if not api_key:
            raise RuntimeError("IBMCLOUD_API_KEY not set")
        try:
            resp = requests.post(
                _IAM_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                    "apikey": api_key,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            expires_in = int(data.get("expires_in", 3600))
            self._expires_at = time.time() + expires_in
            logger.info("token_cache: new IAM token fetched (expires in %ds)", expires_in)
            return self._token
        except Exception as e:
            safe_msg = type(e).__name__
            logger.error("token_cache: IAM token fetch failed — %s", safe_msg)
            raise


# Module-level singleton — shared across all requests
token_cache = TokenCache()
