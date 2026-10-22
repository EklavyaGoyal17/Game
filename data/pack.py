"""Compress world2.json (delta-encoded polylines) and split it into world-a.json (map, roads, POIs) and world-b.json (buildings)."""
import json, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
W = json.load(open('world2.json'))
def delta(p):
    out = [p[0], p[1]]
    for i in range(2, len(p), 2): out += [p[i] - p[i - 2], p[i + 1] - p[i - 1]]
    return out
for e in W['edges']: e['p'] = delta(e['p'])
for b in W['buildings']:
    b['p'] = delta(b['p']); b.pop('r', None)
    if 'ln' in b and 's' not in b: b.pop('ln')
for w in W['walks']: w['p'] = delta(w['p'])
W['meta']['delta'] = 1
dump = lambda o: json.dumps(o, separators=(',', ':'), ensure_ascii=False)
a = {k: v for k, v in W.items() if k != 'buildings'}
b = {'buildings': W['buildings']}
for name, part in (('world-a.json', a), ('world-b.json', b)):
    s = dump(part); open(name, 'w').write(s); print(name, round(len(s) / 1e6, 2), 'MB')
for k in W: print(' ', k, round(len(dump(W[k])) / 1e6, 2))
