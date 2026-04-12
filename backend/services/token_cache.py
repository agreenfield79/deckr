import logging
import os
import time

import requests

logger = logging.getLogger("deckr.token_cache")

_IAM_URL = "https://iam.cloud.ibm.com/identity/token"


class TokenCache:
    def __init__(self, api_key_env_var: str = "IBMCLOUD_API_KEY") -> None:
        self._api_key_env_var = api_key_env_var
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            logger.debug(
                "token_cache: returning cached token for %s (expires in %.0fs)",
                self._api_key_env_var,
                self._expires_at - time.time(),
            )
            return self._token
        return self._fetch_token()

    def _fetch_token(self) -> str:
        api_key = os.getenv(self._api_key_env_var)
        if not api_key:
            raise RuntimeError(f"{self._api_key_env_var} is not set")
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
            logger.info(
                "token_cache: new IAM token fetched for %s (expires in %ds)",
                self._api_key_env_var, expires_in,
            )
            return self._token
        except Exception as e:
            safe_msg = type(e).__name__
            logger.error(
                "token_cache: IAM token fetch failed for %s — %s",
                self._api_key_env_var, safe_msg,
            )
            raise


# Module-level singleton for watsonx.ai — shared across all requests
token_cache = TokenCache()
