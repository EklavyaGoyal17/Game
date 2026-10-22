// ===================== GOOGLE MAPS: the real place you are standing in (Maps JavaScript API · Advanced Markers · Street View) =====================
// Source: Google Maps Platform Code Assist (bootstrap loader below is the documented dynamic library import snippet)
// The 3D city is built only from open data (Overture Maps / OpenStreetMap, see data/). Google Maps content is shown
// only inside Google's own map and Street View widgets in this panel and is never copied into the game world
// (Google Maps Platform Terms: no use of Google Maps content with a non-Google map, no derived mapping datasets).
// Key: window.GMAPS_CONFIG.key (dist/config.js, written by build.py from GOOGLE_MAPS_API_KEY), ?gmapsKey=..., or Settings.
const GMaps = {
  KEY_STORE: 'vh-gmaps-key', ATTRIBUTION: ['gmp_git_agentskills_v1'],
  key: '', ready: null, map: null, marker: null, pano: null, svc: null, lastPano: null, mapType: 'hybrid',
  keyFrom() { return (window.GMAPS_CONFIG && window.GMAPS_CONFIG.key) || new URLSearchParams(location.search).get('gmapsKey') || store.get(this.KEY_STORE) || ''; },
  // game metres -> WGS84 (the same equirectangular projection the data pipeline used)
  toLatLng(x, z) { return { lat: WD.meta.lat0 - z / WD.meta.kz, lng: WD.meta.lon0 + x / WD.meta.kx }; },
  toXZ(lat, lng) { return [(lng - WD.meta.lon0) * WD.meta.kx, (WD.meta.lat0 - lat) * WD.meta.kz]; },
  // compass heading (0 = north, clockwise) of the player / their vehicle; the game's +z points south
  heading() { const h = player.veh ? player.veh.h : player.h; return (Math.atan2(Math.sin(h), -Math.cos(h)) * 180 / Math.PI + 360) % 360; },
  load(key) {
    if (this.ready) return this.ready;
    // prettier-ignore
    ((g) => { var h, a, k, p = "The Google Maps JavaScript API", c = "google", l = "importLibrary", q = "__ib__", m = document, b = window; b = b[c] || (b[c] = {}); var d = b.maps || (b.maps = {}), r = new Set, e = new URLSearchParams, u = () => h || (h = new Promise(async (f, n) => { await (a = m.createElement("script")); e.set("libraries", [...r] + ""); for (k in g) e.set(k.replace(/[A-Z]/g, t => "_" + t[0].toLowerCase()), g[k]); e.set("callback", c + ".maps." + q); a.src = `https://maps.${c}apis.com/maps/api/js?` + e; d[q] = f; a.onerror = () => h = n(Error(p + " could not load.")); a.nonce = m.querySelector("script[nonce]")?.nonce || ""; m.head.append(a) })); d[l] ? console.warn(p + " only loads once. Ignoring:", g) : d[l] = (f, ...n) => r.add(f) && u().then(() => d[l](f, ...n)) })({ key, v: 'weekly', language: 'en', region: 'IN' });
    this.ready = Promise.all(['maps', 'marker', 'streetView'].map(n => google.maps.importLibrary(n)))
      .then(([maps, marker, sv]) => ({ maps, marker, sv }))
      .catch(err => { this.ready = null; throw err; });
    return this.ready;
  },
  // ---------------- panel ----------------
  show() {
    this.key = this.keyFrom();
    $('gmKeyRow').hidden = !!this.key; $('gmBody').hidden = !this.key;
    const ll = this.toLatLng(player.x, player.z);
    $('gmWhere').textContent = `${ll.lat.toFixed(5)}° N, ${ll.lng.toFixed(5)}° E` + (hud.area.textContent ? ' · near ' + hud.area.textContent : '');
    if (!this.key) { $('gmStatus').textContent = 'Add a Google Maps API key to see this spot on Google Maps.'; return; }
    $('gmStatus').textContent = 'Loading Google Maps…';
    this.load(this.key).then(L => this.render(L, ll)).catch(e => { $('gmStatus').textContent = 'Google Maps could not load: ' + e.message; });
  },
  render(L, ll) {
    const { Map } = L.maps, { AdvancedMarkerElement, PinElement } = L.marker, { StreetViewService, StreetViewPanorama } = L.sv;
    if (!this.map) {
      // mapId is required for Advanced Markers; DEMO_MAP_ID works for development (use your own styled map ID in production)
      this.map = new Map($('gmMap'), { center: ll, zoom: 17, mapId: 'DEMO_MAP_ID', mapTypeId: this.mapType, tilt: 0, streetViewControl: false, fullscreenControl: false, internalUsageAttributionIds: this.ATTRIBUTION });
      const pin = new PinElement({ background: '#f6c21c', borderColor: '#15120d', glyphColor: '#15120d', glyphText: '★', scale: 1.2 });
      this.marker = new AdvancedMarkerElement({ map: this.map, position: ll, title: 'You are here' }); this.marker.append(pin);
      // clicking the Google map sets the in-game GPS route to that spot (only the clicked coordinate is used)
      this.map.addListener('click', e => { const [x, z] = this.toXZ(e.latLng.lat(), e.latLng.lng()); if (x < BX0 || x > BX1 || z < BZ0 || z > BZ1) { toast('That spot is outside the game map'); return; } waypoint = null; setWaypoint(x, z); });
      this.svc = new StreetViewService();
      this.pano = new StreetViewPanorama($('gmPano'), { visible: false, addressControl: false, fullscreenControl: false, motionTracking: false });
    } else { this.map.setCenter(ll); this.marker.position = ll; }
    $('gmStatus').textContent = 'Click the map to set a GPS route there · Street View shows the nearest real panorama';
    this.streetView(ll);
  },
  streetView(ll) {
    $('gmPanoMsg').textContent = 'Looking for Street View nearby…';
    this.svc.getPanorama({ location: ll, radius: 120, preference: 'nearest', sources: ['outdoor'] })
      .then(({ data }) => { this.pano.setPano(data.location.pano); this.pano.setPov({ heading: this.heading(), pitch: 0 }); this.pano.setVisible(true); $('gmPanoMsg').textContent = ''; })
      .catch(() => { this.pano.setVisible(false); $('gmPanoMsg').textContent = 'No Street View imagery within 120 m of here.'; });
  },
  saveKey() { const v = $('gmKeyIn').value.trim(); if (!v) return; store.set(this.KEY_STORE, v); $('gmKeyIn').value = ''; this.ready = null; this.show(); },
  forgetKey() { store.del(this.KEY_STORE); this.ready = null; this.map = null; toast('Google Maps key removed (reload to fully unload the API)'); this.show(); },
  toggleType() { this.mapType = this.mapType === 'hybrid' ? 'roadmap' : 'hybrid'; if (this.map) this.map.setMapTypeId(this.mapType); },
};
$('gmKeySave').onclick = () => GMaps.saveKey();
$('gmKeyIn').addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Enter') GMaps.saveKey(); });
$('gmType').onclick = () => GMaps.toggleType();
$('gmForget').onclick = () => GMaps.forgetKey();
$('gmClose').onclick = () => UI.closePanel();
$('pauseGmapsBtn').onclick = () => { setPaused(false); UI.openPanel('gmaps'); };
addEventListener('keydown', e => {
  if (gameState !== 'play' || paused || Menu.open || typing(e) || bm.open) return;
  if (e.code === 'KeyJ' && !Cheats.consoleOpen) { if (UI.panel === 'gmaps') UI.closePanel(); else if (!UI.modalOpen()) UI.openPanel('gmaps'); }
});
