#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${VERSION:-0.3.0~preview5}"
ARCH="$(dpkg --print-architecture)"
PACKAGE="rime-llm-translator"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
mkdir -p "$ROOT/DEBIAN" "$ROOT/usr/bin" \
 "$ROOT/usr/share/rime-llm-translator" \
 "$ROOT/usr/lib/systemd/user" "$ROOT/usr/share/ibus/component" \
 "$ROOT/usr/libexec/rime-llm-translator" "$ROOT/usr/share/doc/$PACKAGE/frontend" dist
cc -std=gnu11 -O2 -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers \
 frontend/rime_main.c frontend/rime_engine.c frontend/rime_settings.c \
 $(pkg-config --cflags --libs ibus-1.0 libnotify rime) \
 -o "$ROOT/usr/libexec/rime-llm-translator/ibus-engine-rime-llm"
install -m 0644 packaging/rime-llm.xml "$ROOT/usr/share/ibus/component/rime-llm.xml"
install -m 0644 frontend/* "$ROOT/usr/share/doc/$PACKAGE/frontend/"
install -m 0755 src/rime_llm_translator.py "$ROOT/usr/bin/rime-llm-translator"
install -m 0644 lua/rime_llm_translator.lua \
 "$ROOT/usr/share/rime-llm-translator/rime_llm_translator.lua"
install -m 0644 lua/rime_llm_ai_hotkey.lua \
 "$ROOT/usr/share/rime-llm-translator/rime_llm_ai_hotkey.lua"
install -m 0644 packaging/rime-llm-translator.service \
 "$ROOT/usr/lib/systemd/user/rime-llm-translator.service"
install -m 0644 packaging/rime-llm-ai.service \
 "$ROOT/usr/lib/systemd/user/rime-llm-ai.service"
install -m 0644 README_CN.md README.md "$ROOT/usr/share/doc/$PACKAGE/"
install -m 0644 frontend/LICENSE "$ROOT/usr/share/doc/$PACKAGE/copyright"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: LE-saber <noreply@github.com>
Depends: python3 (>= 3.10), python3-yaml, python3-venv, ibus-rime, librime-plugin-lua, rime-data-luna-pinyin, libibus-1.0-5, librime1 (>= 1.10.0), libnotify4, libglib2.0-0t64, libc6 (>= 2.38)
Description: Offline machine translation and optional AI candidates for IBus Rime
 Offline Argos Translate via a user virtualenv; optional manual AI correction.
 Run 'rime-llm-translator setup' after package installation.
EOF
dpkg-deb --build --root-owner-group "$ROOT" "dist/${PACKAGE}_${VERSION}_${ARCH}.deb"
dpkg-deb --info "dist/${PACKAGE}_${VERSION}_${ARCH}.deb"
sha256sum "dist/${PACKAGE}_${VERSION}_${ARCH}.deb" > dist/SHA256SUMS
