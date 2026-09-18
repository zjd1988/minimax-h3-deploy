#!/usr/bin/env bash
# 本地编译 SageAttention 2.2.0（GitHub releases 的预编译 wheel 在本机不可达）
set -uo pipefail
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$P/repro/tools/bin:$P/env/bin:$PATH"
export CUDA_HOME=/usr/local/cuda
export TORCH_CUDA_ARCH_LIST=8.6     # 3090 (Ampere sm_86)
export MAX_JOBS=12                   # 容器只有 20 核在线，留余量
export EXT_PARALLEL=4
export NVCC_APPEND_FLAGS="--threads 4"

cd "$P/build_sage"
echo "=== 开始编译 $(date) ==="
echo "  TORCH_CUDA_ARCH_LIST=$TORCH_CUDA_ARCH_LIST  MAX_JOBS=$MAX_JOBS"
time uv pip install --python "$P/env/bin/python" \
     --no-build-isolation . 2>&1
echo "=== 编译退出码 $? / $(date) ==="
