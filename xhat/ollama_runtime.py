"""Sobe/desce o daemon Ollama sob demanda.

O Xhat já usa keep_alive=0 (modelo some da RAM após a resposta).
Ainda assim o serviço `ollama serve` (~40 MB) costuma ficar ligado no systemd.

Com manage_ollama=true (padrão):
- ao chamar a IA → garante que o daemon está no ar
- ao sair do Xhat → para o daemon (RAM ~0 de novo)
"""

from __future__ import annotations

import atexit
import subprocess
import time

import requests

DEFAULT_HOST = "http://127.0.0.1:11434"

# Nesta sessão: subimos o daemon? (para saber se devemos parar no exit)
_started_by_us = False
_atexit_registered = False


def is_up(host: str = DEFAULT_HOST) -> bool:
    """True se a API do Ollama responde."""
    try:
        resp = requests.get(f"{host.rstrip('/')}/api/tags", timeout=1.5)
        return resp.ok
    except requests.RequestException:
        return False


def ensure_running(host: str = DEFAULT_HOST, manage: bool = True) -> None:
    """Garante o daemon no ar; se manage=True, sobe via systemctl se preciso."""
    global _started_by_us, _atexit_registered
    if is_up(host):
        return
    if not manage:
        return
    _systemctl("start")
    _wait_until_up(host)
    _started_by_us = True
    if not _atexit_registered:
        atexit.register(lambda: stop_if_managed(manage=True))
        _atexit_registered = True


def stop_if_managed(manage: bool = True) -> None:
    """Para o daemon ao sair do Xhat (libera a RAM do ollama serve)."""
    global _started_by_us
    if not manage:
        return
    # Para mesmo se já estava ligado: objetivo é ~0 RAM sem o Xhat.
    if not is_up():
        _started_by_us = False
        return
    _systemctl("stop")
    _started_by_us = False


def disable_boot_service() -> tuple[bool, str]:
    """Desliga o Ollama no boot (idempotente). Retorna (ok, mensagem)."""
    try:
        subprocess.run(
            ["systemctl", "is-enabled", "ollama"],
            capture_output=True,
            text=True,
            check=False,
        )
        r = subprocess.run(
            ["sudo", "-n", "systemctl", "disable", "--now", "ollama"],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode == 0:
            return True, "Serviço ollama desabilitado no boot e parado."
        # Tenta com sudo interativo (instalação).
        r2 = subprocess.run(
            ["sudo", "systemctl", "disable", "--now", "ollama"],
            capture_output=True,
            text=True,
            check=False,
        )
        if r2.returncode == 0:
            return True, "Serviço ollama desabilitado no boot e parado."
        return False, (r.stderr or r2.stderr or "Falha ao desabilitar ollama.").strip()
    except FileNotFoundError:
        return False, "systemctl/sudo não disponível."


def install_nopasswd_systemctl(user: str) -> tuple[bool, str]:
    """Permite start/stop do ollama sem senha (sudoers.d)."""
    import tempfile
    from pathlib import Path

    content = (
        f"# Xhat — sobe/desce Ollama sem senha\n"
        f"{user} ALL=(root) NOPASSWD: "
        f"/usr/bin/systemctl start ollama, "
        f"/usr/bin/systemctl stop ollama, "
        f"/bin/systemctl start ollama, "
        f"/bin/systemctl stop ollama\n"
    )
    path = Path("/etc/sudoers.d/xhat-ollama")
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".xhat") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        r = subprocess.run(
            ["sudo", "install", "-m", "440", tmp_path, str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        Path(tmp_path).unlink(missing_ok=True)
        if r.returncode != 0:
            return False, (r.stderr or "falha ao gravar sudoers").strip()
        check = subprocess.run(
            ["sudo", "visudo", "-cf", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode != 0:
            return False, (check.stderr or "sudoers inválido").strip()
        return True, f"sudoers ok: {path}"
    except FileNotFoundError:
        return False, "sudo não disponível."


def _systemctl(action: str) -> None:
    """systemctl start|stop ollama (prefere -n / NOPASSWD)."""
    for cmd in (
        ["sudo", "-n", "systemctl", action, "ollama"],
        ["systemctl", "--user", action, "ollama"],
        ["sudo", "systemctl", action, "ollama"],
    ):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            continue
        if r.returncode == 0:
            return
    # Último recurso: binário direto (modelos do usuário — pode falhar).
    if action == "start":
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def _wait_until_up(host: str, timeout: float = 30.0) -> None:
    """Espera a API ficar pronta após o start."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_up(host):
            return
        time.sleep(0.4)
