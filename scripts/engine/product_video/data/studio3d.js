import * as T from 'three';
import { RoomEnvironment } from './three/RoomEnvironment.js';

const rad = T.MathUtils.degToRad;
const clamp = T.MathUtils.clamp;
const smooth = t => {t = clamp(t, 0, 1); return t * t * t * (t * (t * 6 - 15) + 10);};
let renderer, environment, active, output, outputContext;
const scenes = new Map();

function shape(w, h, r) {
  const s = new T.Shape();
  s.moveTo(-w / 2 + r, -h / 2);
  s.lineTo(w / 2 - r, -h / 2); s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  s.lineTo(w / 2, h / 2 - r); s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  s.lineTo(-w / 2 + r, h / 2); s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  s.lineTo(-w / 2, -h / 2 + r); s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  return s;
}

function slab(w, h, depth, r, material, bevel = .025) {
  const geometry = new T.ExtrudeGeometry(shape(w - 2 * bevel, h - 2 * bevel, r), {
    depth: depth - 2 * bevel, bevelEnabled: true, bevelSegments: 3,
    steps: 1, bevelSize: bevel, bevelThickness: bevel, curveSegments: 16,
  });
  geometry.translate(0, 0, -depth / 2 + bevel);
  const mesh = new T.Mesh(geometry, material);
  mesh.castShadow = mesh.receiveShadow = true;
  return mesh;
}

function screenGeometry(w, h, r) {
  const g = new T.ShapeGeometry(shape(w, h, r), 24);
  const p = g.attributes.position, uv = g.attributes.uv;
  for (let i = 0; i < p.count; i++) uv.setXY(i, (p.getX(i) + w / 2) / w, (p.getY(i) + h / 2) / h);
  return g;
}

function eventOnce(element, name) {
  return new Promise((resolve, reject) => {
    const done = (error) => {clearTimeout(timer); element.removeEventListener(name, success); element.removeEventListener('error', failure); error ? reject(error) : resolve();};
    const success = () => done();
    const failure = () => done(new Error('Screen media could not be decoded. Convert to H.264 MP4 or WebM.'));
    const timer = setTimeout(() => done(new Error('Screen media timed out after 15 seconds.')), 15000);
    element.addEventListener(name, success, {once: true});
    element.addEventListener('error', failure, {once: true});
  });
}

async function media(spec, w, h) {
  let input;
  if (spec.media.type === 'video') {
    input = document.createElement('video');
    input.muted = true; input.preload = 'auto'; input.playsInline = true;
    const ready = eventOnce(input, 'loadeddata');
    input.src = spec.url; input.load(); await ready;
  } else {
    input = new Image(); input.src = spec.url; await input.decode();
  }
  // Canvas fitting preserves every source pixel by default and gives both media types identical UVs.
  const canvas = document.createElement('canvas');
  canvas.width = Math.min(2048, spec.media.width);
  canvas.height = Math.round(canvas.width * h / w);
  if (canvas.height > 2048) {canvas.width = Math.round(canvas.width * 2048 / canvas.height); canvas.height = 2048;}
  const ctx = canvas.getContext('2d', {alpha: false});
  const texture = new T.CanvasTexture(canvas);
  texture.colorSpace = T.SRGBColorSpace;
  texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  texture.generateMipmaps = false;
  texture.minFilter = T.LinearFilter;
  let lastTime = null;
  async function update(time) {
    const video = spec.media.type === 'video';
    const target = video ? clamp((spec.in || 0) + Math.max(0, time) * (spec.rate || 1), 0, Math.max(0, input.duration - .04)) : 0;
    if (lastTime === target) return;
    if (video && Math.abs(input.currentTime - target) > .0001) {
      const ready = eventOnce(input, 'seeked'); input.currentTime = target; await ready;
    }
    ctx.fillStyle = '#080a0e'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    const iw = video ? input.videoWidth : input.naturalWidth, ih = video ? input.videoHeight : input.naturalHeight;
    const factor = (spec.fit === 'cover' ? Math.max : Math.min)(canvas.width / iw, canvas.height / ih);
    ctx.drawImage(input, (canvas.width - iw * factor) / 2, (canvas.height - ih * factor) / 2, iw * factor, ih * factor);
    texture.needsUpdate = true; lastTime = target;
  }
  await update(0);
  return {texture, update, dispose() {texture.dispose(); if (spec.media.type === 'video') {input.removeAttribute('src'); input.load();}}};
}

