"""Turn the OSM-style Vapi extract (osm_vapi.pkl from overture_to_osm.py) into the game's world2.json:
road graph, water / sea / parks, rails with viaduct heights, airport, buildings with heights and styles, trees, lamps, POIs.
Adapted from Madras Hustle's process2.py for Vapi + Daman (Gujarat / DNHDD): sea to the west, GIDC industrial estates,
Daman's forts and airfield, Western Railway + the Mumbai-Ahmedabad bullet train viaduct."""
import pickle, math, json, hashlib, collections, heapq, os, re
from shapely.geometry import Polygon, LineString, Point, box, MultiPolygon
from shapely.ops import unary_union, linemerge, split, polygonize
from shapely.strtree import STRtree
from shapely.prepared import prep

os.chdir(os.path.dirname(os.path.abspath(__file__)))
nodes, ways, rels = pickle.load(open('osm_vapi.pkl', 'rb'))
_W, _S, _E, _N = (float(v) for v in os.environ.get('BBOX', '72.805,20.315,72.99,20.445').split(','))
LAT0, LON0 = round((_S + _N) / 2, 6), round((_W + _E) / 2, 6)
KX = 111320 * math.cos(math.radians(LAT0)); KZ = 110574
def proj(nid):
    la, lo, _ = nodes[nid]
    return ((lo - LON0) * KX, (LAT0 - la) * KZ)
BB = dict(s=_S + 0.001, n=_N - 0.001, w=_W + 0.001, e=_E - 0.001)
CORE = dict(BB)   # keep every footprint: Vapi is mostly low-rise, small buildings are the city
VAPI_CENTRE = (20.3716, 72.9167)   # Overture division point for Vapi (locality); Chala / Vapi town towers cluster around it
XMIN, XMAX = (BB['w'] - LON0) * KX, (BB['e'] - LON0) * KX
ZMIN, ZMAX = (LAT0 - BB['n']) * KZ, (LAT0 - BB['s']) * KZ
WORLD = box(XMIN, ZMIN, XMAX, ZMAX)
print('world', XMIN, XMAX, ZMIN, ZMAX)

def h01(*a):
    return int(hashlib.md5(('|'.join(map(str, a))).encode()).hexdigest()[:8], 16) / 0xffffffff

def way_coords(nd):
    return [proj(n) for n in nd if n in nodes]

def ring_from_rel(members):
    """stitch outer/inner ways of multipolygon into polygons (outer minus inner)"""
    outs, ins = [], []
    for typ, ref, role in members:
        if typ == 'way' and ref in ways:
            c = way_coords(ways[ref][0])
            if len(c) >= 2: (ins if role == 'inner' else outs).append(LineString(c))
    if not outs: return []
    polys = list(polygonize(unary_union(outs)))
    if ins:
        holes = list(polygonize(unary_union(ins)))
        if holes:
            hu = unary_union(holes)
            res = []
            for p in polys:
                d = p.difference(hu)
                res += [g for g in getattr(d, 'geoms', [d]) if g.geom_type == 'Polygon']
            polys = res
    return polys

def q(v): return int(round(v * 10))  # decimeters

# ---------------- ROADS ----------------
DRIVE = {'trunk', 'primary', 'secondary', 'tertiary', 'trunk_link', 'primary_link', 'secondary_link',
         'tertiary_link', 'residential', 'unclassified', 'living_street', 'service', 'road'}
TRAFFIC = DRIVE - {'service'}
WALK = {'footway', 'pedestrian', 'path', 'steps', 'cycleway'}
CLS = {'trunk': 0, 'primary': 0, 'trunk_link': 2, 'primary_link': 2, 'secondary': 1, 'secondary_link': 2,
       'tertiary': 2, 'tertiary_link': 3, 'residential': 3, 'unclassified': 3, 'road': 3, 'living_street': 4,
       'service': 5, 'pedestrian': 6, 'footway': 7, 'path': 7, 'steps': 7, 'cycleway': 7}
DEFW = {0: 18, 1: 12.5, 2: 9, 3: 6.5, 4: 5.2, 5: 4.4, 6: 5, 7: 2.4}

def road_width(t, c):
    hw = t.get('highway', '')
    ow = t.get('oneway') in ('yes', '1', '-1', 'true')
    try:
        w = float(t.get('width', '').replace('m', '').strip())
        if 3 <= w <= 45: return w
    except: pass
    if t.get('lanes'):
        try:
            l = int(t['lanes'].split(';')[0])
            w = l * 3.4 + (1.6 if (not ow and l >= 4) else 0) + (0.8 if c <= 1 else 0)
            return max(w, 3.6)
        except: pass
    if hw == 'trunk': w = 21
    elif hw == 'primary': w = 17
    elif hw == 'secondary': w = 12.5
    elif hw == 'tertiary': w = 9
    elif hw.endswith('_link'): w = 7.5
    else: w = DEFW[c]
    if ow and c <= 2 and not hw.endswith('_link'): w = max(7, w * 0.55)
    return w

road_ways = {}
for wid, (nd, t) in ways.items():
    hw = t.get('highway')
    if hw in DRIVE or hw in WALK:
        if t.get('area') == 'yes': continue
        if t.get('tunnel') in ('yes', 'building_passage'): continue
        if hw == 'service' and t.get('service') in ('parking_aisle', 'drive-through'): continue
        nd2 = [n for n in nd if n in nodes]
        if len(nd2) < 2: continue
        road_ways[wid] = (nd2, t)

# elevated detection
def way_len(nd):
    c = way_coords(nd); return sum(math.dist(c[i], c[i + 1]) for i in range(len(c) - 1))
elev_ways = set()
for wid, (nd, t) in road_ways.items():
    if t.get('bridge') and t.get('highway') in DRIVE:
        try: layer = int(t.get('layer', '1'))
        except: layer = 1
        nm = (t.get('name') or '').lower()
        if layer >= 1 and ('flyover' in nm or way_len(nd) > 160):
            elev_ways.add(wid)
