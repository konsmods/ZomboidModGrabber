const el = (id) => document.getElementById(id);

const urlInput = el("collectionUrl");
const scanBtn = el("scanBtn");
const statusEl = el("status");
const boxesEl = el("collectionBoxes");
const emptyHint = el("emptyHint");
const countEl = el("count");
const modsOut = el("modsOut");
const workshopOut = el("workshopOut");
const mapsOut = el("mapsOut");
const mapsRow = el("mapsRow");
const build42Toggle = el("build42Toggle");
const clearBtn = el("clearBtn");

let state = { collectionOrder: [], collections: {}, mods: {} };
let boxSortable = null;
let modSortables = [];

const COLLAPSE_KEY = "pz-mod-grabber.collapsed";
let collapsed = loadCollapsed();

function loadCollapsed() {
  try {
    return new Set(JSON.parse(localStorage.getItem(COLLAPSE_KEY) || "[]"));
  } catch {
    return new Set();
  }
}
function saveCollapsed() {
  try {
    localStorage.setItem(COLLAPSE_KEY, JSON.stringify([...collapsed]));
  } catch { /* ignore */ }
}

function setStatus(msg, kind) {
  statusEl.textContent = msg || "";
  statusEl.className = "status" + (kind ? " " + kind : "");
}

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function collectionLabel(col) {
  return col.name || `Collection ${col.id}`;
}

function render() {
  renderBoxes();
}

function renderModItem(id) {
  const mod = state.mods[id];
  const li = document.createElement("li");
  li.className = "mod-item";
  li.dataset.id = id;
  if (!mod.ok) li.classList.add("failed");
  else if (!mod.modIds || mod.modIds.length === 0) li.classList.add("no-modid");
  if (mod.enabled === false) li.classList.add("disabled");

  const modIds = mod.modIds || [];
  const disabled = new Set(mod.disabledModIds || []);

  const metaBits = [`<a class="wsid wsid-link" href="https://steamcommunity.com/sharedfiles/filedetails/?id=${escapeAttr(id)}" target="_blank" rel="noopener">${escapeHtml(id)}</a>`];
  if (!mod.ok) {
    metaBits.push(`<span class="fail-tag">fetch failed</span>`);
  } else if (modIds.length === 0) {
    metaBits.push(`<span class="warn-tag">no Mod ID found — check manually</span>`);
  } else if (modIds.length > 1) {
    metaBits.push(`<span class="warn-tag">${modIds.length} mod ids — verify</span>`);
  }

  let togglesHtml = "";
  if (modIds.length > 1) {
    togglesHtml = `<div class="modid-toggles">` + modIds.map((mid) => {
      const on = !disabled.has(mid);
      return `<label class="modid-toggle" title="Enable/disable this Mod ID in the output"><input type="checkbox" data-mid="${escapeAttr(mid)}" ${on ? "checked" : ""}> <code>${escapeHtml(mid)}</code></label>`;
    }).join("") + `</div>`;
  }

  li.innerHTML = `
    <div class="mod-top">
      <span class="drag-handle" title="Drag to reorder">⠿</span>
      <div class="mod-main">
        <div class="mod-name" title="${escapeAttr(mod.name || "")}">${escapeHtml(mod.name || "(untitled)")}</div>
        <div class="mod-meta">${metaBits.join("")}</div>
      </div>
      <input type="checkbox" class="enable-toggle mod-enable" title="Include this mod in the output" ${mod.enabled === false ? "" : "checked"}>
      <button class="remove-btn" title="Remove">✕</button>
    </div>
    <div class="mod-bottom">
      <input class="modid-input" type="text" value="${escapeAttr(modIds.join(";"))}" placeholder="ModIdA;ModIdB">
      ${togglesHtml}
    </div>
  `;

  li.querySelector(".modid-input").addEventListener("change", (e) => onEditModIds(id, e.target.value));
  li.querySelector(".remove-btn").addEventListener("click", () => onRemove(id));
  li.querySelector(".mod-enable").addEventListener("change", (e) => onToggleModEnabled(id, e.target.checked));
  li.querySelectorAll(".modid-toggle input").forEach((cb) => {
    cb.addEventListener("change", () => onToggleModId(id, cb.dataset.mid, cb.checked));
  });

  return li;
}

