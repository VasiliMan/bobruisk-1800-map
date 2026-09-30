#!/usr/bin/env python3
"""Build the combined multi-uezd tile pyramid (replaces the lost build_combined.py).

Layers, bottom to top:
  base   : an existing full-resolution (z7) tile set holding Бобруйск + Речица, already
           masked and baked (the old tiles/7). It is re-used by RENAMING tiles: the whole
           canvas shifts right by DX = a multiple of 256, so no pixel is resampled.
  mozyr  : Мозырский scan, warped by tools/layout.json, clipped to its outline MINUS the
           Бобруйск/Речица outlines (where hand-drawn borders overlap, the uezds whose
           parcels are already traced win).
  pinsk  : Пинский scan, scaled+warped by layout.json, clipped to its outline minus the
           three others.
Then z6..z0 are rebuilt by 2x2 downsampling. Tiles that would be pure background are not
written (the map's background colour shows through).

Coordinates: layout.json and the outlines are in the OLD canvas (origin = top-left of the
Бобруйск scan). The new canvas is old + (DX, 0). The script also writes
data/uezd_outlines.json: every uezd outline in NEW canvas pixels, for the app's
"which uezd is this point in" lookup.

usage: build_tiles.py --base BASE_Z7_DIR --out OUT_DIR [--dx 22016] [--quality 85]
"""
import os, json, math, shutil, argparse, time
import numpy as np, cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
T, Z = 256, 7
PAPER = (232, 228, 208)                       # #map background in style.css

ap = argparse.ArgumentParser()
ap.add_argument('--base', required=True, help='dir with the old z7 tiles: BASE/<x>/<y>.jpg')
ap.add_argument('--out', required=True)
ap.add_argument('--dx', type=int, default=22016, help='shift of the old canvas, multiple of 256')
ap.add_argument('--quality', type=int, default=85)
ap.add_argument('--root', default='.', help='repo root (for tools/layout.json and data/)')
a = ap.parse_args()
assert a.dx % T == 0
R = lambda p: os.path.join(a.root, p)
lay = json.load(open(R('tools/layout.json')))

def rot(deg):
    th = math.radians(deg); c, s = math.cos(th), math.sin(th); return np.array([[c, s], [-s, c]])
def xform(u):                                  # scan px -> NEW canvas px, row-vector form
    L = lay[u]; M = L.get('scale', 1.0) * rot(L['theta_deg']); t = np.array(L['t'], float) + [a.dx, 0]
    return M, t
OUTL = {}
for u in ('bobruisk', 'rechitsa', 'mozyr', 'pinsk'):
    P = np.array(json.load(open(R(f'data/{u}_outline.json')))['points'], float)
    M, t = xform(u); OUTL[u] = P @ M + t
json.dump({u: [[round(x), round(y)] for x, y in P] for u, P in OUTL.items()},
          open(R('data/uezd_outlines.json'), 'w'))
allp = np.vstack(list(OUTL.values()))
W = int(max(allp[:, 0].max(), 20606 + a.dx)) + 256
H = int(max(allp[:, 1].max(), 31110)) + 256
NX, NY = math.ceil(W / T), math.ceil(H / T)
print(f'new canvas {W}x{H} ({NX}x{NY} tiles at z{Z}), DX={a.dx}')

LAYERS = []                                    # (name, src array, dst->src affine, poly, excluded polys, interp)
for u, excl, interp in (('mozyr', ('bobruisk', 'rechitsa'), cv2.INTER_LINEAR),
                        ('pinsk', ('bobruisk', 'rechitsa', 'mozyr'), cv2.INTER_CUBIC)):
    src = os.path.expanduser(lay[u]['scan']); t0 = time.time()
    arr = np.asarray(Image.open(src).convert('RGB'))
    M, t = xform(u); Mi = np.linalg.inv(M)     # canvas = scan @ M + t  ->  scan = (canvas - t) @ Mi
    LAYERS.append((u, arr, Mi, t, OUTL[u], [OUTL[e] for e in excl], interp,
                   OUTL[u].min(0), OUTL[u].max(0)))
    print(f'loaded {u}: {arr.shape[1]}x{arr.shape[0]} in {time.time() - t0:.0f}s')

