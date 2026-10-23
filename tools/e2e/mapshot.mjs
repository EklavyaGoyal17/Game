// Screenshots of the big map (street + landmark labels) and the GIDC sheds from the air.
import fs from 'fs'; import path from 'path'; import { fileURLToPath } from 'url';
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../docs/screenshots'); fs.mkdirSync(OUT, { recursive: true });
export default async function (page) {
  const ev = (fn, a) => page.evaluate(fn, a);
  await ev(() => document.getElementById('startBtn').click());
  await page.waitForFunction(() => !document.getElementById('hud').hidden, null, { timeout: 30000 });
  await ev(() => { const M = window.__mh, p = M.G.places.find(q => q.n === 'Zanda Chowk'); M.tp(p.x, p.z, 0); });
  await page.waitForTimeout(1500);
  await ev(() => { window.__norender = false; });
  await page.keyboard.press('KeyM'); await page.waitForTimeout(800);
  for (const k of [0, 1, 2, 3, 4]) { await page.mouse.move(640, 360); await page.mouse.wheel(0, -300); await page.waitForTimeout(150); }
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, 'vapi_map_labels.png') });
  await page.keyboard.press('KeyM'); await page.waitForTimeout(300);
  await ev(() => { window.__norender = true; const M = window.__mh, p = M.G.places.find(q => q.n === 'GIDC'); M.tp(p.x, p.z, 0); window.__g = p; });
  await page.waitForTimeout(3000);
  const u = await ev(() => { const M = window.__mh, p = window.__g; M.camera.position.set(p.x + 160, 150, p.z + 220); M.camera.lookAt(p.x, 0, p.z); return M.snap(); });
  fs.writeFileSync(path.join(OUT, 'vapi_gidc_sheds.jpg'), Buffer.from(u.split(',')[1], 'base64'));
  return 'ok';
}
