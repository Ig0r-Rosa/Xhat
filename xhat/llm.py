"""Cliente do modelo local via Ollama (HTTP).

Princípio central do Xhat: o modelo só consome recurso na chamada.
Usamos `keep_alive=0` para que o Ollama **descarregue o modelo da RAM logo
após responder**, mantendo o consumo em repouso próximo de zero.
"""

import json
import re

import requests


from . import ollama_runtime


class LLMError(Exception):
    """Erro ao falar com o Ollama (offline, modelo ausente, etc.)."""


class OllamaClient:
    """Wrapper mínimo sobre a API de chat do Ollama."""

    def __init__(
        self,
        host: str,
        model_tag: str,
        timeout: int = 180,
        manage_ollama: bool = True,
    ):
        self.host = host.rstrip("/")
        self.model_tag = model_tag
        self.timeout = timeout
        self.manage_ollama = manage_ollama

    def chat_json(self, system: str, user: str) -> dict:
        """Envia uma conversa e retorna a resposta já parseada como JSON.

        Pede ao Ollama `format=json` e desliga thinking (qwen3.5 esvazia content).
        """
        raw = self._post_chat(system, user, want_json=True)
        return self._parse_json(raw)

    def chat_text(self, system: str, user: str) -> str:
        """Envia uma conversa e retorna a resposta em texto puro."""
        return self._post_chat(system, user, want_json=False)

    def _post_chat(self, system: str, user: str, want_json: bool) -> str:
        """Faz o POST em /api/chat e devolve o conteúdo textual da resposta."""
        ollama_runtime.ensure_running(self.host, manage=self.manage_ollama)
        payload = self._build_payload(system, user, want_json)
        try:
            resp = requests.post(
                f"{self.host}/api/chat", json=payload, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise LLMError(self._friendly_error(exc)) from exc
        data = resp.json()
        if data.get("error"):
            raise LLMError(f"Ollama: {data['error']}")
        return self._extract_content(data)

    def _build_payload(self, system: str, user: str, want_json: bool) -> dict:
        """Monta o corpo da requisição para o Ollama."""
        payload = {
            "model": self.model_tag,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "keep_alive": 0,  # descarrega o modelo da RAM após responder
            # qwen3.5 (capability thinking): sem isso o content vem vazio.
            "think": False,
            "options": {"temperature": 0.1},
        }
        if want_json:
            payload["format"] = "json"
        return payload

    @staticmethod
    def _extract_content(data: dict) -> str:
        """Lê content; se vazio, tenta thinking (modelos com raciocínio)."""
        message = data.get("message") or {}
        content = (message.get("content") or "").strip()
        if content:
            return content
        thinking = (message.get("thinking") or "").strip()
        if thinking:
            return thinking
        return ""

    @classmethod
    def _parse_json(cls, raw: str) -> dict:
        """Converte a string de resposta em dict; tolera cercas markdown."""
        text = cls._normalize_json_text(raw)
        if not text:
            raise LLMError(
                "O modelo devolveu resposta vazia. "
                "Tente de novo ou troque de modelo na sidebar."
            )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Resposta do modelo não é JSON válido:\n{raw[:500]}"
            ) from exc
        if not isinstance(data, dict):
            raise LLMError("O modelo não devolveu um objeto JSON.")
        return data

    @staticmethod
    def _normalize_json_text(raw: str) -> str:
        """Remove cercas ```json e lixo ao redor do objeto."""
        text = (raw or "").strip()
        if not text:
            return ""
        # Remove blocos de thinking que às vezes vazam no texto.
        text = re.sub(
            r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE
        ).strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            return fence.group(1).strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return text[start : end + 1]
        return text

    def _friendly_error(self, exc: Exception) -> str:
        """Traduz erros de rede em mensagens úteis ao usuário."""
        if isinstance(exc, requests.ConnectionError):
            return (
                "Não consegui falar com o Ollama. Ele está rodando?\n"
                "Inicie com: `ollama serve` e baixe o modelo com "
                f"`ollama pull {self.model_tag}`."
            )
        if isinstance(exc, requests.Timeout):
            return (
                "O modelo demorou demais para responder. "
                "Tente de novo (na 1ª chamada ele ainda carrega na RAM)."
            )
        return f"Falha ao chamar o modelo: {exc}"
