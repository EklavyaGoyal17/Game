"""Build Vapi Hustle into dist/: index.html (game code inlined) + world data files.
Set GOOGLE_MAPS_API_KEY to bake a (referrer-restricted!) Maps JavaScript API key into the page for the in-game Google Maps panel."""
import os, glob, shutil
root = os.path.dirname(os.path.abspath(__file__))
tpl = open(os.path.join(root, 'src/template.html'), encoding='utf-8').read()
import json
js = '\n'.join(open(f, encoding='utf-8').read() for f in sorted(glob.glob(os.path.join(root, 'src/[0-9]*.js'))))
# data-driven content authored as JSON, inlined so the page also works as a single file
dialogue = json.load(open(os.path.join(root, 'data', 'dialogue.json'), encoding='utf-8'))
js = 'const DIALOGUE_DATA = ' + json.dumps(dialogue, ensure_ascii=False) + ';\n' + js
importmap = '<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}</script>'
gkey = os.environ.get('GOOGLE_MAPS_API_KEY', '').strip()
cfg = ('<script>window.GMAPS_CONFIG = ' + json.dumps({'key': gkey}) + ';</script>\n') if gkey else ''
html = tpl + '\n' + cfg + importmap + '\n<script type="module">\n' + js + '\n</script>\n'
dist = os.path.join(root, 'dist'); os.makedirs(dist, exist_ok=True)
full = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n</head>\n<body>\n'
        + html + '\n</body>\n</html>\n')
open(os.path.join(dist, 'index.html'), 'w', encoding='utf-8').write(full)          # standalone page for Vercel / any static host
open(os.path.join(root, 'artifact.html'), 'w', encoding='utf-8').write(html)       # body-only version for the Claude artifact
for f in ('world-a.json', 'world-b.json'):
    src = os.path.join(root, 'data', f)
    if os.path.exists(src): shutil.copy(src, os.path.join(dist, f))
print('built dist/index.html', round(len(html) / 1e3), 'KB', '(Google Maps key baked in)' if gkey else '(no Google Maps key: players can add one in the J panel)')
