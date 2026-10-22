// ===================== NEW MISSIONS: The Arrival · Commuter Hustle · Family Favor =====================
function beachLZ() {
  // the longest stretch of sand (Jampore / Devka beach) is the landing zone; fall back to the far end of the runway
  let best = null, ba = 0;
  for (const d of WD.areas.beach) { const pts = toPts(d.p); if (pts.length < 3) continue; const a = Math.abs(signedArea(pts)); if (a > ba) { ba = a; best = pts; } }
  if (!best) { const rw = mainRunway(), e = edgePoint(rw.E, rw.len * 0.8, 1, {}); return [e.x, e.z]; }
  let [cx, cz] = centroid(best); if (!pointInPoly(cx, cz, best)) [cx, cz] = best[Math.floor(best.length / 2)];
  return [cx, cz];
}
function commuterRoute() {
  // origin: the railway station nearest home; destination: another halt at least 3 km down the Western Railway
  const hp = homeProp(), hx = hp ? hp.door.x : 0, hz = hp ? hp.door.z : 0;
  const cands = Metro.stations.filter(S => S.svc).sort((a, b) => dist2(a.x, a.z, hx, hz) - dist2(b.x, b.z, hx, hz));
  for (const S of cands) { const d = Metro.destinations(S).find(o => o.D.elevated && o.km > 3 && o.D.svc); if (d) return { S, D: d.D }; }
  for (const S of cands) { const d = Metro.destinations(S).find(o => o.D.svc && o.km > 2); if (d) return { S, D: d.D }; }
  return null;
}
// Rajesh Kaka's garage: the car-repair listing closest to GIDC Char Rasta
function kakaGarage() {
  const [gx, gz] = placeXZ('GIDC Char Rasta'); let b = null, bd = 1e18;
  for (const s of G.shops) if (s.t === 'repair' || s.t === 'cars') { const d = dist2(s.x, s.z, gx, gz); if (d < bd) { bd = d; b = s; } }
  return b && bd < 1500 * 1500 ? [b.x, b.z] : [gx, gz];
}
function defineTransitMissions(near, hd) {
  const term = Airport.svc, drop = WorldFix.dropoff;
  if (term && drop) MISSIONS.push({
    id: 'm13', title: 'The Arrival', who: 'Krupa', at: near(hd.x, hd.z, 50), unlock: () => true, reward: 8000, rel: ['krupa', 8],
    brief: 'Krupa at Daman Air has a charter plane nobody is free to fly. Drive to Daman Airport, check in like a regular passenger, clear security, board at Gate 2 — then take the controls yourself and put the plane down on the beach landing zone at Jampore.',
    steps: [
      { t: 'phone', from: 'Krupa', msg: 'The charter is fuelled and waiting. Come through the terminal like everyone else, the Coast Guard tower is watching.' },
      { t: 'enter', need: 'car', text: 'Get a <b>car</b>', label: 'Get a car' },
      { t: 'goto', need: 'car', stop: true, to: () => [drop.x, drop.z], r: 14, text: 'Drive to the <b>Daman Airport</b> departures drop-off', label: 'Drive to the airport drop-off' },
      { t: 'event', name: 'airport:enter', text: 'Walk into the <b>terminal</b>', label: 'Enter the terminal', target: () => player.interior ? null : [term.x, term.z] },
      { t: 'event', name: 'airport:ticket', match: d => d.mode === 'charter', text: 'Check in at the <b>Daman Air</b> desk and buy the <b>charter</b>', label: 'Check in for the charter' },
      { t: 'event', name: 'airport:security', text: 'Walk through <b>security</b>', label: 'Clear security' },
      { t: 'event', name: 'airport:board', text: 'Board at <b>Gate 2</b>', label: 'Board at the gate' },
      { t: 'landPlane', to: () => beachLZ(), r: 160, timer: 600, text: 'Take off and land on the <b>beach landing zone</b>', label: 'Fly to the LZ and land' },
    ],
    fail: [{ when: M => M.si >= 7 && player.veh && player.veh.kind === 'plane' && player.veh.y > 590, reason: 'You left controlled airspace.' }],
  });
  const route = commuterRoute();
  if (route) MISSIONS.push({
    id: 'm14', title: 'Commuter Hustle', who: 'Jignesh', at: [route.S.svc.x + 3, route.S.svc.z + 3], unlock: () => true, reward: 6000, rel: ['jignesh', 6],
    brief: `Jignesh left a briefcase on the platform at ${route.D.name}. Ride the Western Railway local like a normal commuter — buy a ticket, go through the gates, board — and grab it before someone else does.`,
    steps: [
      { t: 'phone', from: 'Jignesh', msg: `Platform bench, ${route.D.name}. Don't drive, the highway traffic near the GIDC is murder. Take the local.` },
      { t: 'event', name: 'metro:enter', match: d => d.station === route.S.name, text: `Enter <b>${route.S.name}</b> railway station`, label: 'Enter the railway station', target: () => player.interior ? null : [route.S.svc.x, route.S.svc.z] },
      { t: 'event', name: 'metro:token', match: d => d.to === route.D.name, text: `Buy a ticket to <b>${route.D.name}</b> at the ticket machine`, label: `Buy a ticket to ${route.D.name}` },
      { t: 'event', name: 'metro:gate', text: 'Go through the <b>ticket gates</b>', label: 'Go through the ticket gates' },
      { t: 'event', name: 'metro:board', text: 'Wait on the <b>platform</b> and board the train', label: 'Board the train' },
      { t: 'event', name: 'metro:alight', match: d => d.station === route.D.name, text: `Ride to <b>${route.D.name}</b>${route.D.elevated ? ' (elevated)' : ''} and get off`, label: `Ride to ${route.D.name}` },
      { t: 'pickupIn', interior: 'metro', at: [14, -6.3], where: () => player.interior.svc && player.interior.svc.station === route.D, text: 'Grab the <b>briefcase</b> from the platform bench', label: 'Retrieve the drop' },
      { t: 'goto', to: () => [route.D.svc.x, route.D.svc.z], r: 1e9, check: () => !player.interior, text: 'Leave the station', label: 'Leave the station' },
    ],
  });
  const fam = Living.family;
  if (fam) MISSIONS.push({
    id: 'm15', title: 'Family Favor', who: 'Mummy', trigger: { event: 'family:favor_accepted' }, at: [fam.x + Math.sin(fam.h + Math.PI) * 4, fam.z + Math.cos(fam.h + Math.PI) * 4], unlock: () => true, reward: 5000, rel: ['mummy', 10],
    brief: "Mummy called. Something about Pappa's car and Rajesh Kaka's garage in the GIDC. Go home, talk to her, and do what she asks — carefully, it's Pappa's pride and joy.",
    steps: [
      { t: 'event', name: 'family:enter', pre: () => player.interior && player.interior.type === 'family', text: 'Go inside your <b>family home</b>', label: 'Visit the family home', target: () => player.interior ? null : [fam.x, fam.z] },
      { t: 'event', name: 'family:favor_accepted', pre: M => M.via === 'family:favor_accepted', text: 'Talk to <b>Mummy</b>', label: 'Talk to Mummy' },
      { t: 'spawn', type: 'sedan', color: 0xe8e2d0, at: () => Living.familyCar },
      { t: 'enter', need: 'target', text: "Get in <b>Pappa's Ambassador</b> outside", label: "Get in Pappa's car" },
      { t: 'goto', need: 'target', stop: true, to: () => { const [x, z] = kakaGarage(); const s = roadSpot(x, z, 1, true); return [s.x, s.z]; }, r: 10, timer: 0, text: "Deliver the car to <b>Rajesh Kaka's garage</b> in the GIDC before he closes", label: "Deliver the car to Rajesh Kaka" },
    ],
    fail: [{ when: M => M.target && M.target.health < M.target.spec.hp * 0.4, reason: "You wrecked Pappa's car. Mummy is not speaking to you." }],
  });
  EventBus.on('airport:pilot', d => { if (mission && mission.def.id === 'm13') mission.target = d.v; });
  // delivery timer scales with the distance from the family home
  const m15 = MISSIONS.find(m => m.id === 'm15'); if (m15) { const g = m15.steps[4]; const [x, z] = kakaGarage(); g.timer = Math.round(Math.hypot(x - fam.x, z - fam.z) / 9 + 75); }
}
