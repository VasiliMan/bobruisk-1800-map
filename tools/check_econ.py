#!/usr/bin/env python3
"""Cross-check the owner alphabet (owners.json) against the economic notes (econ.tsv), per uezd.

The alphabet links an owner to parcel numbers through braces spanning several rows, so a
number is easily attached to the wrong owner (e.g. Пинск 50: alphabet → Репнин, economic
notes → воевода Ксаверий Хоминский). The economic notes give, for every plan number, the
«владение …» heading — an independent second source. Matching is by surname stem (first 5
letters) plus first name when both sides give one, so case endings and spelling mostly agree;
every hit is still a lead to check on the scans, not a verdict.

The economic notes are the authority. Findings are graded by that rule:

  CRITICAL  owner is ONLY in the alphabet: the alphabet links him to a number, and he appears
            nowhere in the economic notes of the uezd — something is really wrong (misread
            name, wrong uezd, invented row); check the scans
  DISAGREE  the alphabet links an owner to a number whose econ entry does not name him, or names
            him only as a minor share, or gives another часть — the econ entry wins; the record
            must say so («econ» note on the owner)
  MISSING   econ names an owner for a number that the alphabet does not link (not a big deal —
            the alphabet is partly transcribed); listed when the parcel is traced, or the owner
            is already in the alphabet under another number

usage: check_econ.py [uezd ...]      (default: every uezd that has data/<uezd>/econ.tsv)
"""
import sys, os, re, json
from collections import defaultdict
NUMKEY = str.maketrans('ABCEHKMOPTXaceopxy', 'АВСЕНКМОРТХасеорху')   # as in app.js numKey()
nk = lambda n: str(n).strip().translate(NUMKEY)
PATHS = {'bobruisk': ('data/owners.json', 'data/parcels.geojson', 'data/econ.tsv')}
for u in ('rechitsa', 'mozyr', 'pinsk'):
    PATHS[u] = (f'data/{u}/owners.json', f'data/{u}/parcels.geojson', f'data/{u}/econ.tsv')

# words that say nothing about WHO: titles, offices, institutions, generic and place words
TITLES = set('''князь княз княгиня граф генерал майор майорша подполковник подполковница полковница полковник
капитан ротмистр судья судьи земский земскаго воевода каштелян регент шамбелян маршал стражник хорунжий
подстолий подстароста староста старосты староство действительный статский советник кавалер шляхтич шляхта
шляхты шляхетство околичные околичная околичное околичных чиншовые чиншовая чиншовых владение владения
общаго город город мещане мещан иностранцы монастырь монастыри кляштор кляшторы плебания парафия мужеский
мужской женский часть части брат братьями братом детьми малолетний спорная земля пашенная пинск пинский
пинская пинскаго пинской базилианский грекороссийский римскокатолический'''.split())
# first names: two people of one family share a surname, so a match needs the first name too
NAMES = {w[:4] for w in '''николай васильевич михаил иван игнатий петр павел антоний франтишек федор тимофей
александр адам семен томаш иосиф осип казимир станислав викентий григорий лаврентий доминик матвей самуил
леопольд агафья анна варвара мартин феликс харитон ксаверий богуслав леон король фома каэтан василий
владислав владимир марианна клара розалия фелициана войтех аполинарий кунегунда богумила виктория героним
христофор леонора бенедикт'''.split()}
SURNAME_END = re.compile(r'(ск|цк|ич|вич|ов|ев|ин)[а-я]*$')

def person(text):
    """(surname stems, first-name stems) of a name in any case: first 5 / 4 letters of each word"""
    words = re.findall(r'[а-яёіѣ]+', text.lower().replace('ё', 'е').replace('ѣ', 'е').replace('і', 'и'))
    sur, first = set(), set()
    for w in words:
        if len(w) < 4 or w in TITLES or w[:5] in {t[:5] for t in TITLES}: continue
        if w[:4] in NAMES and not SURNAME_END.search(w[4:]): first.add(w[:4])
        else: sur.add(w[:5])
    return sur, first

