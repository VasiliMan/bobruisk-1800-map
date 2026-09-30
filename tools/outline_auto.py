#!/usr/bin/env python3
"""First-pass uezd outline from a General Survey plan scan.

The uezd border is drawn as a continuous crimson line. We pick out red pixels on a
downscaled copy, close small breaks in the line, flood-fill the paper from the image
edge, and take everything the fill cannot reach as the uezd. The outer contour of that
area is simplified and written as {"uezd": id, "points": [[x,y],...]} in FULL-resolution
scan pixels -- the same format as data/bobruisk_outline.json, ready to correct in
trace.html. (Colour alone cuts pale marsh out; texture swallows cartouches and inset frames. So the
fill is walled by the red line OR coloured map, which handles both.)

usage: outline_auto.py SCAN UEZD_ID OUT.json [--preview PREVIEW.jpg] [--gap PX]
"""
import json, argparse
import numpy as np, cv2
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

ap = argparse.ArgumentParser()
ap.add_argument('scan'); ap.add_argument('uezd'); ap.add_argument('out')
ap.add_argument('--preview')
ap.add_argument('--work', type=int, default=3000, help='width of the working copy (px)')
ap.add_argument('--gap', type=int, default=0, help='max break in the red line to bridge (work px; 0 = auto)')
a = ap.parse_args()

im = Image.open(a.scan); W, H = im.size
im.draft('RGB', (a.work, a.work * H // W))          # fast JPEG downscale when possible
im = im.convert('RGB'); im.thumbnail((a.work, a.work * H // W), Image.LANCZOS)
w, h = im.size; k = W / w
rgb = np.asarray(im)
hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
hh, ss, vv = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
red = (((hh <= 8) | (hh >= 165)) & (ss >= 70) & (vv >= 60) & (vv <= 235)).astype(np.uint8) * 255
gap = a.gap or max(5, w // 250)
line = cv2.morphologyEx(red, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gap, gap)))
line = cv2.dilate(line, np.ones((3, 3), np.uint8))
# the red line alone has breaks; coloured map (saturation, Otsu) is a second wall. Pale marsh
# inside is enclosed by the border + green map, so the paper fill cannot reach it.
sat = cv2.GaussianBlur(hsv[..., 1], (0, 0), 3)
_, satm = cv2.threshold(sat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
satm = cv2.morphologyEx(satm, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gap, gap)))
line = cv2.bitwise_or(line, satm)
# flood the paper from the border of the image; whatever the red line fences off is the uezd
fill = line.copy(); ff = np.zeros((h + 2, w + 2), np.uint8)
for x, y in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
    if fill[y, x] == 0: cv2.floodFill(fill, ff, (x, y), 128)
inside = ((fill != 128)).astype(np.uint8) * 255
inside = cv2.morphologyEx(inside, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gap, gap)))
n, lab, stats, _ = cv2.connectedComponentsWithStats(inside)
big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
blob = (lab == big).astype(np.uint8) * 255
cnts, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
c = max(cnts, key=cv2.contourArea)
poly = cv2.approxPolyDP(c, 0.0012 * cv2.arcLength(c, True), True)[:, 0, :]
pts = [[int(round(x * k)), int(round(y * k))] for x, y in poly]
json.dump({'uezd': a.uezd, 'points': pts}, open(a.out, 'w'))
print(f'{a.uezd}: scan {W}x{H}, work {w}x{h}, red px {red.mean() / 255:.2%}, '
      f'area {stats[big, cv2.CC_STAT_AREA] / (w * h):.0%} of image, {len(pts)} points -> {a.out}')
if a.preview:
    out = rgb.copy()
    cv2.polylines(out, [poly.reshape(-1, 1, 2)], True, (0, 90, 255), max(2, w // 700))
    Image.fromarray(out).save(a.preview, quality=85)
