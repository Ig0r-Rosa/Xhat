#!/usr/bin/env bash
# instala.sh — instala o Xhat, coloca `Xhat` no PATH e abre a TUI.
#
# Uso:
#   ./instala.sh              # instala + abre
#   ./instala.sh --sem-abrir  # só instala
#   ./instala.sh --com-ollama # também puxa os modelos (se ollama existir)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
BIN_DIR="${HOME}/.local/bin"
ABRIR=1
COM_OLLAMA=0

# ---------------------------------------------------------------------------
# Argumentos
# ---------------------------------------------------------------------------
for arg in "$@"; do
  case "$arg" in
    --sem-abrir) ABRIR=0 ;;
    --com-ollama) COM_OLLAMA=1 ;;
    -h|--help)
      echo "Uso: $0 [--sem-abrir] [--com-ollama]"
      exit 0
      ;;
    *)
      echo "Opção desconhecida: $arg" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { printf '\n==> %s\n' "$*"; }
ok()   { printf '    ✓ %s\n' "$*"; }
warn() { printf '    ! %s\n' "$*" >&2; }

precisa_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 não encontrado. Instale python3 (>= 3.10)." >&2
    exit 1
  fi
  local maj min
  maj="$(python3 -c 'import sys; print(sys.version_info.major)')"
  min="$(python3 -c 'import sys; print(sys.version_info.minor)')"
  if (( maj < 3 || (maj == 3 && min < 10) )); then
    echo "Precisa de Python >= 3.10 (achou ${maj}.${min})." >&2
    exit 1
  fi
  ok "Python $(python3 -V | awk '{print $2}')"
}

cria_venv() {
  log "Ambiente virtual"
  if [[ ! -d "$VENV" ]]; then
    python3 -m venv "$VENV"
    ok "Criado $VENV"
  else
    ok "Já existe $VENV"
  fi
}

instala_pacote() {
  log "Instalando Xhat (editável)"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  python -m pip install --upgrade pip -q
  python -m pip install -e "$ROOT" -q
  ok "pip install -e . concluído"
}

garante_bin_dir() {
  mkdir -p "$BIN_DIR"
}

linka_comando() {
  local nome="$1"
  local alvo="$VENV/bin/$nome"
  local link="$BIN_DIR/$nome"

  if [[ ! -x "$alvo" ]]; then
    echo "Entrada não encontrada: $alvo" >&2
    exit 1
  fi

  ln -sfn "$alvo" "$link"
  ok "$link → $alvo"
}

# Inclui ~/.local/bin no PATH das shells comuns (idempotente).
configura_path() {
  log "PATH (~/.local/bin)"
  local linha='export PATH="$HOME/.local/bin:$PATH"'
  local rc

  for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    [[ -f "$rc" ]] || continue
    if grep -Fq '.local/bin' "$rc" 2>/dev/null; then
      ok "Já referenciado em $rc"
    else
      printf '\n# Xhat — comando no terminal\n%s\n' "$linha" >> "$rc"
      ok "Adicionado em $rc"
    fi
  done

  # Sessão atual
  export PATH="$BIN_DIR:$PATH"
  hash -r 2>/dev/null || true
}

opcional_ollama() {
  [[ "$COM_OLLAMA" -eq 1 ]] || return 0
  log "Ollama (modelos)"
  if ! command -v ollama >/dev/null 2>&1; then
    warn "ollama não está no PATH — pule ou instale: https://ollama.com"
    return 0
  fi
  ollama pull qwen3.5:4b
  ollama pull qwen2.5-coder:7b
  ok "Modelos baixados"
}

abre_xhat() {
  [[ "$ABRIR" -eq 1 ]] || return 0
  log "Abrindo Xhat"
  if command -v Xhat >/dev/null 2>&1; then
    exec Xhat
  else
    exec "$VENV/bin/Xhat"
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  echo "Xhat — instalação automática"
  echo "Pasta: $ROOT"

  precisa_python
  cria_venv
  instala_pacote
  garante_bin_dir
  linka_comando Xhat
  linka_comando xhat
  configura_path
  opcional_ollama

  echo
  echo "Pronto. Em um terminal novo:"
  echo "  Xhat"
  echo
  echo "Se 'Xhat' não for encontrado nesta sessão:"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  echo "  Xhat"

  abre_xhat
}

main
