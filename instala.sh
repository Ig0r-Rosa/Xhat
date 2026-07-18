#!/usr/bin/env bash
# instala.sh — instala o Xhat e deixa o comando `Xhat` no terminal.
#
# Não usa .venv na pasta do projeto. O ambiente fica escondido em:
#   ~/.local/share/xhat/venv
#
# Uso:
#   ./instala.sh              # instala + tenta Ollama/modelos + abre
#   ./instala.sh --sem-abrir  # só instala
#   ./instala.sh --sem-ollama # não mexe no Ollama

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARE="${XDG_DATA_HOME:-$HOME/.local/share}/xhat"
VENV="$SHARE/venv"
BIN_DIR="${HOME}/.local/bin"
ABRIR=1
COM_OLLAMA=1

for arg in "$@"; do
  case "$arg" in
    --sem-abrir) ABRIR=0 ;;
    --sem-ollama) COM_OLLAMA=0 ;;
    -h|--help)
      echo "Uso: $0 [--sem-abrir] [--sem-ollama]"
      exit 0
      ;;
    *)
      echo "Opção desconhecida: $arg" >&2
      exit 1
      ;;
  esac
done

log()  { printf '\n==> %s\n' "$*"; }
ok()   { printf '    ✓ %s\n' "$*"; }
warn() { printf '    ! %s\n' "$*" >&2; }

# ---------------------------------------------------------------------------
precisa_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 não encontrado. Ex.: sudo apt install python3 python3-venv python3-pip" >&2
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

# Módulo venv (Debian costuma precisar de python3-venv).
garante_venv_mod() {
  if python3 -c 'import venv' 2>/dev/null; then
    ok "módulo venv ok"
    return 0
  fi
  warn "Falta python3-venv"
  if command -v apt-get >/dev/null 2>&1; then
    log "Tentando: sudo apt-get install -y python3-venv python3-pip"
    sudo apt-get install -y python3-venv python3-pip
  else
    echo "Instale o pacote do venv da sua distro e rode de novo." >&2
    exit 1
  fi
}

# Ambiente isolado FORA do projeto (você não precisa ativar).
cria_ambiente() {
  log "Ambiente em $VENV"
  mkdir -p "$SHARE"
  if [[ ! -d "$VENV" ]]; then
    python3 -m venv "$VENV"
    ok "Criado (escondido do projeto)"
  else
    ok "Já existia"
  fi
  # Remove .venv antigo na pasta do repo, se sobrou.
  if [[ -d "$ROOT/.venv" ]]; then
    rm -rf "$ROOT/.venv"
    ok "Removido .venv antigo do projeto"
  fi
}

instala_pacote() {
  log "Instalando Xhat"
  "$VENV/bin/python" -m pip install --upgrade pip -q
  "$VENV/bin/python" -m pip install -e "$ROOT" -q
  ok "Dependências + comando prontos"
}

garante_bin_dir() {
  mkdir -p "$BIN_DIR"
}

# Wrapper em ~/.local/bin — não depende de ativar venv.
instala_comandos() {
  log "Comandos no PATH"
  local nome alvo
  for nome in Xhat xhat; do
    alvo="$VENV/bin/$nome"
    if [[ ! -x "$alvo" ]]; then
      echo "Não achei $alvo após o pip install." >&2
      exit 1
    fi
    ln -sfn "$alvo" "$BIN_DIR/$nome"
    ok "$BIN_DIR/$nome"
  done
}

configura_path() {
  log "PATH (~/.local/bin)"
  local linha='export PATH="$HOME/.local/bin:$PATH"'
  local rc
  for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    [[ -f "$rc" ]] || continue
    if grep -Fq '.local/bin' "$rc" 2>/dev/null; then
      ok "Já ok em $rc"
    else
      printf '\n# Xhat\n%s\n' "$linha" >> "$rc"
      ok "Adicionado em $rc"
    fi
  done
  export PATH="$BIN_DIR:$PATH"
  hash -r 2>/dev/null || true
}

instala_ollama_se_preciso() {
  [[ "$COM_OLLAMA" -eq 1 ]] || return 0
  log "Ollama"
  if command -v ollama >/dev/null 2>&1; then
    ok "Já instalado"
  else
    warn "Ollama não encontrado — instalando (precisa de rede + sudo)"
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  if ! command -v ollama >/dev/null 2>&1; then
    warn "Ollama ainda não está no PATH. Abra um terminal novo e rode: ollama serve"
    return 0
  fi
  # Sobe o serviço se possível (não falha a instalação se der erro).
  if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    warn "Iniciando ollama serve em background…"
    nohup ollama serve >/dev/null 2>&1 &
    sleep 2
  fi
  ollama pull qwen3.5:4b
  ollama pull qwen2.5-coder:7b
  ok "Modelos baixados"
}

abre_xhat() {
  [[ "$ABRIR" -eq 1 ]] || return 0
  log "Abrindo Xhat"
  exec "$BIN_DIR/Xhat"
}

main() {
  echo "Xhat — instalação automática"
  echo "Projeto: $ROOT"

  precisa_python
  garante_venv_mod
  cria_ambiente
  instala_pacote
  garante_bin_dir
  instala_comandos
  configura_path
  instala_ollama_se_preciso

  echo
  echo "Pronto. Em qualquer terminal:"
  echo "  Xhat"
  echo
  echo "Se nesta sessão ainda não achar o comando:"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""

  abre_xhat
}

main