function place(parent, mesh, x, y, z, rotation = [0, 0, 0]) {
  mesh.position.set(x, y, z); mesh.rotation.set(...rotation); parent.add(mesh); return mesh;
}

function disk(radius, depth, material) {
  const mesh = new T.Mesh(new T.CylinderGeometry(radius, radius, depth, 48), material);
  mesh.castShadow = mesh.receiveShadow = true;
  return mesh;
}

function appleMark(parent, size, x, y, z, material) {
  // An original vector silhouette, facing outward on the back of the enclosure.
  const body = new T.Shape();
  body.moveTo(0, .27);
  body.bezierCurveTo(-.17, .39, -.43, .32, -.43, .03);
  body.bezierCurveTo(-.43, -.20, -.25, -.48, -.12, -.44);
  body.bezierCurveTo(.02, -.39, .03, -.39, .15, -.44);
  body.bezierCurveTo(.28, -.47, .40, -.25, .44, -.14);
  body.bezierCurveTo(.22, -.05, .23, .18, .41, .27);
  body.bezierCurveTo(.26, .44, .10, .32, 0, .27);
  const leaf = new T.Shape(); leaf.moveTo(.01, .35);
  leaf.bezierCurveTo(0, .48, .13, .59, .25, .58);
  leaf.bezierCurveTo(.25, .45, .14, .34, .01, .35);
  const mark = new T.Mesh(new T.ShapeGeometry([body, leaf], 24), material);
  mark.scale.setScalar(size); place(parent, mark, x, y, z, [0, Math.PI, 0]);
}

