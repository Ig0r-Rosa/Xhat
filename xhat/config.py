"""Configuração e caminhos locais do Xhat.

Todos os dados locais (config + memória em .md) ficam em ~/.xhat, para que o
assistente funcione de qualquer diretório e "conheça" o usuário globalmente.
"""

import json
from pathlib import Path

from .models import DEFAULT_MODEL

# Diretório base com config e memória. Ignorado pelo git.
BASE_DIR = Path.home() / ".xhat"
CONFIG_FILE = BASE_DIR / "config.json"


def ensure_base_dir() -> None:
    """Garante que ~/.xhat exista antes de ler/escrever qualquer arquivo."""
    BASE_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Carrega a config; devolve padrões se o arquivo não existir/for inválido."""
    ensure_base_dir()
    if not CONFIG_FILE.exists():
        return _default_config()
    try:
        return {**_default_config(), **json.loads(CONFIG_FILE.read_text("utf-8"))}
    except (json.JSONDecodeError, OSError):
        return _default_config()


def save_config(config: dict) -> None:
    """Persiste a config em disco (formato JSON legível)."""
    ensure_base_dir()
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), "utf-8")


def get_model_key(config: dict) -> str:
    """Retorna a chave do modelo atualmente selecionado."""
    return config.get("model", DEFAULT_MODEL)


def set_model_key(config: dict, key: str) -> dict:
    """Atualiza o modelo selecionado e salva a config."""
    config["model"] = key
    save_config(config)
    return config


def _default_config() -> dict:
    """Valores padrão da config."""
    return {
        "model": DEFAULT_MODEL,
        "ollama_host": "http://localhost:11434",
    }
