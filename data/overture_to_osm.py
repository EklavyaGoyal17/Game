"""Convert the Overture Maps extract (data/overture/*.parquet, from fetch_overture.py) into the
OSM-style (nodes, ways, relations) structure that process_vapi.py consumes.

Overture is open data (OpenStreetMap ODbL + Google/Microsoft open building footprints + TomTom roads,
see https://docs.overturemaps.org/attribution). Each feature is re-tagged with the OSM keys the
game pipeline understands (highway, railway, building, aeroway, amenity, shop, ...).
Output: data/osm_vapi.pkl  ->  (nodes{id: (lat, lon, tags|None)}, ways{id: ([node ids], tags)}, rels{id: ([(type, ref, role)], tags)})
"""
import os, re, pickle, statistics, collections
import pyarrow.parquet as pq
import shapely.wkb as wkb
from shapely.geometry import LineString, Polygon, MultiPolygon, box, Point
from shapely.ops import substring

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'overture')
W, S, E, N = (float(v) for v in os.environ.get('BBOX', '72.805,20.315,72.99,20.445').split(','))
CLIP = box(W - 0.01, S - 0.01, E + 0.01, N + 0.01)

nodes, ways, rels = {}, {}, {}
_nid = {}
def node(lon, lat, tags=None):
    k = (round(lat, 7), round(lon, 7))
    i = _nid.get(k)
    if i is None:
        i = _nid[k] = len(_nid) + 1; nodes[i] = (k[0], k[1], None)
    if tags:
        la, lo, t = nodes[i]; nodes[i] = (la, lo, dict(t or {}, **tags))
    return i
_wid = [0]
def way(coords, tags):
    ids = [node(x, y) for x, y in coords]
    ids = [n for j, n in enumerate(ids) if j == 0 or n != ids[j - 1]]
    if len(ids) < 2: return None
    _wid[0] += 1; ways[_wid[0]] = (ids, tags); return _wid[0]
def area(geom, tags):
    """polygon / multipolygon -> closed way, or a multipolygon relation when there are holes or several parts"""
    geom = geom.intersection(CLIP) if not CLIP.contains(geom) else geom
    if geom.is_empty: return
    polys = [g for g in getattr(geom, 'geoms', [geom]) if g.geom_type == 'Polygon' and not g.is_empty]
    if len(polys) == 1 and not polys[0].interiors:
        way(list(polys[0].exterior.coords), tags); return
    mem = []
    for p in polys:
        w = way(list(p.exterior.coords), {});  mem.append(('way', w, 'outer'))
        for h in p.interiors: w = way(list(h.coords), {}); mem.append(('way', w, 'inner'))
    rels[len(rels) + 1] = ([m for m in mem if m[1]], dict(tags, type='multipolygon'))
def line(geom, tags):
    geom = geom.intersection(CLIP) if not CLIP.contains(geom) else geom
    for g in getattr(geom, 'geoms', [geom]):
        if g.geom_type == 'LineString' and len(g.coords) >= 2: way(list(g.coords), tags)
def rows(name):
    p = os.path.join(SRC, name + '.parquet')
    return pq.read_table(p).to_pylist() if os.path.exists(p) else []
def nm(r): return ((r.get('names') or {}).get('primary') or '').strip()
def flag_ranges(rules, flag):
    """[(a, b)] fractions along the segment where a road/rail flag applies"""
    out = []
    for r in rules or []:
        if flag in (r.get('values') or []): out.append(tuple(r['between']) if r.get('between') else (0.0, 1.0))
    return out
def split_by(g, ranges):
    """cut a linestring into [(part, inside_any_range)] at the given fractional ranges"""
    cuts = sorted({0.0, 1.0, *[c for a, b in ranges for c in (a, b)]})
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 1e-6: continue
        part = substring(g, a, b, normalized=True)
        if part.geom_type != 'LineString' or len(part.coords) < 2: continue
        mid = (a + b) / 2
        out.append((part, any(x <= mid <= y for x, y in ranges)))
    return out

