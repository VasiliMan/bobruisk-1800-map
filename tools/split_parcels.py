#!/usr/bin/env python3
"""Split an editor export (all.parcels.geojson, every feature tagged with `uezd`) back into
data/parcels.geojson (Бобруйск) and data/<uezd>/parcels.geojson, and report what changed.

usage: split_parcels.py EXPORT.geojson
"""
import sys, json
PATH = lambda u: 'data/parcels.geojson' if u == 'bobruisk' else f'data/{u}/parcels.geojson'
exp = json.load(open(sys.argv[1]))
by = {}
for f in exp['features']:
    by.setdefault(f['properties'].get('uezd'), []).append(f)
for u, feats in sorted(by.items(), key=lambda kv: str(kv[0])):
    if u is None: print(f'!! {len(feats)} features without uezd — skipped'); continue
    old = {f['properties']['fid']: f for f in json.load(open(PATH(u)))['features']}
    new = {f['properties']['fid']: f for f in feats}
    added = [k for k in new if k not in old]; gone = [k for k in old if k not in new]
    changed = [k for k in new if k in old and new[k] != old[k]]
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(PATH(u), 'w'), ensure_ascii=False, indent=1)
    print(f'{u}: {len(feats)} features — added {len(added)}, changed {len(changed)}, removed {len(gone)}')
    for k in added: print('   +', new[k]['properties'].get('num'), new[k]['properties'].get('chast'))
    for k in changed: print('   ~', new[k]['properties'].get('num'), new[k]['properties'].get('chast'))
    for k in gone: print('   -', old[k]['properties'].get('num'), old[k]['properties'].get('chast'))