ground_nodes = set()
for wid, (nd, t) in road_ways.items():
    if wid not in elev_ways and t.get('highway') in DRIVE:
        ground_nodes.update(nd)
eadj = collections.defaultdict(list)
for wid in elev_ways:
    nd = road_ways[wid][0]
    for a, b in zip(nd, nd[1:]):
        d = math.dist(proj(a), proj(b)); eadj[a].append((b, d)); eadj[b].append((a, d))
dist = {}
pq = []
for n in eadj:
    if n in ground_nodes or len(eadj[n]) == 1:
        dist[n] = 0; heapq.heappush(pq, (0, n))
while pq:
    d, n = heapq.heappop(pq)
    if d > dist.get(n, 1e18): continue
    for m, w in eadj[n]:
        if d + w < dist.get(m, 1e18): dist[m] = d + w; heapq.heappush(pq, (d + w, m))
def node_h(n):
    if n not in dist: return 0.0
    return round(min(6.8, dist[n] * 0.085), 2)

# split into edges at junctions
use = collections.Counter()
for wid, (nd, t) in road_ways.items():
    if t.get('highway') in DRIVE:
        for n in nd: use[n] += 1
        use[nd[0]] += 1; use[nd[-1]] += 1
names = []; name_idx = {}
def nidx(s):
    if not s: return -1
    if s not in name_idx: name_idx[s] = len(names); names.append(s)
    return name_idx[s]

edges = []  # dict
gnode_id = {}; gnodes = []
def gid(n):
    if n not in gnode_id:
        gnode_id[n] = len(gnodes); x, z = proj(n); gnodes.append([q(x), q(z), int(node_h(n) * 10)])
    return gnode_id[n]

walk_lines = []
for wid, (nd, t) in road_ways.items():
    hw = t['highway']; c = CLS[hw]; w = road_width(t, c)
    if hw in WALK:
        cc = way_coords(nd)
        ls = LineString(cc).intersection(WORLD)
        if ls.is_empty: continue
        for g in getattr(ls, 'geoms', [ls]):
            if g.geom_type == 'LineString' and len(g.coords) >= 2:
                walk_lines.append({'p': [v for x, z in g.coords for v in (q(x), q(z))], 'w': q(w), 'c': c})
        continue
    ow = 0
    if t.get('oneway') in ('yes', '1', 'true') or t.get('junction') in ('roundabout', 'circular'): ow = 1
    if t.get('oneway') == '-1': ow = -1
    if c <= 1 and t.get('oneway') is None and t.get('junction') is None: ow = 0
    elev = wid in elev_ways
    # split points
    cuts = [0] + [i for i in range(1, len(nd) - 1) if use[nd[i]] > 1] + [len(nd) - 1]
    for a, b in zip(cuts, cuts[1:]):
        seg = nd[a:b + 1]
        pts = [proj(n) for n in seg]
        # skip edges fully outside world (with margin)
        if all(not (XMIN - 30 < x < XMAX + 30 and ZMIN - 30 < z < ZMAX + 30) for x, z in pts): continue
        hs = [node_h(n) if elev else 0 for n in seg]
        e = {'a': gid(seg[0]), 'b': gid(seg[-1]), 'p': [v for x, z in pts for v in (q(x), q(z))],
             'w': q(w), 'c': c, 'o': ow, 'n': nidx(t.get('name') or t.get('ref'))}
        if elev and max(hs) > 0.3:
            e['h'] = [int(h * 10) for h in hs]
        if (t.get('bridge') and not elev) or t.get('name', '').endswith('Bridge'): e['br'] = 1
        if t.get('junction') == 'roundabout': e['rb'] = 1
        edges.append(e)
print('edges', len(edges), 'gnodes', len(gnodes), 'elevated edges', sum(1 for e in edges if 'h' in e), 'walk', len(walk_lines))

# largest connected component of traffic graph
adj = collections.defaultdict(set)
for i, e in enumerate(edges):
    if e['c'] <= 4:
        adj[e['a']].add(e['b']); adj[e['b']].add(e['a'])
seen = set(); best = set()
for s in adj:
    if s in seen: continue
    comp = {s}; st = [s]
    while st:
        u = st.pop()
        for v in adj[u]:
            if v not in comp: comp.add(v); st.append(v)
    seen |= comp
    if len(comp) > len(best): best = comp
for e in edges:
    if e['c'] <= 4 and e['a'] in best and e['b'] in best: e['t'] = 1
print('traffic edges', sum(1 for e in edges if e.get('t')))

# ---- street names: most Vapi roads come from TomTom without names. Place listings' address lines ("Koparli Road",
# "Vapi-Daman Main Road") vote for the nearest drivable road; names then spread along straight continuations at junctions.
elines = [LineString([(e['p'][i] / 10, e['p'][i + 1] / 10) for i in range(0, len(e['p']), 2)]) for e in edges]
etree = STRtree(elines)
votes = collections.defaultdict(collections.Counter)
for nid, (la, lo, t) in nodes.items():
    if not t or not t.get('addr_street'): continue
    pt = Point(*proj(nid)); best, bd = None, 45.0
    for i in etree.query(pt.buffer(45)):
        if edges[i]['c'] > 4: continue
        d = elines[i].distance(pt)
        if d < bd: bd, best = d, i
    if best is not None: votes[best][t['addr_street']] += 1
named0 = sum(1 for e in edges if e['n'] >= 0); voted = 0
for i, cnt in votes.items():
    if edges[i]['n'] < 0: edges[i]['n'] = nidx(cnt.most_common(1)[0][0]); voted += 1
def end_dir(i, at_a):
    cs = list(elines[i].coords); a, b = (cs[0], cs[1]) if at_a else (cs[-1], cs[-2])
    dx, dz = b[0] - a[0], b[1] - a[1]; l = math.hypot(dx, dz) or 1; return dx / l, dz / l