# ---------------- roads & rail ----------------
ROAD = {'motorway': 'trunk', 'trunk': 'trunk', 'primary': 'primary', 'secondary': 'secondary', 'tertiary': 'tertiary', 'residential': 'residential',
        'unclassified': 'unclassified', 'living_street': 'living_street', 'service': 'service', 'track': 'service', 'unknown': 'residential',
        'pedestrian': 'pedestrian', 'footway': 'footway', 'sidewalk': 'footway', 'crosswalk': 'footway', 'path': 'path', 'steps': 'steps', 'cycleway': 'cycleway'}
LINKABLE = {'trunk', 'primary', 'secondary', 'tertiary'}
stats = collections.Counter()
for r in rows('segment'):
    g = wkb.loads(r['geometry'])
    if g.geom_type != 'LineString': continue
    if r['subtype'] == 'road':
        hw = ROAD.get(r['class'] or 'unknown')
        if not hw: continue
        if (r.get('subclass') == 'link' or 'is_link' in str(r.get('road_flags'))) and hw in LINKABLE: hw += '_link'
        t = {'highway': hw}
        if nm(r): t['name'] = nm(r)
        acc = r.get('access_restrictions') or []
        for a in acc:
            wh = a.get('when') or {}
            if a.get('access_type') == 'denied' and wh.get('heading') and not wh.get('mode') and not wh.get('vehicle') and not wh.get('using') and not wh.get('during'):
                t['oneway'] = 'yes' if wh['heading'] == 'backward' else '-1'
        for wr in r.get('width_rules') or []:
            if wr.get('between') is None and wr.get('value'): t['width'] = str(wr['value'])
        br, tu = flag_ranges(r.get('road_flags'), 'is_bridge'), flag_ranges(r.get('road_flags'), 'is_tunnel')
        for part, on_br in split_by(g, br) if br else [(g, False)]:
            pieces = split_by(part, tu) if tu else [(part, False)]
            for pp, in_tu in pieces:
                tt = dict(t)
                if on_br: tt['bridge'] = 'yes'; tt['layer'] = '1'
                if in_tu: tt['tunnel'] = 'yes'
                line(pp, tt)
        stats['road'] += 1
    elif r['subtype'] == 'rail':
        name = nm(r); flags = str(r.get('rail_flags'))
        hsr = 'high-speed' in name.lower() or 'high speed' in name.lower()
        t = {'railway': 'rail', 'name': name} if name else {'railway': 'rail'}
        if 'is_freight' in flags: t['usage'] = 'freight'
        if hsr:   # the Mumbai-Ahmedabad bullet train runs on a continuous viaduct through Valsad district
            t.update(bridge='viaduct', highspeed='yes', layer='2'); line(g, t)
        else:
            br = flag_ranges(r.get('rail_flags'), 'is_bridge')
            for part, on_br in split_by(g, br) if br else [(g, False)]:
                line(part, dict(t, bridge='yes') if on_br else t)
        stats['rail'] += 1

# ---------------- water ----------------
for r in rows('water'):
    g = wkb.loads(r['geometry']); sub, cl = r['subtype'], r['class']; name = nm(r)
    if g.geom_type in ('Polygon', 'MultiPolygon'):
        if sub == 'ocean': area(g, {'natural': 'sea'})
        elif cl == 'swimming_pool': area(g, {'leisure': 'swimming_pool'})
        else: area(g, dict({'natural': 'water'}, **({'name': name} if name else {})))
    elif g.geom_type in ('LineString', 'MultiLineString'):
        if sub == 'river': line(g, dict({'waterway': 'river'}, **({'name': name} if name else {})))
        elif sub == 'canal' and cl != 'drain': line(g, {'waterway': 'canal'})
    stats['water'] += 1

# ---------------- land use / land cover ----------------
LU = {'park': {'leisure': 'park'}, 'garden': {'leisure': 'garden'}, 'playground': {'leisure': 'playground'}, 'recreation_ground': {'leisure': 'recreation_ground'},
      'pitch': {'leisure': 'pitch'}, 'stadium': {'leisure': 'stadium'}, 'grass': {'landuse': 'grass'}, 'cemetery': {'landuse': 'cemetery'},
      'industrial': {'landuse': 'industrial'}, 'works': {'landuse': 'industrial'}, 'retail': {'landuse': 'retail'}, 'commercial': {'landuse': 'commercial'},
      'residential': {'landuse': 'residential'}, 'hospital': {'amenity': 'hospital'}, 'school': {'amenity': 'school'}, 'quarry': {'landuse': 'quarry'},
      'airfield': {'aeroway': 'aerodrome'}, 'forest': {'landuse': 'forest'}}
