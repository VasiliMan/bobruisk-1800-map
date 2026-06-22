/* Bobruisk uezd land-ownership map.
   Base = scanned General Survey plan, tiled for Leaflet CRS.Simple.
   Parcels are stored in pixel coordinates of the source scan (15039x14407).
   parcels.geojson: GeoJSON FeatureCollection; each Polygon's coordinates are
   [x, y] PIXEL positions (not lon/lat). app converts via map.unproject(...,MAX_Z). */

const IMG_W = 15039, IMG_H = 14407, MAX_Z = 6, TILE = 256;
const PAGE_W = 2400, PAGE_H = 3200;          // natural size of the owner-index page scans

const map = L.map('map', {
  crs: L.CRS.Simple, minZoom: 0, maxZoom: 9, zoomSnap: 0.25, zoomControl: true,
  attributionControl: false
});

// pixel (x,y) in source scan -> Leaflet LatLng
const px = (x, y) => map.unproject([x, y], MAX_Z);
const toXY = (latlng) => { const p = map.project(latlng, MAX_Z); return [p.x, p.y]; };

const imgBounds = L.latLngBounds(px(0, 0), px(IMG_W, IMG_H));
L.tileLayer('tiles/{z}/{x}/{y}.jpg', {
  tileSize: TILE, minNativeZoom: 0, maxNativeZoom: MAX_Z, bounds: imgBounds, noWrap: true
}).addTo(map);
map.fitBounds(imgBounds);
map.setMaxBounds(imgBounds.pad(0.4));

// ---- color per owner (stable from id hash) ----
function ownerColor(id, owner) {
  if (owner && /монаст|церк|плебан|costel|косте|собор/i.test((owner.title||'')+(owner.name||'')))
    {/* institutions still colored, just noted */}
  let h = 0; for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const hue = h % 360;
  const sat = 55 + (h >> 8) % 25;
  const lig = 58 + (h >> 16) % 14;
  return `hsl(${hue} ${sat}% ${lig}%)`;
}

let OWNERS = [], OWNER_BY_ID = {}, KEY2OWNER = {}, KEY2OWNERS = {}, NUM2OWNERS = {};
let PARCELS = { type: 'FeatureCollection', features: [] };
let layersByOwner = {}, layerByFid = {};
let parcelLayerGroup = L.layerGroup().addTo(map);
let labelGroup = L.layerGroup().addTo(map);
let armsGroup = L.layerGroup().addTo(map);
let editMode = false, selectedFid = null;

Promise.all([
  fetch('data/owners.json').then(r => r.json()),
  fetch('data/parcels.geojson').then(r => r.ok ? r.json() : { type:'FeatureCollection', features:[] }).catch(() => ({ type:'FeatureCollection', features:[] }))
]).then(([od, pd]) => {
  OWNERS = od.owners;
  OWNERS.forEach(o => { o.color = ownerColor(o.id, o); OWNER_BY_ID[o.id] = o;
    o.parcels.forEach(p => { const k = p.chast + ':' + p.num;
      KEY2OWNER[k] = o.id; (KEY2OWNERS[k] = KEY2OWNERS[k] || []).push(o.id);
      // parcels are now keyed by NUMBER alone (часть ignored); a number may be co-owned
      const n = String(p.num); (NUM2OWNERS[n] = NUM2OWNERS[n] || []).push({ id: o.id, major: !!p.major }); }); });
  const fileParcels = pd && pd.features ? pd : PARCELS;
  const local = loadLocal();
  if (local && local.features) { PARCELS = local; showRestoreBanner(); }
  else PARCELS = fileParcels;
  window._fileParcels = fileParcels;       // kept so "load from file" can discard local edits
  buildSidebar(); renderParcels(); updateStat();
});

