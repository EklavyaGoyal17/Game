// Renders a set of README screenshots of Vapi / Daman landmarks into docs/screenshots/.
import fs from 'fs'; import path from 'path'; import { fileURLToPath } from 'url';
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../docs/screenshots'); fs.mkdirSync(OUT, { recursive: true });
export default async function (page) {
  const ev = (fn, a) => page.evaluate(fn, a);
  await ev(() => document.getElementById('startBtn').click());
  await page.waitForFunction(() => !document.getElementById('hud').hidden, null, { timeout: 30000 });
  const out = {};
  // aerial over Vapi town and Chala towers
  out.where = await ev(() => { const M = window.__mh; const P = n => M.G.places.find(p => p.n === n) || M.G.pois.find(p => p.n.includes(n)); return ['Chala', 'Zanda Chowk', 'Moti Daman Fort', 'Devka Beach', 'Daman Airport Terminal', 'GIDC'].map(n => { const p = P(n); return p ? [n, Math.round(p.x), Math.round(p.z)] : [n, null]; }); });
  for (const [n, x, z, yaw, pitch, mode] of [['Zanda Chowk', 0, 0, 0.6, 0.55, 2], ['Moti Daman Fort', 0, 0, 2.2, 0.45, 2], ['GIDC', 0, 0, 1.2, 0.5, 2], ['Daman Airport Terminal', 0, 0, 0.3, 0.4, 2]]) {
    const p = out.where.find(w => w[0] === n); if (!p || p[1] === null) continue;
    await ev(([x, z, yaw, pitch, mode]) => window.__mh.tp(x, z, yaw, pitch, mode), [p[1], p[2], yaw, pitch, mode]);
    await page.waitForTimeout(3000);
    const u = await ev(() => window.__mh.snap()); fs.writeFileSync(path.join(OUT, 'vapi_' + n.toLowerCase().replace(/[^a-z]+/g, '_') + '.jpg'), Buffer.from(u.split(',')[1], 'base64'));
  }
  // high aerial over Vapi town towards Chala
  { const u = await ev(() => { const M = window.__mh, p = M.G.places.find(q => q.n === 'Zanda Chowk'), c = M.G.places.find(q => q.n === 'Chala'); M.tp(p.x, p.z, 0); window.__aer = [p, c]; return 1; }); await page.waitForTimeout(3000);
    const v = await ev(() => { const M = window.__mh, [p, c] = window.__aer; M.camera.position.set(p.x + 250, 330, p.z + 420); M.camera.lookAt((p.x + c.x) / 2, 0, (p.z + c.z) / 2); return M.snap(); }); fs.writeFileSync(path.join(OUT, 'vapi_aerial.jpg'), Buffer.from(v.split(',')[1], 'base64')); }
  // bullet train on the viaduct
  out.bullet = await ev(() => { const M = window.__mh, T = M.trains.find(t => t.bullet); if (!T) return null; M.tp(T.x + 60, T.z + 40, 0, 0.25, 1); return [Math.round(T.x), Math.round(T.z)]; });
  await page.waitForTimeout(2500);
  { const u = await ev(() => { const M = window.__mh, T = M.trains.find(t => t.bullet); if (T) { M.camera.position.set(T.x + 70, T.y + 25, T.z + 70); M.camera.lookAt(T.x, T.y + 8, T.z); } return M.snap(); }); fs.writeFileSync(path.join(OUT, 'vapi_bullet_train.jpg'), Buffer.from(u.split(',')[1], 'base64')); }
  return out;
}
