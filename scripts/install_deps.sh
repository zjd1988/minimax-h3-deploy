#!/usr/bin/env bash
export PATH=/root/miniconda3/bin:$PATH
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "=== 开始安装 ComfyUI 依赖 $(date) ==="
uv pip install --python env/bin/python -r ComfyUI/requirements.txt \
  --index-url https://mirrors.aliyun.com/pypi/simple/
echo "=== 退出码 $? / $(date) ==="
