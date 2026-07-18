# Xhat — Assistente TUI local para Linux

> Chat de terminal (TUI) que **traduz linguagem natural em comandos Linux**, responde dúvidas simples e **pede permissão antes de executar**. Roda **100% local**, leve, e só consome recurso quando é chamado.

---

## 1. Visão geral

| Item | Descrição |
|------|-----------|
| **O que é** | IA de terminal (TUI) em formato de chat |
| **Faz o quê** | Converte pedido em português → comando shell + explica dúvidas simples |
| **Segurança** | Sempre mostra o comando e **pede aprovação** antes de rodar |
| **Uso** | Interativo (chat) ou em automações (modo não-interativo) |
| **Onde roda** | Local (offline após baixar o modelo), sem nuvem |
| **Recurso** | ~0 em repouso; só carrega o modelo quando recebe uma tarefa |

### Exemplo de fluxo

```
você> mover a pasta caminho/da/pasta para novo/caminho/da/pasta
xhat> Comando sugerido:
      sudo mv caminho/da/pasta novo/caminho/da/pasta
      [Enter=aplicar]  [e=editar]  [n=cancelar]
```

---

## 2. Requisitos-chave (do pedido)

| # | Requisito | Como atender |
|---|-----------|--------------|
| 1 | Traduzir NL → comando Linux | Modelo pequeno bom em código/shell |
| 2 | Pedir permissão antes de aplicar | Camada de confirmação obrigatória na TUI |
| 3 | Usável em automações | Flags `--yes` / `--dry-run` / saída JSON |
| 4 | **Não guardar nada na RAM** entre turnos | Estado vive em arquivos `.md`, não em memória |
| 5 | Contexto em `.md` (máx. ~10k chars) | 1 arquivo de contexto + 1 de perfil do usuário |
| 6 | "Esquecer" o irrelevante | Rotina de compactação/resumo ao passar de 10k |
| 7 | Leve e preciso | Modelo 1B–4B quantizado (Q4_K_M) |
| 8 | Não afetar desempenho da máquina | Modelo **carrega sob demanda** e descarrega depois |

---

## 3. Arquitetura de memória em arquivos (sem RAM persistente)

A ideia central: **cada mensagem não acumula na RAM**. O modelo lê os `.md`, pensa, atualiza os `.md` e descarrega.

```
.xhat/
├── contexto.md        # histórico resumido da sessão (máx ~10k chars)
├── perfil.md          # características/preferências do usuário (máx ~10k chars)
└── .gitignore         # ignora a pasta .xhat (dados locais)
```

### Ciclo por mensagem

| Passo | Ação |
|-------|------|
| 1 | Lê `contexto.md` + `perfil.md` |
| 2 | Monta prompt (arquivos + mensagem nova) |
| 3 | Gera resposta / comando |
| 4 | Reescreve `contexto.md` já resumido (não faz "append" infinito) |
| 5 | Atualiza `perfil.md` se aprendeu algo novo do usuário |
| 6 | Se arquivo > 10k chars → compacta (remove o menos relevante) |

> **Vantagem:** contexto sempre pequeno = prompt curto = inferência rápida e barata.
> **Trade-off:** o resumo pode perder detalhes; por isso o `perfil.md` guarda o que é permanente.

### `perfil.md` — exemplos de características

- Distro / gerenciador de pacotes (apt, dnf, pacman…)
- Usa `sudo` com frequência? Prefere comandos verbosos ou curtos?
- Ferramentas favoritas (docker, systemctl, git…)
- Nível: iniciante / avançado

---

## 4. Modelos do projeto (dois modelos, troca na TUI)

O Xhat vem com **dois modelos locais**, escolhíveis dentro da própria TUI. Formato **GGUF Q4_K_M**.

| Modelo | Params | RAM (Q4) | Melhor para | Papel |
|--------|--------|----------|-------------|-------|
| **Qwen3.5 4B** | 4B | ~3 GB | Chat geral, dúvidas, multilíngue (PT) | **Padrão** — rápido e leve |
| **Qwen2.5-Coder 7B** | 7B | ~4.7 GB | Tradução NL→comando e scripts complexos | **Precisão** — quando o comando é crítico |

### Troca de modelo dentro da TUI

| Ação | Ideia de comando |
|------|------------------|
| Ver modelo atual | `/modelo` |
| Trocar para o leve | `/modelo qwen3.5` |
| Trocar para o preciso | `/modelo coder` |
| Atalho | tecla dedicada (ex.: `F2`) alterna entre os dois |

