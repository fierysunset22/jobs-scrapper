(async function(){
const FETCHED = await fetch('/dashboard/data.json').then(r=>r.json()).catch(()=>null);
const DATA = FETCHED || window.__JT_DATA || {};
const $ = (id) => document.getElementById(id);
const TOKEN = DATA.logo_token;
const COLORS = ["#6f9bff","#8b6fff","#ff6f91","#ffa14a","#34d399","#22b8cf","#e879f9"];
const esc = (s) => (s||"").replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));

function readSessionKeywords() {
  try {
    const v = JSON.parse(localStorage.getItem('jt_keywords') || 'null');
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function getEffectiveKeywords() {
  // config.json is the default source for keywords; a saved local override
  // takes precedence for this browser session and never writes back to config.
  const session = readSessionKeywords();
  if (session.length) return session;
  return (DATA.filters && Array.isArray(DATA.filters.keywords)) ? DATA.filters.keywords : [];
}

function saveSessionKeywords(keywords) {
  const next = Array.isArray(keywords) ? keywords : [];
  try {
    localStorage.setItem('jt_keywords', JSON.stringify(next));
  } catch (e) {
    console.error('Failed to save keywords to localStorage', e);
  }
  DATA.filters = DATA.filters || {};
  DATA.filters.keywords = next;
  return next;
}

function readSessionFilters() {
  try {
    const value = JSON.parse(localStorage.getItem('jt_filters') || 'null');
    return value && typeof value === 'object' ? value : {};
  } catch {
    return {};
  }
}

function getEffectiveFilters() {
  return { ...(DATA.filters || {}), ...readSessionFilters() };
}

function saveSessionFilters(filters) {
  const next = {
    work_arrangement: ["any", "remote", "hybrid", "other"].includes(filters.work_arrangement)
      ? filters.work_arrangement : "any",
  };
  try {
    localStorage.setItem('jt_filters', JSON.stringify(next));
  } catch (e) {
    console.error('Failed to save filters to localStorage', e);
  }
  DATA.filters = { ...(DATA.filters || {}), ...next };
  return next;
}

// Show system-level filters, including browser-local overrides.
function renderSystemFilters() {
  const saved = readSessionFilters().work_arrangement;
  $("loc").value = ["remote", "hybrid", "other"].includes(saved) ? saved : "";
}
renderSystemFilters();

const keywordTagsEl = $("keywordTags");
const keywordInputEl = $("keywordInput");

function uniqueKeywords(list) {
  const seen = new Set();
  const out = [];
  for (const item of list || []) {
    const value = String(item || "").trim();
    if (!value) continue;
    const key = value.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(value);
    }
  }
  return out;
}

function getCurrentKeywordTags() {
  return Array.from(keywordTagsEl.querySelectorAll(".keyword-tag")).map((el) => el.dataset.tag || "").filter(Boolean);
}

async function saveKeywords() {
  const nextKeywords = saveSessionKeywords(getCurrentKeywordTags());
  DATA.filters = DATA.filters || {};
  DATA.filters.keywords = nextKeywords;
  render();
}

function renderKeywordTags(list) {
  const tags = uniqueKeywords(list);
  keywordTagsEl.innerHTML = "";
  for (const tag of tags) {
    const el = document.createElement("span");
    el.className = "keyword-tag";
    el.dataset.tag = tag;

    const label = document.createElement("span");
    label.textContent = tag;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "keyword-tag-remove";
    remove.textContent = "×";
    remove.title = `Remove ${tag}`;
    remove.setAttribute("aria-label", `Remove ${tag}`);
    remove.addEventListener("click", () => {
      const next = getCurrentKeywordTags().filter((value) => value.toLowerCase() !== tag.toLowerCase());
      renderKeywordTags(next);
      saveKeywords();
    });

    el.append(label, remove);
    keywordTagsEl.appendChild(el);
  }
  keywordTagsEl.appendChild(keywordInputEl);
  keywordInputEl.value = "";
}

function addKeywordTag(raw) {
  const additions = String(raw || "")
    .split(/[\n,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (!additions.length) return;

  const existing = getCurrentKeywordTags();
  const next = uniqueKeywords([...existing, ...additions]);
  renderKeywordTags(next);
  saveKeywords();
}

function removeLastKeywordTag() {
  const current = getCurrentKeywordTags();
  if (!current.length) return;
  renderKeywordTags(current.slice(0, -1));
  saveKeywords();
}

renderKeywordTags(getEffectiveKeywords());

function currentFilterPayload() {
  return {
    work_arrangement: $("loc").value || "any",
    keywords: getEffectiveKeywords(),
  };
}

keywordInputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === "," || e.key === ";") {
    e.preventDefault();
    addKeywordTag(keywordInputEl.value);
    keywordInputEl.value = "";
    requestAnimationFrame(() => keywordInputEl.focus());
    return;
  }
  if (e.key === "Backspace" && keywordInputEl.value === "") {
    e.preventDefault();
    removeLastKeywordTag();
    requestAnimationFrame(() => keywordInputEl.focus());
  }
});

