#!/usr/bin/env python3
"""动画分镜流水线编排器。

一个 job 描述一整条片子（多个镜头），本脚本负责：
  1. 逐镜头构建工作流并提交给 ComfyUI
  2. **拿到 prompt_id 立刻写 manifest**，这是幂等恢复的关键
  3. 轮询完成、取回产物、把上一镜头喂给下一镜头做 AddGuide 衔接
  4. 全部完成后 ffmpeg concat 成片

重启后重跑同一个 job：已有 prompt_id 的镜头只查状态，绝不重复提交
（一个 10 秒镜头要烧 3.4 分钟 GPU，重复提交是纯浪费）。

用法：
  pipeline.py --job jobs/fox_ep01.json          # 跑一个 job
  pipeline.py --watch                            # 常驻，扫 jobs/ 目录
  pipeline.py --job ... --dry-run                # 只校验不生成
"""
import argparse, json, os, shutil, subprocess, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wf as WF

ROOT = os.environ.get("VIDEO_PIPELINE_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API = "http://127.0.0.1:8188"
INPUT_DIR = os.path.join(ROOT, "ComfyUI", "input")
OUT_DIR = os.path.join(ROOT, "outputs")
JOBS_DIR = os.path.join(ROOT, "jobs")
REL_DIR = os.path.join(ROOT, "releases")


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


# ---------- ComfyUI API ----------

def api_post(path, payload):
    req = urllib.request.Request(API + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


def api_get(path):
    return json.load(urllib.request.urlopen(API + path, timeout=60))


def wait_server(timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            api_get("/system_stats"); return True
        except Exception:
            time.sleep(5)
    return False


def history_output(pid):
    """返回该 prompt_id 的产物相对路径，未完成返回 None。"""
    try:
        h = api_get("/history/" + pid)
    except Exception:
        return None
    if pid not in h:
        return None
    rec = h[pid]
    if rec.get("status", {}).get("status_str") != "success":
        return None
    for _, o in rec.get("outputs", {}).items():
        for _, v in o.items():
            if isinstance(v, list):
                for it in v:
                    if isinstance(it, dict) and "filename" in it:
                        sub = it.get("subfolder", "")
                        return os.path.join(sub, it["filename"]) if sub else it["filename"]
    return None


def queue_idle():
    try:
        q = api_get("/queue")
        return not q.get("queue_running") and not q.get("queue_pending")
    except Exception:
        return False


# ---------- manifest ----------

def compose_prompt(job, shot):
    """拼接风格前缀 + 镜头提示词 + 风格后缀。

    实测跨镜头会漂景别、色温、线条粗细（见 PIPELINE.md），AddGuide 只锚开头几帧
    管不住。把风格描述固定拼进每一条 prompt 是最省事的治法。
    单个镜头可用 "style"/"style_suffix" 覆盖，设成 "" 则该镜头不加。
    """
    pre = shot.get("style", job.get("style", ""))
    suf = shot.get("style_suffix", job.get("style_suffix", ""))
    parts = [x.strip() for x in (pre, shot["prompt"], suf) if x and x.strip()]
    return " ".join(parts)


def manifest_path(job_id):
    return os.path.join(JOBS_DIR, job_id + ".manifest.json")


def load_manifest(job_id):
    p = manifest_path(job_id)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"job_id": job_id, "shots": {}, "created": time.time()}


def save_manifest(m):
    p = manifest_path(m["job_id"])
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)          # 原子替换，防止半截文件


# ---------- 工具 ----------

def probe_frames(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames",
                        "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.strip().split(",")[0])
    except Exception:
        return None


def stage_to_input(src):
    """把上一镜头产物复制进 ComfyUI/input/，LoadVideo 只认这个目录。"""
    dst_name = os.path.basename(src)
    dst = os.path.join(INPUT_DIR, dst_name)
    if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
        shutil.copy2(src, dst)
    return dst_name


# ---------- 主流程 ----------

def run_shot(job, shot, idx, manifest, prev_rel, dry_run=False, retries=2):
    name = shot.get("name") or ("s%02d" % (idx + 1))
    d = dict(job.get("defaults", {}))
    d.update(shot)
    rec = manifest["shots"].get(name, {})

    # --- 幂等：已完成直接返回 ---
    if rec.get("output") and os.path.exists(os.path.join(OUT_DIR, rec["output"])):
        log("  %s 已完成，跳过（%s）" % (name, rec["output"]))
        return rec["output"]

    # --- 幂等：已提交但未取回，只查状态不重提 ---
    if rec.get("prompt_id"):
        log("  %s 已提交过 (prompt_id=%s)，查状态而非重新提交" % (name, rec["prompt_id"]))
        out = poll(rec["prompt_id"], name)
        if out:
            rec["output"] = out; rec["finished"] = time.time()
            manifest["shots"][name] = rec; save_manifest(manifest)
            return out
        log("  %s 之前的提交没有产物，重新提交" % name)

    kind = d.get("kind") or ("r2v" if idx == 0 else "cont")
    prefix = "%s/%s_%s" % (job["id"], job["id"], name)

    kwargs = dict(
        kind=kind, prompt=compose_prompt(job, d),
        seconds=d.get("seconds", 10.0), megapixels=d.get("megapixels", 0.98),
        aspect=d.get("aspect", "9:16 (Portrait Widescreen)"),
        steps=d.get("steps"), seed=d.get("seed", 1000 + idx),
        ref_images=d.get("refs", job.get("refs", [])),
        ref_image_size=d.get("ref_size", "max"),
        guide_frames=d.get("guide_frames", 22),
        guide_audio=d.get("guide_audio", True),
        prefix=prefix,
    )
    if kind == "cont":
        if dry_run:
            # dry-run 时上游还没产物，用占位值让图能构建出来做结构校验
            kwargs["prev_video"] = "__dryrun__.mp4"
            kwargs["prev_frames"] = WF.frames_for(d.get("seconds", 10.0))
        elif prev_rel:
            prev_abs = os.path.join(OUT_DIR, prev_rel)
            kwargs["prev_video"] = stage_to_input(prev_abs)
            kwargs["prev_frames"] = probe_frames(prev_abs)
        else:
            raise RuntimeError("%s 是衔接镜头但没有上一镜头产物" % name)

    graph, length = WF.build(**kwargs)
    log("  %s: kind=%s %.1fs->%d帧 steps=%s seed=%s%s"
        % (name, kind, kwargs["seconds"], length, kwargs["steps"] or WF.DEFAULT_STEPS[kind],
           kwargs["seed"], (" guide<-%s" % kwargs.get("prev_video")) if kind == "cont" else ""))
    if dry_run:
        return None

    attempts = rec.get("attempts", 0)
    last_err = None
    for attempt in range(1, retries + 2):
        try:
            r = api_post("/prompt", {"prompt": graph})
        except Exception as e:
            last_err = "提交失败: %s" % e
            log("  %s 第 %d 次尝试 %s" % (name, attempt, last_err))
            time.sleep(min(30 * attempt, 120)); continue
        pid = r["prompt_id"]
        # ★ 立刻落盘，之后崩溃也不会重复提交
        attempts += 1
        rec = {"prompt_id": pid, "kind": kind, "submitted": time.time(),
               "seed": kwargs["seed"], "length": length, "attempts": attempts}
        manifest["shots"][name] = rec
        save_manifest(manifest)
        log("  %s 已提交 prompt_id=%s（第 %d/%d 次尝试）"
            % (name, pid, attempt, retries + 1))

        out = poll(pid, name)
        if out:
            rec["output"] = out; rec["finished"] = time.time()
            rec["elapsed"] = round(rec["finished"] - rec["submitted"], 1)
            manifest["shots"][name] = rec
            save_manifest(manifest)
            log("  %s 完成，用时 %.1f 分钟 -> %s" % (name, rec["elapsed"] / 60, out))
            return out

        last_err = "生成无产物（prompt_id=%s）" % pid
        # 清掉失败的 prompt_id，否则下次重跑会误判"已提交过"而只查状态
        rec.pop("prompt_id", None)
        rec["last_error"] = last_err
        manifest["shots"][name] = rec
        save_manifest(manifest)
        if attempt <= retries:
            wait = min(20 * attempt, 90)
            log("  %s %s，%d 秒后重试" % (name, last_err, wait))
            time.sleep(wait)
    raise RuntimeError("%s 重试 %d 次仍失败：%s（查 logs/comfyui.log）"
                       % (name, retries, last_err))


def poll(pid, name, idle_grace=3):
    """轮询直到有产物。队列空且历史无记录则判定失败。"""
    misses = 0
    while True:
        out = history_output(pid)
        if out:
            return out
        if queue_idle():
            misses += 1
            if misses >= idle_grace:
                return None
        else:
            misses = 0
        time.sleep(8)


def concat(job, outputs):
    if len(outputs) < 2:
        return None
    os.makedirs(REL_DIR, exist_ok=True)
    lst = os.path.join(REL_DIR, "%s_concat.txt" % job["id"])
    with open(lst, "w") as f:
        for rel in outputs:
            f.write("file %s\n" % os.path.join(OUT_DIR, rel))
    dst = os.path.join(REL_DIR, "%s.mp4" % job["id"])
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat",
                        "-safe", "0", "-i", lst, "-c", "copy", dst],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log("  拼接失败: %s" % r.stderr[:400]); return None
    os.remove(lst)
    return dst


def shot_names(job):
    return [(s.get("name") or ("s%02d" % (i + 1))) for i, s in enumerate(job["shots"])]


def invalidate(job, manifest, redo, cascade=True):
    """清掉指定镜头的 manifest 记录，使其重新生成。

    默认级联：重做 s02 后，s03/s04 是基于**旧的** s02 用 AddGuide 接出来的，
    不一起失效就会出现衔接对不上的成片。--no-cascade 可关掉。
    """
    names = shot_names(job)
    if "all" in redo:
        targets = set(names)
    else:
        unknown = [r for r in redo if r not in names]
        if unknown:
            raise SystemExit("!! 未知镜头名 %s，可用：%s" % (unknown, ", ".join(names)))
        idxs = [names.index(r) for r in redo]
        targets = set(names[min(idxs):]) if cascade else set(redo)
    dropped = [n for n in names if n in targets and n in manifest["shots"]]
    for n in dropped:
        del manifest["shots"][n]
    manifest.pop("release", None)   # 成片也失效，需重新拼接
    save_manifest(manifest)
    if dropped:
        log("已失效镜头：%s%s" % (", ".join(dropped), "（含下游级联）" if cascade else ""))
    else:
        log("指定镜头本来就没有记录，无需失效")


def run_job(path, dry_run=False, redo=None, cascade=True, retries=2):
    with open(path) as f:
        job = json.load(f)
    job.setdefault("id", os.path.splitext(os.path.basename(path))[0])
    log("=== job %s：%d 个镜头 ===" % (job["id"], len(job["shots"])))
    manifest = load_manifest(job["id"])
    manifest["job_file"] = path
    save_manifest(manifest)
    if redo:
        invalidate(job, manifest, redo, cascade)

    outputs, prev = [], None
    for i, shot in enumerate(job["shots"]):
        out = run_shot(job, shot, i, manifest, prev, dry_run, retries)
        if dry_run:
            prev = "__dryrun__.mp4"
            continue
        outputs.append(out); prev = out

    if dry_run:
        log("=== dry-run 校验通过 ==="); return
    if job.get("concat", True):
        dst = concat(job, outputs)
        if dst:
            manifest["release"] = dst; save_manifest(manifest)
            log("=== 成片：%s ===" % dst)
    total = sum(manifest["shots"][s].get("elapsed", 0) for s in manifest["shots"])
    log("=== job %s 完成，总 GPU 时间 %.1f 分钟 ===" % (job["id"], total / 60))


def watch(interval=20):
    log("watch 模式：监视 %s" % JOBS_DIR)
    while True:
        for fn in sorted(os.listdir(JOBS_DIR)):
            if not fn.endswith(".json") or fn.endswith(".manifest.json"):
                continue
            p = os.path.join(JOBS_DIR, fn)
            jid = os.path.splitext(fn)[0]
            m = load_manifest(jid)
            if m.get("release"):
                continue
            try:
                run_job(p)
            except Exception as e:
                log("!! job %s 出错：%s" % (jid, e))
        time.sleep(interval)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例：
  pipeline.py --job jobs/fox_ep01.json                跑（已完成的镜头自动跳过）
  pipeline.py --job jobs/fox_ep01.json --dry-run      只校验，不烧 GPU
  pipeline.py --job jobs/fox_ep01.json --redo s02     重做 s02 及其下游
  pipeline.py --job jobs/fox_ep01.json --redo s02 --no-cascade   只重做 s02
  pipeline.py --job jobs/fox_ep01.json --redo all     整条重做
  pipeline.py --watch                                 常驻，扫 jobs/ 目录""")
    ap.add_argument("--job")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redo", nargs="+", metavar="SHOT",
                    help="重做指定镜头（镜头名，或 all）。默认级联失效下游镜头。")
    ap.add_argument("--no-cascade", action="store_true",
                    help="配合 --redo：只重做指定镜头，不动下游（衔接可能对不上）")
    ap.add_argument("--retries", type=int, default=2,
                    help="单个镜头失败后的重试次数（默认 2）")
    a = ap.parse_args()
    os.makedirs(JOBS_DIR, exist_ok=True)
    if not wait_server():
        log("!! ComfyUI 未就绪"); sys.exit(1)
    if a.watch:
        watch()
    elif a.job:
        run_job(a.job, a.dry_run, a.redo, not a.no_cascade, a.retries)
    else:
        ap.error("需要 --job 或 --watch")