for r in rows('land_use'):
    t = LU.get(r['class'])
    if not t: continue
    g = wkb.loads(r['geometry'])
    if g.geom_type not in ('Polygon', 'MultiPolygon') or not g.intersects(CLIP): continue
    area(g, dict(t, **({'name': nm(r)} if nm(r) else {})))
LAND = {'tree': {'natural': 'wood'}, 'wood': {'natural': 'wood'}, 'forest': {'natural': 'wood'}, 'wetland': {'natural': 'wetland'}, 'beach': {'natural': 'beach'},
        'sand': {'natural': 'sand'}, 'grass': {'natural': 'grassland'}, 'scrub': {'natural': 'scrub'}, 'meadow': {'landuse': 'meadow'}}
for r in rows('land'):
    t = LAND.get(r['class']); g = wkb.loads(r['geometry'])
    if t and g.geom_type in ('Polygon', 'MultiPolygon') and g.intersects(CLIP): area(g, t)

# ---------------- infrastructure: airport, piers, stations ----------------
for r in rows('infrastructure'):
    g = wkb.loads(r['geometry']); sub, cl = r['subtype'], r['class']; st = dict(r.get('source_tags') or [])
    if sub == 'airport':
        if cl in ('runway', 'taxiway') and g.geom_type == 'LineString':
            t = {'aeroway': cl, 'ref': st.get('ref', '')}
            if st.get('width'): t['width'] = st['width']
            line(g, t)
        elif cl == 'apron': area(g, {'aeroway': 'apron'})
        elif cl == 'helipad':
            if g.geom_type == 'Point': node(g.x, g.y, {'aeroway': 'helipad'})
            else: area(g, {'aeroway': 'helipad'})
        elif cl in ('military_airport', 'airport', 'aerodrome', 'international_airport', 'regional_airport') and g.geom_type in ('Polygon', 'MultiPolygon'):
            area(g, {'aeroway': 'aerodrome', 'name': nm(r) or 'Airport'})
    elif sub == 'pier' and g.geom_type in ('Polygon', 'MultiPolygon'): area(g, {'man_made': 'pier'})
    elif sub == 'pier' and g.geom_type == 'LineString': line(g, {'man_made': 'pier'})
    elif sub == 'transit' and cl in ('railway_station', 'railway_halt') and g.geom_type == 'Point':
        node(g.x, g.y, {'railway': 'station', 'name': nm(r) or 'Station'})
    elif sub == 'transit' and cl == 'platform' and g.geom_type in ('Polygon', 'MultiPolygon'): area(g, {'railway': 'platform'})
    elif sub == 'transit' and cl == 'ferry_terminal' and g.geom_type == 'Point' and g.y > 20.40: node(g.x, g.y, {'harbour': 'yes', 'name': nm(r) or 'Daman Jetty'})   # the jetty at the Daman Ganga mouth
    elif sub == 'barrier' and cl == 'city_wall' and g.geom_type == 'LineString': line(g, {'barrier': 'city_wall'})

# ---------------- buildings ----------------
BCLASS = {'train_station': 'train_station', 'hospital': 'hospital', 'mosque': 'mosque', 'church': 'church', 'temple': 'temple', 'school': 'school',
          'apartments': 'apartments', 'commercial': 'commercial', 'retail': 'retail', 'industrial': 'industrial', 'warehouse': 'warehouse', 'house': 'house', 'office': 'office', 'hotel': 'hotel'}
for r in rows('building'):
    g = wkb.loads(r['geometry'])
    if g.geom_type not in ('Polygon', 'MultiPolygon'): continue
    t = {'building': BCLASS.get(r.get('class') or '', 'yes')}
    if r.get('height'): t['height'] = str(round(r['height'], 1))
    elif r.get('num_floors'): t['building:levels'] = str(r['num_floors'])
    if nm(r): t['name'] = nm(r)
    if r['sources'] and r['sources'][0].get('dataset') != 'OpenStreetMap': t['source'] = 'ml'
    area(g, t); stats['building'] += 1

