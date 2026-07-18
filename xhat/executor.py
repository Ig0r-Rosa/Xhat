"""Execução de comandos com confirmação e checagem de perigo.

Regra de ouro do Xhat: nunca executar sem aprovação explícita do usuário.
Comandos com sudo: a TUI pede a senha e autentica via `sudo -S` (sem TTY).
"""

import re
import subprocess

# Padrões que indicam comandos potencialmente destrutivos (rede de segurança
# extra, além do "danger" que o próprio modelo sinaliza).
DANGEROUS_PATTERNS = (
    "rm -rf",
    "rm -r",
    "mkfs",
    "dd ",
    ":(){",
    "> /dev/",
    "chmod -r 777",
    "chown -r",
    "shutdown",
    "reboot",
    "> /etc/",
    "truncate",
)

# Detecta `sudo` como comando (não a palavra solta em strings).
_SUDO_RE = re.compile(r"(^|[;&|]\s*)sudo(\s|$)")


def is_dangerous(command: str) -> bool:
    """Heurística simples para detectar comandos arriscados."""
    low = command.lower()
    return any(pat in low for pat in DANGEROUS_PATTERNS)


def needs_sudo(command: str) -> bool:
    """True se o comando chama sudo (precisa de senha na TUI)."""
    return bool(_SUDO_RE.search(command.strip()))


def run_interactive(command: str, cwd: str | None = None) -> int:
    """Executa herdando o terminal (permite prompt de senha do sudo)."""
    result = subprocess.run(command, shell=True, cwd=cwd)
    return result.returncode


def run_captured(
    command: str,
    cwd: str | None = None,
    sudo_password: str | None = None,
) -> tuple[int, str]:
    """Executa capturando a saída (usado pela TUI para exibir o resultado).

    Se houver senha e o comando usar sudo, autentica antes com `sudo -S -v`
    (a senha NÃO fica no comando nem no histórico).
    """
    if sudo_password is not None and needs_sudo(command):
        code, err = _sudo_auth(sudo_password, cwd=cwd)
        # Zera referência local o quanto antes (a caller também deve limpar).
        sudo_password = None
        if code != 0:
            return code, err

    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, cwd=cwd
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()


def _sudo_auth(password: str, cwd: str | None = None) -> tuple[int, str]:
    """Valida a senha e abre o ticket do sudo para os próximos comandos."""
    result = subprocess.run(
        ["sudo", "-S", "-v"],
        input=f"{password}\n",
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode == 0:
        return 0, ""
    detail = (result.stderr or result.stdout or "").strip()
    if not detail:
        detail = "Senha do sudo incorreta ou sudo não disponível."
    return result.returncode, detail
