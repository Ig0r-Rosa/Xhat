"""Registro dos modelos disponíveis no Xhat.

O projeto trabalha com dois modelos locais, escolhíveis na TUI:
- Qwen3.5 4B  -> leve/padrão, bom para dúvidas e comandos simples
- Qwen2.5-Coder 7B -> mais preciso para tradução de comandos/scripts
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    """Descreve um modelo local e como o Ollama deve chamá-lo."""

    key: str          # identificador curto usado na TUI/config (ex.: "qwen3.5")
    ollama_tag: str   # tag real no Ollama (ex.: "qwen3.5:4b")
    label: str        # texto amigável exibido ao usuário


# Modelos suportados. A chave é o nome curto usado em `/modelo <chave>`.
MODELS: dict[str, ModelSpec] = {
    "qwen3.5": ModelSpec(
        key="qwen3.5",
        ollama_tag="qwen3.5:4b",
        label="Qwen 3.5 4B",
    ),
    "coder": ModelSpec(
        key="coder",
        ollama_tag="qwen2.5-coder:7b",
        label="Qwen 2.5 - Coder 7B",
    ),
}

# Modelo usado quando o usuário ainda não escolheu nenhum.
DEFAULT_MODEL = "qwen3.5"


def get_model(key: str) -> ModelSpec:
    """Retorna a especificação do modelo pela chave curta.

    Cai no modelo padrão se a chave for desconhecida.
    """
    return MODELS.get(key, MODELS[DEFAULT_MODEL])


def list_models() -> list[ModelSpec]:
    """Lista todos os modelos disponíveis (para exibir na TUI)."""
    return list(MODELS.values())