node_edges = collections.defaultdict(list)
for i, e in enumerate(edges):
    if e['c'] <= 5: node_edges[e['a']].append((i, True)); node_edges[e['b']].append((i, False))
spread = 0; budget = collections.Counter()
for _ in range(80):
    changed = 0
    for i, e in enumerate(edges):
        if e['n'] < 0 or e['c'] > 5: continue
        for at_a in (True, False):
            nd = e['a'] if at_a else e['b']; d0 = end_dir(i, at_a); best, bdef = None, 32
            for j, ja in node_edges[nd]:
                if j == i: continue
                d1 = end_dir(j, ja); defl = math.degrees(math.acos(max(-1, min(1, -(d0[0] * d1[0] + d0[1] * d1[1])))))
                if defl < bdef and abs(edges[j]['c'] - e['c']) <= 1: bdef, best = defl, j
            if best is not None and edges[best]['n'] < 0 and budget[e['n']] < 6000:
                edges[best]['n'] = e['n']; budget[e['n']] += elines[best].length; changed += 1; spread += 1
    if not changed: break
print('street names: osm/tomtom', named0, '+ from addresses', voted, '+ spread', spread, '=', sum(1 for e in edges if e['n'] >= 0), '/', len(edges))

# road polygons for tree/building checks
road_polys = []
for e in edges:
    p = e['p']; cc = [(p[i] / 10, p[i + 1] / 10) for i in range(0, len(p), 2)]
    if 'h' in e and max(e['h']) > 30: continue
    road_polys.append(LineString(cc).buffer(e['w'] / 20 + 0.5, cap_style=2))
road_union = unary_union(road_polys)

# ---------------- AREAS ----------------
def area_polys_for(pred):
    out = []
    for wid, (nd, t) in ways.items():
        if pred(t) and len(nd) >= 4 and nd[0] == nd[-1]:
            c = way_coords(nd)
            if len(c) >= 4:
                p = Polygon(c)
                if p.is_valid and p.area > 1: out.append((p, t, wid))
    for rid, (m, t) in rels.items():
        if t.get('type') == 'multipolygon' and pred(t):
            for p in ring_from_rel(m): out.append((p, t, 'r%d' % rid))
    return out

def is_water(t):
    return t.get('natural') == 'water' or t.get('waterway') == 'riverbank' or t.get('landuse') in ('reservoir', 'basin')
water = [p for p, t, _ in area_polys_for(is_water)]
for wid, (nd, t) in ways.items():
    ww = t.get('waterway')
    if ww in ('river', 'canal'):
        c = way_coords(nd)
        if len(c) < 2: continue
        nm = (t.get('name') or '')
        w = 70 if ww == 'river' and 'Daman Ganga' in nm else (40 if ww == 'river' and 'Kolak' in nm else (18 if ww == 'river' else 7))
        water.append(LineString(c).buffer(w / 2))
# sea: Overture's ocean polygon (the Arabian Sea lies west of Daman), stretched past the west edge of the map
sea_parts = [p for p, t, _ in area_polys_for(lambda t: t.get('natural') == 'sea')]
sea = unary_union(sea_parts).buffer(0) if sea_parts else Polygon()
if not sea.is_empty:
    sea = unary_union([sea, box(XMIN - 2000, ZMIN - 300, sea.bounds[0] + 40, ZMAX + 300)]).buffer(0)
SEA_SIDE = 'w' if not sea.is_empty and sea.centroid.x < (XMIN + XMAX) / 2 else 'e'
print('sea area', round(sea.area), sea.is_valid, 'side', SEA_SIDE)
water_u = unary_union(water).difference(sea).intersection(WORLD).simplify(1.0)

def green_pred(t):
    return t.get('leisure') in ('park', 'garden', 'playground', 'recreation_ground', 'golf_course') or \
        t.get('landuse') in ('grass', 'village_green', 'recreation_ground', 'cemetery', 'forest', 'meadow') or \
        t.get('natural') in ('wood', 'scrub', 'grassland', 'wetland')
greens = [(p, t) for p, t, _ in area_polys_for(green_pred)]
pitches = [(p, t) for p, t, _ in area_polys_for(lambda t: t.get('leisure') in ('pitch', 'stadium', 'sports_centre'))]
beach = [p for p, t, _ in area_polys_for(lambda t: t.get('natural') in ('beach', 'sand'))]
platforms = [p for p, t, _ in area_polys_for(lambda t: t.get('railway') == 'platform' or t.get('public_transport') == 'platform' and t.get('railway'))]
pools = [p for p, t, _ in area_polys_for(lambda t: t.get('leisure') == 'swimming_pool')]

def enc_poly(p, tol=0.6):
    out = []
    p = p.intersection(WORLD)
    for g in getattr(p, 'geoms', [p]):
        if g.geom_type != 'Polygon' or g.area < 4: continue
        g = g.simplify(tol)
        if g.is_empty or g.geom_type != 'Polygon': continue
        c = list(g.exterior.coords)[:-1]
        if len(c) < 3: continue
        holes = [[v for x, z in list(h.coords)[:-1] for v in (q(x), q(z))] for h in g.interiors if Polygon(h).area > 20]
        d = {'p': [v for x, z in c for v in (q(x), q(z))]}
        if holes: d['hl'] = holes
        out.append(d)
    return out

areas = {'water': [], 'sea': enc_poly(sea, 2), 'green': [], 'pitch': [], 'beach': [], 'platform': [], 'pool': []}
for g in getattr(water_u, 'geoms', [water_u]): areas['water'] += enc_poly(g, 1.0)
for p, t in greens: areas['green'] += enc_poly(p)
for p, t in pitches: areas['pitch'] += enc_poly(p)
for p in beach: areas['beach'] += enc_poly(p, 1.5)
for p in platforms: areas['platform'] += enc_poly(p, 0.3)
for p in pools: areas['pool'] += enc_poly(p, 0.3)
print({k: len(v) for k, v in areas.items()})

