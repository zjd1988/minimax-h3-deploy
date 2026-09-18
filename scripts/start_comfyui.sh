#!/usr/bin/env bash
# ComfyUI 启动脚本（3090 / 驱动 570 适配版）
#
# 与原机（4090D + 535 驱动 + CUDA13 前向兼容层）的差异：
# 1. 本机驱动 570.133.07，原生支持 CUDA 12.8，不需要 LD_LIBRARY_PATH 兼容层 hack。
# 2. torch 用 2.9.1+cu128（cu130 需要 >=580 驱动）。
# 3. --use-sage-attention 仅在 sageattention 可导入时启用（SageAttention 2.2.0
#    需按 sm_86 本地编译，见 scripts/build_sage.sh；未编译前走 PyTorch SDPA）。
set -euo pipefail
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$P/repro/tools/bin:$P/env/bin:$PATH"

SAGE_FLAG=""
if "$P/env/bin/python" -c "import sageattention" 2>/dev/null; then
  SAGE_FLAG="--use-sage-attention"
fi

# 3090 实测：243 帧 768x1344 默认模式会在 int8_linear 分配时 OOM。
# 1) --lowvram：dynamic VRAM loading 更激进地换出权重
# 2) expandable_segments：减少碎片导致的假性 OOM
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
exec "$P/env/bin/python" "$P/ComfyUI/main.py" \
  --listen 127.0.0.1 --port 8188 \
  --output-directory "$P/outputs" \
  --extra-model-paths-config "$P/extra_model_paths.yaml" \
  --novram \
  $SAGE_FLAG \
  "$@"