async function iphone17ProMax(spec) {
  // Chassis ratio: 78 x 163.4 x 8.75 mm. Detail radii are visual approximations.
  const h = 5.2, unit = h / 163.4, w = 78 * unit, depth = 8.75 * unit, radius = .36;
  const group = new T.Group(), clay = spec.finish === 'clay';
  const color = new T.Color(spec.color || '#bbc0c5');
  const metal = new T.MeshPhysicalMaterial({color, metalness: clay ? 0 : .82,
    roughness: clay ? .78 : .32, clearcoat: clay ? 0 : .22});
  const glass = new T.MeshPhysicalMaterial({color: color.clone().multiplyScalar(.78),
    metalness: clay ? 0 : .62, roughness: clay ? .78 : .44, clearcoat: clay ? 0 : .18, envMapIntensity: .8});
  const black = new T.MeshPhongMaterial({color: '#030407', specular: '#0a0c10', shininess: 24});
  const inset = new T.MeshStandardMaterial({color: '#14161b', roughness: .65});
  group.add(slab(w, h, depth, radius, metal, .055));
  // Ceramic back inset ends below the raised camera plateau.
  place(group, slab(w - .24, 3.36, .014, .28, glass, .003), 0, -.72, -depth / 2 - .004);
  const logo = new T.MeshStandardMaterial({color: color.clone().multiplyScalar(.74), metalness: .65, roughness: .3});
  appleMark(group, .49, 0, -.60, -depth / 2 - .015, logo);
  const frontZ = depth / 2;
  place(group, slab(w - .028, h - .028, .024, radius - .012, black, .004), 0, 0, frontZ);
  const sh = 5.036, sw = sh * 1320 / 2868;
  const feed = await media(spec, sw, sh);
  place(group, new T.Mesh(screenGeometry(sw, sh, .292),
    new T.MeshBasicMaterial({map: feed.texture, toneMapped: false})), 0, 0, frontZ + .017);
  place(group, slab(.72, .196, .012, .094, black, .002), 0, sh / 2 - .18, frontZ + .028);
  const lensGlass = new T.MeshPhysicalMaterial({color: '#0b1223', metalness: .38, roughness: .20, clearcoat: .5, envMapIntensity: .65});
  place(group, disk(.043, .003, lensGlass), .235, sh / 2 - .18, frontZ + .037, [Math.PI / 2, 0, 0]);
  place(group, slab(.30, .018, .008, .007, inset, .002), 0, h / 2 - .018, frontZ - .004);
  const cameraZ = -depth / 2 - .10;
  place(group, slab(w - .14, 1.48, .21, .30, metal, .05), 0, h / 2 - .84, cameraZ);
  // Back-view coordinates reverse X: two lenses on the left, one centered between them.
  const lenses = [[.77, 2.07], [.77, 1.34], [.12, 1.705]];
  const ring = new T.MeshPhysicalMaterial({color: color.clone().multiplyScalar(.76), metalness: .92, roughness: .22});
  const optical = new T.MeshPhysicalMaterial({color: '#101c38', roughness: .11, metalness: .52, clearcoat: 1});
  for (const [x, y] of lenses) {
    place(group, disk(.322, .09, ring), x, y, cameraZ - .11, [Math.PI / 2, 0, 0]);
    place(group, disk(.285, .025, black), x, y, cameraZ - .166, [Math.PI / 2, 0, 0]);
    place(group, disk(.186, .008, lensGlass), x, y, cameraZ - .182, [Math.PI / 2, 0, 0]);
    const dome = new T.Mesh(new T.SphereGeometry(.176, 40, 20), lensGlass);
    dome.scale.z = .13; place(group, dome, x, y, cameraZ - .181);
    place(group, disk(.064, .002, optical), x, y, cameraZ - .205, [Math.PI / 2, 0, 0]);
  }
  const flash = new T.MeshStandardMaterial({color: '#f0ecd7', roughness: .35, metalness: .1});
  place(group, disk(.116, .016, flash), -.82, 2.08, cameraZ - .113, [Math.PI / 2, 0, 0]);
  place(group, disk(.117, .013, black), -.82, 1.35, cameraZ - .114, [Math.PI / 2, 0, 0]);
  place(group, disk(.020, .012, inset), -.82, 1.70, cameraZ - .116, [Math.PI / 2, 0, 0]);
  for (const [x, y, length] of [[w / 2, .70, .54], [w / 2, -.95, .53],
    [-w / 2, 1.34, .24], [-w / 2, .78, .43], [-w / 2, .24, .43]]) {
    place(group, slab(.042, length, .095, .018, metal, .007), x, y, 0);
  }
  // Side-facing dark inserts depict the connector and acoustic openings.
  place(group, slab(.29, .088, .01, .041, inset, .002), 0, -h / 2 - .001, 0, [Math.PI / 2, 0, 0]);
  for (const side of [-1, 1]) for (let i = 0; i < 5; i++) {
    place(group, disk(.019, .006, inset), side * (.39 + i * .093), -h / 2, 0);
  }
  const antenna = new T.MeshStandardMaterial({color: color.clone().multiplyScalar(.7), roughness: .7});
  for (const x of [-w / 2, w / 2]) for (const y of [-2.10, 2.10]) {
    place(group, slab(.006, .032, depth - .09, .002, antenna, .001), x, y, 0);
  }
  return {group, feed, spec};
}