// ---- autosave to browser localStorage (safety net; Export still writes the real file) ----
const LS_KEY = 'bobruisk_parcels_v1';
let saveTimer = null;
function markDirty() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(PARCELS));
      localStorage.setItem(LS_KEY + '_t', new Date().toISOString());
      const el = document.getElementById('saveind');
      if (el) el.textContent = '✓ автосохранено ' + new Date().toLocaleTimeString('ru');
    } catch (e) { console.warn('autosave failed', e); }
  }, 400);
}
function loadLocal() {
  try { const s = localStorage.getItem(LS_KEY); return s ? JSON.parse(s) : null; }
  catch (e) { return null; }
}
function showRestoreBanner() {
  const t = localStorage.getItem(LS_KEY + '_t');
  const bar = document.createElement('div');
  bar.id = 'restore-banner';
  bar.innerHTML = `Загружены ваши правки из автосохранения браузера` +
    (t ? ` (${new Date(t).toLocaleString('ru')})` : '') +
    `. <button id="rb-keep">оставить</button> <button id="rb-file">загрузить из файла</button>`;
  document.getElementById('sidebar').prepend(bar);
  document.getElementById('rb-keep').onclick = () => bar.remove();
  document.getElementById('rb-file').onclick = () => {
    if (!confirm('Отбросить правки из автосохранения и загрузить data/parcels.geojson?')) return;
    PARCELS = JSON.parse(JSON.stringify(window._fileParcels));
    localStorage.removeItem(LS_KEY); localStorage.removeItem(LS_KEY + '_t');
    selectedFid = null; clearVertexEdit(); renderParcels(); renderEditSel && renderEditSel();
    updateStat(); bar.remove();
  };
}

// ---- render parcels ----
// All owners of a parcel NUMBER (часть ignored). Co-owners are treated as EQUAL
// shares — no major/minor; listing order is just owners.json order.
function ownersOfNum(num) {
  const entries = NUM2OWNERS[String(num)] || [];
  const seen = new Set(), list = [];
  entries.forEach(e => { if (OWNER_BY_ID[e.id] && !seen.has(e.id)) { seen.add(e.id); list.push(OWNER_BY_ID[e.id]); } });
  return list;
}
function ownersOfFeature(f) { return ownersOfNum(f.properties.num); }
function ownerOfFeature(f) { return ownersOfFeature(f)[0] || null; }