function renderBoxes() {
  boxesEl.innerHTML = "";
  modSortables.forEach((s) => s.destroy());
  modSortables = [];

  const cids = state.collectionOrder.filter((c) => state.collections[c]);
  let total = 0;

  for (const cid of cids) {
    const col = state.collections[cid];
    const wsids = (col.order || []).filter((id) => state.mods[id]);
    total += wsids.length;

    const box = document.createElement("div");
    box.className = "collection-box";
    box.dataset.collection = cid;
    if (collapsed.has(cid)) box.classList.add("collapsed");
    if (col.enabled === false) box.classList.add("disabled");

    const header = document.createElement("div");
    header.className = "box-header";
    header.innerHTML = `
      <span class="drag-handle collection-drag" title="Drag to reorder collections">⠿</span>
      <span class="collapse-toggle">${collapsed.has(cid) ? "▸" : "▾"}</span>
      <div class="box-title">
        <div class="collection-name" title="${escapeAttr(col.url || "")}"><a href="${escapeAttr(col.url || "")}" target="_blank" rel="noopener">${escapeHtml(collectionLabel(col))}</a></div>
        <div class="collection-meta">
          <a class="wsid wsid-link" href="${escapeAttr(col.url || "")}" target="_blank" rel="noopener">${escapeHtml(cid)}</a>
          <span>${wsids.length} mods</span>
        </div>
      </div>
      <div class="box-actions">
        <input type="checkbox" class="enable-toggle collection-enable" title="Include this collection in the output" ${col.enabled === false ? "" : "checked"}>
        <button class="refresh-btn" title="Refresh collection">↻</button>
        <button class="remove-btn" title="Delete collection">✕</button>
      </div>
    `;
    header.addEventListener("click", (e) => {
      if (e.target.closest("button") || e.target.closest(".collection-drag") || e.target.closest("a") || e.target.closest("input")) return;
      onToggleCollection(cid);
    });
    header.querySelector(".refresh-btn").addEventListener("click", () => onRefreshCollection(cid));
    header.querySelector(".remove-btn").addEventListener("click", () => onDeleteCollection(cid));
    header.querySelector(".collection-enable").addEventListener("change", (e) => onToggleCollectionEnabled(cid, e.target.checked));
    box.appendChild(header);

    const ul = document.createElement("ul");
    ul.className = "mod-list";
    ul.dataset.collection = cid;
    for (const id of wsids) ul.appendChild(renderModItem(id));
    box.appendChild(ul);
    boxesEl.appendChild(box);

    modSortables.push(new Sortable(ul, {
      handle: ".drag-handle",
      animation: 150,
      onEnd: () => onReorder(cid, ul),
    }));
  }

  countEl.textContent = total ? `(${total})` : "";
  emptyHint.hidden = cids.length > 0;

  buildOutputs();

  if (!boxSortable) {
    boxSortable = new Sortable(boxesEl, {
      handle: ".collection-drag",
      animation: 150,
      onEnd: onReorderCollections,
    });
  }
}

function onToggleCollection(cid) {
  if (collapsed.has(cid)) collapsed.delete(cid);
  else collapsed.add(cid);
  saveCollapsed();
  const box = boxesEl.querySelector(`.collection-box[data-collection="${cid}"]`);
  if (box) {
    box.classList.toggle("collapsed", collapsed.has(cid));
    box.querySelector(".collapse-toggle").textContent = collapsed.has(cid) ? "▸" : "▾";
  }
}

function orderedIds() {
  const seen = new Set();
  const ids = [];
  const cids = state.collectionOrder.filter((c) => state.collections[c]);
  for (const cid of cids) {
    const col = state.collections[cid];
    if (col.enabled === false) continue;
    for (const id of col.order || []) {
      const mod = state.mods[id];
      if (!mod || mod.enabled === false) continue;
      if (!seen.has(id)) {
        seen.add(id);
        ids.push(id);
      }
    }
  }
  return ids;
}

