"""Execução de comandos com confirmação e checagem de perigo.

Regra de ouro do Xhat: nunca executar sem aprovação explícita do usuário.
"""

import subprocess

# Padrões que indicam comandos potencialmente destrutivos (rede de segurança
# extra, além do "danger" que o próprio modelo sinaliza).
DANGEROUS_PATTERNS = (
    "rm -rf", "rm -r", "mkfs", "dd ", ":(){", "> /dev/", "chmod -r 777",
    "chown -r", "shutdown", "reboot", "> /etc/", "truncate",
)


def is_dangerous(command: str) -> bool:
    """Heurística simples para detectar comandos arriscados."""
    low = command.lower()
    return any(pat in low for pat in DANGEROUS_PATTERNS)


def run_interactive(command: str, cwd: str | None = None) -> int:
    """Executa herdando o terminal (permite prompt de senha do sudo)."""
    result = subprocess.run(command, shell=True, cwd=cwd)
    return result.returncode


def run_captured(command: str, cwd: str | None = None) -> tuple[int, str]:
    """Executa capturando a saída (usado pela TUI para exibir o resultado)."""
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, cwd=cwd
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()
