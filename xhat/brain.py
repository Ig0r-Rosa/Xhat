"""Orquestra a interpretação de uma mensagem do usuário.

Fluxo da IA (2 passagens, por baixo dos panos):
1) Interpretar — resumir/formatar o pedido
2) Decidir — escolher a ação (comando, pesquisa, conversa, …)

Pesquisa web só ocorre se a 2ª passagem pedir intent=pesquisa.
"""

from dataclasses import dataclass
from pathlib import Path

from .choices import try_resolve_choice
from .llm import OllamaClient
from .memory import Memory
from .navigate import (
    extract_dir_name,
    heaviest_command,
    last_nav_target,
    list_cwd_command,
    wants_options_list,
)
from .prompts import (
    DECIDE_PROMPT,
    INTERPRET_PROMPT,
    SEARCH_ANSWER_PROMPT,
    SEARCH_VERIFY_PROMPT,
    SUMMARY_PROMPT,
    build_decide_prompt,
    build_search_prompt,
    build_search_verify_prompt,
    build_user_prompt,
)
from .search import search_query_from_message, search_web
from .workdir import (
    find_directories,
    looks_like_cd,
    try_apply_cd,
)

# Intenções válidas devolvidas pelo modelo.
INTENT_COMMAND = "comando"
INTENT_FILE = "arquivo"
INTENT_QUESTION = "duvida"
INTENT_SEARCH = "pesquisa"
INTENT_NAVIGATE = "navegar"


@dataclass
class Reply:
    """Resposta interpretada de um turno."""

    intent: str
    answer: str
    command: str
    danger: bool

    @property
    def is_executable(self) -> bool:
        """Indica se há um comando a confirmar/executar."""
        return self.intent in (INTENT_COMMAND, INTENT_FILE) and bool(self.command)


