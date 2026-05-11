#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate 1 Seedance 2.0 (doubao-seedance-1-0-pro) demo video for YN-BRA-001.

Supports both text-to-video and image-to-video (first-frame) modes.

Flow:
  1. POST task to ARK contents/generations/tasks (async)
  2. Poll GET task status every 10s until "succeeded" (90-180s typical)
  3. Extract video_url from response
  4. Download mp4 to OUT_PATH
  5. Print file size, elapsed time, task_id

Cost: ~12 RMB per video (12s x 1 RMB/s).
Timeout cap: 5 minutes total.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

API_KEY = os.environ.get("VIDEO_API_KEY") or os.environ.get("MEDIA_API_KEY") or os.environ.get("ARK_API_KEY", "")
if not API_KEY:
    print("❌ VIDEO_API_KEY/MEDIA_API_KEY/ARK_API_KEY 未设置。配置后重试"); sys.exit(1)
API_BASE = (os.environ.get("VIDEO_BASE_URL") or os.environ.get("MEDIA_BASE_URL") or os.environ.get("ARK_ENDPOINT") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
TASK_URL = f"{API_BASE}/contents/generations/tasks"
MODEL = os.environ.get("VIDEO_MODEL") or os.environ.get("ARK_VIDEO_MODEL") or "doubao-seedance-1-0-pro-250528"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT_PATH = os.path.join(os.path.dirname(_SCRIPT_DIR), "_demo_seed", "videos", "yn-bra-001-12s.mp4")

DEFAULT_PROMPT = (
    "12 second TikTok style sportswear advertisement: 4 cuts (3 sec each). "
    "Cut 1 (hook): asian woman 25-30 confidently pulling back hair, soft window light, "
    "wearing matte black sports bra with chrome front zipper. "
    "Cut 2: extreme close-up of fingers pulling chrome zipper down 3cm to reveal "
    "breathable mesh inner fabric. "
    "Cut 3: low-angle slow motion of jumping jacks showing high-elasticity fabric, "
    "no breast bounce, gym setting. "
    "Cut 4: face camera, zips up, slight confident smile, end frame on centered product reveal. "
    "Cinematic professional fashion photography, golden hour color grading. "
    "--resolution 720p --ratio 9:16 --duration 12 --fps 24 --watermark false"
)

MAX_TOTAL_SECS = 300   # hard 5-minute cap
POLL_INTERVAL = 10     # seconds


def http_json(url: str, method: str = "GET", body=None, timeout: int = 60):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def submit_task(prompt: str, image_url: str | None = None) -> str:
    """POST task. Return task id. If image_url provided, runs image-to-video."""
    content = [{"type": "text", "text": prompt}]
    if image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url}, "role": "first_frame"})
    body = {"model": MODEL, "content": content}
    mode = "image-to-video" if image_url else "text-to-video"
    print(f"[submit] POST {TASK_URL} ({mode})", flush=True)
    try:
        result = http_json(TASK_URL, method="POST", body=body, timeout=60)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"[submit] HTTP {e.code}: {err}", flush=True)
        raise
    task_id = result.get("id") or result.get("task_id") or (result.get("data") or {}).get("id")
    if not task_id:
        raise RuntimeError(f"no task id in response: {result}")
    print(f"[submit] task_id={task_id}", flush=True)
    return task_id


