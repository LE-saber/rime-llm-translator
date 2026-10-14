#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${VERSION:-0.2.0~preview4}"
PACKAGE="rime-llm-translator"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
mkdir -p "$ROOT/DEBIAN" "$ROOT/usr/bin" \
 "$ROOT/usr/share/rime-llm-translator" \
 "$ROOT/usr/lib/systemd/user" dist
install -m 0755 src/rime_llm_translator.py "$ROOT/usr/bin/rime-llm-translator"
install -m 0644 lua/rime_llm_translator.lua \
 "$ROOT/usr/share/rime-llm-translator/rime_llm_translator.lua"
install -m 0644 lua/rime_llm_ai_hotkey.lua \
 "$ROOT/usr/share/rime-llm-translator/rime_llm_ai_hotkey.lua"
install -m 0644 packaging/rime-llm-translator.service \
 "$ROOT/usr/lib/systemd/user/rime-llm-translator.service"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Maintainer: LE-saber <noreply@github.com>
Depends: python3 (>= 3.10), python3-yaml, python3-venv, ibus-rime, librime-plugin-lua, rime-data-luna-pinyin
Description: Offline machine translation and optional AI candidates for IBus Rime
 Offline Argos Translate via a user virtualenv; optional manual AI correction.
 Run 'rime-llm-translator setup' after package installation.
EOF
dpkg-deb --build --root-owner-group "$ROOT" "dist/${PACKAGE}_${VERSION}_all.deb"
dpkg-deb --info "dist/${PACKAGE}_${VERSION}_all.deb"