// ---- geometry helpers (pixel space) ----
function ringArea(r) { let a = 0; for (let i = 0, n = r.length - 1; i < n; i++) a += r[i][0]*r[i+1][1] - r[i+1][0]*r[i][1]; return Math.abs(a) / 2; }
function pointInRing(p, r) {
  let inside = false;
  for (let i = 0, j = r.length - 2; i < r.length - 1; j = i++) {
    const xi = r[i][0], yi = r[i][1], xj = r[j][0], yj = r[j][1];
    if (((yi > p[1]) !== (yj > p[1])) && (p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}
// child considered enclosed by parent if >=85% of its vertices fall inside parent ring
function ringInside(child, parent) {
  let inside = 0, tot = child.length - 1;
  for (let i = 0; i < tot; i++) if (pointInRing(child[i], parent)) inside++;
  return tot > 0 && inside / tot >= 0.85;
}
// returns { fid -> [holeRing,...] } : direct enclaves punched as holes in their smallest container
function computeEnclaves(active) {
  active.forEach(f => { f._ring = f.geometry.coordinates[0]; f._area = ringArea(f._ring); });
  const holes = {};
  active.forEach(child => {
    let best = null;
    active.forEach(parent => {
      if (parent === child || parent._area <= child._area) return;
      if (ringInside(child._ring, parent._ring) && (!best || parent._area < best._area)) best = parent;
    });
    child._parentFid = best ? best.properties.fid : null;
    if (best) (holes[best.properties.fid] = holes[best.properties.fid] || []).push(child._ring);
  });
  return holes;
}

function renderParcels() {
  parcelLayerGroup.clearLayers(); labelGroup.clearLayers(); armsGroup.clearLayers();
  layersByOwner = {}; layerByFid = {};
  const fill = document.getElementById('toggle-fill').checked;
  const showLabels = document.getElementById('toggle-labels').checked;
  const showArms = document.getElementById('toggle-arms').checked;

  const active = PARCELS.features.filter(f => f.geometry.type === 'Polygon');
  const holesByParent = computeEnclaves(active);
  // draw bigger (containing) parcels first so enclaves sit on top
  const ordered = [...active].sort((a, b) => b._area - a._area);

  ordered.forEach(f => {
    const pr = f.properties;
    const owners = ownersOfFeature(f);
    const owner = owners[0] || null;
    const color = owner ? owner.color : '#999';
    const ringsXY = [f.geometry.coordinates[0], ...(holesByParent[pr.fid] || [])];
    const rings = ringsXY.map(r => r.map(c => px(c[0], c[1])));
    const poly = L.polygon(rings, {
      color: '#6b5a2a', weight: 1, fillColor: color, fillOpacity: fill ? 0.5 : 0, opacity: 0.9
    });
    poly.featureRef = f;
    poly.on('click', () => editMode ? selectParcel(f.properties.fid) : openPopup(poly, f));
    poly.addTo(parcelLayerGroup);
    layerByFid[pr.fid] = poly;
    owners.forEach(o => (layersByOwner[o.id] = layersByOwner[o.id] || []).push(poly));

    // outer-ring centroid (used for number + arms; avoids landing inside a hole)
    const r = f.geometry.coordinates[0];
    let cx = 0, cy = 0; for (let i = 0; i < r.length - 1; i++) { cx += r[i][0]; cy += r[i][1]; }
    const n = r.length - 1; const c = px(cx / n, cy / n);

    // show every co-owner's arms/cross, fanned out side by side at the parcel centre
    const symOwners = owners.filter(o => o.arms || o.inst);
    if (showArms && symOwners.length) {
      const html = symOwners.map(o => o.arms
        ? `<img class="map-arms" src="arms/${o.arms}" alt="">`
        : `<span class="map-cross">${INST_SYM[o.inst] || '✟'}</span>`).join('');
      const w = symOwners.length * 42;
      L.marker(c, { interactive: false, icon: L.divIcon({
        className: 'arms-marker', html, iconSize: [w, 46], iconAnchor: [w / 2, 46] }) }).addTo(armsGroup);
    }
    if (showLabels) {
      L.marker(c, { interactive: false, icon: L.divIcon({
        className: 'parcel-label', html: `<span class="parcel-num">${pr.num}</span>`,
        iconSize: [24, 16], iconAnchor: [12, 0] }) }).addTo(labelGroup);
    }
  });
  if (selectedFid && layerByFid[selectedFid]) enableVertexEdit(layerByFid[selectedFid]);
}

const INST_SYM = { orthodox: '☦', catholic: '✝', uniate: '✠', monastery: '✟' };
const INST_LBL = { orthodox: 'православный храм / монастырь', catholic: 'католический костёл',
                   uniate: 'униатский храм / монастырь', monastery: 'монастырь' };
function armsBlock(owner) {
  if (owner && owner.arms)
    return `<div class="popup-arms"><img src="arms/${owner.arms}" alt="герб">` +
           (owner.arms_cap ? `<div class="arms-cap">${owner.arms_cap}</div>` : '') + `</div>`;
  if (owner && owner.inst)
    return `<div class="popup-arms inst"><span class="inst-sym">${INST_SYM[owner.inst] || '✟'}</span>` +
           `<span>${INST_LBL[owner.inst] || ''}</span></div>`;
  return '';
}
// inline style that shows just the cropped name region of an index page (no image files)
function cropImgStyle(c, maxW, maxH) {
  const scale = Math.min(maxW / c.w, maxH / c.h);
  return `width:${(c.w*scale).toFixed(0)}px;height:${(c.h*scale).toFixed(0)}px;`
    + `background-image:url(verify_img/p${c.page}.jpg);`
    + `background-size:${(PAGE_W*scale).toFixed(0)}px ${(PAGE_H*scale).toFixed(0)}px;`
    + `background-position:${(-c.x*scale).toFixed(1)}px ${(-c.y*scale).toFixed(1)}px;`;
}
function cropBlock(owner) {
  if (!owner || !owner.crop) return '';
  return `<div class="popup-crop"><div class="popup-crop-cap">оригинал записи:</div>`
    + `<div class="popup-crop-img" style="${cropImgStyle(owner.crop, 300, 156)}"></div></div>`;
}
function linksBlock(owner) {
  if (!owner || !owner.links || !owner.links.length) return '';
  return `<div class="popup-links">` +
    owner.links.map(l => `<a href="${l.url}" target="_blank" rel="noopener">${l.label} ↗</a>`).join('') +
    `</div>`;
}
// the detail body for one owner (no name heading): original spelling, title, crop, arms, links
function cardBody(owner) {
  const flag = owner.flag ? `<div class="popup-flag">⚠ ${owner.flag}</div>` : '';
  return `${owner.name_ru ? `<div class="popup-orig">${owner.name_ru}</div>` : ''}
    ${owner.title ? `<div class="popup-meta">${owner.title}</div>` : ''}
    ${cropBlock(owner)}${flag}${armsBlock(owner)}${linksBlock(owner)}`;
}
function nameHead(owner) {
  // "⚠ чтение требует проверки" badge hidden for now (uncertain flag kept in data)
  return `<span class="co-sw" style="background:${owner.color}"></span>${owner.name}`;
}
// sole owner: full card, always expanded
function ownerCard(owner) {
  if (!owner) return `<div class="popup-name">— владелец не определён —</div>`;
  return `<div class="owner-card"><div class="popup-name">${nameHead(owner)}</div>${cardBody(owner)}</div>`;
}
// co-owner: collapsed row that expands on click (toggle handled by a delegated listener)
function coItem(owner) {
  return `<div class="co-item"><div class="co-toggle"><span class="co-caret">▸</span>${nameHead(owner)}</div>` +
    `<div class="co-body">${cardBody(owner)}</div></div>`;
}
let currentPopupCtx = null;   // context for the "сообщить об ошибке" button in the open popup
function openPopup(poly, f) {
  const pr = f.properties;
  const owners = ownersOfFeature(f);
  let html = `<div class="popup-head">Участок № ${pr.num}</div>`;
  if (owners.length > 1)
    html += `<div class="popup-coowners-h">Несколько владельцев (${owners.length}):</div>` +
            owners.map(coItem).join('');
  else
    html += ownerCard(owners[0] || null);
  if (pr.place) html += `<div class="popup-meta">${pr.place}</div>`;
  html += `<button class="popup-fb" type="button">✎ Сообщить об ошибке</button>`;
  currentPopupCtx = {
    num: pr.num, chast: pr.chast,
    owners: owners.map(o => o.name).join(', ') || '—',
    owner_ids: owners.map(o => o.id).join(','),
  };
  // ensure the popup is at least as wide as the widest crop image (crops can be
  // hidden in collapsed co-owner rows, so size for them up front to avoid overflow)
  let cropW = 0;
  owners.forEach(o => {
    if (o.crop) cropW = Math.max(cropW, o.crop.w * Math.min(300 / o.crop.w, 156 / o.crop.h));
  });
  const opts = { maxWidth: 340 };
  if (cropW) opts.minWidth = Math.min(340, Math.ceil(cropW) + 12);
  poly.bindPopup(html, opts).openPopup();
}
// expand/collapse a co-owner row (delegated so it works for any popup)
document.addEventListener('click', e => {
  const t = e.target.closest('.co-toggle');
  if (t) t.parentElement.classList.toggle('open');
  if (e.target.closest('.popup-fb') && typeof openFeedbackModal === 'function')
    openFeedbackModal(currentPopupCtx);
});

// ---- sidebar ----
function buildSidebar() {
  const list = document.getElementById('owner-list');
  list.innerHTML = '';
  const sorted = [...OWNERS].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
  sorted.forEach(o => {
    const el = document.createElement('div');
    el.className = 'owner'; el.dataset.id = o.id;
    el.dataset.search = (o.name + ' ' + (o.name_ru||'') + ' ' + (o.title||'')).toLowerCase();
    const pcs = [...new Set(o.parcels.map(p => p.num))].join(', ');
    el.innerHTML = `<span class="sw" style="background:${o.color}"></span>
      <span class="nm">${o.name}</span>
      <span class="pc">${pcs}</span>`;
    el.addEventListener('click', () => focusOwner(o.id));
    list.appendChild(el);
  });
}

function focusOwner(id) {
  const polys = layersByOwner[id];
  if (!polys || !polys.length) {
    const o = OWNER_BY_ID[id];
    alert(`«${o.name}»: участок(и) ${[...new Set(o.parcels.map(p=>p.num))].join(', ')} ещё не оцифрованы.`);
    return;
  }
  const b = polys.reduce((acc, p) => acc.extend(p.getBounds()), L.latLngBounds(polys[0].getBounds()));
  map.flyToBounds(b.pad(0.6), { maxZoom: 6 });
  polys.forEach(p => { p.setStyle({ weight: 3, color: '#c0392b' });
    setTimeout(() => p.setStyle({ weight: 1, color: '#6b5a2a' }), 2200); });
  if (polys.length === 1 && !editMode) openPopup(polys[0], polys[0].featureRef);
}

document.getElementById('search').addEventListener('input', e => {
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll('.owner').forEach(el =>
    el.classList.toggle('hidden', q && !el.dataset.search.includes(q)));
});
document.getElementById('toggle-fill').addEventListener('change', renderParcels);
document.getElementById('toggle-labels').addEventListener('change', renderParcels);
document.getElementById('toggle-arms').addEventListener('change', renderParcels);

function updateStat() {
  document.getElementById('stat').textContent =
    `${OWNERS.length} владельцев · ${PARCELS.features.length} участков`;
}

// ================= EDIT MODE =================
document.getElementById('toggle-edit').addEventListener('change', e => {
  editMode = e.target.checked;
  document.getElementById('edit-panel').classList.toggle('hidden', !editMode);
  if (!editMode) { selectedFid = null; clearVertexEdit(); }
  renderParcels();
});

let vtxMarkers = [], editedPoly = null;
function clearVertexEdit() { vtxMarkers.forEach(m => map.removeLayer(m)); vtxMarkers = []; editedPoly = null; }

function selectParcel(fid) {
  selectedFid = fid; clearVertexEdit();
  const poly = layerByFid[fid]; if (poly) enableVertexEdit(poly);
  renderEditSel();
}

function enableVertexEdit(poly) {
  clearVertexEdit(); editedPoly = poly;
  const f = poly.featureRef;
  const ring = f.geometry.coordinates[0];
  poly.setStyle({ weight: 3, color: '#c0392b' });
  const redraw = () => poly.setLatLngs([ring.map(p => px(p[0], p[1]))]);
  // number of distinct (non-closing) vertices
  const n = (ring.length > 1 && ring[0][0] === ring[ring.length-1][0]
             && ring[0][1] === ring[ring.length-1][1]) ? ring.length - 1 : ring.length;
  const ensureClosed = () => {
    if (ring.length > 1) ring[ring.length - 1] = ring[0].slice();
  };

  // --- real vertex handles (solid red) ---
  for (let i = 0; i < n; i++) {
    const m = L.marker(px(ring[i][0], ring[i][1]), { draggable: true,
      icon: L.divIcon({ className: 'vtx', iconSize: [13, 13] }) }).addTo(map);
    m.vtxIndex = i;
    m.on('drag', () => {
      const xy = toXY(m.getLatLng());
      ring[m.vtxIndex] = xy;
      if (m.vtxIndex === 0) ensureClosed();
      redraw();
    });
    m.on('dragend', () => { markDirty(); enableVertexEdit(poly); }); // refresh midpoints
    m.on('contextmenu', () => { // right-click = delete vertex
      if (n <= 3) return;
      ring.splice(m.vtxIndex, 1);
      ensureClosed(); markDirty();
      enableVertexEdit(poly);
    });
    vtxMarkers.push(m);
  }

  // --- midpoint handles (hollow): drag one to insert a new vertex on that edge ---
  for (let i = 0; i < n; i++) {
    const a = ring[i], b = ring[(i + 1) % n];
    const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    const mm = L.marker(px(mid[0], mid[1]), { draggable: true,
      icon: L.divIcon({ className: 'vtx-mid', iconSize: [11, 11] }) }).addTo(map);
    mm.edgeIndex = i; mm.inserted = false;
    mm.on('dragstart', () => {
      ring.splice(mm.edgeIndex + 1, 0, toXY(mm.getLatLng()));
      ensureClosed(); mm.inserted = true; mm.newIndex = mm.edgeIndex + 1;
    });
    mm.on('drag', () => {
      if (!mm.inserted) return;
      ring[mm.newIndex] = toXY(mm.getLatLng());
      redraw();
    });
    mm.on('dragend', () => { markDirty(); enableVertexEdit(poly); }); // rebuild: new vertex + fresh midpoints
    vtxMarkers.push(mm);
  }
}

// write a primary + co-owner list back onto a parcel's properties (dedup, keep order)
function commitOwners(pr, primary, extras) {
  const list = [...new Set([primary, ...extras].filter(Boolean))];
  if (list.length > 1) { pr.owner_ids = list; pr.owner_id = list[0]; }
  else if (list.length === 1) { pr.owner_id = list[0]; delete pr.owner_ids; }
  else { delete pr.owner_id; delete pr.owner_ids; }
}
function renderEditSel() {
  const box = document.getElementById('edit-sel');
  const f = PARCELS.features.find(x => x.properties.fid === selectedFid);
  if (!f) { box.innerHTML = '<em>участок не выбран</em>'; return; }
  const pr = f.properties;
  const primary = (pr.owner_ids && pr.owner_ids[0]) || pr.owner_id || '';
  const extras = pr.owner_ids ? pr.owner_ids.slice(1) : [];
  const optsFor = (sel) => OWNERS.map(o => `<option value="${o.id}" ${o.id===sel?'selected':''}>${o.name}</option>`).join('');
  const coRows = extras.map((id, i) =>
    `<div class="ed-co-row"><span>${(OWNER_BY_ID[id]||{}).name || id}</span>` +
    `<button class="ed-co-del" data-i="${i}" title="убрать совладельца">✕</button></div>`).join('');
  box.innerHTML = `
    <label>№ участка<input id="ed-num" value="${pr.num}"></label>
    <label>Владелец<select id="ed-owner"><option value="">— по номеру —</option>${optsFor(primary)}</select></label>
    <div class="ed-co">Несколько владельцев:${coRows || '<span class="ed-co-none">— нет —</span>'}
      <div class="ed-co-add"><select id="ed-co-sel"><option value="">+ добавить совладельца…</option>${optsFor('')}</select></div></div>
    <label>Место/подпись<input id="ed-place" value="${pr.place||''}"></label>
    <label><input type="checkbox" id="ed-draft" ${pr.status==='draft'?'checked':''}> черновик</label>
    <button id="ed-del" style="border-color:#c0392b;color:#c0392b">удалить участок</button>`;
  const upd = () => {
    pr.num = document.getElementById('ed-num').value;
    commitOwners(pr, document.getElementById('ed-owner').value, extras);
    pr.place = document.getElementById('ed-place').value || undefined;
    pr.status = document.getElementById('ed-draft').checked ? 'draft' : 'verified';
    renderParcels(); updateStat(); markDirty();
  };
  ['ed-num','ed-owner','ed-place','ed-draft'].forEach(id =>
    document.getElementById(id).addEventListener('change', upd));
  document.getElementById('ed-co-sel').addEventListener('change', e => {
    const id = e.target.value; if (!id) return;
    commitOwners(pr, document.getElementById('ed-owner').value, [...extras, id]);
    renderParcels(); updateStat(); markDirty(); renderEditSel();
  });
  box.querySelectorAll('.ed-co-del').forEach(btn => btn.addEventListener('click', () => {
    const i = +btn.dataset.i; const next = extras.slice(); next.splice(i, 1);
    commitOwners(pr, document.getElementById('ed-owner').value, next);
    renderParcels(); updateStat(); markDirty(); renderEditSel();
  }));
  document.getElementById('ed-del').addEventListener('click', () => {
    PARCELS.features = PARCELS.features.filter(x => x.properties.fid !== selectedFid);
    selectedFid = null; clearVertexEdit(); renderParcels(); renderEditSel(); updateStat(); markDirty();
  });
}

document.getElementById('btn-newparcel').addEventListener('click', () => {
  const c = map.getCenter(); const [x, y] = toXY(c); const s = 120;
  const ring = [[x-s,y-s],[x+s,y-s],[x+s,y+s],[x-s,y+s],[x-s,y-s]];
  const fid = 'p' + Date.now();
  PARCELS.features.push({ type:'Feature', properties:{ fid, chast:3, num:'?', status:'draft' },
    geometry:{ type:'Polygon', coordinates:[ring] } });
  renderParcels(); selectParcel(fid); updateStat(); markDirty();
});

document.getElementById('btn-export').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(PARCELS, null, 1)], { type:'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'parcels.geojson'; a.click();
});
