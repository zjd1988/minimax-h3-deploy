#!/usr/bin/env python3
"""Multi-connection downloader for a URL list -> /workspace/wheels/."""
import os, sys, urllib.request
import concurrent.futures as cf

CHUNK = 32 * 2**20
CONN = 16
OUT = "/workspace/wheels/"

def probe_size(url):
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return int(r.headers["Content-Range"].split("/")[-1])

def fetch_range(url, start, end, part):
    total = end - start + 1
    for _ in range(20):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if have >= total:
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
            pass
    raise RuntimeError(f"part incomplete {part}")

def download(url):
    name = url.rsplit("/", 1)[-1]
    dst = os.path.join(OUT, name)
    if os.path.exists(dst):
        try:
            if os.path.getsize(dst) == probe_size(url):
                print("SKIP", name, flush=True)
                return
        except Exception:
            pass
        os.remove(dst)
    size = probe_size(url)
    nparts = -(-size // CHUNK)  # ceil: cover the tail
    bounds = [(i * CHUNK, min(size, (i + 1) * CHUNK) - 1) for i in range(nparts)]
    partnames = [f"{dst}.part{i:04d}" for i in range(nparts)]
    with cf.ThreadPoolExecutor(CONN) as ex:
        list(ex.map(lambda t: fetch_range(url, t[0], t[1], t[2]),
                    [(s, e, p) for (s, e), p in zip(bounds, partnames)]))
    with open(dst, "wb") as out:
        for p in partnames:
            with open(p, "rb") as f:
                while True:
                    b = f.read(2**20)
                    if not b:
                        break
                    out.write(b)
            os.remove(p)
    if os.path.getsize(dst) != size:
        os.remove(dst)
        raise RuntimeError(f"size mismatch {name}")
    print(f"OK {name} {size}", flush=True)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    urls = [l.strip() for l in open(sys.argv[1]) if l.strip()]
    for u in urls:
        for a in range(3):
            try:
                download(u)
                break
            except Exception as e:
                print(f"RETRY{a} {u}: {e}", flush=True)
        else:
            print("FAILED", u, flush=True)
            sys.exit(1)
    print("ALL_DONE", flush=True)
