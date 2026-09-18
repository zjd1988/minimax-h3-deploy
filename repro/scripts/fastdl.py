#!/usr/bin/env python3
"""Multi-connection ranged downloader for ModelScope files, with resume + sha256 verify."""
import os, sys, hashlib, concurrent.futures as cf
import urllib.request

BASE = "https://www.modelscope.cn/models/Comfy-Org/MiniMax-H3/resolve/master/"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../models/")
CHUNK = 32 * 2**20
CONN = 16

def head_size(url):
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        cr = r.headers["Content-Range"]  # bytes 0-0/TOTAL
        return int(cr.split("/")[-1])

def fetch_range(url, start, end, path, part):
    total = end - start + 1
    for _ in range(20):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if have >= total:
            if have > total:
                raise RuntimeError(f"part oversize {part}")
            return
        s = start + have
        req = urllib.request.Request(url, headers={"Range": f"bytes={s}-{end}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(part, "ab") as f:
                while True:
                    b = r.read(2**20)
                    if not b:
                        break
                    f.write(b)
        except Exception:
            pass  # loop and resume
    have = os.path.getsize(part) if os.path.exists(part) else 0
    if have < total:
        raise RuntimeError(f"part incomplete {part}: {have}/{total}")

def download(rel, sha=None):
    url = BASE + rel
    dst = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        if sha and sha256(dst) == sha:
            print(f"SKIP(done) {rel}", flush=True)
            return
        os.remove(dst)
    size = head_size(url)
    nparts = -(-size // CHUNK)  # ceil: must cover the tail!
    bounds = [(i * CHUNK, min(size, (i + 1) * CHUNK) - 1) for i in range(nparts)]
    for i in range(nparts):
        part = f"{dst}.part{i:04d}"
        if os.path.exists(part) and os.path.getsize(part) > bounds[i][1] - bounds[i][0] + 1:
            os.remove(part)  # stale part from old buggy run
    with cf.ThreadPoolExecutor(CONN) as ex:
        futs = []
        for i, (s, e) in enumerate(bounds):
            part = f"{dst}.part{i:04d}"
            futs.append(ex.submit(fetch_range, url, s, e, dst, part))
        for f in futs:
            f.result()
    # assemble
    with open(dst, "wb") as out:
        for i in range(nparts):
            part = f"{dst}.part{i:04d}"
            with open(part, "rb") as p:
                while True:
                    b = p.read(2**20)
                    if not b:
                        break
                    out.write(b)
            os.remove(part)
    if os.path.getsize(dst) != size:
        print(f"SIZE_MISMATCH {rel} {os.path.getsize(dst)} != {size}", flush=True)
        os.remove(dst)
        raise RuntimeError("size mismatch")
    if sha:
        got = sha256(dst)
        print(f"{'OK' if got == sha else 'SHA_MISMATCH'} {rel}", flush=True)
    else:
        print(f"OK {rel}", flush=True)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(4 * 2**20), b""):
            h.update(b)
    return h.hexdigest()

if __name__ == "__main__":
    import json
    files = json.load(open(os.path.join(os.path.dirname(__file__), "../scripts/models.json")))
    for it in files:
        for attempt in range(3):
            try:
                download(it["path"], it["sha256"])
                break
            except Exception as e:
                print(f"RETRY{attempt} {it['path']}: {e}", flush=True)
        else:
            print(f"FAILED {it['path']}", flush=True)
            sys.exit(1)
    print("ALL_DONE", flush=True)
