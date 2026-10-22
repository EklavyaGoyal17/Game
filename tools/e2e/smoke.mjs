// Quick boot check: starts the game, reports what the world built, and saves an aerial + street screenshot.
import fs from 'fs'; import path from 'path'; import { fileURLToPath } from 'url';
const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'out'); fs.mkdirSync(OUT, { recursive: true });
export default async function (page) {
  const ev = (fn, a) => page.evaluate(fn, a);
  await ev(() => document.getElementById('startBtn').click());
  await page.waitForFunction(() => !document.getElementById('hud').hidden, null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  const info = await ev(() => {
    const M = window.__mh;
    return {
      stats: M.WorldFix.stats, bounds: M.bounds, player: [Math.round(M.player.x), Math.round(M.player.z)],
      stations: M.Metro.stations.map(s => s.name + (s.svc ? '' : ' (no door)')), terminal: !!M.Airport.svc, runways: M.AIR.runways.length,
      props: M.PROPERTIES.map(p => p.id + ':' + (p.door ? 'ok' : 'NO DOOR')), missions: M.MISSIONS.map(m => m.id + '@' + m.pos.map(Math.round)),
      trains: M.trains.length, services: Object.entries(M.services.reduce((a, s) => (a[s.type] = (a[s.type] || 0) + 1, a), {})),
      area: document.getElementById('area').textContent, street: document.getElementById('street').textContent,
    };
  });
  const snap = async n => { const u = await ev(() => window.__mh.snap()); fs.writeFileSync(path.join(OUT, n + '.jpg'), Buffer.from(u.split(',')[1], 'base64')); };
  await snap('smoke_street');
  await ev(() => { const M = window.__mh; M.camera.position.set(M.player.x + 300, 260, M.player.z + 300); M.camera.lookAt(M.player.x, 0, M.player.z); window.__norender = true; });
  return info;
}
