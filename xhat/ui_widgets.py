"""Widgets reutilizáveis da TUI (bolhas de chat e painéis)."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static


class ChatBubble(Vertical):
    """Bolha de mensagem (usuário à direita, IA à esquerda)."""

    DEFAULT_CSS = """
    ChatBubble { height: auto; width: 1fr; }
    """

    def __init__(self, label: str, body: str, kind: str = "ai", **kwargs):
        # kind: user | ai | system | thinking | command | danger
        super().__init__(**kwargs)
        self.bubble_label = label
        self.bubble_body = body
        self.kind = kind
        self.add_class("bubble", f"bubble-{kind}")

    def compose(self) -> ComposeResult:
        """Monta o corpo da bolha; rótulo só se houver texto."""
        if self.bubble_label:
            yield Label(f"[{self.bubble_label}]", classes="bubble-label")
        yield Static(self.bubble_body, classes="bubble-body", markup=True)


class SidePanel(Vertical):
    """Painel com título na sidebar (borda arredondada)."""

    DEFAULT_CSS = """
    SidePanel { height: auto; }
    """

    def __init__(self, title: str, **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self.add_class("side-panel")

    def compose(self) -> ComposeResult:
        """Título do painel; o App adiciona o restante via `with`."""
        yield Label(self._title, classes="panel-title")
