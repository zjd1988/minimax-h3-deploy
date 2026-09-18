#!/usr/bin/env bash
# 服务管理：本容器 PID1 是平台的 supervisord，没有 systemd，
# 且 supervisord.conf 无 [include] 段——改它有搞挂 sshd/code-server 的风险，
# 所以用 nohup + pidfile 自己管。scripts/*.service 是迁到真实 VM 时的参考。
set -uo pipefail
P="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$P/repro/tools/bin:$PATH"
RUN=$P/logs
mkdir -p "$RUN"

# 进程匹配模式（方括号防止 pgrep 匹配到自己的命令行）
pat_comfyui='ComfyUI/mai[n].py'
pat_pipeline='pipeline[.]py --watch'

svc_pid() {  # $1=名字
  local f="$RUN/$1.pid" pid
  # 先看 pidfile
  if [ -f "$f" ]; then
    pid=$(cat "$f" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then echo "$pid"; return 0; fi
  fi
  # pidfile 缺失或失效时，回落到进程匹配——
  # 手工 nohup 起的进程没有 pidfile，不认领的话 status 会误报"已停止"
  local pat; eval "pat=\$pat_$1"
  pid=$(pgrep -f "$pat" 2>/dev/null | head -1)
  if [ -n "$pid" ]; then
    echo "$pid" > "$f"          # 认领，后续 stop 才管得了它
    echo "$pid"; return 0
  fi
  rm -f "$f"
  return 1
}

start_comfyui() {
  if svc_pid comfyui >/dev/null; then echo "comfyui 已在运行 (pid $(svc_pid comfyui))"; return 0; fi
  nohup bash "$P/scripts/start_comfyui.sh" >> "$P/logs/comfyui.log" 2>&1 &
  echo $! > "$RUN/comfyui.pid"
  echo "comfyui 已启动 (pid $!)，等待 API..."
  for i in $(seq 1 90); do
    curl -s -m 3 http://127.0.0.1:8188/system_stats >/dev/null 2>&1 && { echo "  API 就绪 (~$((i*5))s)"; return 0; }
    sleep 5
  done
  echo "  !! 90 次轮询后 API 仍未就绪，查 logs/comfyui.log"; return 1
}

start_pipeline() {
  if svc_pid pipeline >/dev/null; then echo "pipeline 已在运行 (pid $(svc_pid pipeline))"; return 0; fi
  nohup /root/miniconda3/bin/python "$P/driver/pipeline.py" --watch >> "$P/logs/pipeline.log" 2>&1 &
  echo $! > "$RUN/pipeline.pid"
  echo "pipeline watch 已启动 (pid $!)"
}

stop_svc() {
  local pid; pid=$(svc_pid "$1")
  if [ -z "$pid" ]; then echo "$1 未在运行"; rm -f "$RUN/$1.pid"; return 0; fi
  kill "$pid" 2>/dev/null
  for i in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  kill -9 "$pid" 2>/dev/null
  rm -f "$RUN/$1.pid"
  echo "$1 已停止"
}

status() {
  for s in comfyui pipeline; do
    local pid; pid=$(svc_pid "$s")
    if [ -n "$pid" ]; then printf "  %-10s 运行中 pid=%s\n" "$s" "$pid"
    else                   printf "  %-10s 已停止\n" "$s"; fi
  done
  printf "  %-10s " "API"
  curl -s -m 5 http://127.0.0.1:8188/system_stats >/dev/null 2>&1 && echo "可达" || echo "不可达"
  printf "  %-10s %s\n" "GPU" "$(nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader 2>/dev/null)"
}

case "${1:-status}" in
  start)    start_comfyui && start_pipeline ;;
  stop)     stop_svc pipeline; stop_svc comfyui ;;
  restart)  stop_svc pipeline; stop_svc comfyui; sleep 3; start_comfyui && start_pipeline ;;
  start-comfyui)  start_comfyui ;;
  start-pipeline) start_pipeline ;;
  stop-pipeline)  stop_svc pipeline ;;
  status)   status ;;
  *) echo "用法: svc.sh {start|stop|restart|status|start-comfyui|start-pipeline|stop-pipeline}"; exit 1 ;;
esac
