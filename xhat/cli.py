"""Ponto de entrada de linha de comando do Xhat.

Modos:
- `Xhat`                    -> abre a TUI vazia (chat)
- `Xhat 'mover a para b'`   -> interação única (não abre TUI, só confirma)
"""

import argparse
import sys

from . import __version__
from . import ollama_runtime
from .config import get_model_key, load_config
from .llm import OllamaClient
from .models import MODELS, get_model


def main(argv: list[str] | None = None) -> int:
    """Interpreta os argumentos e despacha para o modo correto."""
    args = _build_parser().parse_args(argv)
    config = load_config()
    client = _make_client(config, args.model)
    manage = bool(config.get("manage_ollama", True))
    try:
        # Só o comando sem texto abre a TUI vazia; qualquer pedido vai para single-shot.
        if args.text:
            return _run_single(client, args)
        return _start_tui(client)
    finally:
        # Ao sair do Xhat, para o daemon Ollama (RAM ~0 em repouso).
        ollama_runtime.stop_if_managed(manage=manage)


def _build_parser() -> argparse.ArgumentParser:
    """Define todos os argumentos da CLI."""
    parser = argparse.ArgumentParser(
        prog="Xhat",
        description="Assistente local que traduz linguagem natural em comandos Linux.",
    )
    parser.add_argument(
        "text",
        nargs="*",
        help="Pedido para interação única (não abre a TUI).",
    )
    parser.add_argument(
        "-M",
        "--model",
        choices=list(MODELS.keys()),
        help="Modelo a usar nesta execução (sobrescreve a config).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Executa sem pedir confirmação (uso em automações).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Só mostra o comando sugerido, sem executar.",
    )
    parser.add_argument("--version", action="version", version=f"Xhat {__version__}")
    return parser


def _make_client(config: dict, model_override: str | None) -> OllamaClient:
    """Cria o cliente do modelo com base na config (ou no override da CLI)."""
    key = model_override or get_model_key(config)
    spec = get_model(key)
    return OllamaClient(
        host=config["ollama_host"],
        model_tag=spec.ollama_tag,
        manage_ollama=bool(config.get("manage_ollama", True)),
    )


def _run_single(client: OllamaClient, args: argparse.Namespace) -> int:
    """Executa o modo de interação única a partir do texto posicional."""
    from .single_shot import run_single_shot

    message = " ".join(args.text)
    return run_single_shot(
        message, client, auto_approve=args.yes, dry_run=args.dry_run
    )


def _start_tui(client: OllamaClient) -> int:
    """Abre a TUI de chat vazia (único caminho que inicia a interface)."""
    from .tui import XhatApp

    XhatApp(client=client).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