function macKeyboard(group, y, metal, black) {
  const kw = 5.39, kh = 2.08, centerZ = 1.47;
  place(group, slab(kw + .14, kh + .10, .015, .12, black, .003), 0, y, centerZ, [-Math.PI / 2, 0, 0]);
  const keys = new T.MeshPhongMaterial({color: '#121315', specular: '#111214', shininess: 12});
  const canvas = document.createElement('canvas'); canvas.width = 1536; canvas.height = 660;
  const ctx = canvas.getContext('2d'); ctx.fillStyle = '#c7c8ca'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  const rows = [
    [['esc', 1.25], ...Array.from({length: 12}, (_, i) => ['F' + (i + 1), 1]), ['◉', 1.25]],
    [['`', 1], ...'1234567890-='.split('').map(s => [s, 1]), ['delete', 1.5]],
    [['tab', 1.5], ...'QWERTYUIOP[]'.split('').map(s => [s, 1]), ['\\', 1]],
    [['caps lock', 1.75], ..."ASDFGHJKL;'".split('').map(s => [s, 1]), ['return', 1.75]],
    [['shift', 2.25], ...'ZXCVBNM,./'.split('').map(s => [s, 1]), ['shift', 2.25]],
    [['fn', 1], ['control', 1], ['option', 1], ['command', 1.25], ['', 5.25], ['command', 1.25], ['option', 1], ['←', 1], ['↕', 1], ['→', 1]],
  ];
  rows.forEach((row, ri) => {
    const unit = kw / row.reduce((sum, entry) => sum + entry[1], 0);
    let x = -kw / 2;
    row.forEach(([label, weight]) => {
      const width = weight * unit - .035, height = ri === 0 ? .225 : .282;
      const z = centerZ - kh / 2 + .15 + ri * .345;
      place(group, slab(width, height, .024, .035, keys, .005), x + weight * unit / 2, y + .019, z, [-Math.PI / 2, 0, 0]);
      ctx.font = `${label.length > 2 ? 15 : 23}px Arial`;
      ctx.fillText(label, (x + weight * unit / 2 + kw / 2) / kw * canvas.width, (z - centerZ + kh / 2) / kh * canvas.height);
      x += weight * unit;
    });
  });
  const texture = new T.CanvasTexture(canvas); texture.colorSpace = T.SRGBColorSpace;
  texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  const legends = new T.MeshBasicMaterial({map: texture, transparent: true, depthWrite: false, toneMapped: false});
  legends.userData.ownedMap = true;
  place(group, new T.Mesh(new T.PlaneGeometry(kw, kh), legends), 0, y + .033, centerZ, [-Math.PI / 2, 0, 0]);
  // Instancing keeps the fine speaker perforations to one draw call.
  const holes = new T.InstancedMesh(new T.CircleGeometry(.008, 6), black, 2 * 9 * 58);
  const dummy = new T.Object3D(); let index = 0;
  for (const side of [-1, 1]) for (let col = 0; col < 9; col++) for (let row = 0; row < 58; row++) {
    dummy.position.set(side * (2.91 + col * .026), y + .005, .43 + row * .036);
    dummy.rotation.x = -Math.PI / 2; dummy.updateMatrix(); holes.setMatrixAt(index++, dummy.matrix);
  }
  group.add(holes);
  const rim = new T.MeshStandardMaterial({color: '#63676c', metalness: .75, roughness: .35});
  place(group, slab(3.03, 1.55, .006, .11, rim, .001), 0, y - .001, 3.45, [-Math.PI / 2, 0, 0]);
  place(group, slab(3.00, 1.52, .008, .105, metal, .002), 0, y + .001, 3.45, [-Math.PI / 2, 0, 0]);
}

