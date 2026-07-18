"""Modo de interação única: `Xhat 'mover arquivo tal para tal'`.

Não abre a TUI. Interpreta a mensagem e, se for um comando, mostra e pede
confirmação antes de executar. Se for dúvida, apenas responde.
"""

from .brain import Brain, Reply
from .executor import is_dangerous, run_interactive
from .llm import LLMError, OllamaClient
from .workdir import default_cwd, try_apply_cd

# Cores ANSI para deixar a saída legível no terminal.
_BOLD, _RED, _GREEN, _CYAN, _DIM, _RESET = (
    "\033[1m", "\033[31m", "\033[32m", "\033[36m", "\033[2m", "\033[0m",
)


def run_single_shot(
    message: str,
    client: OllamaClient,
    auto_approve: bool = False,
    dry_run: bool = False,
) -> int:
    """Executa o fluxo de interação única. Retorna o código de saída do processo."""
    brain = Brain(client)
    cwd = default_cwd()
    try:
        reply = brain.interpret(message, cwd=str(cwd))
    except LLMError as exc:
        print(f"{_RED}{exc}{_RESET}")
        return 1
    return _dispatch(message, reply, brain, auto_approve, dry_run, cwd)


def _dispatch(
    message: str,
    reply: Reply,
    brain: Brain,
    auto_approve: bool,
    dry_run: bool,
    cwd,
) -> int:
    """Direciona para o fluxo de comando ou de dúvida."""
    if reply.is_executable:
        return _handle_command(message, reply, brain, auto_approve, dry_run, cwd)
    return _handle_question(message, reply, brain)


def _handle_question(message: str, reply: Reply, brain: Brain) -> int:
    """Exibe a resposta de uma dúvida e registra na memória."""
    print(f"{_CYAN}{reply.answer}{_RESET}")
    brain.remember(message, reply)
    return 0


def _handle_command(
    message: str,
    reply: Reply,
    brain: Brain,
    auto_approve: bool,
    dry_run: bool,
    cwd,
) -> int:
    """Mostra o comando, pede confirmação e executa se aprovado."""
    brain.remember(message, reply)
    if dry_run:
        _print_command_box(reply)
        print(f"{_DIM}(dry-run: nada foi executado){_RESET}")
        return 0
    final = reply.command if auto_approve else _confirm(reply)
    if final is None:
        print(f"{_DIM}Cancelado.{_RESET}")
        return 0
    print(f"{_DIM}$ {final}{_RESET}")
    new_cwd = try_apply_cd(final, cwd)
    if new_cwd is not None:
        print(f"{_GREEN}Diretório: {new_cwd}{_RESET}")
        return 0
    return run_interactive(final, cwd=str(cwd))


def _confirm(reply: Reply) -> str | None:
    """Mostra o comando e coleta a decisão do usuário.

    Retorna o comando final a executar, ou None se cancelado.
    """
    _print_command_box(reply)
    choice = input("[Enter=aplicar  e=editar  n=cancelar] ").strip().lower()
    if choice == "n":
        return None
    if choice == "e":
        return _edit_command(reply.command)
    return reply.command


def _edit_command(command: str) -> str | None:
    """Permite ao usuário digitar um comando ajustado."""
    edited = input(f"Novo comando (Enter mantém):\n  {command}\n> ").strip()
    return edited or command


def _print_command_box(reply: Reply) -> None:
    """Imprime o comando sugerido e alerta se for perigoso."""
    if reply.answer:
        print(f"{_DIM}{reply.answer}{_RESET}")
    print(f"{_BOLD}Comando sugerido:{_RESET}")
    print(f"  {_GREEN}{reply.command}{_RESET}")
    if reply.danger or is_dangerous(reply.command):
        print(f"{_RED}{_BOLD}⚠  Comando potencialmente destrutivo!{_RESET}")
