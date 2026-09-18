#!/usr/bin/env python3
"""Ref2VA + AddGuide 续镜测试。"""
import json, sys, time, urllib.request, urllib.error, argparse, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_wf_cont import build
API = "http://127.0.0.1:8188"

def post(p, d):
    r = urllib.request.Request(API+p, data=json.dumps(d).encode(),
                               headers={"Content-Type":"application/json"})
    try: return json.load(urllib.request.urlopen(r, timeout=90))
    except urllib.error.HTTPError as e:
        print("!! HTTP %d\n%s" % (e.code, e.read().decode()[:3000])); sys.exit(1)

def get(p): return json.load(urllib.request.urlopen(API+p, timeout=60))

ap = argparse.ArgumentParser()
ap.add_argument("--refs", nargs="+", required=True)
ap.add_argument("--prev-video", required=True)
ap.add_argument("--prompt", required=True)
ap.add_argument("--seconds", type=float, default=10.0)
ap.add_argument("--steps", type=int, default=4)
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--guide-frames", type=int, default=22)
ap.add_argument("--prev-frames", type=int, default=243)
ap.add_argument("--no-audio", action="store_true")
ap.add_argument("--prefix", default="video/cont")
ap.add_argument("--validate-only", action="store_true")
a = ap.parse_args()

wf, length = build(a.prompt, a.refs, a.prev_video, a.seconds, 0.98,
                   "9:16 (Portrait Widescreen)", a.steps, a.seed, "max",
                   a.guide_frames, a.prev_frames, not a.no_audio, a.prefix)
print("=== 续镜配置 ===")
print("  上一镜头: %s (%d 帧) | 锚定尾部 %d 帧 @ frame_idx=0 | 音频锚定: %s"
      % (a.prev_video, a.prev_frames, a.guide_frames, "否" if a.no_audio else "是"))
print("  新镜头: %.1fs -> %d 帧 | 参考图 %s | %d 步 | seed=%d"
      % (a.seconds, length, ",".join(a.refs), a.steps, a.seed))

t0=time.time(); r=post("/prompt",{"prompt":wf}); pid=r["prompt_id"]
print("  prompt_id:", pid)
if a.validate_only: print("  ✅ 校验通过"); sys.exit(0)
print("=== 运行中 ===")
while True:
    time.sleep(6)
    h=get("/history/"+pid)
    if pid in h: break
    q=get("/queue")
    if not q.get("queue_running") and not q.get("queue_pending"):
        time.sleep(4); h=get("/history/"+pid)
        if pid in h: break
        print("  !! 队列空但无结果"); sys.exit(2)
dt=time.time()-t0; rec=h[pid]; st=rec.get("status",{})
print("=== 完成 ===")
print("  状态  :", st.get("status_str"))
print("  耗时  : %.1f 秒 (%.1f 分钟)" % (dt, dt/60))
for _,o in rec.get("outputs",{}).items():
    for k,v in o.items():
        if isinstance(v,list):
            for it in v:
                if isinstance(it,dict) and "filename" in it:
                    print("  产物  : %s/%s" % (it.get("subfolder",""), it["filename"]))
if st.get("status_str")!="success": print(json.dumps(st,ensure_ascii=False,indent=1)[:2500])
