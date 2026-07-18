"""Heurísticas para pedidos de navegação (pasta pelo nome).

Não depende do modelo: detecta "vá para MeuHypr" e "quais as opções?".
Também reconhece "pasta/arquivo mais pesado deste diretório" sem chamar a IA.
"""

import re

from .memory import parse_turns

# Pedido de ir para pasta / diretório.
_NAV_VERB = re.compile(
    r"\b(mude|mudar|v[aá]|ir|entre|entrar|abre|abrir|cd|vai)\b",
    re.IGNORECASE,
)
_NAV_PLACE = re.compile(
    r"\b(diret[oó]rio|pasta|folder|dir)\b",
    re.IGNORECASE,
)
# Extrai o nome após "do/da/de" ou no final.
_NAME_PATTERNS = (
    re.compile(
        r"(?:diret[oó]rio|pasta|folder|dir)\s+(?:do|da|de)\s+[\"']?([^\s\"']+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:diret[oó]rio|pasta)\s+[\"']?([A-Za-z0-9_.-]+)",
        re.IGNORECASE,
    ),
    re.compile(r"\bcd\s+[\"']?([^\s\"']+)", re.IGNORECASE),
    re.compile(
        r"\b(?:para|pro|pra)\s+(?:o|a|ao|à)?\s*[\"']?([A-Za-z0-9_.-]+)",
        re.IGNORECASE,
    ),
)
# Pedido explícito pelas opções numeradas da busca anterior (não "lista pastas").
_OPTIONS_ASK = re.compile(
    r"\b("
    r"quais\s+(são\s+)?(as\s+)?op[cç][oõ]es|"
    r"(mostra|mostre|liste|lista)\s+(as\s+)?op[cç][oõ]es|"
    r"op[cç][oõ]es\s+de\s+novo|"
    r"onde\s+(est[aá]|fica)\b"
    r")",
    re.IGNORECASE,
)

_QUOTED_SIMPLE = re.compile(r"“([^”]+)”|\"([^\"]+)\"|'([^']+)'")

# Palavras que nunca são nome de pasta (ex.: "pasta mais pesada").
_STOP_NAMES = frozenset(
    {
        "o",
        "a",
        "os",
        "as",
        "um",
        "uma",
        "meu",
        "minha",
        "mais",
        "menos",
        "pesada",
        "pesado",
        "pesadas",
        "pesados",
        "grande",
        "grandes",
        "pequena",
        "pequeno",
        "deste",
        "desta",
        "desses",
        "destas",
        "neste",
        "nesta",
        "aqui",
        "atual",
        "qual",
        "quais",
        "que",
        "com",
        "sem",
        "para",
        "por",
        "em",
        "no",
        "na",
        "dos",
        "das",
        "do",
        "da",
        "de",
        "maior",
        "menor",
        "arquivo",
        "arquivos",
        "pasta",
        "pastas",
        "diretorio",
        "diretório",
        "folder",
        "dir",
    }
)

# "arquivo/pasta mais pesado(a) neste/deste diretório"
_HEAVIEST = re.compile(r"\bmais\s+pesad[oa]s?\b", re.IGNORECASE)
_FILE_WORD = re.compile(r"\b(arquivo|arquivos|file|files)\b", re.IGNORECASE)
_DIR_WORD = re.compile(
    r"\b(pasta|pastas|diret[oó]rio|diret[oó]rios|folder|folders|dir)\b",
    re.IGNORECASE,
)


def is_heaviest_query(message: str) -> bool:
    """True se pergunta pelo item mais pesado (não é navegação)."""
    return bool(_HEAVIEST.search(message.strip()))


def heaviest_command(message: str) -> tuple[str, str] | None:
    """Comando + resposta para 'mais pesado/pesada' no diretório atual."""
    text = message.strip()
    if not is_heaviest_query(text):
        return None
    wants_dir = bool(_DIR_WORD.search(text)) and not bool(_FILE_WORD.search(text))
    if wants_dir:
        return (
            "du -h --max-depth=1 . 2>/dev/null | sort -hr | head -n 20",
            "Listando as pastas mais pesadas neste diretório.",
        )
    return (
        "find . -type f -printf '%s %p\\n' 2>/dev/null | sort -nr | head -n 5",
        "Procurando os arquivos mais pesados neste diretório.",
    )


def extract_dir_name(message: str) -> str | None:
    """Se a mensagem pede ir a uma pasta pelo nome, devolve esse nome."""
    text = message.strip()
    if not text:
        return None
    # "pasta mais pesada…" não é navegação.
    if is_heaviest_query(text):
        return None
    # Só navega com verbo (vá/mude/cd…) ou "pasta NomeProprio".
    has_verb = bool(_NAV_VERB.search(text))
    has_place = bool(_NAV_PLACE.search(text))
    if not (has_verb or has_place):
        return None
    for pattern in _NAME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        name = match.group(1).strip().strip(".,;:?!")
        if _is_valid_dir_name(name):
            # Sem verbo: exige parecer nome próprio (evita "pasta mais").
            if not has_verb and name.islower() and len(name) < 4:
                continue
            return name
    return None


def _is_valid_dir_name(name: str) -> bool:
    """Filtra artigos, adjetivos e lixo extraído por regex."""
    if not name or "/" in name:
        return False
    return name.lower() not in _STOP_NAMES


def wants_options_list(message: str) -> bool:
    """True só se pede as opções numeradas da busca anterior."""
    text = message.strip()
    if is_heaviest_query(text):
        return False
    return bool(_OPTIONS_ASK.search(text))


def list_cwd_command(message: str) -> tuple[str, str] | None:
    """Comando para listar pastas/itens do diretório atual (sem navegar)."""
    text = message.strip()
    if not text or wants_options_list(text):
        return None
    # "lista as disciplinas…", "mostra as pastas…" → ls no cwd.
    if not re.search(
        r"\b(lista|liste|listar|mostra|mostre|exibe|exibir)\b", text, re.I
    ):
        return None
    if not re.search(
        r"\b(pasta|pastas|disciplina|disciplinas|diretori|diretóri|conteudo|conteúdo)\b",
        text,
        re.I,
    ):
        return None
    return (
        "ls -1",
        "Listando o conteúdo deste diretório.",
    )


def last_nav_target(context: str) -> str | None:
    """Descobre o último nome de pasta buscado (histórico .md)."""
    turns = parse_turns(context)
    for turn in reversed(turns):
        for line in turn.splitlines():
            if line.startswith("- Usuário: "):
                name = extract_dir_name(line.removeprefix("- Usuário: "))
                if name:
                    return name
    for turn in reversed(turns):
        for line in turn.splitlines():
            if "Xhat:" in line or line.startswith("- Xhat"):
                for match in _QUOTED_SIMPLE.finditer(line):
                    name = next(g for g in match.groups() if g)
                    if name and "/" not in name and _is_valid_dir_name(name):
                        return name.strip()
    return None