- A escolha do modelo fica salva em config (ex.: `.xhat/config.toml`).
- Trocar de modelo **descarrega** o anterior e só carrega o novo **na próxima chamada** (não pré-carrega).

### Regra de recurso (vale para os DOIS modelos)

| Estado | Consumo |
|--------|---------|
| TUI aberta, sem pedido | ≈ 0 (nenhum modelo em memória) |
| Você envia uma mensagem | Carrega o modelo escolhido → responde |
| Terminou a resposta | Descarrega (timeout curto) → volta a ≈ 0 |

> **Independente do modelo**, o recurso só é gasto **na chamada e na interação**. Em repouso, nenhum dos dois fica ocupando RAM/CPU.

> **Dica:** dá pra usar Qwen3.5 4B no dia a dia (leve) e alternar para o Coder 7B só quando o comando for arriscado/complexo.

---

## 5. Runtime (como rodar o modelo)

| Opção | Vantagem | Uso |
|-------|----------|-----|
| **llama.cpp** | Controle fino, carrega/descarrega sob demanda, roda CPU puro (AVX2/AVX512) | **Melhor p/ "0 recurso em repouso"** |
| **Ollama** | Simples (1 comando), gerencia modelos | Ótimo p/ começar rápido |

### Sobre "não afetar o desempenho"

| Estratégia | Efeito |
|-----------|--------|
| Carregar o modelo **escolhido só na chamada** e descarregar após responder | RAM/CPU ≈ 0 quando ocioso |
| **Um modelo por vez** (nunca os dois juntos) | Não soma o consumo dos dois |
| Ao trocar de modelo na TUI, descarregar o anterior | Sem acúmulo de RAM |
| Ollama com `keep_alive=0` (ou llama.cpp carrega/descarrega) | Descarrega logo após responder |
| Limitar `--threads` | Não monopoliza a CPU durante a inferência |
| Contexto pequeno (10k) | Menos processamento por turno |

> Em repouso o Xhat é só um binário parado esperando input — nenhum dos dois modelos fica em memória.

---

## 6. Modos de operação

| Modo | Comando (ideia) | Comportamento |
|------|-----------------|---------------|
| **Chat (TUI)** | `xhat` | Interativo, pede aprovação por comando |
| **Uma tacada** | `xhat "compactar a pasta logs"` | Sugere, pergunta, executa |
| **Automação** | `xhat --yes "..."` | Executa sem perguntar (cuidado) |
| **Simulação** | `xhat --dry-run "..."` | Só mostra o comando, não roda |
| **JSON** | `xhat --json "..."` | Saída estruturada p/ scripts |

### Segurança na execução

- **Nunca** executa sem confirmação no modo chat.
- Destaca comandos perigosos (`rm -rf`, `dd`, `mkfs`, `> /dev/...`).
- Opção de **editar** o comando antes de aplicar.
- Log local do que foi executado.

---

## 7. Stack sugerida

| Camada | Opção sugerida | Por quê |
|--------|----------------|---------|
| Linguagem | **Python** ou **Go/Rust** | Python = rápido de prototipar; Go/Rust = binário leve |
| TUI | `Textual`/`Rich` (Py) ou `Bubble Tea` (Go) | Chat bonito no terminal |
| Inferência | `llama.cpp` (via `llama-cpp-python`) | Carregamento sob demanda |
| Modelo | Qwen3.5 4B GGUF Q4_K_M | Padrão equilibrado |
| Memória | Arquivos `.md` + rotina de resumo | Requisito central do projeto |

---

## 8. Roadmap sugerido (MVP → completo)

| Fase | Entrega |
|------|---------|
| **MVP** | TUI chat + tradução NL→comando + confirmação + 1 modelo local |
| **v2** | Memória em `.md` (contexto + perfil) com limite de 10k e resumo |
| **v3** | Modos automação (`--yes`, `--dry-run`, `--json`) |
| **v4** | Detecção de comandos perigosos + log + editar antes de aplicar |
| **v5** | Troca fácil de modelo + auto-descarregamento p/ 0 recurso ocioso |

---

## 9. Riscos e cuidados

| Risco | Mitigação |
|-------|-----------|
| Comando errado/destrutivo | Confirmação obrigatória + destaque de perigo |
| Modelo pequeno "alucina" comando | Poucos exemplos no prompt + `--dry-run` padrão |
| Resumo perde contexto importante | `perfil.md` guarda o permanente; contexto guarda o recente |
| `--yes` em automação | Restringir a comandos de uma allowlist |
