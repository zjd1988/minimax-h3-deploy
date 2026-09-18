#!/usr/bin/env bash
export PATH=/root/miniconda3/bin:$PATH
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "=== 重装配套的 torch 三件套 $(date) ==="
uv pip install --python env/bin/python --reinstall \
  "torch==2.9.1+cu130" "torchvision==0.24.1+cu130" "torchaudio==2.9.1+cu130" \
  --index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu130/ \
  --extra-index-url https://mirrors.aliyun.com/pypi/simple/ \
  --index-strategy unsafe-best-match
echo "=== 退出码 $? / $(date) ==="
