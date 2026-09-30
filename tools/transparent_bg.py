#!/usr/bin/env python3
"""Make the white/paper background of a coat-of-arms image transparent.

Only near-white pixels CONNECTED TO THE IMAGE EDGE are removed, so white and silver
inside the arms (mantle ermine, argent fields) stay. The cut gets a soft 1-2 px edge.
Writes a PNG (JPEG cannot hold transparency).

usage: transparent_bg.py IN [OUT.png] [--tol 18] [--min 225] [--paper DIST] [--preview PREVIEW.jpg]
"""
import argparse, os
import numpy as np, cv2
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument('src'); ap.add_argument('out', nargs='?')
ap.add_argument('--min', type=int, default=225, help='darkest channel value still counted as white')
ap.add_argument('--tol', type=int, default=18, help='max channel spread (colourlessness)')
ap.add_argument('--paper', type=int, default=0,
                help='instead of "white": remove pixels within this colour distance of the paper '
                     'colour, measured as the median of the image border (for grey/tinted paper)')
ap.add_argument('--preview', help='also save the result over a green backdrop, for checking')
a = ap.parse_args()
out = a.out or os.path.splitext(a.src)[0] + '.png'

im = np.asarray(Image.open(a.src).convert('RGB')).astype(np.int16)
h, w, _ = im.shape
if a.paper:
    edge = np.concatenate([im[0], im[-1], im[:, 0], im[:, -1]])
    paper = np.median(edge, axis=0)
    white = (np.sqrt(((im - paper) ** 2).sum(2)) <= a.paper).astype(np.uint8) * 255
else:
    white = ((im.min(2) >= a.min) & ((im.max(2) - im.min(2)) <= a.tol)).astype(np.uint8) * 255
ff = white.copy(); m = np.zeros((h + 2, w + 2), np.uint8)
for x in range(0, w, 2):
    for y in (0, h - 1):
        if ff[y, x] == 255: cv2.floodFill(ff, m, (x, y), 128)
for y in range(0, h, 2):
    for x in (0, w - 1):
        if ff[y, x] == 255: cv2.floodFill(ff, m, (x, y), 128)
bg = (ff == 128)
alpha = np.clip(cv2.GaussianBlur((~bg).astype(np.float32), (0, 0), 0.8) * 1.2, 0, 1)
rgba = np.dstack([im.astype(np.uint8), (alpha * 255).astype(np.uint8)])
Image.fromarray(rgba, 'RGBA').save(out, optimize=True)
print(f'{a.src} -> {out}: background {bg.mean():.0%}')
if a.preview:
    b = Image.new('RGBA', (w, h), (70, 110, 60, 255)); b.alpha_composite(Image.open(out))
    b.convert('RGB').save(a.preview, quality=85)
