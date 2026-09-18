#!/usr/bin/env python3
"""Ref2VA 基准与生成。"""
import json, sys, time, urllib.request, urllib.error, argparse, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_wf_r2v import build

API = "http://127.0.0.1:8188"

def post(path, payload):
    req = urllib.request.Request(API+path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type":"application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=90))
    except urllib.error.HTTPError as e:
        print("!! HTTP %d\n%s" % (e.code, e.read().decode()[:3000])); sys.exit(1)

def get(p): return json.load(urllib.request.urlopen(API+p, timeout=60))

ap = argparse.ArgumentParser()
ap.add_argument("--refs", nargs="+", required=True)
ap.add_argument("--prompt", required=True)
ap.add_argument("--seconds", type=float, default=10.0)
ap.add_argument("--megapixels", type=float, default=0.98)
ap.add_argument("--aspect", default="9:16 (Portrait Widescreen)")
ap.add_argument("--steps", type=int, default=4)
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--ref-size", default="max", choices=["match","max"])
ap.add_argument("--prefix", default="video/r2v")
ap.add_argument("--validate-only", action="store_true")
a = ap.parse_args()

wf, length = build(a.prompt, a.refs, a.seconds, a.megapixels, a.aspect,
                   a.steps, a.seed, a.ref_size, a.prefix)
print("=== Ref2VA 配置 ===")
print("  参考图 %d 张: %s" % (len(a.refs), ", ".join(a.refs)))
print("  %.1fs -> %d 帧 | %s @ %.2f MP | %d 步 | ref_image_size=%s | seed=%d"
      % (a.seconds, length, a.aspect, a.megapixels, a.steps, a.ref_size, a.seed))

t0 = time.time()
r = post("/prompt", {"prompt": wf})
pid = r["prompt_id"]
print("  prompt_id:", pid)
if a.validate_only:
    print("  ✅ 校验通过（已入队）"); sys.exit(0)
print("=== 运行中 ===")
while True:
    time.sleep(6)
    h = get("/history/"+pid)
    if pid in h: break
    q = get("/queue")
    if not q.get("queue_running") and not q.get("queue_pending"):
        time.sleep(4); h = get("/history/"+pid)
        if pid in h: break
        print("  !! 队列空但无结果，查 logs/comfyui.log"); sys.exit(2)

dt = time.time()-t0
rec = h[pid]; st = rec.get("status",{})
print("=== 完成 ===")
print("  状态    :", st.get("status_str"))
print("  总耗时  : %.1f 秒 (%.1f 分钟)" % (dt, dt/60))
for nid,o in rec.get("outputs",{}).items():
    for k,v in o.items():
        if isinstance(v,list):
            for it in v:
                if isinstance(it,dict) and "filename" in it:
                    print("  产物    : %s/%s" % (it.get("subfolder",""), it["filename"]))
if st.get("status_str") != "success":
    print(json.dumps(st, ensure_ascii=False, indent=1)[:2500])
