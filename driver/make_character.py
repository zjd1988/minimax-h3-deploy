#!/usr/bin/env python3
"""角色设定图生成器 —— 动画流水线的第 0 步。

Ref2VA 的身份保真度完全取决于参考图。实测（见 REF2VA.md）：
  · 场景截图当参考 → 参考场景被拖进新镜头开头约 2.5 秒
  · 干净背景设定图 → 场景不污染，身份照样保住
所以正确做法是先用 T2V 生成一段"角色转身展示"，再抽干净帧当设定图。

用法：
  make_character.py --name fox2 \
    --desc "a small round owl with huge amber eyes, cream chest, ..." \
    --frames 3
产物：assets/<name>_sheet_0.png ...，并自动复制进 ComfyUI/input/
"""
import argparse, json, os, subprocess, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wf as WF
from pipeline import api_post, api_get, poll, log, ROOT, OUT_DIR, INPUT_DIR, wait_server

ASSETS = os.path.join(ROOT, "assets")

# 转身展示的提示词骨架。要点：
#  · plain neutral background —— 这是整个设计的核心，别让场景进来
#  · 明确说 turnaround / front, side, back —— 一段视频里拿到多个角度
#  · static camera —— 镜头别动，抽帧才干净
TURNAROUND = (
    "Character reference sheet for 2D animation. {desc} "
    "The character stands centered on a completely plain flat light grey background, "
    "no scenery, no props, no floor, no shadow, full body visible head to toe. "
    "It slowly turns in place: front view, then three-quarter view, then side view, "
    "then back. Even flat studio lighting, static camera, no camera movement. "
    "Hand-drawn 2D animation, clean uniform black outlines, flat cel shading. Silent."
)


def extract_frames(video_abs, name, n, seconds):
    os.makedirs(ASSETS, exist_ok=True)
    # 跳过头尾，取中间均匀分布的 n 帧（开头常有起手动作，结尾可能糊）
    lo, hi = seconds * 0.15, seconds * 0.85
    times = [lo + (hi - lo) * i / max(1, n - 1) for i in range(n)] if n > 1 else [seconds / 2]
    out = []
    for i, t in enumerate(times):
        dst = os.path.join(ASSETS, "%s_sheet_%d.png" % (name, i))
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "%.2f" % t,
                            "-i", video_abs, "-vframes", "1", dst],
                           capture_output=True, text=True)
        if r.returncode != 0:
            log("  抽帧失败 t=%.1f: %s" % (t, r.stderr[:200])); continue
        subprocess.run(["cp", dst, INPUT_DIR], check=False)
        out.append(os.path.basename(dst))
        log("  t=%.1fs -> %s" % (t, os.path.basename(dst)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="角色代号，用作文件名前缀")
    ap.add_argument("--desc", required=True, help="角色外观描述（英文，越具体越稳）")
    ap.add_argument("--frames", type=int, default=3, help="抽几张设定图（Ref2VA 最多吃 9 张）")
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--aspect", default="9:16 (Portrait Widescreen)")
    a = ap.parse_args()

    if not wait_server():
        log("!! ComfyUI 未就绪"); sys.exit(1)

    prompt = TURNAROUND.format(desc=a.desc.strip().rstrip("."))
    graph, length = WF.build("t2v", prompt, seconds=a.seconds, megapixels=0.98,
                             aspect=a.aspect, steps=a.steps, seed=a.seed,
                             prefix="character/%s_turnaround" % a.name)
    log("=== 生成角色转身片 %s：%.1fs -> %d 帧, %d 步 ===" % (a.name, a.seconds, length, a.steps))
    pid = api_post("/prompt", {"prompt": graph})["prompt_id"]
    log("  prompt_id=%s" % pid)
    t0 = time.time()
    rel = poll(pid, a.name)
    if not rel:
        log("!! 生成失败，查 logs/comfyui.log"); sys.exit(2)
    log("  转身片完成，用时 %.1f 分钟 -> %s" % ((time.time() - t0) / 60, rel))

    log("=== 抽取 %d 张设定图 ===" % a.frames)
    sheets = extract_frames(os.path.join(OUT_DIR, rel), a.name, a.frames, a.seconds)

    meta = {"name": a.name, "desc": a.desc, "turnaround": rel,
            "sheets": sheets, "created": time.time()}
    with open(os.path.join(ASSETS, "%s.json" % a.name), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    log("=== 完成。job 里这样写： \"refs\": %s ===" % json.dumps(sheets))


if __name__ == "__main__":
    main()
