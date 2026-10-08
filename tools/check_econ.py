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
  DISAGREE  the alphabet links an owner to a number whose econ entry does not name him (a co-owner
            the notes list under «also» is agreement), or gives another часть — the econ entry wins; the record
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
TITLES = set('''князь княз княгиня граф графиня генерал майор майорша подполковник подполковница полковница
полковник капитан ротмистр поручик судья судьи сендзина земский земскаго воевода каштелян каштеляничи регент
шамбелян маршал стражник хорунжий хорунжина подстолий подстолина подстароста староста старостина старосты
староство подкоморжий подкоморич подкоморша подкоморий чешник писарь писарева гродский мостовничий ловчий
обозный комиссар асессор регистратор коллежский действительный статский тайный советник кавалер адмирал
бригадир генеральша ротмистрша возный бывший отставной шляхтич шляхта шляхты шляхетство околичные околичная
околичное околичных чиншовые чиншовая чиншовых владение владения общаго общем город город мещане мещан
иностранцы монастырь монастыри кляштор кляшторы плебания парафия церковь церкви церковная священно
священника служителей церковнослужителей покосы сенные выгоне выгонная градская мужеский мужской женский
часть части брат братьями братом детьми жена жены малолетний спорная земля пашенная пожизненном помещик
помещица помещики польских российских российскаго российской росийских росийскаго грекороссийскаго греко войск городъ выгонною землею земли губернии пинск пинский пинская пинскаго пинской речицкий
речицкая бобруйский бобруйская воскресения христова успения рождества преображения господня
пресвятой богородицы чудотворца архангела великомученицы базилианский грекороссийский римскокатолический доминиканский'''.split())
STOP5 = {re.sub(r'(.)\\1', r'\\1', t)[:5] for t in TITLES}
# first names: two people of one family share a surname, so a match needs the first name too.
# Seeded here, extended from the alphabet (its names are «Surname First [First…]»).
NAMES = {re.sub(r'(.)\1', r'\1', w)[:5] for w in '''николай васильевич михаил иван игнатий петр павел антоний франтишек федор тимофей
александр адам семен томаш иосиф осип казимир станислав викентий григорий лаврентий доминик доменик матвей
самуил леопольд агафья анна варвара мартин феликс харитон ксаверий богуслав леон король фома каэтан василий
владислав владимир марианна марьяна клара розалия фелициана войтех аполинарий кунегунда богумила виктория
героним христофор христина леонора бенедикт флориан амброжий рафал ансельм пляцид людвик людвиг алоизий
каролина елена елеонора троян дионисий дионизий куприян валериан карл кароль филип филипп максим яков
гилярий гиполит фадей тадеуш онуфрий прасковья софья сергей степан лука андрей анатолий никодим гавриил
фаддей иоанн магдалена мартын франтишка дызма фердинанд гедеон бернард аполония апполония
констанция бригида симон зигмунт'''.split()} | {'ян'}
NAMES_N = set()   # filled lazily from NAMES (see names_n())
SURNAME_END = re.compile(r'(ск|цк|ич|вич|ов|ев|ин)[а-я]*$')

def words_of(text):
    # doubled letters collapsed (Фаддей = Фадей, Аллопеус = Алопеус)
    return [re.sub(r'(.)\1', r'\1', w) for w in
            re.findall(r'[а-яёіѣ]+', text.lower().replace('ё', 'е').replace('ѣ', 'е').replace('і', 'и')
                       .replace('ь', '').replace('ъ', ''))]   # Пеньтковский = Пентковский

NM = str.maketrans('йы', 'еи')     # case/spelling slips in first names: Фаддеем ~ Фадей, Мартын ~ Мартин
def is_name(w):
    """a first name in any case form; never a word that looks like a surname (-ский/-цкий/-вич)"""
    if len(w) < 4 or re.search(r'.{3}(ск|цк|вич)', w): return False
    return w[:5].translate(NM) in NAMES_N

NAMES_N.update(n.translate(NM) for n in NAMES)

def person(text):
    """(surname stems, first-name stems) of a name in any case: first 5 / 4 letters of each word"""
    sur, first = set(), set()
    for w in words_of(text):
        if w == 'ян' or w == 'яна': first.add('ян'); continue
        if len(w) < 4 or w in TITLES or (w[:5] in STOP5 and not SURNAME_END.search(w[5:])): continue
        if is_name(w): first.add(w[:5].translate(NM))
        else: sur.add(w[:5])
    return sur, first

