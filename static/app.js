const el = (id) => document.getElementById(id);

const urlInput = el("collectionUrl");
const scanBtn = el("scanBtn");
const statusEl = el("status");
const listEl = el("modList");
const emptyHint = el("emptyHint");
const countEl = el("count");
const modsOut = el("modsOut");
const workshopOut = el("workshopOut");
const mapsOut = el("mapsOut");
const mapsRow = el("mapsRow");
const build42Toggle = el("build42Toggle");
const clearBtn = el("clearBtn");

let state = { order: [], mods: {} };
let sortable = null;

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

function render() {
  listEl.innerHTML = "";
  const ids = state.order.filter((id) => state.mods[id]);
  countEl.textContent = ids.length ? `(${ids.length})` : "";
  emptyHint.hidden = ids.length > 0;

  for (const id of ids) {
    const mod = state.mods[id];
    const li = document.createElement("li");
    li.className = "mod-item";
    li.dataset.id = id;
    if (!mod.ok) li.classList.add("failed");
    else if (!mod.modIds || mod.modIds.length === 0) li.classList.add("no-modid");

    const metaBits = [`<span class="wsid">${id}</span>`];
    if (!mod.ok) {
      metaBits.push(`<span class="fail-tag">fetch failed</span>`);
    } else if (!mod.modIds || mod.modIds.length === 0) {
      metaBits.push(`<span class="warn-tag">no Mod ID found — check manually</span>`);
    } else if (mod.modIds.length > 1) {
      metaBits.push(`<span class="warn-tag">${mod.modIds.length} mod ids — verify</span>`);
    }

    li.innerHTML = `
      <span class="drag-handle" title="Drag to reorder">⠿</span>
      <div class="mod-main">
        <div class="mod-name" title="${escapeAttr(mod.name || "")}">${escapeHtml(mod.name || "(untitled)")}</div>
        <div class="mod-meta">${metaBits.join("")}</div>
      </div>
      <input class="modid-input" type="text" value="${escapeAttr((mod.modIds || []).join(";"))}" placeholder="ModIdA;ModIdB">
      <button class="remove-btn" title="Remove">✕</button>
    `;

    const input = li.querySelector(".modid-input");
    input.addEventListener("change", () => onEditModIds(id, input.value));

    li.querySelector(".remove-btn").addEventListener("click", () => onRemove(id));

    listEl.appendChild(li);
  }

  if (!sortable) {
    sortable = new Sortable(listEl, {
      handle: ".drag-handle",
      animation: 150,
      onEnd: onReorder,
    });
  }

  buildOutputs();
}

function buildOutputs() {
  const ids = state.order.filter((id) => state.mods[id]);
  const useB42 = build42Toggle.checked;

  const modIdLines = [];
  const workshopLines = [];
  const mapSet = new Set();

  for (const id of ids) {
    const mod = state.mods[id];
    workshopLines.push(id);
    for (const mid of mod.modIds || []) {
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

async function onScan() {
  const url = urlInput.value.trim();
  if (!url) {
    setStatus("Paste a Steam Workshop collection URL first.", "error");
    return;
  }
  scanBtn.disabled = true;
  setStatus("Scanning collection…");
  try {
    const res = await api("/api/scan", { method: "POST", body: JSON.stringify({ url }) });
    state = res.data;
    render();
    const bits = [`Scanned ${res.scannedCount} mods`];
    if (res.newlyAdded.length) bits.push(`${res.newlyAdded.length} new`);
    if (res.noModId.length) bits.push(`${res.noModId.length} missing a Mod ID`);
    if (res.failed.length) bits.push(`${res.failed.length} failed to fetch`);
    setStatus(bits.join(" · "), res.failed.length ? "error" : "ok");
  } catch (e) {
    setStatus(e.message, "error");
  } finally {
    scanBtn.disabled = false;
  }
}

async function onReorder() {
  const order = [...listEl.children].map((li) => li.dataset.id);
  state.order = order;
  buildOutputs();
  try {
    await api("/api/reorder", { method: "POST", body: JSON.stringify({ order }) });
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

async function onRemove(id) {
  try {
    state = await api(`/api/mods/${id}`, { method: "DELETE" });
    render();
  } catch (e) {
    setStatus(e.message, "error");
  }
}

async function onClearAll() {
  if (!confirm("Remove every mod from the list? This can't be undone.")) return;
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
