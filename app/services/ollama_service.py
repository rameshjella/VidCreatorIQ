import json

import requests

from app.config import settings


class OllamaService:
    def __init__(self, model: str | None = None):
        self.model = model or settings.ollama_model

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{settings.ollama_url}/api/tags", timeout=2)
            return resp.ok
        except requests.RequestException:
            return False

    def generate_json(self, prompt: str) -> dict:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
        }
        resp = requests.post(f"{settings.ollama_url}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return json.loads(data.get("response", "{}"))

    def generate_text(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        resp = requests.post(f"{settings.ollama_url}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