async function macbookPro16(spec) {
  // 355.7 x 248.1 x 16.8 mm closed envelope; static 102-degree display opening.
  const w = 6.8, unit = w / 355.7, d = 248.1 * unit, baseThickness = .242, lidThickness = .079;
  const lidH = d - .08, hingeY = -2.35;
  const group = new T.Group(), clay = spec.finish === 'clay';
  const color = new T.Color(spec.color || '#aeb2b6');
  const metal = new T.MeshPhysicalMaterial({color, metalness: clay ? 0 : .88, roughness: clay ? .78 : .31,
    clearcoat: clay ? 0 : .15});
  const black = new T.MeshPhongMaterial({color: '#040507', specular: '#08090b', shininess: 15});
  const baseY = hingeY - baseThickness / 2;
  place(group, slab(w, d, baseThickness, .24, metal, .04), 0, baseY, d / 2 - .16, [-Math.PI / 2, 0, 0]);
  macKeyboard(group, hingeY + .004, metal, black);
  const hinge = disk(.095, 5.28, black);
  place(group, hinge, 0, hingeY + .013, .002, [0, 0, Math.PI / 2]);
  const lid = new T.Group(); lid.position.set(0, hingeY + .045, -.07); lid.rotation.x = rad(-12); group.add(lid);
  place(lid, slab(w, lidH, lidThickness, .20, metal, .02), 0, lidH / 2, 0);
  place(lid, slab(w - .075, lidH - .075, .013, .16, black, .003), 0, lidH / 2, lidThickness / 2);
  const sw = w - .23, sh = sw * 2234 / 3456, sy = lidH - .092 - sh / 2, sz = lidThickness / 2 + .013;
  const feed = await media(spec, sw, sh);
  place(lid, new T.Mesh(screenGeometry(sw, sh, .125), new T.MeshBasicMaterial({map: feed.texture, toneMapped: false})), 0, sy, sz);
  place(lid, slab(.66, .147, .008, .033, black, .002), 0, sy + sh / 2 - .069, sz + .007);
  const camera = new T.MeshPhysicalMaterial({color: '#102139', metalness: .5, roughness: .15});
  place(lid, disk(.025, .003, camera), .06, sy + sh / 2 - .071, sz + .014, [Math.PI / 2, 0, 0]);
  const logo = new T.MeshPhysicalMaterial({color: '#101113', metalness: .7, roughness: .24});
  appleMark(lid, .72, 0, lidH / 2, -lidThickness / 2 - .001, logo);
  const portMetal = new T.MeshStandardMaterial({color: color.clone().multiplyScalar(.68), metalness: .8, roughness: .3});
  const port = (side, z, width, height, radius) => {
    const x = side * (w / 2 + .001);
    place(group, slab(width, height, .005, radius, portMetal, .001), x, baseY + .009, z, [0, side * Math.PI / 2, 0]);
    place(group, slab(width - .018, height - .018, .006, Math.max(.005, radius - .009), black, .001),
      x + side * .004, baseY + .009, z, [0, side * Math.PI / 2, 0]);
  };
  port(-1, .43, .27, .087, .035); // MagSafe
  port(-1, .95, .16, .064, .027); port(-1, 1.30, .16, .064, .027);
  port(-1, 1.82, .068, .068, .033);
  port(1, .49, .27, .093, .024); // HDMI
  port(1, 1.01, .16, .064, .027); port(1, 1.66, .47, .039, .014);
  place(group, slab(.84, .039, .008, .016, black, .002), 0, hingeY - .031, d - .158);
  for (const x of [-2.6, 2.6]) for (const z of [.52, d - .86]) {
    place(group, disk(.16, .028, black), x, hingeY - baseThickness - .006, z);
  }
  return {group, feed, spec};
}

async function device(spec) {
  if (spec.model === 'iphone-17-pro-max') return iphone17ProMax(spec);
  if (spec.model === 'macbook-pro-16') return macbookPro16(spec);
  const model = spec.model || 'phone';
  const dimensions = {phone: [2.34, 4.82, .22, .29], tablet: [4.35, 5.8, .20, .24],
    laptop: [6.2, 3.95, .16, .17], panel: [6.0, 6.0 * spec.media.height / spec.media.width, .10, .13]};
  const [w, h, depth, radius] = dimensions[model];
  const group = new T.Group();
  const clay = spec.finish === 'clay';
  const metal = new T.MeshPhysicalMaterial({color: spec.color || (clay ? '#e2ddd5' : '#848b96'),
    metalness: clay ? 0 : .92, roughness: clay ? .75 : .25, clearcoat: clay ? 0 : .25});
  const bezel = new T.MeshPhysicalMaterial({color: '#090b10', metalness: .18, roughness: .24, clearcoat: 1});
  group.add(slab(w, h, depth, radius, metal));
  const front = slab(w - .05, h - .05, .035, radius - .025, bezel, .008);
  front.position.z = depth / 2 + .012; group.add(front);
  const border = model === 'phone' ? .085 : model === 'tablet' ? .14 : .10;
  const sw = w - border * 2, sh = h - border * 2;
  const feed = await media(spec, sw, sh);
  const screen = new T.Mesh(screenGeometry(sw, sh, Math.max(.02, radius - border)),
    new T.MeshBasicMaterial({map: feed.texture, toneMapped: false}));
  screen.position.z = depth / 2 + .04; group.add(screen);
  if (model === 'phone' || model === 'tablet') {
    const power = slab(.05, .52, .09, .02, metal, .005);
    power.position.set(w / 2 + .018, .7, 0); group.add(power);
    const volume = power.clone(); volume.position.set(-w / 2 - .018, .9, 0); group.add(volume);
    const speaker = slab(.38, .035, .015, .012, bezel, .003);
    speaker.position.set(0, h / 2 - .048, depth / 2 + .022); group.add(speaker);
    // A generic camera cluster makes the rear view a modeled surface, without a brand asset.
    const bump = slab(.73, .83, .08, .13, metal, .016);
    bump.position.set(-w / 2 + .55, h / 2 - .6, -depth / 2 - .04); group.add(bump);
    for (const y of [h / 2 - .4, h / 2 - .8]) {
      const lens = new T.Mesh(new T.CylinderGeometry(.145, .145, .09, 40), bezel);
      lens.rotation.x = Math.PI / 2; lens.position.set(-w / 2 + .55, y, -depth / 2 - .105); group.add(lens);
    }
  }
  if (model === 'laptop') {
    const base = slab(w + .16, 3.8, .14, .16, metal);
    base.rotation.x = -Math.PI / 2; base.position.set(0, -h / 2 - .045, 1.72); group.add(base);
    const keyboard = slab(w - .55, 1.68, .018, .09, bezel, .004);
    keyboard.rotation.x = -Math.PI / 2; keyboard.position.set(0, -h / 2 + .035, 1.13); group.add(keyboard);
    const keyMat = new T.MeshStandardMaterial({color: '#30343b', roughness: .6});
    for (let row = 0; row < 4; row++) for (let col = 0; col < 13; col++) {
      const key = slab(.36, .29, .016, .025, keyMat, .004);
      key.rotation.x = -Math.PI / 2; key.position.set((col - 6) * .40, -h / 2 + .051, .56 + row * .37); group.add(key);
    }
    const pad = slab(2.15, 1.12, .012, .08, metal, .004);
    pad.rotation.x = -Math.PI / 2; pad.position.set(0, -h / 2 + .035, 2.67); group.add(pad);
  }
  return {group, feed, spec};
}