# ---------------- places (POIs, shops) ----------------
CAT = {  # Overture basic_category -> OSM-style tags understood by the pipeline
    'hospital': {'amenity': 'hospital'}, 'police_station': {'amenity': 'police'}, 'movie_theater': {'amenity': 'cinema'}, 'theatre': {'amenity': 'theatre'},
    'hindu_place_of_worship': {'amenity': 'place_of_worship', 'religion': 'hindu'}, 'christian_place_of_worship': {'amenity': 'place_of_worship', 'religion': 'christian'},
    'muslim_place_of_worship': {'amenity': 'place_of_worship', 'religion': 'muslim'}, 'jain_place_of_worship': {'amenity': 'place_of_worship', 'religion': 'jain'},
    'place_of_worship': {'amenity': 'place_of_worship'}, 'college_university': {'amenity': 'college'}, 'shopping_mall': {'shop': 'mall'},
    'hotel': {'tourism': 'hotel'}, 'resort': {'tourism': 'hotel'}, 'stadium_arena': {'leisure': 'stadium'}, 'historic_site': {'historic': 'yes'},
    'fort': {'historic': 'fort'}, 'landmark_and_historical_building': {'historic': 'yes'}, 'museum': {'tourism': 'museum'}, 'beach': {'tourism': 'attraction', 'natural_feature': 'beach'},
    'gas_station': {'amenity': 'fuel'}, 'fueling_station': {'amenity': 'fuel'}, 'bank_or_credit_union': {'amenity': 'bank'}, 'atm': {'amenity': 'atm'},
    'fashion_and_apparel_store': {'shop': 'clothes'}, 'electronics_store': {'shop': 'electronics'}, 'convenience_store': {'shop': 'convenience'},
    'grocery_store': {'shop': 'supermarket'}, 'supermarket': {'shop': 'supermarket'}, 'food_and_beverage_store': {'shop': 'convenience'},
    'warehouse_club_store': {'shop': 'supermarket'}, 'jewelry_store': {'shop': 'jewelry'}, 'auto_dealer': {'shop': 'car'}, 'vehicle_dealer': {'shop': 'car'},
    'automotive_service': {'shop': 'car_repair'}, 'automotive_repair': {'shop': 'car_repair'}, 'restaurant': {'amenity': 'restaurant'},
    'casual_eatery': {'amenity': 'restaurant'}, 'fast_food_restaurant': {'amenity': 'fast_food'}, 'cafe': {'amenity': 'cafe'}, 'farmers_market': {'amenity': 'marketplace'},
    'market': {'amenity': 'marketplace'}, 'manufacturer': {'man_made': 'works'}, 'b2b_industrial_and_machine_service': {'man_made': 'works'},
    'chemical_plant': {'man_made': 'works'}, 'b2b_transportation_and_storage_service': {'man_made': 'works'}, 'supplier_or_distributor': {'man_made': 'works'}, 'fire_station': {'amenity': 'fire_station'}, 'bus_station': {'amenity': 'bus_station'},
}
JEWEL = re.compile(r'jewel|gold|ornament|zaveri|jhaveri|diamond', re.I)
NOISE = (round(20.3667, 4), round(72.9, 4))   # geocoder fallback point many listings share (no real location)
loc_words = collections.defaultdict(list)
streets = []
SKIP_WORD = re.compile(r'\b(rd|road|floor|complex|plaza|mall|square|near|opp|marg|cir|circle|tower|hub|park|centre|center|building|shop|gujarat|india|valsad|gj|gf|main|via|service|highway|nh|sector|phase|plot|block|wing|street|lane|business|house|market|bazar|bazaar|apartment|residency|society)\b', re.I)
for r in rows('place'):
    g = wkb.loads(r['geometry'])
    if g.geom_type != 'Point' or not (W <= g.x <= E and S <= g.y <= N): continue
    if (round(g.y, 4), round(g.x, 4)) == NOISE: continue
    conf = r.get('confidence') or 0
    name = nm(r); cat = r.get('basic_category') or ''
    # neighbourhood names mined from the address lines of every listing (used for the HUD's area label)
    for a in r.get('addresses') or []:
        for part in (a.get('freeform') or '').split(','):
            p = part.strip().strip('.').title()
            if 3 <= len(p) <= 22 and not re.search(r'\d', p) and not SKIP_WORD.search(p): loc_words[p].append((g.x, g.y))
            # street names from address lines ("Koparli Rd", "Vapi - Daman Main Rd"): voted onto the nearest road in process_vapi.py
            st = re.sub(r'\s+', ' ', p.replace(' - ', '-').replace(' -', '-').replace('- ', '-'))
            st = re.sub(r'\bRd\b\.?', 'Road', st); st = re.sub(r'\bMarg\b', 'Marg', st)
            for a_, b_ in (('Silvasa', 'Silvassa'), ('Koraparli', 'Koparli'), ('Chharawada', 'Chharwada'), ('Gidc', 'GIDC'), ('Costal', 'Coastal'), ('Silvassa-Vapi', 'Vapi-Silvassa'), ('Vapi Silvassa', 'Vapi-Silvassa'), ('Vapi Daman', 'Vapi-Daman'), ('Chanodcolony', 'Chanod Colony')): st = st.replace(a_, b_)
            if st in ('Unnamed Road', 'Main Road', 'Service Road', 'Road', 'Main Bazar Road') and st != 'Main Bazar Road': continue
            if re.search(r'\b(Road|Marg|Highway|Path)\b', st) and 6 <= len(st) <= 34 and not re.search(r'\d|\b(Near|Opp|Behind|Nr)\b', st, re.I):
                streets.append((g.x, g.y, st))
    if conf < 0.55 or not name: continue
    t = CAT.get(cat)
    if not t and JEWEL.search(name) and 'store' in cat: t = {'shop': 'jewelry'}
    if t and t.get('shop') == 'clothes' and JEWEL.search(name): t = {'shop': 'jewelry'}
    if not t: continue
    node(g.x, g.y, dict(t, name=name)); stats['place'] += 1

