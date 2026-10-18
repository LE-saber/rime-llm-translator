#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
SOURCE="$PWD/.build/mozilla"
REVISION="$(cat native/mt/engine.lock)"
if [ ! -d "$SOURCE/.git" ]; then
  git clone --filter=blob:none --no-checkout https://github.com/mozilla/translations.git "$SOURCE"
fi
git -C "$SOURCE" checkout --detach "$REVISION"
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