def same(a, b):
    """same person: shared surname stem, and first names agree when both sides give one"""
    return bool(a[0] & b[0]) and (not a[1] or not b[1] or bool(a[1] & b[1]))

def load_econ(path):
    rows = {}
    for line in open(path):
        if line.startswith('#') or line.startswith('num\t') or not line.strip(): continue
        num, parts, img, owners, also = (line.rstrip('\n').split('\t') + ['', ''])[:5]
        rows[nk(num)] = dict(parts={int(p) for p in parts.split(',') if p.strip().isdigit()},
                             img=img, owners=owners, also=also,
                             principal=[(x.strip(), person(x)) for x in owners.split(';') if x.strip()],
                             minor=[(x.strip(), person(x)) for x in also.split(';') if x.strip()])
    return rows

uezds = sys.argv[1:] or [u for u, p in PATHS.items() if os.path.exists(p[2])]
for u in uezds:
    op, pp, ep = PATHS[u]
    if not os.path.exists(ep): print(f'\n===== {u}: no {ep} — skipped'); continue
    econ = load_econ(ep)
    owners = json.load(open(op))['owners']
    feats = json.load(open(pp))['features']
    traced = {nk(f['properties'].get('num')) for f in feats}
    who = {o['id']: person(' '.join(filter(None, [o.get('name_ru'), o.get('name'), o.get('alt')]))) for o in owners}
    byn = defaultdict(list)
    for o in owners:
        for p in o['parcels']: byn[nk(p['num'])].append((o, p.get('chast')))
    print(f'\n===== {u}: {len(econ)} econ entries, {len(owners)} alphabet owners =====')
    out = []
    every = [p for e in econ.values() for _, p in e['principal'] + e['minor']]
    for num, links in byn.items():
        e = econ.get(num)
        for o, ch in links:
            w = who[o['id']]
            if not w[0]: continue
            if not any(same(w, p) for p in every):
                out.append(('CRITICAL', num, f"{o['name']} → {num}/{ch}: not in the economic notes at all"))
                continue
            if not e:
                out.append(('DISAGREE', num, f"{o['name']} → {num}/{ch}: no econ entry for {num}"))
                continue
            elsewhere = sorted({n for n, e2 in econ.items() if n != num and any(same(w, p) for _, p in e2['principal'])},
                               key=lambda n: n.zfill(4))
            hint = f" (econ has him at {', '.join(elsewhere)})" if elsewhere else ''
            if any(same(w, p) for _, p in e['principal']): pass
            elif any(same(w, p) for _, p in e['minor']):
                out.append(('DISAGREE', num, f"{o['name']} → {num}/{ch}: econ (IMG_{e['img']}) has him only as a share; "
                                             f"владение: {e['owners']}{hint}"))
            else:
                out.append(('DISAGREE', num, f"{o['name']} → {num}/{ch}: econ (IMG_{e['img']}): {e['owners']}{hint}"))
            if ch and e['parts'] and ch not in e['parts']:
                out.append(('DISAGREE', num, f"{o['name']}: alphabet часть {ch}, econ {sorted(e['parts'])}"))
    for num, e in econ.items():
        linked = [who[o['id']] for o, _ in byn.get(num, [])]
        for label, p in e['principal']:
            if not p[0] or any(same(p, l) for l in linked): continue
            cand = [o for o in owners if same(who[o['id']], p)]
            if cand:
                out.append(('MISSING', num, f"econ (IMG_{e['img']}) «{label}» = {', '.join(o['name'] for o in cand)}, not linked to {num}"))
            elif num in traced:
                out.append(('MISSING', num, f"traced; econ (IMG_{e['img']}) owner «{label}» not in the alphabet"))
    order = {'CRITICAL': 0, 'DISAGREE': 1, 'MISSING': 2}
    for sev, num, msg in sorted(out, key=lambda t: (order[t[0]], t[1].zfill(4))):
        print(f'  {sev:8s} {num}: {msg}')
    print('  — ' + ', '.join(f"{k} {sum(1 for t in out if t[0] == k)}" for k in order))
