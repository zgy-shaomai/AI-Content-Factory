#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate 11 Seedream 4.0 demo images for YN-BRA-001 sportswear demo.
Sequential calls to avoid RPM limits (~30s per image, ~5-8 min total).
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

API_KEY = os.environ.get("ARK_API_KEY", "")
if not API_KEY:
    print("❌ ARK_API_KEY 未设置。export ARK_API_KEY=ark-... 后重试"); sys.exit(1)
API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
MODEL = "doubao-seedream-4-0-250828"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "_demo_seed", "images")

os.makedirs(OUT_DIR, exist_ok=True)

PROMPTS = [
    ("01-studio-front", "studio shot of a 28-year-old asian woman wearing matte black sports bra with chrome front zipper on minimalist light gray background, frontal view, eye level, soft diffused natural light from camera left, breathable mesh fabric texture visible at sides, sweat-wicking nylon-spandex blend with subtle matte sheen, preserve original tonal logo placement on left chest 6cm below collarbone 3cm wide, neutral undertone, no color shift to navy blue or warm brown, professional fashion photography, ultra detailed, 1024x1024"),
    ("02-studio-side", "studio profile shot of same 28-year-old asian woman wearing matte black sports bra with front zipper, side view facing camera-right, minimalist light gray seamless background, soft natural light from front-left at 45 degrees, breathable mesh side panels visible, high elasticity fabric showing natural drape, sweat-wicking nylon-spandex blend, brand color matte black with neutral undertone, professional fashion editorial style, sharp focus on fabric texture, 1024x1024"),
    ("03-studio-back", "studio back shot of same 28-year-old asian woman wearing matte black sports bra, viewed from behind, minimalist light gray background, even soft lighting, racerback design clearly visible, breathable mesh fabric across upper back, high-elasticity strap support visible, no logo on back, matte black brand color, ultra detailed editorial photography, 1024x1024"),
    ("04-fabric-macro", "extreme close-up macro photograph of breathable mesh fabric surface on a matte black sports bra, sweat-wicking nylon-spandex blend showing fine weave pattern, subtle matte sheen, fiber detail at 1:1 magnification, soft directional lighting from upper-left to reveal texture depth, neutral undertone, professional product photography, no model, white seamless background blur, 1024x1024"),
    ("05-zipper-action", "cinematic close-up of asian woman's hand pulling chrome front zipper of matte black sports bra, fingers gripping zipper pull with subtle motion blur on the pull, natural skin tone, soft directional light from window left, breathable mesh fabric texture visible around zipper area, preserve logo placement on left chest just below frame, lifestyle editorial style, shallow depth of field, 1024x1024"),
    ("06-logo-closeup", "extreme close-up of branded logo on matte black sports bra fabric on left chest area, tonal embroidery or heat-transfer print, breathable mesh fabric texture surrounding logo, sweat-wicking nylon-spandex blend, soft natural lighting from top-left to highlight logo subtle dimensionality, no human face in frame, neutral matte black color with no color shift, professional product detail photography, 1024x1024"),
    ("07-yoga-studio", "wide lifestyle shot of same 28-year-old asian woman in matte black sports bra and matching black yoga pants doing warrior pose in a sun-drenched yoga studio at golden morning hour, wooden floor, large arched window with soft warm sunlight streaming in, minimalist scandinavian decor, plants in background, breathable mesh fabric visible, professional photography in editorial fashion style, ultra detailed, 1024x1024"),
    ("08-gym-training", "dynamic action shot of same asian woman wearing matte black sports bra performing battle rope exercises in modern minimalist gym with concrete floors, controlled motion blur on the ropes, focused expression, sweat sheen on skin showing effort, dramatic side lighting from large industrial windows, breathable mesh fabric and matte sheen visible, sweat-wicking performance shown, editorial sports photography, 1024x1024"),
    ("09-park-running", "lifestyle shot of same asian woman jogging through a green urban park at golden hour, wearing matte black sports bra and running shorts, motion blur in legs and trees, focused forward gaze, warm late afternoon sunlight casting long shadows, breathable mesh fabric visible, sweat-wicking performance demonstrated, athletic editorial style with cinematic color grading, 1024x1024"),
    ("10-mountain-outdoor", "cinematic outdoor shot of same asian woman in matte black sports bra and hiking shorts standing on a rocky mountain ridge with sweeping vista in background, dramatic golden hour lighting, slight wind in hair, confident pose looking toward distant peaks, breathable mesh fabric subtly visible, lifestyle adventure photography editorial, ultra detailed, 1024x1024"),
    ("11-beach-coast", "coastal lifestyle shot of same asian woman in matte black sports bra walking along wet sand at sunset, ocean waves and distant horizon, warm orange-pink sky, footprints in sand behind her, soft sea breeze in hair, breathable mesh fabric visible, peaceful confident expression, fashion editorial photography, ultra detailed, 1024x1024"),
]


def call_seedream(prompt: str, retries: int = 2, timeout: int = 120) -> str:
    """Call ARK Seedream API and return image URL. Retries on transient errors."""
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "size": "1024x1024",
        "watermark": False,
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if "data" in data and data["data"] and data["data"][0].get("url"):
                return data["data"][0]["url"]
            last_err = f"unexpected resp: {json.dumps(data)[:300]}"
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                err_body = ""
            last_err = f"HTTP {e.code}: {err_body}"
            # Rate limit: back off longer
            if e.code in (429, 503):
                time.sleep(15 * (attempt + 1))
                continue
            if e.code in (500, 502, 504) and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            break
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
    raise RuntimeError(last_err or "unknown error")


def download(url: str, path: str, timeout: int = 60) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def main() -> int:
    success = 0
    failures = []
    t0 = time.time()
    for i, (name, prompt) in enumerate(PROMPTS, start=1):
        out_path = os.path.join(OUT_DIR, f"{name}.png")
        print(f"[{i:02d}/11] {name} ... ", end="", flush=True)
        ts = time.time()
        try:
            url = call_seedream(prompt)
            size = download(url, out_path)
            elapsed = time.time() - ts
            print(f"OK {size:,}B ({elapsed:.1f}s)")
            success += 1
        except Exception as e:
            elapsed = time.time() - ts
            print(f"FAIL ({elapsed:.1f}s) -> {e}")
            failures.append((name, str(e)))
        # small jitter between calls to be polite to RPM limits
        if i < len(PROMPTS):
            time.sleep(2)

    total = time.time() - t0
    print("-" * 60)
    print(f"done in {total:.1f}s | success: {success}/11 | failed: {len(failures)}")
    if failures:
        for n, err in failures:
            print(f"  - {n}: {err}")
    # final dir count
    try:
        files = [f for f in os.listdir(OUT_DIR) if f.lower().endswith(".png")]
        print(f"_demo_seed/images/ contains {len(files)} PNG files")
    except Exception as e:
        print(f"could not list output dir: {e}")
    return 0 if success == 11 else 1


if __name__ == "__main__":
    sys.exit(main())
