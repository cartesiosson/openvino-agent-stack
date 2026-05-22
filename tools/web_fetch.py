"""
title: Web Fetch
author: agent-stack
version: 0.1.0
description: Descarga una URL y devuelve texto plano (HTML limpio).
required_open_webui_version: 0.5.0
"""

import re
import httpx
from pydantic import BaseModel, Field


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class Tools:
    class Valves(BaseModel):
        timeout: int = Field(default=15, description="Timeout en segundos")
        max_chars: int = Field(default=8000, description="Máximo de caracteres devueltos")
        user_agent: str = Field(
            default="Mozilla/5.0 (compatible; AgentBot/0.1)",
            description="User-Agent en las peticiones",
        )

    def __init__(self):
        self.valves = self.Valves()

    def fetch_url(self, url: str) -> str:
        """
        Descarga una URL (http/https) y devuelve su contenido como texto plano.

        :param url: URL absoluta
        :return: texto extraído, truncado a max_chars
        """
        if not url.startswith(("http://", "https://")):
            return "error: solo se permiten http(s)"

        try:
            with httpx.Client(
                timeout=self.valves.timeout,
                headers={"User-Agent": self.valves.user_agent},
                follow_redirects=True,
            ) as client:
                r = client.get(url)
                r.raise_for_status()
                body = r.text
        except Exception as e:
            return f"error: {e}"

        text = _TAG_RE.sub(" ", body)
        text = _WS_RE.sub(" ", text).strip()
        return text[: self.valves.max_chars]