# rail lines -> long merged lines with elevation (viaducts)
rail_ways = {}
for wid, (nd, t) in ways.items():
    if t.get('railway') in ('rail', 'light_rail', 'subway') and t.get('tunnel') not in ('yes',) and t.get('service') not in ('spur', 'yard', 'siding', 'crossover') and t.get('usage') not in ('industrial',):
        nd2 = [n for n in nd if n in nodes]
        if len(nd2) >= 2: rail_ways[wid] = (nd2, t)
r_elev = set(wid for wid, (nd, t) in rail_ways.items() if t.get('bridge') and (t.get('bridge') == 'viaduct' or way_len(nd) > 250))
r_ground = set(); [r_ground.update(nd) for wid, (nd, t) in rail_ways.items() if wid not in r_elev]
radj = collections.defaultdict(list)
for wid in r_elev:
    nd = rail_ways[wid][0]
    for a_, b_ in zip(nd, nd[1:]):
        d = math.dist(proj(a_), proj(b_)); radj[a_].append((b_, d)); radj[b_].append((a_, d))
rdist = {}; pq = []
for n in radj:
    if n in r_ground or len(radj[n]) == 1: rdist[n] = 0; heapq.heappush(pq, (0, n))
while pq:
    d, n = heapq.heappop(pq)
    if d > rdist.get(n, 1e18): continue
    for m, w in radj[n]:
        if d + w < rdist.get(m, 1e18): rdist[m] = d + w; heapq.heappush(pq, (d + w, m))
coord_h = {}
for wid, (nd, t) in rail_ways.items():
    cap = 15.0 if t.get('highspeed') == 'yes' else 9.0   # the bullet-train viaduct runs ~15 m up, well above the Western Railway
    for n in nd:
        x, z = proj(n); coord_h[(round(x, 2), round(z, 2))] = round(min(cap, rdist.get(n, 0) * 0.03), 2) if wid in r_elev or n in rdist else 0.0
hsr_lines = unary_union([LineString(way_coords(nd)) for nd, t in rail_ways.values() if t.get('highspeed') == 'yes'] or [Point(1e9, 1e9)])
freight_lines = unary_union([LineString(way_coords(nd)) for nd, t in rail_ways.values() if t.get('usage') == 'freight'] or [Point(1e9, 1e9)])
rail_lines_raw = [LineString(way_coords(nd)) for nd, t in rail_ways.values()]
def strokes(lines, max_turn=35):
    """chain rail pieces through junctions by the straightest continuation, so a main line stays one line through a station yard"""
    m = linemerge(unary_union(lines)); parts = [g for g in getattr(m, 'geoms', [m]) if g.length > 0]
    key = lambda c: (round(c[0], 1), round(c[1], 1))
    ends = collections.defaultdict(list)
    for i, p in enumerate(parts): cs = p.coords; ends[key(cs[0])].append((i, 0)); ends[key(cs[-1])].append((i, 1))
    def away(i, e):   # unit direction leaving the junction into part i
        p = parts[i]; d = min(25.0, p.length)
        a = p.interpolate(0 if e == 0 else p.length); b = p.interpolate(d if e == 0 else p.length - d)
        dx, dz = b.x - a.x, b.y - a.y; l = math.hypot(dx, dz) or 1; return dx / l, dz / l
    pair = {}
    for k, lst in ends.items():
        if len(lst) < 2: continue
        cands = []
        for ai in range(len(lst)):
            for bi in range(ai + 1, len(lst)):
                (ia, ea), (ib, eb) = lst[ai], lst[bi]
                if ia == ib: continue
                da, db = away(ia, ea), away(ib, eb)
                defl = math.degrees(math.acos(max(-1, min(1, -(da[0] * db[0] + da[1] * db[1])))))
                if defl < max_turn: cands.append((defl, lst[ai], lst[bi]))
        for defl, a, b in sorted(cands):
            if a not in pair and b not in pair: pair[a] = b; pair[b] = a
    seen, out = set(), []
    def walk(i, e_in):
        cs = []
        while i not in seen:
            seen.add(i); pc = list(parts[i].coords)
            if e_in == 1: pc = pc[::-1]
            cs += pc if not cs else pc[1:]
            nxt = pair.get((i, 1 - e_in))
            if not nxt: break
            i, e_in = nxt
        return cs
    for i in range(len(parts)):   # start from free ends first so lines run end to end
        for e in (0, 1):
            if i not in seen and (i, e) not in pair: out.append(walk(i, e))
    for i in range(len(parts)):
        if i not in seen: out.append(walk(i, 0))
    return [LineString(c) for c in out if len(c) >= 2]
merged = strokes(rail_lines_raw)
rails = []
for g in merged:
    g2 = g.intersection(WORLD)
    for gg in getattr(g2, 'geoms', [g2]):
        if gg.geom_type != 'LineString' or gg.length < 120: continue
        cs = list(gg.coords)
        hs = [coord_h.get((round(x, 2), round(z, 2)), None) for x, z in cs]
        # fill gaps by nearest known
        last = 0
        for i in range(len(hs)):
            if hs[i] is None: hs[i] = last
            last = hs[i]
        rl = {'p': [v for x, z in cs for v in (q(x), q(z))], 'h': [int(h * 10) for h in hs], 'L': int(gg.length)}
        mid = gg.interpolate(0.5, normalized=True)
        if hsr_lines.distance(mid) < 3: rl['hs'] = 1          # Mumbai-Ahmedabad high-speed rail (bullet train)
        elif freight_lines.distance(mid) < 3: rl['fr'] = 1    # Western Dedicated Freight Corridor
        rails.append(rl)
rails.sort(key=lambda r: -r['L'])
print('rails', len(rails), 'longest', [r['L'] for r in rails[:8]], 'elevated ways', len(r_elev))
# aeroways
air = {'runway': [], 'taxi': [], 'apron': [], 'helipad': []}
for wid, (nd, t) in ways.items():
    a_ = t.get('aeroway')
    if a_ in ('runway', 'taxiway') and not (nd[0] == nd[-1] and len(nd) > 4):
        c = way_coords(nd)
        if len(c) < 2: continue
        try: w = float(t.get('width', '0').replace('m', ''))
        except: w = 0
        if not w: w = 45 if a_ == 'runway' else 18
        air['runway' if a_ == 'runway' else 'taxi'].append({'p': [v for x, z in c for v in (q(x), q(z))], 'w': q(w), 'n': t.get('ref', '')})
