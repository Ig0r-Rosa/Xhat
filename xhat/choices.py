"""Resolve respostas curtas a listas numeradas do histórico.

Ex.: o Xhat listou pastas 1. e 2.; o usuário responde "1." → caminho da opção 1.
Isso não depende do modelo acertar a referência — lê o contexto.md.
"""

import re

from .memory import parse_turns

# "1", "1.", "opção 2", "opcao 2"
_NUM_RE = re.compile(
    r"^\s*(?:op(?:ç|c)[aã]o\s+)?(\d+)\s*\.?\s*$",
    re.IGNORECASE,
)
_ORDINAL = {
    "primeira": 1,
    "primeiro": 1,
    "segunda": 2,
    "segundo": 2,
    "terceira": 3,
    "terceiro": 3,
    "quarta": 4,
    "quarto": 4,
    "última": -1,
    "ultima": -1,
    "último": -1,
    "ultimo": -1,
}
# Linhas do tipo: 1. /caminho/absoluto
_PATH_LINE_RE = re.compile(r"^\s*(\d+)\.\s+(/\S+)\s*$")


def try_resolve_choice(message: str, context: str) -> str | None:
    """Se a mensagem escolher um item da última lista, devolve o valor."""
    index = _parse_choice_index(message)
    if index is None:
        return None
    options = extract_last_numbered_options(context)
    if not options:
        return None
    if index == -1:
        return options[-1]
    if 1 <= index <= len(options):
        return options[index - 1]
    return None


def extract_last_numbered_options(context: str) -> list[str]:
    """Extrai a última lista numerada (1. /caminho) das respostas do Xhat."""
    for turn in reversed(parse_turns(context)):
        found = _paths_from_text(turn)
        if found:
            return found
    return []


def _parse_choice_index(message: str) -> int | None:
    """Converte '1.', 'opção 2', 'a primeira' em índice (1-based ou -1)."""
    text = message.strip().lower()
    if not text:
        return None
    cleaned = re.sub(r"^(a|o)\s+", "", text)
    if cleaned in _ORDINAL:
        return _ORDINAL[cleaned]
    match = _NUM_RE.match(text)
    if match:
        return int(match.group(1))
    return None


def _paths_from_text(text: str) -> list[str]:
    """Lê pares 'N. /caminho' de um bloco de turno."""
    by_num: dict[int, str] = {}
    for line in text.replace("\\n", "\n").splitlines():
        match = _PATH_LINE_RE.match(line.strip())
        if match:
            by_num[int(match.group(1))] = match.group(2)
    if not by_num:
        return []
    return [by_num[i] for i in sorted(by_num)]