keywordInputEl.addEventListener("blur", () => {
  if (keywordInputEl.value.trim()) {
    addKeywordTag(keywordInputEl.value);
    keywordInputEl.value = "";
    requestAnimationFrame(() => keywordInputEl.focus());
  }
});

// Handle filter changes
function updateFilters() {
  saveSessionFilters({
    work_arrangement: $("loc").value || "any",
  });
  render();
}

$("loc").addEventListener("change", updateFilters);

// Header / stats
// generated_at is an ISO-8601 UTC instant; format it in the viewer's own
// timezone. Fall back to the raw value if it's ever not a parseable date.
function fmtUpdated(iso) {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}
$("upd").textContent = "Updated " + fmtUpdated(DATA.generated_at);

// Show whether the latest update completed cleanly.
(function () {
  const s = $("updStatus");
  if (DATA.update_ok) {
    s.textContent = "✓";              // ✓
    s.className = "upd-status ok";
    s.title = "Last update completed successfully";
  } else {
    s.textContent = "!";
    s.className = "upd-status warn";
    const errs = DATA.update_errors || [];
    s.title = "Last update had problems:\n" + (errs.length ? errs.join("\n") : "see logs");
  }
  s.hidden = false;
})();
$("stNew").textContent = DATA.new_count;
$("stTotal").textContent = DATA.total_jobs;
$("stCos").textContent = DATA.companies.length;
$("stRemote").textContent = DATA.remote_count;

// Banner
const banner = $("banner");
if (DATA.new_count > 0) {
  banner.classList.add("has");
  $("bannerTxt").textContent = DATA.new_count + (DATA.new_count === 1 ? " new role" : " new roles") + " discovered in today's run";
} else {
  banner.classList.add("none");
  $("bannerTxt").textContent = "You're all caught up — no new roles since the last run";
}

// Company filter
const sel = $("company");
sel.innerHTML = `<option value="">All Companies</option>` +
  DATA.companies.map(c => `<option value="${esc(c.company)}">${esc(c.company)} (${c.count})</option>`).join("");

function colorFor(name) {
  let h = 0; for (const ch of name) h = (h*31 + ch.charCodeAt(0)) >>> 0;
  return COLORS[h % COLORS.length];
}
function iniHtml(company) {
  const ini = esc(company.slice(0,2).toUpperCase());
  return `<span class="ini" style="background:${colorFor(company)}">${ini}</span>`;
}
function logoFail(img) { img.parentNode.innerHTML = iniHtml(img.getAttribute("data-co") || "?"); }
function logoHtml(company, domain) {
  if (TOKEN && domain) {
    const src = `https://img.logo.dev/${encodeURIComponent(domain)}?token=${encodeURIComponent(TOKEN)}&size=72&format=png&retina=true`;
    return `<span class="logo"><img src="${src}" alt="${esc(company)}" data-co="${esc(company)}" loading="lazy" onerror="logoFail(this)"></span>`;
  }
  return `<span class="logo">${iniHtml(company)}</span>`;
}

// ---- Persistent per-user state (survives every dashboard rebuild) -----------
// Followed/dismissed roles are saved server-side (data/preferences.json) when a
// live server (serve.py) is actually answering, so they sync across
// browsers/machines. On a static host (GitHub Pages) or over file:// there's no
// server, so we fall back to per-browser localStorage. We feature-detect the
// API rather than trusting the protocol: GitHub Pages is https:// but has no
// backend. Tracked roles are stored as full snapshots so a followed job can
// still be shown after it disappears from the live feed ("no longer available").
let serverPrefs = false;   // set true only once /api/prefs answers
const LS_TRACK = "jt_tracked_v1";   // { [id]: jobSnapshot }
const LS_HIDE  = "jt_hidden_v1";    // [ id, ... ]
function lsGet(k, def) { try { const v = JSON.parse(localStorage.getItem(k)); return v ?? def; } catch { return def; } }
function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }

// Seed from the prefs embedded at build time so the first paint is correct;
// initPrefs() then reconciles with the freshest source below.
let tracked = (DATA.prefs && DATA.prefs.tracked) || {};
let hidden = new Set((DATA.prefs && DATA.prefs.hidden) || []);
let showHidden = false;