class Brain:
    """Interpreta mensagens com memória em disco e IA em 2 passagens."""

    def __init__(self, client: OllamaClient):
        self.client = client
        self.memory = Memory(summarizer=self._summarize)

    def interpret(self, message: str, cwd: str = "") -> Reply:
        """Atalhos locais + IA (interpretar → decidir)."""
        cwd_path = Path(cwd) if cwd else Path.cwd()
        context = self.memory.read_context()
        profile = self.memory.read_profile()

        # Atalhos determinísticos (sem LLM).
        choice = try_resolve_choice(message, context)
        if choice:
            return self._reply_from_choice(choice)
        heavy = heaviest_command(message)
        if heavy:
            command, answer = heavy
            return Reply(
                intent=INTENT_COMMAND,
                answer=answer,
                command=command,
                danger=False,
            )
        # Listar pastas/disciplinas → sempre no cwd atual (nunca reabre navegação).
        listed = list_cwd_command(message)
        if listed:
            command, answer = listed
            return Reply(
                intent=INTENT_COMMAND,
                answer=answer,
                command=command,
                danger=False,
            )
        if wants_options_list(message):
            name = last_nav_target(context) or extract_dir_name(message)
            if name:
                return self._navigate_to_named_dir({"dir_name": name}, cwd_path)
        dir_name = extract_dir_name(message)
        if dir_name:
            return self._navigate_to_named_dir({"dir_name": dir_name}, cwd_path)

        # IA: 1ª interpreta/resume → 2ª decide a ação.
        data = self._two_pass(message, cwd, context, profile)
        intent = data.get("intent")
        if intent == INTENT_SEARCH:
            return self._answer_with_search(message, data, cwd, context)
        if intent == INTENT_NAVIGATE:
            return self._navigate_to_named_dir(data, cwd_path)
        reply = self._to_reply(data)
        return self._fix_bad_cd(reply, cwd_path)

    def _two_pass(
        self, message: str, cwd: str, context: str, profile: str
    ) -> dict:
        """1ª passagem interpreta; 2ª passagem decide a ação."""
        user_prompt = build_user_prompt(context, profile, message, cwd=cwd)
        interpretation = self.client.chat_json(INTERPRET_PROMPT, user_prompt)
        decision = self.client.chat_json(
            DECIDE_PROMPT,
            build_decide_prompt(message, cwd, context, interpretation),
        )
        if not isinstance(decision, dict) or not decision.get("intent"):
            return self._fallback_from_interpretation(interpretation, message)
        return decision

    def _fallback_from_interpretation(
        self, interpretation: dict, message: str
    ) -> dict:
        """Se a 2ª passagem falhar, deriva uma ação mínima da 1ª."""
        tipo = str(interpretation.get("tipo") or "duvida")
        if tipo == "pesquisa" or interpretation.get("precisa_web"):
            query = (
                str(interpretation.get("search_query") or "").strip()
                or search_query_from_message(message)
            )
            return {
                "intent": INTENT_SEARCH,
                "command": "",
                "answer": "Pesquisando…",
                "danger": False,
                "search_query": query,
                "dir_name": "",
            }
        if tipo == "navegar":
            return {
                "intent": INTENT_NAVIGATE,
                "command": "",
                "answer": "",
                "danger": False,
                "search_query": "",
                "dir_name": str(interpretation.get("dir_name") or ""),
            }
        if tipo == "conversa":
            return {
                "intent": INTENT_QUESTION,
                "command": "",
                "answer": "Oi! Em que posso ajudar?",
                "danger": False,
                "search_query": "",
                "dir_name": "",
            }
        return {
            "intent": INTENT_QUESTION,
            "command": "",
            "answer": str(interpretation.get("resumo") or "Pode detalhar?"),
            "danger": False,
            "search_query": "",
            "dir_name": "",
        }

    def _reply_from_choice(self, chosen: str) -> Reply:
        """Transforma a opção escolhida em um `cd` (se for caminho)."""
        path = Path(chosen)
        if path.is_dir():
            return Reply(
                intent=INTENT_COMMAND,
                answer=f"Ok, usando [b]{chosen}[/].",
                command=f"cd {chosen}",
                danger=False,
            )
        return Reply(
            intent=INTENT_QUESTION,
            answer=f"Você escolheu: [b]{chosen}[/]. Como sigo com isso?",
            command="",
            danger=False,
        )

    def _fix_bad_cd(self, reply: Reply, cwd: Path) -> Reply:
        """Se o modelo inventou um `cd` inválido, busca a pasta pelo nome."""
        if not reply.command or not looks_like_cd(reply.command):
            return reply
        if try_apply_cd(reply.command, cwd) is not None:
            return reply
        name = Path(reply.command.strip().split(maxsplit=1)[-1]).name
        name = name.strip("\"'")
        if not name or name in {".", ".."}:
            return reply
        return self._navigate_to_named_dir({"dir_name": name}, cwd)

    def _navigate_to_named_dir(self, data: dict, cwd) -> Reply:
        """Localiza pasta pelo nome; se várias, pergunta qual usar."""
        name = str(data.get("dir_name") or "").strip()
        if not name:
            return Reply(
                intent=INTENT_QUESTION,
                answer="Qual o nome da pasta que você quer abrir?",
                command="",
                danger=False,
            )
        matches = find_directories(name, cwd=cwd)
        if not matches:
            return Reply(
                intent=INTENT_QUESTION,
                answer=(
                    f"Não encontrei pasta “[b]{name}[/]”. "
                    "Quer que eu busque com outro nome ou um caminho parcial?"
                ),
                command="",
                danger=False,
            )
        if len(matches) == 1:
            best = matches[0]
            return Reply(
                intent=INTENT_COMMAND,
                answer=f"Encontrei [b]{best}[/].",
                command=f"cd {best}",
                danger=False,
            )
        extras = "\n".join(f"{i}. {p}" for i, p in enumerate(matches[:5], 1))
        return Reply(
            intent=INTENT_QUESTION,
            answer=(
                f"Encontrei várias pastas “[b]{name}[/]”. Qual delas?\n{extras}"
            ),
            command="",
            danger=False,
        )

    def _answer_with_search(
        self, message: str, data: dict, cwd: str, context: str
    ) -> Reply:
        """Busca na web e resume só com base nos resultados (2 passagens)."""
        query = str(
            data.get("search_query") or search_query_from_message(message)
        ).strip()
        results = search_web(query)
        if not results:
            return Reply(
                intent=INTENT_QUESTION,
                answer=(
                    "Não consegui pesquisar agora (sem rede ou busca vazia). "
                    "Tente de novo quando estiver online."
                ),
                command="",
                danger=False,
            )
        draft = self.client.chat_json(
            SEARCH_ANSWER_PROMPT, build_search_prompt(message, results)
        )
        verified = self.client.chat_json(
            SEARCH_VERIFY_PROMPT,
            build_search_verify_prompt(message, results, draft),
        )
        final = verified if verified.get("intent") else draft
        reply = self._to_reply(final)
        reply.intent = INTENT_QUESTION
        if reply.answer and "pesquisa web" not in reply.answer.lower():
            reply.answer = (
                f"{reply.answer.rstrip()}\n\n[dim](com base na pesquisa web)[/]"
            )
        return reply

    def remember(self, message: str, reply: Reply) -> None:
        """Registra o turno na memória com comando + resposta."""
        self.memory.append_turn(message, self._summary_for_memory(reply))

    def _summary_for_memory(self, reply: Reply) -> str:
        """Monta o texto gravado no .md: comando e/ou resposta."""
        parts: list[str] = []
        if reply.command:
            parts.append(f"comando=`{reply.command}`")
        if reply.answer:
            parts.append(reply.answer)
        if not parts:
            parts.append(f"(intent={reply.intent})")
        return " | ".join(parts)

    def _to_reply(self, data: dict) -> Reply:
        """Converte o JSON do modelo em `Reply`, com valores seguros."""
        return Reply(
            intent=data.get("intent", INTENT_QUESTION),
            answer=str(data.get("answer", "")).strip(),
            command=str(data.get("command", "")).strip(),
            danger=bool(data.get("danger", False)),
        )

    def _summarize(self, text: str) -> str:
        """Compacta a memória via modelo quando ela ultrapassa o limite."""
        return self.client.chat_text(SUMMARY_PROMPT, text)