def tile_mask(poly, excl, x0, y0):
    m = np.zeros((T, T), np.uint8)
    cv2.fillPoly(m, [np.round(poly - [x0, y0]).astype(np.int32)], 255)
    for e in excl: cv2.fillPoly(m, [np.round(e - [x0, y0]).astype(np.int32)], 0)
    return m

# ---- z7 ----
t0 = time.time(); copied = rendered = 0
bx = a.dx // T
for tx in range(NX):
    for ty in range(NY):
        x0, y0 = tx * T, ty * T
        base = os.path.join(a.base, str(tx - bx), f'{ty}.jpg')
        has_base = tx - bx >= 0 and os.path.exists(base)
        hits = [L for L in LAYERS if not (x0 > L[8][0] or x0 + T < L[7][0] or y0 > L[8][1] or y0 + T < L[7][1])]
        out = os.path.join(a.out, str(Z), str(tx), f'{ty}.jpg')
        img = None
        for (u, arr, Mi, t, poly, excl, interp, lo, hi) in hits:
            m = tile_mask(poly, excl, x0, y0)
            if not m.any(): continue
            # dst pixel (i,j) in tile -> canvas (x0+i, y0+j) -> scan = ((x0+i,y0+j) - t) @ Mi
            A = np.zeros((2, 3)); A[:, :2] = Mi.T; A[:, 2] = (np.array([x0, y0]) - t) @ Mi
            warped = cv2.warpAffine(arr, A, (T, T), flags=interp | cv2.WARP_INVERSE_MAP,
                                    borderMode=cv2.BORDER_CONSTANT, borderValue=PAPER)
            if img is None:
                img = np.asarray(Image.open(base).convert('RGB')).copy() if has_base else np.full((T, T, 3), PAPER, np.uint8)
            img[m > 0] = warped[m > 0]
        if img is not None:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            Image.fromarray(img).save(out, quality=a.quality); rendered += 1
        elif has_base:
            os.makedirs(os.path.dirname(out), exist_ok=True); shutil.copyfile(base, out); copied += 1
    if tx % 20 == 0: print(f'  z7 column {tx}/{NX}  copied {copied}, rendered {rendered}  ({time.time() - t0:.0f}s)')
print(f'z7 done: copied {copied}, rendered {rendered} in {time.time() - t0:.0f}s')

# ---- z6..z0 by 2x2 downsampling ----
for z in range(Z - 1, -1, -1):
    n = 0; nx, ny = math.ceil(NX / 2 ** (Z - z)), math.ceil(NY / 2 ** (Z - z))
    for tx in range(nx):
        for ty in range(ny):
            quad = np.full((2 * T, 2 * T, 3), PAPER, np.uint8); any_ = False
            for dx in (0, 1):
                for dy in (0, 1):
                    p = os.path.join(a.out, str(z + 1), str(2 * tx + dx), f'{2 * ty + dy}.jpg')
                    if os.path.exists(p):
                        quad[dy * T:(dy + 1) * T, dx * T:(dx + 1) * T] = np.asarray(Image.open(p).convert('RGB')); any_ = True
            if not any_: continue
            d = os.path.join(a.out, str(z), str(tx)); os.makedirs(d, exist_ok=True)
            Image.fromarray(cv2.resize(quad, (T, T), interpolation=cv2.INTER_AREA)).save(os.path.join(d, f'{ty}.jpg'), quality=a.quality); n += 1
    print(f'z{z}: {n} tiles')
print(json.dumps({'IMG_W': W, 'IMG_H': H, 'DX': a.dx}))
