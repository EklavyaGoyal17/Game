// ===================== HEISTS & DIRTY MONEY: bank vaults, millionaire bungalows, hawala laundering =====================
// Robbery loot is dirty cash: it can't be spent, it's lost if you're wasted or busted, and it only becomes real money
// after a hawala front washes it (for a cut). Heists are deliberately hard: alarms, armed guards, SWAT, 4-5 stars.
const GUARD_LOOK = { skin: 0x6b4429, shirt: 0x3d3a2c, lower: 0x2a2a26, kind: 'tee', female: false, hair: 0x141210, shoe: 0x111111, h: 1.02, long: false, accent: 0xd4a72c, build: 1.15 };
const Heists = {
  active: null,           // { kind: 'vault' | 'mansion', svc, left, total, loot }
  mansions: [], hawalas: [], guards: [],
  COOLDOWN: 20 * 60 * 1000,   // a hit place stays locked down for 20 minutes of real time
  get dirty() { return saveData.dirty || 0; },
  addDirty(n) { saveData.dirty = Math.round((saveData.dirty || 0) + n); this.hud(true); toast(`+${money(n)} dirty cash · launder it at a hawala front (₹ on the map)`); Sound.cash(); },
  hud(flash) { const el = $('dirty'); if (!el) return; const d = this.dirty; el.hidden = d <= 0; el.textContent = money(d) + ' dirty'; if (flash) { el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); } },
  lose(why) { if (this.dirty > 0) { toast(`${why}: lost ${money(this.dirty)} dirty cash`); saveData.dirty = 0; this.hud(); } },
  hkey(svc) { return svc.hid || ('bank@' + Math.round(svc.x) + ',' + Math.round(svc.z)); },
  cooled(svc) { const t = (saveData.heists || {})[this.hkey(svc)]; return !t || Date.now() - t > this.COOLDOWN; },
  init() {
    saveData.heists = saveData.heists || {};
    SERVICE_STYLE.mansion = { label: 'Millionaire Bungalow', icon: '♛', col: '#ffd24c' };
    SERVICE_STYLE.hawala = { label: 'Hawala (launder cash)', icon: '%', col: '#ff9a3c' };
    // ---- millionaire bungalows: big free-standing houses with gardens, away from the apartment blocks ----
    const cand = [];
    for (const B of BLD) {
      if (B.ind || B.s || B.tm || B.area < 320 || B.area > 1500 || B.h > 12.5) continue;
      let near = 0; for (const j of bldNear(B.cx, B.cz, 40)) if (BLD[j] !== B) near++;
      if (near <= 3) cand.push({ B, score: B.area / (near + 1) * (0.8 + hash2(B.bi, 61) * 0.4) });
    }
    cand.sort((a, b) => b.score - a.score);
    const OWNERS = ['Seth Mafatlal', 'Shah Chemicals', 'Desai Paper Mills', 'Seth Kantilal', 'Mehta Pharma', 'Bhanushali Dyes', 'Parekh Plastics', 'Seth Hiralal', 'Daman Liquor Baron', 'Vora Textiles'];
    for (const { B } of cand) {
      if (this.mansions.length >= 9) break;
      if (this.mansions.some(m => dist2(m.x, m.z, B.cx, B.cz) < 900 * 900)) continue;
      const d = nearestWallDoor(B.cx, B.cz, Math.sqrt(B.area) + 20); if (!d || d.bi !== B.pi) continue;
      const name = OWNERS[this.mansions.length % OWNERS.length] + ' bungalow';
      const s = addService('mansion', d.x, d.z, { h: d.h, name, r: 2, hid: 'mansion' + this.mansions.length, loot: Math.round(250000 + B.area * 250 + hash2(B.bi, 63) * 150000) });
      this.mansions.push(s);
    }
    SERVICE_HANDLERS.mansion = s => { if (!this.cooled(s)) { toast('Police tape everywhere. This bungalow was hit recently.'); return; } enterInterior('mansion', s); };
    // ---- hawala fronts: back offices of electronics / textile shops in the bazaars of Vapi, GIDC and Nani Daman ----
    const cands = G.shops.filter(p => p.t === 'electronics' || p.t === 'clothes');
    for (const area of ['Zanda Chowk', 'GIDC Char Rasta', 'Nani Daman', 'Chala']) {
      const [ax, az] = placeXZ(area); let best = null, bd = 1e18;
      for (const p of cands) { const dd = dist2(p.x, p.z, ax, az); if (dd < bd) { bd = dd; best = p; } }
      if (!best || bd > 1500 * 1500) continue; const d = nearestWallDoor(best.x, best.z); if (!d) continue;
      this.hawalas.push(addService('hawala', d.x, d.z, { h: d.h, name: 'Hawala · ' + (best.n || area), r: 1.8, area }));
    }
    SERVICE_HANDLERS.hawala = s => this.hawalaMenu(s);
    this.buildMansion();
    // bank vault heist, outside missions: stand at the vault and drill it while the SWAT team comes in
    const BI = INT.bank;
    Triggers.add({ id: 'heist:vault', interior: 'bank', x: BI.x + BI.spots.vault[0], z: BI.z + BI.spots.vault[1], r: 2.4,
      prompt: () => mission || this.active ? null : this.cooled(player.interior.svc) ? 'Drill the vault (heist · 5 stars)' : 'The vault is empty after the last hit',
      onUse: () => { if (!mission && !this.active && this.cooled(player.interior.svc)) this.start('vault', player.interior.svc, 45, 150000 + Math.random() * 100000); } });
    this.hud();
  },
  buildMansion() {
    const marble = new THREE.MeshStandardMaterial({ color: 0xece7de, roughness: 0.18, metalness: 0.05 });
    const I = addInterior('mansion', 30, 22, 5.2, (g, W, D, H, I) => {
      ibox(g, marble, W - 0.2, 0.02, D - 0.2, 0, 0.01, 0);
      ibox(g, IMAT.red, 10, 0.03, 6, -6, 0.03, 2);                                                   // carpet
      ibox(g, IMAT.fabric, 5, 0.6, 1.4, -6, 0.3, -1); ibox(g, IMAT.fabric, 1.4, 0.6, 4, -10, 0.3, 2);   // sofas
      ibox(g, IMAT.gold, 1.2, 2.6, 0.2, -6, 2.3, -D / 2 + 0.2);                                       // gilded mirror
      for (let k = 0; k < 4; k++) ibox(g, new THREE.MeshStandardMaterial({ color: [0x8a1e74, 0x1f4fb3, 0xc8251c, 0x178a45][k] }), 2.2, 1.5, 0.08, 4 + k * 3, 2.6, -D / 2 + 0.15);   // paintings
      const ch = new THREE.Mesh(new THREE.SphereGeometry(1.1, 12, 8), new THREE.MeshStandardMaterial({ color: 0xfff4d0, emissive: 0xffd890, emissiveIntensity: 1.2 })); ch.position.set(-4, H - 1.2, 0); g.add(ch);   // chandelier
      ibox(g, IMAT.wood, 6, 0.9, 2, 8, 0.45, 4);                                                     // dining
      I.walls.push([4, -D / 2, 4, -3], [4, 3, 4, D / 2 - 4]);                                         // partition: hall | study
      ibox(g, IMAT.wall, 0.25, H, D / 2 - 3, 4, H / 2, (-D / 2 - 3) / 2); ibox(g, IMAT.wall, 0.25, H, D / 2 - 7, 4, H / 2, (3 + D / 2 - 4) / 2);
      ibox(g, IMAT.metal, 1.6, 2.0, 1.2, 12.5, 1.0, -8.6); ibox(g, IMAT.dark, 0.5, 0.5, 0.05, 12.5, 1.3, -7.98);   // the safe, in the study
      I.spots = { safe: [12.5, -7.2], hall: [-6, 3] };
      I.guardSpots = [[-10, -6], [-2, 6], [8, -2], [10, 6], [0, -7], [-12, 7]];
    });
    I.onEnter = svc => this.populate(I, svc); I.onExit = () => this.depopulate();
    Triggers.add({ id: 'heist:safe', interior: 'mansion', x: I.x + I.spots.safe[0], z: I.z + I.spots.safe[1], r: 2.2,
      prompt: () => this.active ? null : 'Crack the safe (heist · armed guards)',
      onUse: () => { if (!this.active && !(mission && mission.def.id === 'm17')) this.start('mansion', player.interior.svc, 60, player.interior.svc.loot); } });
    this.I = I;
  },
  populate(I, svc) {
    this.depopulate();
    const n = 4 + Math.floor(Math.random() * 3);
    for (let k = 0; k < n; k++) { const [x, z] = I.guardSpots[k % I.guardSpots.length]; const w = new Walker(GUARD_LOOK, I.x + x, I.z + z); w.state = 'stand'; w.special = true; w.health = 140; w.h = Math.random() * TAU; w.arm(k % 2 ? 'smg' : 'pistol'); this.guards.push(w); }
    toast('Private security inside. They will open fire the moment you go for the safe.');
  },
  depopulate() { for (const w of this.guards) w.remove(); this.guards = []; },
  alarm(level) { for (const w of this.guards) if (!w.dead) { w.state = 'cop'; w.hostile = true; } Police.set(Math.max(Police.level, level)); },
  start(kind, svc, secs, loot) {
    this.active = { kind, svc, left: secs, total: secs, loot: Math.round(loot), spawned: false };
    if (kind === 'vault') { this.alarm(4); spawnRaiders({ inside: 'bank' }); toast('Alarm! Keep the drill running: stay at the vault.'); }
    else { this.alarm(3); toast('The guards heard the drill! Stay at the safe until it opens.'); }
    EventBus.emit('heist:start', { kind, name: svc && svc.name });
  },
  update(dt) {
    const H = this.active; if (!H) return;
    const type = H.kind === 'vault' ? 'bank' : 'mansion';
    if (player.dead) { this.active = null; EventBus.emit('heist:failed', { kind: H.kind }); return; }
    if (!player.interior || player.interior.type !== type) {
      if (H.done) { this.active = null; Police.set(Math.max(Police.level, H.kind === 'vault' ? 5 : 4)); toast('Get away and lose the heat, then launder the cash.'); }
      else { this.active = null; toast('You abandoned the heist.'); EventBus.emit('heist:failed', { kind: H.kind }); }
      return;
    }
    if (H.done) { setObjective('Get out with the loot'); return; }
    const I = INT[type], sp = I.spots[H.kind === 'vault' ? 'vault' : 'safe'];
    const at = Math.hypot(player.x - (I.x + sp[0]), player.z - (I.z + sp[1])) < 2.6;
    if (at) H.left -= dt;
    setObjective(at ? `${H.kind === 'vault' ? 'Drilling the vault' : 'Cracking the safe'} · <b>${Math.ceil(H.left)}s</b> · hold your ground` : `Get back to the <b>${H.kind === 'vault' ? 'vault' : 'safe'}</b>, the drill stops without you`);
    if (H.kind === 'mansion' && !H.spawned && H.left < H.total * 0.5) { H.spawned = true; Police.set(4); spawnRaiders({ inside: 'mansion' }); toast('Gujarat Police SWAT is coming through the front door!'); }
    if (H.left <= 0) {
      H.done = true; this.addDirty(H.loot); saveData.heists[this.hkey(H.svc)] = Date.now();
      saveData.stats.heists = (saveData.stats.heists || 0) + 1; saveGame(true);
      banner(H.kind === 'vault' ? 'VAULT CRACKED' : 'SAFE CRACKED', money(H.loot) + ' in dirty cash · now get out', false, 3.5);
      EventBus.emit('heist:done', { kind: H.kind, loot: H.loot });
    }
  },
  hawalaMenu(s) {
    const d = this.dirty, rel = Math.max(0, Math.min(10, (saveData.stats.laundered || 0) / 200000)), cut = Math.round(30 - rel);   // regulars get a better rate
    Menu.show(s.name, d > 0 ? `${money(d)} dirty · the operator keeps ${cut}%` : 'No dirty cash to wash. Come back after a job.', [
      { label: `Launder everything (${money(d * (1 - cut / 100))} clean to your bank)`, disabled: d <= 0, action: () => { const clean = Math.round(d * (1 - cut / 100)); payBank(clean); saveData.stats.laundered = (saveData.stats.laundered || 0) + d; saveData.dirty = 0; this.hud(); saveGame(true); toast(`Washed ${money(d)} · ${money(clean)} reached your bank`); EventBus.emit('launder', { dirty: d, clean }); return 'close'; } },
      { label: 'Leave', action: () => 'close' }]);
  },
};
// nearby buildings by centroid (bungalow detection)
function bldNear(x, z, r) { const out = []; for (const i of chunkAt(x, z).bld) if (dist2(BLD[i].cx, BLD[i].cz, x, z) < r * r) out.push(i); return out; }
Systems.register('heists', { init() { Heists.init(); }, update(dt) { Heists.update(dt); } }, 35);
