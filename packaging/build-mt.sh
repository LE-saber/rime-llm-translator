#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
SOURCE="$PWD/.build/mozilla"
REVISION="$(cat native/mt/engine.lock)"
if [ ! -d "$SOURCE/.git" ]; then
  git clone --filter=blob:none --no-checkout https://github.com/mozilla/translations.git "$SOURCE"
fi
git -C "$SOURCE" checkout --detach "$REVISION"
PATCH="$PWD/native/mt/low-memory.patch"
PATCH_HASH="$(sha256sum "$PATCH" | cut -d ' ' -f 1)"
PREVIOUS_PATCH="$(cat "$SOURCE/.rime-mt-patch" 2>/dev/null || true)"
if [ "$PREVIOUS_PATCH" != "$PATCH_HASH" ] || ! git -C "$SOURCE" apply --reverse --check "$PATCH" 2>/dev/null; then
  # Only generated third-party checkout files owned by this build patch.
  git -C "$SOURCE" restore --source="$REVISION" -- \
    inference/marian-fork/src/tensors/tensor_allocator.h \
    inference/src/translator/translation_model.h \
    inference/src/translator/translation_model.cpp
  git -C "$SOURCE" apply --check "$PATCH"
  git -C "$SOURCE" apply "$PATCH"
  printf '%s\n' "$PATCH_HASH" > "$SOURCE/.rime-mt-patch"
fi
# Only inference dependencies, never emsdk, training tools, CUDA or NCCL.
git -C "$SOURCE" submodule update --init --depth 1 \
  inference/3rd_party/ssplit-cpp \
  inference/marian-fork/src/3rd_party/sentencepiece \
  inference/marian-fork/src/3rd_party/intgemm \
  inference/marian-fork/src/3rd_party/simd_utils
cmake -S native/mt -B .build/mt -DCMAKE_BUILD_TYPE=Release -DMOZILLA_SOURCE="$SOURCE"
cmake --build .build/mt --target rime-mt --parallel 2
strip .build/mt/rime-mt
git -C "$SOURCE" submodule status > .build/mt/SOURCE_REVISIONS
ldd .build/mt/rime-mt