// Jobs present in the current run, by id → used to detect tracked roles that
// have since vanished, and to refresh stored snapshots with the latest data.
const byId = new Map(DATA.jobs.map(j => [j.id, j]));

// Persist the current state to its backing store (live server if one answered,
// otherwise per-browser localStorage).
function persist() {
  if (serverPrefs) {
    fetch("/api/prefs", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracked, hidden: [...hidden] }) }).catch(() => {});
  } else {
    lsSet(LS_TRACK, tracked);
    lsSet(LS_HIDE, [...hidden]);
  }
}

// Load the authoritative state, refresh live snapshots, then do the first paint.
async function initPrefs() {
  if (location.protocol.startsWith("http")) {
    try {
      const r = await fetch("/api/prefs");
      if (r.ok) { const p = await r.json();
        tracked = p.tracked || {}; hidden = new Set(p.hidden || []);
        serverPrefs = true; }
    } catch {}
  }
  if (!serverPrefs) {  // static host (GitHub Pages) or file:// → local fallback
    const t = lsGet(LS_TRACK, null), h = lsGet(LS_HIDE, null);
    if (t) tracked = t;
    if (h) hidden = new Set(h);
  }
  // Keep snapshots of still-live tracked roles current with the latest fetch.
  let dirty = false;
  for (const id of Object.keys(tracked)) {
    if (byId.has(id)) { tracked[id] = byId.get(id); dirty = true; }
  }
  if (dirty) persist();
  render();
}

function toggleTrack(id) {
  if (tracked[id]) delete tracked[id];
  else { const j = byId.get(id) || tracked[id]; if (j) tracked[id] = j; }
  persist();
  renderAll();
}
function toggleHide(id) {
  if (hidden.has(id)) hidden.delete(id); else hidden.add(id);
  persist();
  renderAll();
}
// One delegated listener handles every row's track / dismiss button.
document.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = btn.getAttribute("data-id");
  if (btn.dataset.act === "track") toggleTrack(id);
  else if (btn.dataset.act === "hide") toggleHide(id);
});

function actionsHtml(j, ctx) {
  const isTracked = !!tracked[j.id];
  const star = `<button class="iconbtn track${isTracked ? " on" : ""}" data-act="track" data-id="${esc(j.id)}" title="${isTracked ? "Stop following" : "Follow this role"}" aria-label="${isTracked ? "Stop following" : "Follow this role"}">${isTracked ? "★" : "☆"}</button>`;
  if (ctx === "tracked") return `<div class="acts">${star}</div>`;
  const isHidden = hidden.has(j.id);
  const drop = `<button class="iconbtn drop" data-act="hide" data-id="${esc(j.id)}" title="${isHidden ? "Restore to list" : "Not interested — hide this role"}" aria-label="${isHidden ? "Restore to list" : "Not interested"}">${isHidden ? "↩" : "✕"}</button>`;
  return `<div class="acts">${star}${drop}</div>`;
}

function workLocationType(location) {
  const value = (location || "").toLowerCase();
  if (/\bremote\b/.test(value)) return "remote";
  if (/\bhybrid\b/.test(value)) return "hybrid";
  if (/\b(?:on[- ]?site|in[- ]office|office[- ]based)\b/.test(value)) return "onsite";
  return "unknown";
}