# neighbourhood labels: words used as an address part by many listings that cluster tightly in one spot
GENERIC = {'Vapi', 'Daman', 'Nani', 'Moti', 'Gujarat', 'Road', 'Nr', 'Char Rasta', 'Vapi East', 'Vapi West', 'Ground Floor', 'First Floor', 'Second Floor', 'Shoppers Gate', "Shopper'S Gate", 'Fort Area'}
JUNK = re.compile(r'\b(St|Behind|Signature|Fortune|Dream|Royal|Sun)\b')
places_out = []
for w, pts in loc_words.items():
    if w in GENERIC or JUNK.search(w) or len(pts) < 5: continue
    xs = sorted(p[0] for p in pts); ys = sorted(p[1] for p in pts)
    mx, my = statistics.median(xs), statistics.median(ys)
    near = [p for p in pts if abs(p[0] - mx) < 0.012 and abs(p[1] - my) < 0.012]
    if len(near) < max(4, 0.6 * len(pts)): continue
    mx, my = statistics.median([p[0] for p in near]), statistics.median([p[1] for p in near])
    places_out.append((w, mx, my, len(near)))
places_out.sort(key=lambda p: -p[3])
merged = []
for w, x, y, n in places_out:
    key = re.sub(r'[^a-z]', '', w.lower())
    if any(re.sub(r'[^a-z]', '', m[0].lower()).startswith(key[:5]) or (abs(m[1] - x) < 0.004 and abs(m[2] - y) < 0.004) for m in merged): continue
    merged.append((w, x, y, n))
for w, x, y, n in merged: node(x, y, {'place': 'suburb' if n >= 40 else 'neighbourhood', 'name': w})
# towns from the Overture divisions (Vapi, Daman, ...)
for r in rows('division'):
    g = wkb.loads(r['geometry'])
    if g.geom_type == 'Point' and r['subtype'] in ('locality', 'macrohood', 'neighborhood') and W <= g.x <= E and S <= g.y <= N and nm(r):
        node(g.x, g.y, {'place': 'suburb', 'name': {'Fort': 'Moti Daman Fort'}.get(nm(r), nm(r))})

for x, y, st in streets: node(x, y, {'addr_street': st})
pickle.dump((nodes, ways, rels), open(os.path.join(HERE, 'osm_vapi.pkl'), 'wb'))
print('address street names', len(streets), len({s for *_, s in streets}))
print('nodes', len(nodes), 'ways', len(ways), 'rels', len(rels), dict(stats))
print('neighbourhoods', [(w, n) for w, x, y, n in merged])
