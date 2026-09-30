#!/usr/bin/env python3
"""Cut one scan into a Leaflet CRS.Simple tile pyramid: OUT/{z}/{x}/{y}.jpg.

Zoom maxZ is the scan at full resolution (maxZ = ceil(log2(max(W,H)/256))); each lower
zoom halves it. Used for the per-uezd tracing pyramids (tiles_<uezd>/, local only,
gitignored) that trace.html reads.

usage: make_tiles.py SCAN OUT_DIR [--quality 85]
"""
import os, math, argparse
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
T = 256

ap = argparse.ArgumentParser()
ap.add_argument('scan'); ap.add_argument('out'); ap.add_argument('--quality', type=int, default=85)
a = ap.parse_args()

im = Image.open(a.scan).convert('RGB')
W, H = im.size
maxZ = math.ceil(math.log2(max(W, H) / T))
print(f'{a.scan}: {W}x{H}, maxZ={maxZ}')
level = im
for z in range(maxZ, -1, -1):
    w, h = level.size
    n = 0
    for x in range(math.ceil(w / T)):
        d = os.path.join(a.out, str(z), str(x)); os.makedirs(d, exist_ok=True)
        for y in range(math.ceil(h / T)):
            tile = level.crop((x * T, y * T, min(w, (x + 1) * T), min(h, (y + 1) * T)))
            if tile.size != (T, T):                      # pad edge tiles with paper colour
                pad = Image.new('RGB', (T, T), (232, 228, 208)); pad.paste(tile); tile = pad
            tile.save(os.path.join(d, f'{y}.jpg'), quality=a.quality); n += 1
    print(f'  z{z}: {w}x{h} -> {n} tiles')
    if z: level = level.resize((max(1, w // 2), max(1, h // 2)), Image.LANCZOS)
print(f'CFG: W:{W}, H:{H}, maxZ:{maxZ}')