for p, t, _ in area_polys_for(lambda t: t.get('aeroway') in ('apron',) or (t.get('aeroway') == 'runway')):
    air['apron'] += enc_poly(p, 1.0)
for nid, (la, lo, t) in nodes.items():
    if t and t.get('aeroway') == 'helipad':
        x, z = proj(nid); air['helipad'].append([q(x), q(z)])
for p, t, _ in area_polys_for(lambda t: t.get('aeroway') == 'helipad'):
    air['helipad'].append([q(p.centroid.x), q(p.centroid.y)])
print('air', {k: len(v) for k, v in air.items()})
# piers
piers = []
for wid, (nd, t) in ways.items():
    if t.get('man_made') in ('pier', 'breakwater', 'groyne'):
        c = way_coords(nd)
        if len(c) < 2: continue
        if nd[0] == nd[-1] and len(c) > 3: piers += [dict(d, a=1) for d in enc_poly(Polygon(c).buffer(0), 0.5)]
        else: piers.append({'p': [v for x, z in c for v in (q(x), q(z))], 'w': q(8 if t.get('man_made') == 'pier' else 10)})
print('piers', len(piers))
# shops & services
shops = []
def shop_type(t):
    sh = t.get('shop'); a_ = t.get('amenity')
    if a_ == 'fuel': return 'fuel'
    if a_ == 'bank': return 'bank'
    if a_ == 'atm': return 'atm'
    if sh in ('convenience', 'supermarket', 'general', 'kiosk'): return 'store'
    if sh in ('jewelry', 'jewellery'): return 'jewel'
    if sh in ('car', 'car_repair', 'motorcycle'): return 'cars' if sh != 'car_repair' else 'repair'
    if sh in ('clothes', 'fashion', 'boutique'): return 'clothes'
    if sh in ('electronics', 'mobile_phone', 'computer'): return 'electronics'
    if a_ in ('restaurant', 'fast_food', 'cafe'): return 'food'
    return None
seen_sh = set()
def add_shop(t, x, z):
    ty = shop_type(t)
    if not ty or not (XMIN + 20 < x < XMAX - 20 and ZMIN + 20 < z < ZMAX - 20): return
    k = (ty, round(x / 25), round(z / 25))
    if k in seen_sh: return
    seen_sh.add(k); shops.append({'t': ty, 'n': (t.get('name:en') or t.get('name') or '')[:40], 'x': q(x), 'z': q(z)})
for nid, (la, lo, t) in nodes.items():
    if t and shop_type(t): x, z = proj(nid); add_shop(t, x, z)
for wid, (nd, t) in ways.items():
    if shop_type(t) and len(nd) > 2:
        c = way_coords(nd)
        if len(c) > 2:
            try: cen = Polygon(c).centroid; add_shop(t, cen.x, cen.y)
            except: pass
print('shops', collections.Counter(x['t'] for x in shops))

# ---------------- LANDMARKS / POIs ----------------
pois = []
def poi_type(t):
    if t.get('railway') == 'station' or t.get('public_transport') == 'station' and t.get('railway'): return 'station'
    if t.get('station') == 'subway' or t.get('railway') == 'subway_entrance': return 'metro'
    a = t.get('amenity')
    if a in ('hospital',): return 'hospital'
    if a in ('police',): return 'police'
    if a in ('cinema', 'theatre'): return 'cinema'
    if a in ('place_of_worship',): return 'worship'
    if a in ('college', 'university'): return 'college'
    if a in ('marketplace',): return 'market'
    if a in ('fuel',): return 'fuel'
    if t.get('tourism') in ('museum', 'attraction', 'gallery'): return 'sight'
    if t.get('tourism') == 'hotel': return 'hotel'
    if t.get('shop') in ('mall', 'department_store'): return 'mall'
    if t.get('leisure') == 'stadium': return 'stadium'
    if t.get('aeroway') in ('aerodrome', 'terminal'): return 'airport'
    if t.get('harbour') or t.get('landuse') == 'port' or t.get('industrial') == 'port': return 'port'
    if t.get('historic'): return 'sight'
    return None
seen_names = set()
def add_poi(t, x, z, area=0):
    ty = poi_type(t); nm = t.get('name:en') or t.get('name')
    if not ty or not nm: return
    if not (XMIN < x < XMAX and ZMIN < z < ZMAX): return
    key = (ty, nm)
    if key in seen_names: return
    seen_names.add(key)
    pois.append({'t': ty, 'n': nm, 'x': q(x), 'z': q(z), 'a': int(area)})
for wid, (nd, t) in ways.items():
    if poi_type(t) and len(nd) > 2:
        c = way_coords(nd)
        try:
            p = Polygon(c); cen = p.centroid; add_poi(t, cen.x, cen.y, p.area)
        except: pass
for rid, (m, t) in rels.items():
    if poi_type(t) and t.get('type') == 'multipolygon':
        ps = ring_from_rel(m)
        if ps:
            u = unary_union(ps); add_poi(t, u.centroid.x, u.centroid.y, u.area)
for nid, (la, lo, t) in nodes.items():
    if t and poi_type(t):
        x, z = proj(nid); add_poi(t, x, z)
places = []
for nid, (la, lo, t) in nodes.items():
    if t and t.get('place') in ('suburb', 'neighbourhood', 'quarter') and t.get('name'):
        x, z = proj(nid)
        if XMIN < x < XMAX and ZMIN < z < ZMAX:
            places.append({'n': t.get('name:en') or t['name'], 'x': q(x), 'z': q(z), 's': 1 if t['place'] == 'suburb' else 0})