function locationForDisplay(location) {
  return (location || "")
    .replace(/\b(?:remote|hybrid|on[- ]?site|in[- ]office|office[- ]based)\b/gi, "")
    .replace(/\s*[-|/]\s*/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function rowHtml(j, ctx) {
  const gone = ctx === "tracked" && !byId.has(j.id);
  const badge = gone ? `<div class="badge gone">GONE</div>`
    : (j.isNew ? `<div class="badge">NEW</div>` : "");
  const type = j.work_type || workLocationType(j.location);
  const typeLabel = { remote: "Remote", hybrid: "Hybrid", onsite: "On-site", unknown: "Unknown" }[type];
  const typeChip = `<div class="chip ${type}">${typeLabel}</div>`;
  const displayLocation = locationForDisplay(j.location);
  const loc = displayLocation ? `<div class="chip location-chip" title="${esc(j.location)}">${esc(displayLocation)}</div>` : "—";
  const view = j.url ? `<a class="view" href="${esc(j.url)}" target="_blank" rel="noopener">View →</a>` : `<span class="c-view"></span>`;
  const cls = "row" + (gone ? " gone" : (j.isNew ? " new" : ""))
    + (ctx === "main" && hidden.has(j.id) ? " hiddenrow" : "");
  const upd = gone ? "no longer listed" : (j.updated || "—");
  return `<div class="${cls}">
    <div class="c-logo">${logoHtml(j.company, j.domain)}</div>
    <div class="c-role"><div class="title">${esc(j.title)}</div><div class="co">${esc(j.company)}</div></div>
    <div class="c-status">${badge}</div>
    <div class="c-type">${typeChip}</div>
    <div class="c-loc">${loc}</div>
    <div class="c-upd upd">${esc(upd)}</div>
    ${view}
    <div class="c-act">${actionsHtml(j, ctx)}</div>
  </div>`;
}

function renderTracked() {
  const items = Object.values(tracked);
  const panel = $("tracked");
  if (!items.length) { panel.style.display = "none"; return; }
  // Vanished roles float to the top so they catch the eye; then newest-first.
  items.sort((a, b) => (byId.has(b.id) ? 0 : 1) - (byId.has(a.id) ? 0 : 1)
    || (Number(b.isNew) - Number(a.isNew))
    || a.company.localeCompare(b.company));
  const goneCount = items.filter(j => !byId.has(j.id)).length;
  panel.style.display = "block";
  $("trackedCt").textContent = items.length + (items.length === 1 ? " role" : " roles")
    + (goneCount ? ` · ${goneCount} no longer available` : "");
  $("trackedRows").innerHTML = items.map(j => rowHtml(j, "tracked")).join("");
}

function render() {
  renderTracked();
  const q = $("search").value.trim().toLowerCase();
  const co = sel.value;
  const lf = $("loc").value;
  const rows = DATA.jobs.filter(j => {
    if (tracked[j.id]) return false;                 // shown in the Following panel
    if (!showHidden && hidden.has(j.id)) return false;
    if (showHidden && !hidden.has(j.id)) return false;
    if (co && j.company !== co) return false;
    const type = j.work_type || workLocationType(j.location);
    if (lf === "other" && (type === "remote" || type === "hybrid")) return false;
    if (lf && lf !== "other" && type !== lf) return false;
    if (q && !(j.title + " " + j.company + " " + j.location).toLowerCase().includes(q)) return false;
    return true;
  });
  // If the user saved session keywords, apply them as an additional
  // client-side filter so the displayed jobs reflect the user's edits
  // even though the repo-level pipeline may not yet have re-run.
  const activeKw = getEffectiveKeywords();
  const filtered = (activeKw.length)
    ? rows.filter(j => {
        const hay = (j.title + ' ' + (j.company||'') + ' ' + (j.location||'')).toLowerCase();
        return activeKw.some(k => hay.includes((k||'').toLowerCase()));
      })
    : rows;
  $("bannerCt").textContent = filtered.length + " of " + DATA.total_jobs + " jobs";
  $("rows").innerHTML = filtered.map(j => rowHtml(j, "main")).join("");
  const emptyEl = $("empty");
  emptyEl.style.display = filtered.length ? "none" : "block";
  emptyEl.textContent = showHidden
    ? "Nothing hidden yet — use ✕ on a role to mark it as not interested."
    : (sessKw.length
      ? "No jobs match your saved keywords. Clear them or edit the keyword list to restore the full feed."
      : "No jobs match your current filters.");

  // "Show hidden" toggle reflects the current count.
  const hb = $("hideToggle");
  if (hidden.size) {
    hb.style.display = "inline-flex";
    hb.classList.toggle("on", showHidden);
    hb.textContent = (showHidden ? "Hide dismissed · " : "Show dismissed · ") + hidden.size;
  } else {
    hb.style.display = "none";
    showHidden = false;
  }
}
const renderAll = render;
$("hideToggle").addEventListener("click", () => { showHidden = !showHidden; render(); });
$("search").addEventListener("input", render);
sel.addEventListener("change", render);
$("loc").addEventListener("change", render);

// Refresh: over HTTP via serve.py it triggers a real re-fetch, then reloads.
// On a static host (GitHub Pages) or file://, there's no backend to re-scrape,
// so it just reloads the latest published page instead of reporting a failure.
$("refresh").addEventListener("click", async () => {
  const b = $("refresh");
  if (b.classList.contains("busy")) return;
  b.classList.add("busy"); $("refreshLabel").textContent = "Refreshing…";
  if (location.protocol.startsWith("http")) {
    try {
      const r = await fetch("/api/refresh", { method: "POST" });
      // No backend on this host (e.g. GitHub Pages): the endpoint doesn't
      // exist, so just reload the published page rather than showing a failure.
      if (r.status === 404 || r.status === 405) { location.reload(); return; }
      if (!r.ok) throw new Error(r.status);
    } catch (e) {
      $("refreshLabel").textContent = "Refresh failed";
      b.classList.remove("busy");
      return;
    }
  } else {
    await new Promise(res => setTimeout(res, 400));
  }
  location.reload();
});

initPrefs();
})();