function pose(item, index, count, progress, motion) {
  const s = item.spec;
  let position = s.position || [(index - (count - 1) / 2) * 2.65, index % 2 ? -.18 : .18, index * -.7];
  let rotation = s.rotation || [8, count > 1 ? (index - (count - 1) / 2) * -13 : -16, count > 1 ? (index % 2 ? 4 : -5) : -5];
  let scale = s.scale || 1;
  if (s.keyframes) {
    const frames = s.keyframes;
    const i = Math.min(frames.length - 2, Math.max(0, frames.findIndex((f, i) => i < frames.length - 1 && progress <= frames[i + 1].at)));
    const a = frames[i], b = frames[i + 1];
    const t = clamp((progress - a.at) / (b.at - a.at), 0, 1), p = b.ease === 'linear' ? t : smooth(t);
    position = a.position.map((v, j) => T.MathUtils.lerp(v, b.position[j], p));
    // Euler interpolation keeps explicit full-turn keyframes; quaternions would take the short arc.
    rotation = a.rotation.map((v, j) => T.MathUtils.lerp(v, b.rotation[j], p));
    scale = T.MathUtils.lerp(a.scale || scale, b.scale || scale, p);
  } else {
    position = [...position]; rotation = [...rotation];
    const p = smooth(progress);
    if (motion === 'orbit') {rotation[1] += 25 * (p - .5); rotation[0] += 5 * (p - .5);}
    if (motion === 'reveal') {rotation[1] += 58 * (1 - p); position[1] -= .35 * (1 - p);}
    if (motion === 'rise') {position[1] += .65 * (p - .5); rotation[2] += 7 * (p - .5);}
    if (motion === 'push') scale *= 1 + .12 * p;
  }
  item.group.position.fromArray(position); item.group.rotation.set(...rotation.map(rad)); item.group.scale.setScalar(scale);
}

