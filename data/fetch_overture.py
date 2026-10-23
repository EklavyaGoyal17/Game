"""Download Overture Maps features inside a bounding box (no DuckDB extensions needed).

Overture's GeoParquet files are spatially clustered and carry min/max statistics for
bbox.xmin/xmax/ymin/ymax per row group, so only the row groups that overlap the box are read.
Usage: python3 fetch_overture.py <out_dir> <type> [<type> ...]   (types: building, segment, connector, water, land_use, land, place, division_area, infrastructure)
"""
import os, sys, pickle, time
import pyarrow.fs as pafs, pyarrow.parquet as pq, pyarrow.compute as pc, pyarrow as pa

RELEASE = os.environ.get('OVERTURE_RELEASE', '2026-10-21.0')
BBOX = tuple(float(v) for v in os.environ.get('BBOX', '72.805,20.315,72.99,20.445').split(','))  # W,S,E,N
THEME = {'building': 'buildings', 'segment': 'transportation', 'connector': 'transportation', 'water': 'base', 'land_use': 'base',
         'land': 'base', 'infrastructure': 'base', 'land_cover': 'base', 'place': 'places', 'division_area': 'divisions', 'division': 'divisions'}

def s3():
    kw = dict(anonymous=True, region='us-west-2')
    if os.environ.get('HTTPS_PROXY'): kw['proxy_options'] = os.environ['HTTPS_PROXY']
    if os.path.exists('/root/.ccr/ca-bundle.crt'): kw['tls_ca_file_path'] = '/root/.ccr/ca-bundle.crt'
    return pafs.S3FileSystem(**kw)

def rg_bbox(md, rg, idx):
    st = {}
    for name, ci in idx.items():
        s = md.row_group(rg).column(ci).statistics
        if s is None or not s.has_min_max: return None
        st[name] = (s.min, s.max)
    return st

def fetch(fs, typ, W, S, E, N):
    base = f'overturemaps-us-west-2/release/{RELEASE}/theme={THEME[typ]}/type={typ}/'
    files = [i.path for i in fs.get_file_info(pafs.FileSelector(base)) if i.path.endswith('.parquet')]
    tables = []
    for f in files:
        pf = pq.ParquetFile(f, filesystem=fs)
        md = pf.metadata; sch = md.schema
        idx = {sch.column(i).path: i for i in range(md.num_columns) if sch.column(i).path in ('bbox.xmin', 'bbox.xmax', 'bbox.ymin', 'bbox.ymax')}
        keep = []
        for rg in range(md.num_row_groups):
            b = rg_bbox(md, rg, idx)
            if b is None or (b['bbox.xmin'][0] <= E and b['bbox.xmax'][1] >= W and b['bbox.ymin'][0] <= N and b['bbox.ymax'][1] >= S): keep.append(rg)
        if not keep: continue
        t = pf.read_row_groups(keep)
        bb = t.column('bbox')
        m = pc.and_(pc.and_(pc.less_equal(pc.struct_field(bb, 'xmin'), E), pc.greater_equal(pc.struct_field(bb, 'xmax'), W)),
                    pc.and_(pc.less_equal(pc.struct_field(bb, 'ymin'), N), pc.greater_equal(pc.struct_field(bb, 'ymax'), S)))
        t = t.filter(m)
        print(f'  {typ} {f.rsplit("/", 1)[-1][:12]} row groups {len(keep)}/{md.num_row_groups} -> {t.num_rows}', flush=True)
        if t.num_rows: tables.append(t)
    return pa.concat_tables(tables, promote_options='permissive') if tables else None

if __name__ == '__main__':
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    fs = s3(); W, S, E, N = BBOX
    for typ in sys.argv[2:]:
        t0 = time.time(); t = fetch(fs, typ, W, S, E, N)
        if t is None: print(typ, 'none'); continue
        pq.write_table(t, os.path.join(out, typ + '.parquet'))
        print(typ, t.num_rows, 'rows', round(time.time() - t0), 's', flush=True)