def find_video_url(obj):
    """Recursively search for a video URL field anywhere in the response."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("video_url", "url") and isinstance(v, str) and v.startswith("http") and (
                ".mp4" in v or "video" in v or "tos" in v or "volces" in v or k == "video_url"
            ):
                return v
            found = find_video_url(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_video_url(item)
            if found:
                return found
    return None


def poll_task(task_id: str, started_at: float) -> str:
    """Poll until succeeded; return video URL. Raises on failure."""
    url = f"{TASK_URL}/{task_id}"
    while True:
        elapsed = time.time() - started_at
        if elapsed > MAX_TOTAL_SECS:
            raise TimeoutError(f"poll exceeded {MAX_TOTAL_SECS}s budget")
        try:
            result = http_json(url, method="GET", timeout=30)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            print(f"[poll] HTTP {e.code}: {err}", flush=True)
            time.sleep(POLL_INTERVAL)
            continue
        status = result.get("status") or (result.get("data") or {}).get("status")
        print(f"[poll] t={int(elapsed)}s status={status}", flush=True)
        if status == "succeeded":
            video_url = find_video_url(result)
            if not video_url:
                raise RuntimeError(f"succeeded but no video_url in: {json.dumps(result)[:500]}")
            return video_url
        if status == "failed":
            raise RuntimeError(f"task failed: {json.dumps(result)[:800]}")
        time.sleep(POLL_INTERVAL)


def download(url: str, dest: str) -> int:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"[download] {url[:100]}...", flush=True)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
        total = 0
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
    return total


def run_once(prompt: str, image_url: str | None, started: float) -> tuple[str, str]:
    """Submit + poll once. Returns (task_id, video_url). Raises on failure."""
    task_id = submit_task(prompt, image_url=image_url)
    video_url = poll_task(task_id, started)
    return task_id, video_url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT_PATH, help="output mp4 path")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT, help="video prompt")
    ap.add_argument("--image-url", default=None,
                    help="first-frame image URL (image-to-video). If unsupported, falls back to text-only.")
    ap.add_argument("--dialogue", default=None,
                    help="dialogue text wrapped in <dialogue>...</dialogue> for native voice track. "
                         "If --prompt already contains <dialogue> tags, this is ignored.")
    args = ap.parse_args()

    started = time.time()
    image_url = args.image_url
    prompt = args.prompt
    # If dialogue flag provided and prompt doesn't already have the tag, splice it in before the params
    if args.dialogue and "<dialogue>" not in prompt:
        # try to insert before the first "--" parameter, otherwise append
        idx = prompt.find(" --")
        dialog_chunk = f" <dialogue>{args.dialogue}</dialogue>"
        if idx > 0:
            prompt = prompt[:idx] + dialog_chunk + prompt[idx:]
        else:
            prompt = prompt + dialog_chunk
    out_path = args.out

    # Strategy:
    #   1. Try image-to-video if image_url given.
    #   2. On OutputImageSensitiveContentDetected, retry once.
    #   3. If image-to-video rejected (4xx on submit) OR repeatedly fails, downgrade to text-only.
    task_id = None
    video_url = None
    last_err = None

    attempt_modes = []
    if image_url:
        attempt_modes.append(("i2v", image_url))
        attempt_modes.append(("i2v-retry", image_url))   # one retry for sensitive-content flake
        attempt_modes.append(("t2v-fallback", None))     # downgrade to text-only
    else:
        attempt_modes.append(("t2v", None))
        attempt_modes.append(("t2v-retry", None))

    for label, img in attempt_modes:
        try:
            print(f"[attempt] mode={label}", flush=True)
            task_id, video_url = run_once(prompt, img, started)
            break
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            last_err = f"HTTP {e.code} {err_body[:300]}"
            print(f"[attempt] {label} failed: {last_err}", flush=True)
            # if image rejected (4xx) and we still have a t2v fallback queued, just continue
            continue
        except RuntimeError as e:
            msg = str(e)
            last_err = msg
            print(f"[attempt] {label} failed: {msg[:300]}", flush=True)
            # OutputImageSensitiveContentDetected -> retry next iteration
            # task failed for other reasons -> still try next iteration
            continue
        except TimeoutError as e:
            raise   # don't retry on timeout, we're already over budget

    if not video_url:
        raise RuntimeError(f"all attempts failed. last_err={last_err}")

    # download
    size_bytes = download(video_url, out_path)
    elapsed = time.time() - started

    # final report
    size_mb = size_bytes / (1024 * 1024)
    print("")
    print("=" * 60)
    print(f"OK  file:        {out_path}")
    print(f"OK  size:        {size_bytes:,} bytes ({size_mb:.2f} MB)")
    print(f"OK  elapsed:     {elapsed:.1f} s")
    print(f"OK  task_id:     {task_id}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        sys.exit(1)