async function createScene(spec, aspect, region) {
  const scene = new T.Scene();
  const background = spec.background || '#e5e3df';
  scene.background = new T.Color(background); scene.environment = environment;
  const lighting = spec.lighting || 'studio';
  scene.environmentIntensity = lighting === 'rim' ? .75 : lighting === 'soft' ? 1.3 : 1;
  const camera = new T.PerspectiveCamera(spec.camera?.fov || 32, aspect, .1, 200);
  const key = new T.DirectionalLight('#fff4e7', lighting === 'rim' ? 2 : 3.2);
  key.position.set(-3, 7, 6); key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024); key.shadow.camera.left = -10; key.shadow.camera.right = 10;
  key.shadow.camera.top = 10; key.shadow.camera.bottom = -10;
  key.shadow.normalBias = .025; key.shadow.bias = -.0001; key.shadow.radius = 5; key.shadow.blurSamples = 12;
  scene.add(key, new T.HemisphereLight('#ffffff', background, .65));
  const rim = new T.DirectionalLight(lighting === 'rim' ? '#b9d7ff' : '#e8edff', lighting === 'rim' ? 5 : 2);
  rim.position.set(5, 3, -4); scene.add(rim);
  const group = new T.Group(); scene.add(group);
  const items = [];
  for (const s of spec.devices) {const item = await device(s); group.add(item.group); items.push(item);}
  if (spec.floor !== false) {
    const ground = new T.Mesh(new T.PlaneGeometry(200, 200), new T.ShadowMaterial({opacity: lighting === 'soft' ? .15 : .23}));
    ground.rotation.x = -Math.PI / 2; ground.position.y = -3.25; ground.receiveShadow = true; scene.add(ground);
  }
  return {scene, camera, items, spec, region};
}

function disposeScene(value) {
  value.items.forEach(i => i.feed.dispose());
  value.scene.traverse(o => {
    if (o.isInstancedMesh) o.dispose();
    o.geometry?.dispose();
    if (o.material) {
      if (o.material.userData.ownedMap) o.material.map.dispose();
      o.material.dispose();
    }
    o.shadow?.dispose();
  });
}

window.studio = {
  init(width, height) {
    renderer = new T.WebGLRenderer({antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance'});
    renderer.setSize(width, height); renderer.setPixelRatio(1);
    output = document.createElement('canvas'); output.width = width; output.height = height;
    outputContext = output.getContext('2d', {alpha: false});
    renderer.outputColorSpace = T.SRGBColorSpace; renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15; renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.VSMShadowMap;
    document.body.appendChild(renderer.domElement);
    const pmrem = new T.PMREMGenerator(renderer), room = new RoomEnvironment();
    environment = pmrem.fromScene(room, .04).texture; room.dispose(); pmrem.dispose();
    const gl = renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info');
    return {revision: T.REVISION, renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)};
  },
  async frame({id, spec, elapsed, progress, reduced, region}) {
    if (!scenes.has(id)) {
      if (scenes.size >= 3) {const oldest = scenes.keys().next().value; disposeScene(scenes.get(oldest)); scenes.delete(oldest);}
      scenes.set(id, await createScene(spec, output.width / output.height, region));
    }
    active = scenes.get(id); scenes.delete(id); scenes.set(id, active);
    const {scene, camera, items} = active;
    const p = reduced ? .5 : clamp(progress, 0, 1);
    for (let i = 0; i < items.length; i++) {
      pose(items[i], i, items.length, p, reduced ? 'still' : spec.motion || 'orbit');
      await items[i].feed.update(elapsed);
    }
    const cam = spec.camera || {}, start = cam.position || [0, 1, items.some(i => ['laptop', 'macbook-pro-16'].includes(i.spec.model)) ? 16.5 : 15];
    const end = cam.end_position || start, target = cam.target || [0, 0, 0], endTarget = cam.end_target || target;
    camera.position.fromArray(start.map((v, i) => T.MathUtils.lerp(v, end[i], smooth(p))));
    camera.lookAt(...target.map((v, i) => T.MathUtils.lerp(v, endTarget[i], smooth(p))));
    const [x, y, width, height] = region || [0, 0, output.width, output.height];
    renderer.setSize(width, height, false);
    renderer.setViewport(0, 0, width, height); renderer.setScissorTest(false);
    camera.aspect = width / height; camera.updateProjectionMatrix();
    renderer.render(scene, camera);
    outputContext.fillStyle = spec.background || '#e5e3df';
    outputContext.fillRect(0, 0, output.width, output.height);
    outputContext.drawImage(renderer.domElement, x, y, width, height);
    return output.toDataURL('image/png').split(',')[1];
  },
};