print('pois', collections.Counter(p['t'] for p in pois), 'places', len(places))

# ---------------- BUILDINGS ----------------
landmark_rules = [  # (substring in name, style, min floors)
    ('fort', 'fort', 3), ('bom jesus', 'saracenic_w', 3), ('our lady', 'saracenic_w', 3), ('church', 'saracenic_w', 2),
    ('lighthouse', 'tower', 8), ('stadium', 'stadium', 5), ('cricket ground', 'stadium', 3), ('sports complex', 'stadium', 4),
    ('railway station', 'modern', 2),
    ('mall', 'modern', 4), ('shopping', 'modern', 3), ('hospital', 'modern', 4), ('airport', 'modern', 3),
]
bpolys = []
for wid, (nd, t) in ways.items():
    if 'building' in t and len(nd) >= 4 and nd[0] == nd[-1] and t.get('building') not in ('roof', 'construction', 'no'):
        c = way_coords(nd)
        try:
            p = Polygon(c)
            if not p.is_valid: p = p.buffer(0)
            if p.geom_type == 'Polygon' and p.area > 6: bpolys.append((p, t, wid))
        except: pass
for rid, (m, t) in rels.items():
    if t.get('type') == 'multipolygon' and 'building' in t:
        for p in ring_from_rel(m):
            if p.area > 6: bpolys.append((p, t, 'r%d' % rid))
print('buildings raw', len(bpolys))

# commercial landuse & names of containing areas (for landmark styling of unnamed parts)
named_areas = []
for p, t, _ in area_polys_for(lambda t: bool(t.get('name')) and (t.get('amenity') or t.get('railway') or t.get('tourism') or t.get('landuse') in ('railway',) or t.get('leisure') == 'stadium' or t.get('historic') or t.get('aeroway'))):
    named_areas.append((p, (t.get('name:en') or t.get('name')).lower()))
na_tree = STRtree([p for p, _ in named_areas]) if named_areas else None
comm = [p for p, t, _ in area_polys_for(lambda t: t.get('landuse') in ('commercial', 'retail'))]
comm_u = prep(unary_union(comm)) if comm else None
# GIDC: Vapi's chemical / paper / pharma estates are long low sheds, not apartment blocks
ind = [p for p, t, _ in area_polys_for(lambda t: t.get('landuse') in ('industrial', 'quarry'))]
works_pts = [Point(*proj(nid)).buffer(140) for nid, (la, lo, t) in nodes.items() if t and t.get('man_made') == 'works']
ind = ind + works_pts   # factories listed by name (manufacturers, chemical plants, godowns) mark their surroundings as estate land
ind_u = prep(unary_union(ind).buffer(15)) if ind else None
resid = [p for p, t, _ in area_polys_for(lambda t: t.get('landuse') == 'residential')]
resid_u = prep(unary_union(resid)) if resid else None
major = prep(unary_union([LineString([(e['p'][i] / 10, e['p'][i + 1] / 10) for i in range(0, len(e['p']), 2)]) for e in edges if e['c'] <= 1]).buffer(45))
home_pt = Point(0, 0)
vx_, vz_ = (VAPI_CENTRE[1] - LON0) * KX, (LAT0 - VAPI_CENTRE[0]) * KZ
# place-of-worship / landmark POIs mark the footprint they stand in (temples get a shikhara, churches the colonial facade)
poi_marks = []
for nid, (la, lo, t) in nodes.items():
    if not t: continue
    if t.get('amenity') == 'place_of_worship' or t.get('historic') in ('fort',) or t.get('leisure') == 'stadium' or t.get('shop') == 'mall' or t.get('amenity') == 'hospital':
        x, z = proj(nid); poi_marks.append((Point(x, z), t))

# the old fort walls of Moti and Nani Daman stand as thick stone ramparts
for wid, (nd, t) in list(ways.items()):
    if t.get('barrier') == 'city_wall':
        c = way_coords(nd)
        if len(c) < 2: continue
        rp = LineString(c).buffer(2.6, cap_style=2, join_style=2)
        for g in getattr(rp, 'geoms', [rp]):
            if g.geom_type == 'Polygon' and g.area > 6: bpolys.append((g, {'building': 'wall', 'name': 'Daman Fort Wall', 'height': '8'}, 'w%d' % wid))
# POI footprints: the building a temple / church / fort / stadium / mall point stands in takes its name and kind
b_tree = STRtree([p for p, _, _ in bpolys])
poi_tags = {}
for pt, t in poi_marks:
    for i in b_tree.query(pt):
        if bpolys[i][0].contains(pt) and bpolys[i][0].area < 60000: poi_tags.setdefault(i, t); break
# Daman airport terminal: the largest building beside the apron that is not on the airside
aprons = [p for p, t, _ in area_polys_for(lambda t: t.get('aeroway') == 'apron')]
term_i = -1
if aprons:
    ap_u = unary_union(aprons); best = 0
    for i in b_tree.query(ap_u.buffer(250)):
        p = bpolys[i][0]
        if p.distance(ap_u) < 250 and not p.intersects(ap_u) and 150 < p.area < 20000 and p.area > best: best = p.area; term_i = i
    if term_i >= 0:
        poi_tags[term_i] = {'aeroway': 'terminal', 'name': 'Daman Airport Terminal'}
        cen = bpolys[term_i][0].centroid
        pois.append({'t': 'airport', 'n': 'Daman Airport Terminal', 'x': q(cen.x), 'z': q(cen.y), 'a': int(bpolys[term_i][0].area)})
