#!/usr/bin/env python3
"""P3 基准：提交一次生成，记录墙钟耗时与产物。"""
import json, sys, time, urllib.request, urllib.error, argparse, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_wf import build

API = "http://127.0.0.1:8188"

def post(path, payload):
    req = urllib.request.Request(API+path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type":"application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print("!! HTTP %d\n%s" % (e.code, body[:3000]))
        sys.exit(1)

def get(path):
    return json.load(urllib.request.urlopen(API+path, timeout=60))

ap = argparse.ArgumentParser()
ap.add_argument("--seconds", type=float, default=2.0)
ap.add_argument("--megapixels", type=float, default=0.4)
ap.add_argument("--aspect", default="16:9 (Widescreen)")
ap.add_argument("--steps", type=int, default=8)
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--prompt", default=(
    "A cheerful cartoon fox in a sunlit forest clearing, hand-drawn 2D animation style, "
    "warm autumn palette. The fox looks up, ears twitching, then breaks into a wide smile. "
    "Camera slowly pushes in. Gentle acoustic guitar, soft birdsong, leaves rustling."))
ap.add_argument("--prefix", default="video/bench")
a = ap.parse_args()

wf, length = build(a.prompt, a.seconds, a.megapixels, a.aspect, a.steps, a.seed, a.prefix)
print("=== 基准配置 ===")
print("  时长 %.1fs -> %d 帧 | %s @ %.2f MP | %d 步 | seed=%d | 8step turbo LoRA"
      % (a.seconds, length, a.aspect, a.megapixels, a.steps, a.seed))

t0 = time.time()
r = post("/prompt", {"prompt": wf})
pid = r["prompt_id"]
print("  prompt_id:", pid)
print("=== 运行中 ===")

last = ""
while True:
    time.sleep(5)
    h = get("/history/"+pid)
    if pid in h:
        break
    try:
        q = get("/queue")
        run = len(q.get("queue_running", []))
        pend = len(q.get("queue_pending", []))
        el = time.time()-t0
        cur = "  %5.0fs  running=%d pending=%d" % (el, run, pend)
        if cur[8:] != last[8:]:
            print(cur, flush=True)
        last = cur
        if run == 0 and pend == 0:
            time.sleep(3)
            h = get("/history/"+pid)
            if pid in h: break
            print("  !! 队列已空但无历史记录，可能崩溃，检查 logs/comfyui.log"); sys.exit(2)
    except Exception as e:
        print("  轮询异常:", e)

dt = time.time()-t0
rec = h[pid]
status = rec.get("status", {})
print("=== 完成 ===")
print("  状态      :", status.get("status_str"), "| completed:", status.get("completed"))
print("  总耗时    : %.1f 秒 (%.1f 分钟)" % (dt, dt/60))
print("  每步均摊  : %.1f 秒/步  (含模型加载)" % (dt/a.steps))
outs = rec.get("outputs", {})
for nid, o in outs.items():
    for k, v in o.items():
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and "filename" in item:
                    print("  产物      : %s/%s" % (item.get("subfolder",""), item["filename"]))
if status.get("status_str") != "success":
    print(json.dumps(status, ensure_ascii=False, indent=1)[:2000])
