#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${VERSION:-0.3.0~preview12}"
ARCH="$(dpkg --print-architecture)"
PACKAGE="rime-llm-translator"
bash packaging/build-mt.sh
python3 packaging/fetch-mt-models.py
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
mkdir -p "$ROOT/DEBIAN" "$ROOT/usr/bin" \
 "$ROOT/usr/share/rime-llm-translator" \
 "$ROOT/usr/lib/systemd/user" "$ROOT/usr/share/ibus/component" \
 "$ROOT/usr/libexec/rime-llm-translator" "$ROOT/usr/share/doc/$PACKAGE/frontend" dist
cc -std=gnu11 -O2 -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers \
 frontend/rime_main.c frontend/rime_engine.c frontend/rime_settings.c frontend/rime_panel.c \
 $(pkg-config --cflags --libs ibus-1.0 libnotify rime) \
 -o "$ROOT/usr/libexec/rime-llm-translator/ibus-engine-rime-llm"
install -m 0644 packaging/rime-llm.xml "$ROOT/usr/share/ibus/component/rime-llm.xml"
install -m 0644 frontend/* "$ROOT/usr/share/doc/$PACKAGE/frontend/"
install -m 0755 src/rime_llm_translator.py "$ROOT/usr/bin/rime-llm-translator"
install -m 0644 src/rime_mt.py "$ROOT/usr/share/rime-llm-translator/"
install -m 0644 src/rime_long_text.py src/rime_gui.py src/rime_shell.py src/rime_llm_translator.py "$ROOT/usr/share/rime-llm-translator/"
mkdir -p "$ROOT/usr/share/rime-llm-translator/gnome-extension"
install -m 0644 gnome-extension/* "$ROOT/usr/share/rime-llm-translator/gnome-extension/"
mkdir -p "$ROOT/usr/share/applications"
install -m 0644 packaging/rime-llm-settings.desktop "$ROOT/usr/share/applications/"
install -m 0755 .build/mt/rime-mt "$ROOT/usr/libexec/rime-llm-translator/"
install -m 0644 native/mt/models.lock.json "$ROOT/usr/share/rime-llm-translator/"
mkdir -p "$ROOT/usr/share/rime-llm-translator/models"
for DIRECTION in zh-en en-ja; do
  mkdir -p "$ROOT/usr/share/rime-llm-translator/models/$DIRECTION"
  find ".build/models/$DIRECTION" -maxdepth 1 -type f ! -name '*.gz' \
    -exec install -m 0644 '{}' "$ROOT/usr/share/rime-llm-translator/models/$DIRECTION/" \;
done
sha256sum .build/mt/rime-mt native/mt/models.lock.json native/mt/engine.lock native/mt/main.cpp \
  native/mt/CMakeLists.txt native/mt/low-memory.patch packaging/build-mt.sh packaging/fetch-mt-models.py \
  | sha256sum | cut -d ' ' -f 1 > "$ROOT/usr/share/rime-llm-translator/mt-revision"
# Complete corresponding third-party inference sources, including dependency
# license texts, pinned commits and the unmodified Mozilla license.
tar --exclude-vcs --exclude=inference/3rd_party/emsdk \
  -C .build/mozilla -cJf .build/mt/inference-source.tar.xz inference LICENSE .gitmodules
install -m 0644 .build/mt/inference-source.tar.xz .build/mt/SOURCE_REVISIONS \
  native/mt/engine.lock "$ROOT/usr/share/doc/$PACKAGE/"
mkdir -p "$ROOT/usr/share/doc/$PACKAGE/mt-wrapper"
install -m 0644 native/mt/main.cpp native/mt/CMakeLists.txt native/mt/low-memory.patch packaging/build-mt.sh \
  "$ROOT/usr/share/doc/$PACKAGE/mt-wrapper/"
install -m 0644 lua/rime_llm_translator.lua \
 "$ROOT/usr/share/rime-llm-translator/rime_llm_translator.lua"
install -m 0644 lua/rime_llm_ai_hotkey.lua \
 "$ROOT/usr/share/rime-llm-translator/rime_llm_ai_hotkey.lua"
install -m 0644 packaging/rime-llm-translator.service \
 "$ROOT/usr/lib/systemd/user/rime-llm-translator.service"
install -m 0644 packaging/rime-llm-ai.service \
 "$ROOT/usr/lib/systemd/user/rime-llm-ai.service"
install -m 0644 README_CN.md README.md docs/UPGRADE_CLEANUP.md docs/MANUAL_TEST.md docs/LONG_TEXT.md "$ROOT/usr/share/doc/$PACKAGE/"
install -m 0644 frontend/LICENSE "$ROOT/usr/share/doc/$PACKAGE/copyright"
INSTALLED_SIZE="$(du -sk "$ROOT/usr" | cut -f 1)"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Installed-Size: $INSTALLED_SIZE
Maintainer: LE-saber <noreply@github.com>
Depends: python3 (>= 3.11), python3-yaml, python3-gi, gir1.2-gtk-3.0, gir1.2-ibus-1.0, ibus-gtk3, ibus-rime, librime-plugin-lua, rime-data-luna-pinyin, rime-prelude, rime-essay, rime-data-stroke, libibus-1.0-5, librime1 (>= 1.10.0), libnotify4, libglib2.0-0t64, libc6 (>= 2.38), libstdc++6, libopencc1.1
Description: Offline machine translation and optional AI candidates for IBus Rime
 CPU-only native Bergamot with bundled Chinese-English-Japanese INT8 models.
 No pip installation or first-run model downloads. Optional manual AI correction.
 Run 'rime-llm-translator setup' after package installation.
EOF
dpkg-deb --build --root-owner-group "$ROOT" "dist/${PACKAGE}_${VERSION}_${ARCH}.deb"
dpkg-deb --info "dist/${PACKAGE}_${VERSION}_${ARCH}.deb"
(cd dist && sha256sum "${PACKAGE}_${VERSION}_${ARCH}.deb") > dist/SHA256SUMS