function buildOutputs() {
  const ids = orderedIds();
  const useB42 = build42Toggle.checked;

  const modIdLines = [];
  const workshopLines = [];
  const mapSet = new Set();

  for (const id of ids) {
    const mod = state.mods[id];
    workshopLines.push(id);
    const disabled = new Set(mod.disabledModIds || []);
    for (const mid of mod.modIds || []) {
      if (disabled.has(mid)) continue;
      modIdLines.push(useB42 ? `\\${mid}` : mid);
    }
    for (const m of mod.maps || []) {
      mapSet.add(m);
    }
  }

  modsOut.value = `Mods=${modIdLines.join(";")}`;
  workshopOut.value = `WorkshopItems=${workshopLines.join(";")}`;

  if (mapSet.size > 0) {
    mapsRow.hidden = false;
    mapsOut.value = `Map=${[...mapSet].join(";")}`;
  } else {
    mapsRow.hidden = true;
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

async function scanUrl(url, statusMsg) {
  scanBtn.disabled = true;
  setStatus(statusMsg || "Scanning collection…");
  try {
    const res = await api("/api/scan", { method: "POST", body: JSON.stringify({ url }) });
    state = res.data;
    render();
    const bits = [`Scanned ${res.scannedCount} mods`];
    if (res.newlyAdded.length) bits.push(`${res.newlyAdded.length} new`);
    if (res.removed.length) bits.push(`${res.removed.length} removed`);
    if (res.noModId.length) bits.push(`${res.noModId.length} missing a Mod ID`);
    if (res.failed.length) bits.push(`${res.failed.length} failed to fetch`);
    setStatus(bits.join(" · "), res.failed.length ? "error" : "ok");
  } catch (e) {
    setStatus(e.message, "error");
  } finally {
    scanBtn.disabled = false;
  }
}

async function onScan() {
  const url = urlInput.value.trim();
  if (!url) {
    setStatus("Paste a Steam Workshop collection URL first.", "error");
    return;
  }
  await scanUrl(url);
}

async function onRefreshCollection(cid) {
  const col = state.collections[cid];
  if (!col || !col.url) return;
  await scanUrl(col.url, `Scanning "${collectionLabel(col)}"…`);
}

async function onReorder(cid, ul) {
  const order = [...ul.children].map((li) => li.dataset.id);
  state.collections[cid].order = order;
  buildOutputs();
  try {
    await api("/api/reorder", { method: "POST", body: JSON.stringify({ collection: cid, order }) });
  } catch (e) {
    setStatus(e.message, "error");
  }
}

async function onReorderCollections() {
  const order = [...boxesEl.children].map((b) => b.dataset.collection);
  state.collectionOrder = order;
  buildOutputs();
  try {
    await api("/api/reorder-collections", { method: "POST", body: JSON.stringify({ order }) });
  } catch (e) {
    setStatus(e.message, "error");
  }
}

async function onEditModIds(id, raw) {
  const modIds = raw.split(/[;,]/).map((s) => s.trim()).filter(Boolean);
  state.mods[id].modIds = modIds;
  render();
  try {
    await api(`/api/mods/${id}`, { method: "POST", body: JSON.stringify({ modIds }) });
  } catch (e) {
    setStatus(e.message, "error");
  }
}

async function onToggleModId(id, mid, enabled) {
  const mod = state.mods[id];
  const disabled = new Set(mod.disabledModIds || []);
  if (enabled) disabled.delete(mid);
  else disabled.add(mid);
  mod.disabledModIds = [...disabled];
  buildOutputs();
  try {
    await api(`/api/mods/${id}`, { method: "POST", body: JSON.stringify({ disabledModIds: mod.disabledModIds }) });
  } catch (e) {
    setStatus(e.message, "error");
  }
}

async function onToggleModEnabled(id, enabled) {
  state.mods[id].enabled = enabled;
  document.querySelectorAll(`.mod-item[data-id="${id}"]`).forEach((li) => {
    li.classList.toggle("disabled", !enabled);
  });
  buildOutputs();
  try {
    await api(`/api/mods/${id}`, { method: "POST", body: JSON.stringify({ enabled }) });
  } catch (e) {
    setStatus(e.message, "error");
  }
}

async function onToggleCollectionEnabled(cid, enabled) {
  state.collections[cid].enabled = enabled;
  const box = boxesEl.querySelector(`.collection-box[data-collection="${cid}"]`);
  if (box) box.classList.toggle("disabled", !enabled);
  buildOutputs();
  try {
    await api(`/api/collections/${cid}`, { method: "POST", body: JSON.stringify({ enabled }) });
  } catch (e) {
    setStatus(e.message, "error");
  }
}

async function onRemove(id) {
  try {
    state = await api(`/api/mods/${id}`, { method: "DELETE" });
    render();
  } catch (e) {
    setStatus(e.message, "error");
  }
}

async function onDeleteCollection(cid) {
  const col = state.collections[cid];
  const label = collectionLabel(col);
  if (!confirm(`Delete collection "${label}" and all of its mods?\n\nThis only removes mods that don't belong to any other collection. This can't be undone.`)) return;
  try {
    state = await api(`/api/collections/${cid}`, { method: "DELETE" });
    render();
    setStatus(`Deleted collection "${label}".`);
  } catch (e) {
    setStatus(e.message, "error");
  }
}

async function onClearAll() {
  if (!confirm("Remove every collection and mod from the list? This can't be undone.")) return;
  try {
    state = await api("/api/clear", { method: "POST" });
    render();
    setStatus("List cleared.");
  } catch (e) {
    setStatus(e.message, "error");
  }
}

function setupCopyButtons() {
  document.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const target = el(btn.dataset.copy);
      await navigator.clipboard.writeText(target.value);
      btn.textContent = "Copied!";
      btn.classList.add("copied");
      setTimeout(() => {
        btn.textContent = "Copy";
        btn.classList.remove("copied");
      }, 1200);
    });
  });
}

async function init() {
  scanBtn.addEventListener("click", onScan);
  urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") onScan(); });
  build42Toggle.addEventListener("change", buildOutputs);
  clearBtn.addEventListener("click", onClearAll);
  setupCopyButtons();

  try {
    state = await api("/api/mods");
  } catch (e) {
    setStatus(e.message, "error");
  }
  render();
}

init();
