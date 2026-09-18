#!/usr/bin/env bash
# 打包 git 仓库供 Mac 端推送到 GitHub。
# 本机连不上 github.com，只能走 bundle 中转，详见 docs/OPERATIONS.md。
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -n "$(git status --porcelain)" ]; then
  echo "!! 有未提交的改动，先 commit："
  git status --short
  exit 1
fi

OUT=/tmp/video-pipeline.bundle
BR=$(git rev-parse --abbrev-ref HEAD)
git bundle create "$OUT" --all
echo
echo "已生成 $OUT ($(du -h "$OUT" | cut -f1))"
echo "分支: $BR    最新提交: $(git log -1 --oneline)"
echo
echo "接下来在 Mac 上执行："
echo "  scp caoyang_lsem_dev01:$OUT /tmp/"
echo "  cd <本地克隆目录> && git pull /tmp/$(basename $OUT) $BR && git push"
