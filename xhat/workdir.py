"""Diretório de trabalho da sessão do Xhat.

Comandos `cd` não persistem em subprocessos isolados; por isso o Xhat guarda
o caminho atual e usa em todas as execuções da sessão.
Também localiza pastas pelo nome (ex.: MeuHypr) antes de mudar.
"""

import os
import re
import shlex
from pathlib import Path

# Captura `cd caminho` (com ou sem aspas / ~).
CD_RE = re.compile(r"^\s*cd\s+(?P<path>.+?)\s*$", re.IGNORECASE)

# Pastas a ignorar na busca (ruído / cache).
_SKIP_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".cache", ".local",
    ".cargo", ".npm", ".venv", "venv", ".cursor",
}


def default_cwd() -> Path:
    """Diretório inicial: pasta de onde o Xhat foi chamado."""
    return Path.cwd().resolve()


def format_cwd(cwd: Path) -> str:
    """Texto amigável para a barra (troca $HOME por ~)."""
    home = Path.home()
    if cwd == home:
        return "~"
    try:
        return "~/" + str(cwd.relative_to(home))
    except ValueError:
        return str(cwd)


def try_apply_cd(command: str, cwd: Path) -> Path | None:
    """Se o comando for um `cd`, devolve o novo Path; senão None."""
    match = CD_RE.match(command.strip())
    if not match:
        return None
    raw = match.group("path").strip()
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = [raw]
    if not parts:
        return None
    target = _expand_path(parts[0], cwd)
    if target.is_dir():
        return target.resolve()
    return None


def looks_like_cd(command: str) -> bool:
    """True se o comando parece um `cd` (mesmo com caminho inválido)."""
    return CD_RE.match(command.strip()) is not None


def find_directories(
    name: str, cwd: Path | None = None, limit: int = 8
) -> list[Path]:
    """Procura pastas cujo nome bate com `name` (case-insensitive)."""
    needle = name.strip().strip("/").strip()
    if not needle:
        return []
    roots = _search_roots(cwd)
    exact: list[Path] = []
    partial: list[Path] = []
    needle_l = needle.lower()
    for root in roots:
        for found in _walk_named(root, needle_l, max_depth=5):
            if found.name.lower() == needle_l:
                exact.append(found)
            else:
                partial.append(found)
    ranked = _dedupe_prefer(exact) + _dedupe_prefer(partial)
    return ranked[:limit]


def pick_best_directory(matches: list[Path]) -> Path | None:
    """Escolhe o melhor candidato (já ranqueado por find_directories)."""
    return matches[0] if matches else None


def _search_roots(cwd: Path | None) -> list[Path]:
    """Raízes onde procurar pastas pelo nome."""
    roots: list[Path] = []
    home = Path.home()
    candidates = [
        cwd.resolve() if cwd else None,
        home,
        home / "Compartilhado",
        home / "Documentos",
        Path("/srv/compartilhado"),
    ]
    for path in candidates:
        if path is None:
            continue
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


def _walk_named(root: Path, needle_l: str, max_depth: int) -> list[Path]:
    """Percorre até max_depth e coleta pastas com nome correspondente."""
    found: list[Path] = []
    root_depth = len(root.parts)
    for dirpath, dirnames, _ in os.walk(root, followlinks=False):
        current = Path(dirpath)
        depth = len(current.parts) - root_depth
        if depth > max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
        name_l = current.name.lower()
        if depth >= 1 and (name_l == needle_l or needle_l in name_l):
            found.append(current)
            if len(found) >= 20:
                break
    return found


def _dedupe_prefer(paths: list[Path]) -> list[Path]:
    """Remove duplicatas e ordena: fora de .cursor, caminho mais curto."""
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)

    def score(p: Path) -> tuple[int, int, str]:
        noisy = 1 if ".cursor" in p.parts else 0
        return (noisy, len(str(p)), str(p))

    return sorted(unique, key=score)


def _expand_path(raw: str, cwd: Path) -> Path:
    """Expande ~ e caminhos relativos a partir do cwd atual."""
    expanded = os.path.expanduser(raw)
    path = Path(expanded)
    if not path.is_absolute():
        path = cwd / path
    return path
