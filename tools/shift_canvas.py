#!/usr/bin/env python3
"""Shift all canvas-pixel data by (DX, DY) after the tile canvas grows (see build_tiles.py).

Touches: every uezd's parcels.geojson (polygon coordinates) and data/towns.json (x, y).
Per-scan outlines (data/<uezd>_outline.json) are in their own SCAN pixels and are NOT
shifted; tools/layout.json keeps the old-canvas placement and build_tiles.py adds DX.
Run once per canvas change; prints what it did.

usage: shift_canvas.py DX [DY]
"""
import sys, json, glob
dx = int(sys.argv[1]); dy = int(sys.argv[2]) if len(sys.argv) > 2 else 0

def shift_ring(r): return [[x + dx, y + dy] for x, y in r]
for p in ['data/parcels.geojson'] + sorted(glob.glob('data/*/parcels.geojson')):
    d = json.load(open(p)); n = 0
    for f in d['features']:
        g = f['geometry']
        if g['type'] == 'Polygon': g['coordinates'] = [shift_ring(r) for r in g['coordinates']]
        elif g['type'] == 'MultiPolygon': g['coordinates'] = [[shift_ring(r) for r in poly] for poly in g['coordinates']]
        n += 1
    txt = json.dumps(d, ensure_ascii=False, indent=1)
    open(p, 'w').write(txt); print(f'{p}: {n} features shifted')
t = json.load(open('data/towns.json'))
for tw in t['towns']: tw['x'] += dx; tw['y'] += dy
open('data/towns.json', 'w').write(json.dumps(t, ensure_ascii=False, indent=1) + '\n')
print(f'data/towns.json: {len(t["towns"])} towns shifted')
