#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${VERSION:-0.1.0~preview2}"
PACKAGE="rime-llm-translator"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
mkdir -p "$ROOT/DEBIAN" "$ROOT/usr/bin" \
 "$ROOT/usr/share/rime-llm-translator" \
 "$ROOT/usr/lib/systemd/user" dist
install -m 0755 src/rime_llm_translator.py "$ROOT/usr/bin/rime-llm-translator"
install -m 0644 lua/rime_llm_translator.lua \
 "$ROOT/usr/share/rime-llm-translator/rime_llm_translator.lua"
install -m 0644 packaging/rime-llm-translator.service \
 "$ROOT/usr/lib/systemd/user/rime-llm-translator.service"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Maintainer: LE-saber <noreply@github.com>
Depends: python3 (>= 3.10), python3-yaml, ibus-rime, librime-plugin-lua, rime-data-luna-pinyin
Description: Multilingual AI translation candidates for IBus Rime
 A user-scoped background worker with OpenAI-compatible API support.
 Run 'rime-llm-translator setup' after package installation.
EOF
dpkg-deb --build --root-owner-group "$ROOT" "dist/${PACKAGE}_${VERSION}_all.deb"
dpkg-deb --info "dist/${PACKAGE}_${VERSION}_all.deb"
