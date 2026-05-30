from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger("healthalert.llm")

# LLM ayarlarini tek yerde toplayan hafif istemciyi tanimlar.
class LLMClient:

    # Varsayilan ayarlar veya verilen parametrelerle istemciyi hazirlar.
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL
        self.max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        self.timeout = timeout or settings.LLM_TIMEOUT

    # API anahtarı yapılandırılmış mı kontrol eder.
    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    # LLM API'ye asenkron sohbet isteği gönderir.
    async def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> Optional[str]:
        if not self.is_configured:
            logger.warning("LLM API key not configured — skipping LLM call")
            return None

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        for attempt in range(1, 4):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]

                logger.error(
                    "LLM API error (attempt %d): %d %s",
                    attempt,
                    resp.status_code,
                    resp.text[:300],
                )
                if resp.status_code in (400, 401, 403, 404):
                    break

            except httpx.TimeoutException:
                logger.warning("LLM timeout (attempt %d/%d)", attempt, 3)
            except Exception:
                logger.exception("LLM unexpected error (attempt %d/%d)", attempt, 3)

        return None

    # Sunucu sağlık durumunu döndürür.
    async def health_check(self) -> Dict[str, Any]:
        if not self.is_configured:
            return {"status": "not_configured", "model": self.model}

        try:
            result = await self.chat(
                [{"role": "user", "content": "Merhaba"}],
                max_tokens=10,
                temperature=0.0,
            )
            return {
                "status": "ok" if result else "error",
                "model": self.model,
                "base_url": self.base_url,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc), "model": self.model}

_default_client: Optional[LLMClient] = None

# Uygulama genelinde paylasilan varsayilan LLM istemcisini dondurur.
def get_llm_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
