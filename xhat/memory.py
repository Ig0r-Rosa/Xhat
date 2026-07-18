"""Memória do Xhat em arquivos .md (sem estado acumulado na RAM).

Em vez de manter todo o histórico na memória, cada turno lê e reescreve dois
arquivos, sempre pequenos:

- contexto.md -> turnos recentes (rotativo: ao passar do limite, apaga o mais antigo)
- perfil.md   -> características permanentes do usuário

Também há um teto de ~10k caracteres por arquivo (compactação/resumo).
"""

from pathlib import Path
from typing import Callable

from .config import BASE_DIR, ensure_base_dir

CONTEXT_FILE = BASE_DIR / "contexto.md"
PROFILE_FILE = BASE_DIR / "perfil.md"
MAX_CHARS = 10_000
# Quantidade máxima de turnos no histórico (FIFO: sai o mais antigo).
MAX_TURNS = 12


class Memory:
    """Lê/escreve os arquivos de contexto e perfil, respeitando os limites."""

    def __init__(self, summarizer: Callable[[str], str] | None = None):
        # `summarizer` recebe um texto grande e devolve um resumo (via LLM).
        self.summarizer = summarizer
        ensure_base_dir()

    def read_context(self) -> str:
        """Retorna o conteúdo do contexto (ou vazio se não existir)."""
        return _read(CONTEXT_FILE)

    def read_profile(self) -> str:
        """Retorna o conteúdo do perfil (ou vazio se não existir)."""
        return _read(PROFILE_FILE)

    def append_turn(self, user_msg: str, assistant_summary: str) -> None:
        """Adiciona um turno e remove os mais antigos se passar de MAX_TURNS."""
        turns = parse_turns(self.read_context())
        turns.append(
            f"### Turno\n"
            f"- Usuário: {user_msg}\n"
            f"- Xhat: {assistant_summary}\n"
        )
        # Rotativo: mantém só os N mais novos.
        turns = turns[-MAX_TURNS:]
        content = "\n".join(turns)
        if not content.endswith("\n"):
            content += "\n"
        _write(CONTEXT_FILE, self._enforce_limit(content))

    def recent_user_messages(self, limit: int = MAX_TURNS) -> list[str]:
        """Lista pedidos do usuário, do mais novo para o mais antigo."""
        messages: list[str] = []
        for turn in parse_turns(self.read_context()):
            for line in turn.splitlines():
                if line.startswith("- Usuário: "):
                    messages.append(line.removeprefix("- Usuário: ").strip())
                    break
        # Mais novos primeiro (para a sidebar).
        return list(reversed(messages[-limit:]))

    def update_profile(self, new_profile: str) -> None:
        """Substitui o perfil por uma versão atualizada (já dentro do limite)."""
        _write(PROFILE_FILE, self._enforce_limit(new_profile))

    def _enforce_limit(self, content: str) -> str:
        """Garante que o texto caiba em MAX_CHARS (resume ou corta o excesso)."""
        if len(content) <= MAX_CHARS:
            return content
        if self.summarizer:
            return self.summarizer(content)[:MAX_CHARS]
        return content[-MAX_CHARS:]


def parse_turns(context: str) -> list[str]:
    """Divide o contexto.md em blocos de turno (do mais antigo ao mais novo)."""
    text = context.strip()
    if not text:
        return []
    if "### Turno" in text:
        return [f"### Turno\n{c.strip()}\n" for c in text.split("### Turno") if c.strip()]
    # Formato antigo: agrupa por linhas "- Usuário:".
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("- Usuário:") and current:
            blocks.append("\n".join(current) + "\n")
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current) + "\n")
    return blocks


def _read(path: Path) -> str:
    """Lê um arquivo texto; devolve string vazia se não existir."""
    return path.read_text("utf-8") if path.exists() else ""


def _write(path: Path, content: str) -> None:
    """Escreve texto em um arquivo, criando o diretório se preciso."""
    ensure_base_dir()
    path.write_text(content, "utf-8")
