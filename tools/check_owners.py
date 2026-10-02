#!/usr/bin/env python3
"""Cross-check traced parcels against the owner index, per uezd.

The map shows a parcel's owners by looking up (uezd, chast, num) in owners.json — not the
owner_id stored on the feature. So a co-owner is lost when the index lists him under the
same number but a different часть than the traced parcel, or when a feature names an owner
the index doesn't link to that parcel. This lists every such case.

  A  traced parcel: index owners under the SAME num but another часть (likely hidden co-owners)
  B  traced parcel: feature owner_id/owner_ids not in the index for that (chast, num)
  C  traced parcel with no index owner at all
  D  index (chast, num) that is not traced yet (to-do list)

usage: check_owners.py [uezd ...]      (default: all)
"""
import sys, json
from collections import defaultdict
# same folding as numKey() in app.js: Latin look-alikes -> Cyrillic, trimmed
NUMKEY = str.maketrans('ABCEHKMOPTXaceopxy', 'АВСЕНКМОРТХасеорху')
nk = lambda n: str(n).strip().translate(NUMKEY)
UEZDS = {'bobruisk': ('data/owners.json', 'data/parcels.geojson'),
         'rechitsa': ('data/rechitsa/owners.json', 'data/rechitsa/parcels.geojson'),
         'mozyr':    ('data/mozyr/owners.json', 'data/mozyr/parcels.geojson'),
         'pinsk':    ('data/pinsk/owners.json', 'data/pinsk/parcels.geojson')}
for u in (sys.argv[1:] or UEZDS):
    od = json.load(open(UEZDS[u][0])); owners = od['owners'] if isinstance(od, dict) else od
    feats = json.load(open(UEZDS[u][1]))['features']
    idx = defaultdict(set); name = {}
    for o in owners:
        name[o['id']] = o['name']
        for p in o['parcels']: idx[(p.get('chast'), nk(p['num']))].add(o['id'])
    traced = {}
    for f in feats:
        pr = f['properties']
        for c in (pr.get('parts') or [pr.get('chast')]):     # multi-sheet parcels list all their parts
            traced[(c, nk(pr.get('num')))] = pr
    print(f'\n===== {u}: {len(owners)} owners, {len(traced)} traced parcels =====')
    for (ch, num), pr in sorted(traced.items(), key=lambda k: (str(k[0][1]).zfill(4), k[0][0] or 0)):
        here = set().union(*[idx.get((c, num), set()) for c in (pr.get('parts') or [ch])])
        if pr.get('parts') and ch != pr.get('chast'): continue   # report a multi-part parcel once
        other = {c: ids for (c, n), ids in idx.items() if n == num and c not in (pr.get('parts') or [ch]) and ids - here}
        for c, ids in other.items():
            print(f'  A  {num}/{ch}: index also has {num}/{c}: ' + ', '.join(name[i] for i in sorted(ids - here)))
        feat = set(pr.get('owner_ids') or ([pr['owner_id']] if pr.get('owner_id') else []))
        for i in sorted(feat - here):
            print(f'  B  {num}/{ch}: feature owner «{name.get(i, i)}» not in index for {num}/{ch}')
        if not here: print(f'  C  {num}/{ch}: no owner in the index')
    todo = sorted(k for k in idx if k not in traced)
    print(f'  D  not traced ({len(todo)}): ' + ', '.join(f'{n}/{c}' for c, n in sorted(todo, key=lambda k: (str(k[1]).zfill(4), k[0] or 0))))