buildings = []
home_idx = -1; home_best = -1
for bi_, (p, t, wid) in enumerate(bpolys):
    cen = p.centroid
    if not WORLD.contains(cen): continue
    pt_ = poi_tags.get(bi_)
    if pt_:
        t = dict(t, **{k: v for k, v in pt_.items() if k != 'name'})
        if not t.get('name') and pt_.get('name'): t['name'] = pt_['name']
        if pt_.get('amenity') == 'place_of_worship': t['building'] = {'christian': 'church', 'muslim': 'mosque'}.get(pt_.get('religion'), 'temple')
    nm = (t.get('name:en') or t.get('name') or '').lower()
    style = None; minf = 0
    cand = nm
    if not cand and na_tree is not None:
        for i in na_tree.query(cen):
            if named_areas[i][0].contains(cen): cand = named_areas[i][1]; break
    for sub, st, mf in landmark_rules:
        if re.search(r'\b' + re.escape(sub) + r'\b', cand):
            style, minf = st, mf; break
    lv = None
    try:
        if t.get('height'): lv = float(t['height'].replace('m', '')) / 3.2
        elif t.get('building:levels'): lv = float(t['building:levels'])
    except: lv = None
    a = p.area; r = h01(wid)
    industrial = ind_u is not None and ind_u.contains(cen) and a > 120 and not style
    rect = a / max(p.minimum_rotated_rectangle.area, 1e-6)   # 1 = a clean rectangle (planned blocks, sheds)
    daman = cen.x < (72.86 - LON0) * KX                       # Daman: old low-rise town, beach hotels
    resid = resid_u is not None and resid_u.contains(cen)
    cat = (pt_ or {})
    if lv is None:
        if industrial: lv = (3 if a > 3000 else 2) + int(r * 1.6)   # GIDC sheds and reactor halls, 6-13 m
        elif cat.get('tourism') == 'hotel': lv = 4 + int(r * 4)
        elif cat.get('amenity') == 'hospital': lv = 4 + int(r * 3)
        elif cat.get('amenity') in ('college', 'school'): lv = 3 + int(r * 2)
        elif a < 60: lv = 1 + int(r * 2)
        elif a < 200: lv = 2 + int(r * 2)                    # town houses, 2-3 floors
        elif 250 < a < 1600 and rect > 0.82 and (resid or math.hypot(cen.x - vx_, cen.y - vz_) < 4500):
            lv = 4 + int(r * 4)                              # planned housing societies: G+3 to G+6 rectangular blocks
        elif a < 700: lv = 3 + int(r * 2)                    # shop-houses and small blocks
        elif a < 2500: lv = 3 + int(r * 4)
        else: lv = 2 + int(r * 3)                            # big footprints: warehouses, malls, schools
        if daman and cat.get('tourism') != 'hotel': lv = min(lv, 2 + int(h01(wid, 'd') * 2.5))
        if major.contains(cen) and not industrial: lv += int(h01(wid, 'm') * 2.5)
        if comm_u is not None and comm_u.contains(cen): lv += 1
        if t.get('building') in ('house', 'hut', 'shed', 'garage', 'roof', 'kiosk'): lv = min(lv, 2)
        if t.get('building') in ('temple', 'church', 'mosque'): lv = min(lv, 3)
        if t.get('building') in ('apartments', 'commercial', 'office', 'hotel', 'hospital'): lv = max(lv, 4)
    lv = max(lv, minf, 1)
    tagged = bool(t.get('height') or t.get('building:levels'))
    # Vapi's high-rise residential towers cluster within a few km of the town centre (Chala, Vapi-Daman road, Koparli road)
    dc = math.hypot(cen.x - vx_, cen.y - vz_)
    if not tagged and not industrial and not style and not daman and 450 < a < 3200 and rect > 0.7 and dc < 3200 and h01(wid, 'tw') < 0.06 * (1 - dc / 3600):
        lv = max(lv, 11 + int(h01(wid, 'tl') * 9))
    if lv >= 8: lv = lv * 1.4
    if t.get('aeroway') == 'terminal': lv = max(lv, 4); style = 'modern'; cand = 'daman airport terminal'
    if t.get('aeroway') == 'hangar': lv = max(lv, 5)
    simp = p.simplify(0.5 if a < 2000 else 1.0)
    if simp.geom_type != 'Polygon' or simp.area < 4: simp = p
    c = list(simp.exterior.coords)[:-1]
    if len(c) < 3: continue
    kind = 0  # 0 generic res,1 commercial,2 house,3 worship,4 landmark
    bt = t.get('building')
    if bt in ('commercial', 'office', 'retail', 'hotel', 'industrial', 'warehouse') or (comm_u is not None and comm_u.contains(cen)) or industrial: kind = 1
    if bt in ('house', 'hut', 'shed', 'garage', 'kiosk'): kind = 2
    if bt in ('temple', 'church', 'mosque', 'cathedral', 'chapel', 'shrine') or t.get('amenity') == 'place_of_worship': kind = 3
    b = {'p': [v for x, z in c for v in (q(x), q(z))], 'h': int(round(lv * 3.2 * 10)), 'k': kind, 'r': int(r * 255)}
    if style: b['s'] = style; b['ln'] = cand[:40]
    if t.get('name'): b['n'] = t.get('name:en') or t.get('name')
    if t.get('building') in ('temple',) or ('temple' in nm or 'mandir' in nm or 'derasar' in nm): b['tm'] = 1
    if industrial: b['in'] = 1
    if a > 2000 and b['h'] > 120: pass
    buildings.append(b)
print('buildings', len(buildings), 'home idx', home_idx, 'home best', home_best)


# ---- dedupe overlapping buildings (prevents z-fighting) ----
def bpoly(b): return Polygon([(b['p'][i] / 10, b['p'][i + 1] / 10) for i in range(0, len(b['p']), 2)]).buffer(0)
order = sorted(range(len(buildings)), key=lambda i: -bpoly(buildings[i]).area)
kept = []; kept_polys = []; drops = 0; shrunk = 0
from shapely.strtree import STRtree as _ST
polys_all = [bpoly(b) for b in buildings]
tree_all = _ST(polys_all)
removed = set()
for i in order:
    if i in removed: continue
    pi_ = polys_all[i]
    for j in tree_all.query(pi_):
        if j == i or j in removed: continue
        pj = polys_all[j]
        if pj.area > pi_.area: continue
        try: inter = pi_.intersection(pj).area
        except Exception: continue
        if inter > 0.6 * pj.area:
            if buildings[j]['h'] > buildings[i]['h'] + 30 and not buildings[j].get('home'):
                sp = pj.buffer(-0.35)
                if sp.geom_type == 'Polygon' and sp.area > 4:
                    c = list(sp.exterior.coords)[:-1]; buildings[j]['p'] = [v for x, z in c for v in (q(x), q(z))]; shrunk += 1; continue
            removed.add(j); drops += 1
