#!/usr/bin/env python3
"""Split an editor export (all.parcels.geojson, every feature tagged with `uezd`) back into
data/parcels.geojson (Бобруйск) and data/<uezd>/parcels.geojson, and report what changed.

Guard: the map prefers the browser's autosave over the data files, so an export can come
from a STALE autosave and silently undo fixes made in the files since (num corrected,
chast/parts/owner_id filled in, parcels added). Before writing anything, every parcel whose
num, chast, parts, owner_id or owner_ids would be dropped or changed, and every parcel that
would disappear, is listed, and nothing is written unless --force is given.

usage: split_parcels.py EXPORT.geojson [--force]
"""
import sys, json
PATH = lambda u: 'data/parcels.geojson' if u == 'bobruisk' else f'data/{u}/parcels.geojson'
GUARDED = ('num', 'chast', 'parts', 'owner_id', 'owner_ids')
force = '--force' in sys.argv
exp = json.load(open([a for a in sys.argv[1:] if a != '--force'][0]))
by = {}
for f in exp['features']:
    u = f['properties'].pop('uezd', None)          # the app re-derives it; files don't store it
    for k in [k for k in f if k.startswith('_')]: del f[k]   # app-internal (_ring, _area, _parentFid)
    by.setdefault(u, []).append(f)

plan, risky = [], []
for u, feats in sorted(by.items(), key=lambda kv: str(kv[0])):
    if u is None: print(f'!! {len(feats)} features without uezd — skipped'); continue
    old = {f['properties']['fid']: f for f in json.load(open(PATH(u)))['features']}
    for f in old.values():
        f['properties'].pop('uezd', None)
        for k in [k for k in f if k.startswith('_')]: del f[k]
    new = {f['properties']['fid']: f for f in feats}
    for k, of in old.items():
        po = of['properties']
        if k not in new:
            risky.append(f'{u} {po.get("num")}/{po.get("chast")}: parcel would be removed'); continue
        pn = new[k]['properties']
        for key in GUARDED:
            if po.get(key) not in (None, [], '') and pn.get(key) != po.get(key):
                risky.append(f'{u} {po.get("num")}/{po.get("chast")}: {key} {po.get(key)!r} -> {pn.get(key)!r}')
    plan.append((u, feats, old, new))

if risky:
    print(f'!! {len(risky)} change(s) would drop or overwrite data already in the files '
          '(stale browser autosave?):')
    for r in risky: print('   ', r)
    if not force:
        sys.exit('nothing written — check the export, or rerun with --force if these edits are intended')

for u, feats, old, new in plan:
    added = [k for k in new if k not in old]; gone = [k for k in old if k not in new]
    changed = [k for k in new if k in old and new[k] != old[k]]
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(PATH(u), 'w'), ensure_ascii=False, indent=1)
    print(f'{u}: {len(feats)} features — added {len(added)}, changed {len(changed)}, removed {len(gone)}')
    for k in added: print('   +', new[k]['properties'].get('num'), new[k]['properties'].get('chast'))
    for k in changed: print('   ~', new[k]['properties'].get('num'), new[k]['properties'].get('chast'))
    for k in gone: print('   -', old[k]['properties'].get('num'), old[k]['properties'].get('chast'))