def alphabet_person(o):
    """alphabet names are «Surname First…»: the first word is the surname, the rest first names"""
    w = [x for x in words_of(o.get('name', '')) if x not in TITLES and (x[:5] not in STOP5 or SURNAME_END.search(x[5:]))]
    if not w: return set(), set()
    if len(w) > 1 and w[0][:5] in NAMES and w[-1][:5] not in NAMES: w = w[1:] + w[:1]   # «Павел Лежский»
    sur = {w[0][:5]}
    first = {('ян' if x == 'ян' else x[:5].translate(NM)) for x in w[1:] if len(x) >= 2 and x[:5] not in STOP5}
    NAMES.update(f for f in first if f != 'ян')
    NAMES_N.update(n.translate(NM) for n in NAMES)
    return sur, first

def _norm(st):
    """spelling-insensitive surname stem: doubled letters collapsed, unstressed а/о, е/и, т/ц merged"""
    st = re.sub(r'(.)\1', r'\1', st)
    return st.translate(str.maketrans('аиц', 'оет'))

def _lev(a, b):
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        p, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (ca != cb))
    return d[-1]

def same(a, b):
    """same person: a surname stem in common (up to one spelling slip, or two when both sides
    give the same first name), and first names agree when both sides give one"""
    fa, fb = a[1], b[1]
    if fa and fb and not ({x.translate(NM) for x in fa} & {y.translate(NM) for y in fb}): return False
    tol = 2 if (fa and fb) else 1    # a matching first name allows a second spelling slip (Залеский/Зеленский)
    def close(x, y):
        x, y = _norm(x), _norm(y)
        if min(len(x), len(y)) < 5: return x.startswith(y) or y.startswith(x)   # short surnames: Волк/Волком
        return _lev(x, y) <= tol
    return any(close(x, y) for x in a[0] for y in b[0])

def econ_names(o):
    """`econ_name` on an owner (string or list): how the notes spell an institution"""
    v = o.get('econ_name') or []
    return [v] if isinstance(v, str) else v

def load_econ(path):
    rows = {}
    for line in open(path):
        if line.startswith('#') or line.startswith('num\t') or not line.strip(): continue
        num, parts, img, owners, also = (line.rstrip('\n').split('\t') + ['', ''])[:5]
        rows[nk(num)] = dict(parts={int(p) for p in parts.split(',') if p.strip().isdigit()},
                             img=img, owners=owners, also=also,
                             principal=[(x.strip(), person(x)) for x in owners.split(';') if x.strip()],
                             minor=[(x.strip(), person(x)) for x in re.split(r'[;,]| и ', also) if x.strip()])
    return rows

uezds = sys.argv[1:] or [u for u, p in PATHS.items() if os.path.exists(p[2])]
for u in uezds:
    op, pp, ep = PATHS[u]
    if not os.path.exists(ep): print(f'\n===== {u}: no {ep} — skipped'); continue
    owners = json.load(open(op))['owners']
    feats = json.load(open(pp))['features']
    traced = {nk(f['properties'].get('num')) for f in feats}
    # institutions and староства («Староство Речицкое (гр. Юдицкий)») are matched on every word
    who = {o['id']: person(' '.join(filter(None, [o.get('name'), o.get('name_ru'), *econ_names(o)]))) if o.get('inst') or re.match(r'(староств|кляштор|плебан|монаст|церк|казен)', o.get('name', '').lower()) or '(' in o.get('name', '')
           else alphabet_person(o) for o in owners}
    econ = load_econ(ep)          # after `who`: alphabet_person() extends NAMES
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
            if not any(same(w, p) for p in every) and not any(
                    n in e2['owners'] + e2['also'] for n in econ_names(o) for e2 in econ.values()):
                kin = sorted({n for n, e2 in econ.items() for _, p in e2['principal'] + e2['minor'] if same((w[0], set()), p)},
                             key=lambda n: n.zfill(4))
                if kin:   # surname is there, first name differs
                    out.append(('DISAGREE', num, f"{o['name']} → {num}/{ch}: econ has the surname with another first name at "
                                                 f"{', '.join(kin)}" + (f" (IMG_{e['img']}: {e['owners']})" if e else '')))
                else:
                    out.append(('CRITICAL', num, f"{o['name']} → {num}/{ch}: not in the economic notes at all"))
                continue
            if not e:
                out.append(('DISAGREE', num, f"{o['name']} → {num}/{ch}: no econ entry for {num}"))
                continue
            elsewhere = sorted({n for n, e2 in econ.items() if n != num and any(same(w, p) for _, p in e2['principal'])},
                               key=lambda n: n.zfill(4))
            hint = f" (econ has him at {', '.join(elsewhere)})" if elsewhere else ''
            # `econ_name` on an owner: how the notes spell an institution whose name has no distinctive word
            if econ_names(o) and any(n in e['owners'] + ' ' + e['also'] for n in econ_names(o)): pass
            elif any(same(w, p) for _, p in e['principal']): pass
            elif any(same(w, p) for _, p in e['minor']):
                pass   # a co-owner the notes confirm; a missing principal is reported below as MISSING
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
