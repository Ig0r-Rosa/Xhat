"""TUI de chat do Xhat (Textual) — layout com sidebar e bolhas.

- Sidebar: modelo clicável e histórico recente
- Chat: bolhas (você à direita, Xhat à esquerda)
- Confirmação de comando com botões Aplicar / Editar / Cancelar
"""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Input,
    Label,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option
from textual.worker import Worker

from .brain import Brain, Reply
from .config import get_model_key, load_config, set_model_key
from .executor import is_dangerous, run_captured
from .llm import LLMError, OllamaClient
from .memory import Memory
from .models import MODELS, get_model, list_models
from .ui_widgets import ChatBubble
from .workdir import default_cwd, format_cwd, try_apply_cd


class XhatApp(App):
    """Aplicação TUI principal com visual de chat."""

    CSS_PATH = Path(__file__).with_name("tui.tcss")
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [("ctrl+c", "quit", "Sair")]

    def __init__(self, client: OllamaClient):
        super().__init__()
        self.config = load_config()
        self.client = client
        self.brain = Brain(client)
        self.pending_command: str | None = None
        self._thinking: ChatBubble | None = None
        self.cwd = default_cwd()

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        """Monta sidebar, chat, confirmação e input (sem footer/palette)."""
        with Horizontal(id="body"):
            yield from self._compose_sidebar()
            yield from self._compose_main()

    def _compose_sidebar(self) -> ComposeResult:
        """Coluna esquerda: modelo (topo) e histórico (resto da altura)."""
        with Vertical(id="sidebar"):
            with Vertical(classes="side-panel", id="model-panel"):
                yield OptionList(id="model-list")
            with Vertical(classes="side-panel", id="history-panel"):
                yield Label("Histórico Recente", classes="panel-title")
                yield OptionList(id="history-list")

    def _compose_main(self) -> ComposeResult:
        """Coluna direita: chat + confirmação + cwd + prompt."""
        with Vertical(id="main"):
            yield VerticalScroll(id="chat")
            with Horizontal(id="confirm"):
                yield Static(id="confirm-spacer")
                yield Button("Aplicar", id="apply", variant="success")
                yield Button("Editar", id="edit", variant="warning")
                yield Button("Cancelar", id="cancel", variant="error")
            yield Label(id="cwd-label", classes="cwd-label")
            with Horizontal(id="prompt-row"):
                yield Button("?", id="help-btn", classes="subtle-btn")
                yield Input(
                    placeholder="Digite sua mensagem...",
                    id="prompt",
                )

    def on_mount(self) -> None:
        """Inicializa listas clicáveis, cwd e foca o prompt."""
        # Garante histórico esticado até embaixo (Textual às vezes ignora 1fr).
        self.query_one("#history-panel").styles.height = "1fr"
        self.query_one("#history-list").styles.height = "1fr"
        self._fill_model_list()
        self._refresh_history()
        self._refresh_cwd_label()
        self._post_system("Bem-vindo ao Xhat.")
        self.query_one("#prompt", Input).focus()

    # ----------------------------------------------------------- cliques mouse
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Trata clique/Enter em modelo ou histórico."""
        list_id = event.option_list.id
        if list_id == "model-list":
            self._on_model_clicked(event.option)
        elif list_id == "history-list":
            self._on_history_clicked(event.option)

    def _on_model_clicked(self, option: Option) -> None:
        """Troca o modelo ao clicar na lista (sem pré-carregar na RAM)."""
        key = str(option.id) if option.id else ""
        if key in MODELS and key != get_model_key(self.config):
            self._switch_model(key)

    def _on_history_clicked(self, option: Option) -> None:
        """Coloca no input o pedido completo do histórico clicado."""
        key = str(option.id) if option.id else ""
        if not key.startswith("h"):
            return
        items = self._history_items()
        index = int(key[1:])
        if 0 <= index < len(items):
            prompt = self.query_one("#prompt", Input)
            prompt.value = items[index]
            prompt.focus()

    # --------------------------------------------------------------- eventos UI
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Envia a mensagem do campo de entrada."""
        text = event.value.strip()
        self.query_one("#prompt", Input).value = ""
        if text:
            self._submit(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Botões de confirmação e o atalho sutil de ajuda."""
        if event.button.id == "help-btn":
            self._cmd_help()
            return
        actions = {"apply": self._apply, "edit": self._edit, "cancel": self._cancel}
        action = actions.get(event.button.id)
        if action:
            action()

    # ----------------------------------------------------------- entrada texto
    def _submit(self, text: str) -> None:
        """Direciona slash, shell direto (!) ou pergunta à IA."""
        self._post_user(text)
        if text.startswith("/"):
            self._handle_slash(text)
        elif text.startswith("!"):
            self._offer_command(text[1:].strip(), answer="Comando manual.")
        else:
            self._ask_model(text)

    def _handle_slash(self, text: str) -> None:
        """Interpreta /modelo, /ajuda, /reset, /limpar, /sair."""
        cmd, _, arg = text[1:].partition(" ")
        handlers = {
            "modelo": lambda: self._cmd_model(arg.strip()),
            "ajuda": self._cmd_help,
            "reset": self._cmd_reset,
            "limpar": self._cmd_reset,
            "sair": self.exit,
        }
        handler = handlers.get(cmd)
        if handler:
            handler()
        else:
            self._post_system(f"[red]Comando desconhecido:[/] /{cmd}")

    # -------------------------------------------------------------- modelos
    def _fill_model_list(self) -> None:
        """Preenche a lista de modelos e destaca o atual."""
        current = get_model_key(self.config)
        widget = self.query_one("#model-list", OptionList)
        widget.clear_options()
        for spec in list_models():
            mark = "● " if spec.key == current else "○ "
            widget.add_option(Option(f"{mark}{spec.label}", id=spec.key))
        keys = list(MODELS.keys())
        if current in keys:
            widget.highlighted = keys.index(current)

    def _cmd_model(self, arg: str) -> None:
        """Troca via texto: `/modelo` lista; `/modelo coder` aplica."""
        if not arg:
            self._post_system(
                "Clique em um modelo na sidebar ou use `/modelo qwen3.5|coder`."
            )
            return
        if arg not in MODELS:
            self._post_system(f"[red]Modelo inválido:[/] {arg}")
            return
        self._switch_model(arg)

    def _switch_model(self, key: str) -> None:
        """Aplica troca de modelo e atualiza a UI (descarrega o anterior)."""
        self.config = set_model_key(self.config, key)
        spec = get_model(key)
        self.client = OllamaClient(self.config["ollama_host"], spec.ollama_tag)
        self.brain = Brain(self.client)
        self._fill_model_list()
        self._post_system(f"Modelo alterado para [b]{spec.label}[/].")

    def _refresh_history(self) -> None:
        """Atualiza a sidebar com o histórico rotativo (mais novos no topo)."""
        widget = self.query_one("#history-list", OptionList)
        widget.clear_options()
        items = Memory().recent_user_messages()
        if not items:
            widget.add_option(Option("(vazio)", id="empty"))
            return
        for i, text in enumerate(items):
            # Mostra mais texto; a lista agora tem altura quase total da tela.
            widget.add_option(Option(text[:60], id=f"h{i}"))

    def _history_items(self) -> list[str]:
        """Pedidos recentes do usuário (mesmo critério da sidebar)."""
        return Memory().recent_user_messages()

    # ------------------------------------------------------------- fluxo IA
    def _ask_model(self, text: str) -> None:
        """Mostra 'pensando…' e chama o modelo em thread."""
        self._show_thinking()
        self.run_worker(
            lambda: self._interpret(text),
            thread=True,
            exclusive=True,
            name="interpret",
            group="llm",
        )

    def _interpret(self, text: str) -> None:
        """(Thread) Interpreta e agenda a exibição na UI."""
        try:
            reply = self.brain.interpret(text, cwd=str(self.cwd))
            self.brain.remember(text, reply)
            self.call_from_thread(self._show_reply, reply)
        except LLMError as exc:
            self.call_from_thread(self._on_llm_error, str(exc))

    def _on_llm_error(self, message: str) -> None:
        """Remove 'pensando…' e mostra o erro."""
        self._clear_thinking()
        self._post_system(f"[red]{message}[/]")

    def _show_reply(self, reply: Reply) -> None:
        """Exibe resposta da IA ou oferece comando para confirmar."""
        self._clear_thinking()
        self._refresh_history()
        if reply.is_executable:
            self._offer_command(reply.command, reply.answer, reply.danger)
        else:
            self._post_ai(reply.answer or "(sem resposta)")

    # --------------------------------------------------------- confirmar cmd
    def _offer_command(self, command: str, answer: str = "", danger: bool = False):
        """Mostra bolha de comando e habilita os botões."""
        if not command:
            self._post_system("[yellow]Nenhum comando gerado.[/]")
            return
        self.pending_command = command
        body = ""
        if answer:
            body += f"{answer}\n\n"
        body += f"[b]$ {command}[/]"
        if danger or is_dangerous(command):
            body += "\n\n[bold red]⚠ Comando potencialmente destrutivo![/]"
            self._mount_bubble("Xhat", body, "danger")
        else:
            self._mount_bubble("Xhat", body, "command")
        self._toggle_confirm(True)

    def _apply(self) -> None:
        """Aplica o comando pendente (cd local ou shell no cwd)."""
        command = self.pending_command
        self._toggle_confirm(False)
        if not command:
            return
        if self._try_change_directory(command):
            return
        self._post_system(f"$ {command}")
        self.run_worker(
            lambda: self._execute(command), thread=True, group="exec"
        )

    def _try_change_directory(self, command: str) -> bool:
        """Se for `cd`, atualiza o diretório da sessão e a barra."""
        from .workdir import looks_like_cd

        new_cwd = try_apply_cd(command, self.cwd)
        if new_cwd is not None:
            self.cwd = new_cwd
            self._refresh_cwd_label()
            self._post_system(f"Diretório: [b]{format_cwd(self.cwd)}[/]")
            return True
        if looks_like_cd(command):
            self._post_system(f"[red]Diretório inválido:[/] {command}")
            return True
        return False

    def _execute(self, command: str) -> None:
        """(Thread) Roda o comando no cwd atual e devolve a saída."""
        code, output = run_captured(command, cwd=str(self.cwd))
        self.call_from_thread(self._show_output, code, output)

    def _show_output(self, code: int, output: str) -> None:
        """Exibe resultado da execução em bolha de sistema."""
        color = "green" if code == 0 else "red"
        text = output if output else "(sem saída)"
        self._post_system(f"{text}\n[{color}]exit={code}[/]")

    def _edit(self) -> None:
        """Coloca o comando no input com prefixo !."""
        self._toggle_confirm(False)
        prompt = self.query_one("#prompt", Input)
        prompt.value = f"!{self.pending_command or ''}"
        prompt.focus()

    def _cancel(self) -> None:
        """Cancela o comando pendente."""
        self._toggle_confirm(False)
        self.pending_command = None
        self._post_system("Cancelado.")

    # ------------------------------------------------------------------ helpers
    def _toggle_confirm(self, visible: bool) -> None:
        """Mostra/esconde a barra Aplicar/Editar/Cancelar."""
        self.query_one("#confirm").set_class(visible, "visible")

    def _cmd_help(self) -> None:
        """Ajuda rápida dentro do chat."""
        self._post_ai(
            "Comandos:\n"
            "• [b]/modelo[/] / clique na sidebar — troca o modelo\n"
            "• [b]/ajuda[/] — esta ajuda\n"
            "• [b]/reset[/] — limpa a tela do chat\n"
            "• [b]/sair[/] — fecha o Xhat\n"
            "• Prefixe com [b]![/] para comando shell manual"
        )

    def _cmd_reset(self) -> None:
        """Limpa as bolhas do chat (não apaga a memória em disco)."""
        chat = self.query_one("#chat", VerticalScroll)
        chat.remove_children()
        self._thinking = None
        self._post_system("Chat limpo. Digite uma nova mensagem.")

    def _show_thinking(self) -> None:
        """Exibe bolha temporária enquanto a IA processa (2x por baixo dos panos)."""
        self._clear_thinking()
        self._thinking = ChatBubble("Xhat", "Pensando....", kind="thinking")
        self.query_one("#chat", VerticalScroll).mount(self._thinking)
        self._thinking.scroll_visible()

    def _clear_thinking(self) -> None:
        """Remove a bolha de 'pensando…' se existir."""
        if self._thinking is not None:
            self._thinking.remove()
            self._thinking = None

    def _post_user(self, text: str) -> None:
        """Publica bolha do usuário (direita, ciano) — sem rótulo [Você]."""
        self._mount_bubble("", text, "user")

    def _post_ai(self, text: str) -> None:
        """Publica bolha da IA (esquerda, verde)."""
        self._mount_bubble("Xhat", text, "ai")

    def _post_system(self, text: str) -> None:
        """Publica bolha de sistema (central, neutra)."""
        self._mount_bubble("sistema", text, "system")

    def _mount_bubble(self, label: str, body: str, kind: str) -> None:
        """Monta uma bolha no scroll do chat e rola até ela."""
        bubble = ChatBubble(label, body, kind=kind)
        chat = self.query_one("#chat", VerticalScroll)
        chat.mount(bubble)
        bubble.scroll_visible()

    def _refresh_cwd_label(self) -> None:
        """Atualiza o texto do diretório acima do campo de mensagem."""
        self.query_one("#cwd-label", Label).update(f"{format_cwd(self.cwd)}")

    def _model_label(self) -> str:
        """Rótulo amigável do modelo atual."""
        return get_model(get_model_key(self.config)).label

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Hook reservado para estados de worker."""
        return
