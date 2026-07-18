"""Pesquisa na internet via DuckDuckGo (sem API key).

Usado quando o usuário pede fatos atuais (notícias, esportes, etc.).
O modelo local só resume o que a rede trouxe — nunca inventa.
"""

import html
import re

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}

# Pedido explícito de pesquisa.
_EXPLICIT_SEARCH = re.compile(
    r"\b(pesquis\w*|busca(?:r)?|procure|procurar|google|na\s+internet|na\s+web)\b",
    re.IGNORECASE,
)
# Temas que quase sempre precisam de web (modelo local alucina fácil).
_NEEDS_WEB = re.compile(
    r"\b("
    r"copa|mundial|olimp[ií]|elei[cç]|not[ií]cia|placar|resultado|"
    r"quem\s+ganhou|contra\s+qual|perdeu\s+para|hoje|ontem|"
    r"202[4-9]|presidente|bolsa|d[oó]lar|clima|temperatur|"
    r"munic[ií]pio|prefeito|governador|futebol|campeonato"
    r")\b",
    re.IGNORECASE,
)
# Perguntas factuais do mundo real (não do terminal).
_FACT_QUESTION = re.compile(
    r"\b("
    r"quem\s+(é|foi|ganhou|perdeu|venceu)|"
    r"qual\s+(é|foi|era|o|a)\b|"
    r"quais\s+(são|foram)|"
    r"quando\s+(foi|aconteceu|nasceu|ocorreu)|"
    r"onde\s+(fica|é|fica|aconteceu|nasceu)|"
    r"contra\s+qual|"
    r"em\s+que\s+(país|ano|cidade)"
    r")",
    re.IGNORECASE,
)
# Assunto local: terminal / arquivos — não forçar web.
_LOCAL_TOPIC = re.compile(
    r"\b("
    r"arquivo|pasta|diret[oó]rio|comando|terminal|linux|shell|"
    r"cwd|ls|chmod|chown|docker|systemd|processo|pid|"
    r"este\s+diret|deste\s+diret|neste\s+diret|aqui"
    r")\b",
    re.IGNORECASE,
)
_NAV_VERB = re.compile(
    r"\b(mude|mudar|v[aá]|cd|abre|abrir|entre|entrar)\b",
    re.IGNORECASE,
)


def wants_web_search(message: str) -> bool:
    """True se a mensagem exige base sólida da web (não memória do modelo)."""
    text = message.strip()
    if not text:
        return False
    if _EXPLICIT_SEARCH.search(text):
        return True
    if _NAV_VERB.search(text):
        return False
    if _LOCAL_TOPIC.search(text) and not _NEEDS_WEB.search(text):
        return False
    if _NEEDS_WEB.search(text):
        return True
    # "Qual país…", "Quem ganhou…" sem ser sobre pasta/arquivo.
    return bool(_FACT_QUESTION.search(text) and not _LOCAL_TOPIC.search(text))


def search_query_from_message(message: str) -> str:
    """Limpa verbos de 'pesquise/busque' e deixa a consulta objetiva."""
    text = message.strip()
    text = re.sub(
        r"^\s*(pesquis\w*|busca(?:r)?|procure|procurar)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip() or message.strip()


def search_web(query: str, limit: int = 8) -> str:
    """Busca na web e devolve um texto resumido para o modelo usar.

    Retorna string vazia se a busca falhar (rede/offline).
    """
    query = query.strip()
    if not query:
        return ""
    try:
        results = _fetch_results(query, limit)
    except requests.RequestException:
        return ""
    if not results:
        return ""
    return _format_results(query, results)


def _fetch_results(query: str, limit: int) -> list[tuple[str, str]]:
    """Faz POST no DuckDuckGo HTML e extrai título + trecho."""
    resp = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers=_HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    return _parse_html(resp.text, limit)


def _parse_html(page: str, limit: int) -> list[tuple[str, str]]:
    """Extrai pares (título, snippet) do HTML do DuckDuckGo."""
    titles = re.findall(
        r'class="result__a"[^>]*>(.*?)</a>', page, flags=re.IGNORECASE | re.DOTALL
    )
    snippets = re.findall(
        r'class="result__snippet"[^>]*>(.*?)</(?:a|td|span)>',
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )
    results: list[tuple[str, str]] = []
    for i, title in enumerate(titles[:limit]):
        snippet = snippets[i] if i < len(snippets) else ""
        results.append((_clean(title), _clean(snippet)))
    return results


def _clean(raw: str) -> str:
    """Remove tags HTML e entidades de um trecho."""
    text = re.sub(r"<[^>]+>", "", raw)
    return html.unescape(text).strip()


def _format_results(query: str, results: list[tuple[str, str]]) -> str:
    """Formata os resultados para entrar no prompt do modelo."""
    lines = [f"Consulta: {query}", "Resultados:"]
    for i, (title, snippet) in enumerate(results, 1):
        lines.append(f"{i}. {title}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)