buildings = [b for k, b in enumerate(buildings) if k not in removed]
print('dedupe dropped', drops, 'shrunk', shrunk, 'left', len(buildings))

# ---------------- TREES & LIGHTS ----------------
btree = STRtree([Polygon([(b['p'][i] / 10, b['p'][i + 1] / 10) for i in range(0, len(b['p']), 2)]) for b in buildings])
bgeoms = btree.geometries
water_all = unary_union([water_u, sea])
def free(x, z, rad=1.5):
    pt = Point(x, z)
    if not WORLD.contains(pt): return False
    for i in btree.query(pt.buffer(rad)):
        if bgeoms[i].distance(pt) < rad: return False
    if road_union.distance(pt) < 0.6: return False
    if water_all.contains(pt): return False
    return True
trees = []
for nid, (la, lo, t) in nodes.items():
    if t and t.get('natural') == 'tree':
        x, z = proj(nid)
        if free(x, z, 1): trees.append((x, z))
for e in edges:
    if e['c'] > 4 or 'h' in e: continue
    p = e['p']; cc = [(p[i] / 10, p[i + 1] / 10) for i in range(0, len(p), 2)]
    ls = LineString(cc); L = ls.length
    step = 16 if e['c'] >= 3 else 20
    s = 4 + h01(e['a'], e['b']) * step
    while s < L - 3:
        pt = ls.interpolate(s); pt2 = ls.interpolate(min(L, s + 0.5))
        dx, dz = pt2.x - pt.x, pt2.y - pt.y; m = math.hypot(dx, dz) or 1
        nx, nz = -dz / m, dx / m
        for side in (1, -1):
            if h01(s, side, e['a']) < 0.55:
                off = e['w'] / 20 + 1.8 + h01(s, side) * 1.2
                x, z = pt.x + nx * off * side, pt.y + nz * off * side
                if free(x, z, 1.6): trees.append((x, z))
        s += step * (0.7 + 0.6 * h01(s, e['b']))
for p, t in greens:
    pp = p.intersection(WORLD)
    if pp.is_empty: continue
    n = int(min(pp.area / 180, 400))
    minx, minz, maxx, maxz = pp.bounds
    k = 0; tries = 0
    while k < n and tries < n * 6:
        tries += 1
        x = minx + h01(id(p), tries, 'x') * (maxx - minx); z = minz + h01(id(p), tries, 'z') * (maxz - minz)
        if pp.contains(Point(x, z)) and free(x, z, 1.5): trees.append((x, z)); k += 1
gx = XMIN + 10
while gx < XMAX - 10:
    gz = ZMIN + 10
    while gz < ZMAX - 10:
        x = gx + (h01(gx, gz, 'a') - 0.5) * 18; z = gz + (h01(gx, gz, 'b') - 0.5) * 18
        if h01(gx, gz, 'c') < 0.25 and free(x, z, 4.0): trees.append((x, z))
        gz += 30
    gx += 30
if len(trees) > 42000:
    trees = [t_ for i, t_ in enumerate(trees) if h01(i, 'keep') < 42000 / len(trees)]
print('trees', len(trees))
lights = []
for e in edges:
    if e['c'] > 2: continue
    p = e['p']; cc = [(p[i] / 10, p[i + 1] / 10) for i in range(0, len(p), 2)]
    ls = LineString(cc); L = ls.length; s = 10
    while s < L - 5:
        pt = ls.interpolate(s); pt2 = ls.interpolate(min(L, s + 0.5))
        dx, dz = pt2.x - pt.x, pt2.y - pt.y; m = math.hypot(dx, dz) or 1
        off = e['w'] / 20 + 0.8
        hh = 0
        if 'h' in e:
            # approx height along
            hh = None
        if hh is not None:
            lights.append([q(pt.x - dz / m * off), q(pt.y + dx / m * off), int(math.degrees(math.atan2(dz, dx)))])
        s += 38
print('lights', len(lights))

# coconut palms line the Daman seafront; inland Vapi gets neem, mango and banyan with the odd palm
coast_band = prep(sea.buffer(1400)) if not sea.is_empty else None
def near_coast(x, z):
    if coast_band is not None and coast_band.contains(Point(x, z)): return h01(x, z, 'palm') < 0.7
    return h01(x, z, 'palm') < 0.05
for pl in places:
    pl['n'] = re.sub(r'\bGidc\b', 'GIDC', pl['n'])
out = {
    'meta': {'lat0': LAT0, 'lon0': LON0, 'kx': KX, 'kz': KZ, 'bounds': [q(XMIN), q(ZMIN), q(XMAX), q(ZMAX)], 'sea': SEA_SIDE, 'city': 'Vapi',
             'src': 'Overture Maps ' + os.environ.get('OVERTURE_RELEASE', '2026-10-21.0') + ' (OpenStreetMap ODbL, Google Open Buildings, Microsoft ML Buildings, TomTom)'},
    'names': names, 'nodes': gnodes, 'edges': edges, 'walks': walk_lines, 'areas': areas, 'rails': rails,
    'buildings': buildings, 'trees': [[q(x), q(z)] + ([1] if near_coast(x, z) else []) for x, z in trees], 'lights': lights, 'pois': pois, 'places': places,
    'air': air, 'piers': piers, 'shops': shops,
}
s = json.dumps(out, separators=(',', ':'), ensure_ascii=False)
open('world2.json', 'w').write(s)
print('world.json MB', len(s) / 1e6)
