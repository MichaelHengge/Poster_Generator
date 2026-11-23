/* Poster Generator front-end: collects settings, requests SVG previews, handles exports. */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const STORE = "posterGen.settings.v1";

  let CFG = null;          // server config (defaults, presets, ...)
  let S = {};              // current settings
  let userPalettes = {};
  let reqId = 0;

  const COLUMN_PRESETS = ["1:1", "1:1:1", "1:1:1:1", "1:2", "2:1", "1:2:1", "2:1:1", "1:1:2"];
  // schematic icons for the layout styles: [x, y, w, h, key?] in a 30x40 box
  const STYLE_ICONS = {
    columns: [[2, 2, 8, 18], [11, 2, 8, 10], [20, 2, 8, 14], [2, 22, 8, 16], [11, 14, 8, 24], [20, 18, 8, 20]],
    columns_span: [[2, 2, 8, 16], [11, 2, 8, 10], [20, 2, 8, 10], [2, 20, 8, 18], [11, 14, 17, 12, 1], [11, 28, 8, 10], [20, 28, 8, 10]],
    hero: [[2, 2, 26, 14, 1], [2, 18, 8, 20], [11, 18, 8, 20], [20, 18, 8, 20]],
    bento: [[2, 2, 12, 10], [16, 2, 12, 10], [2, 14, 26, 8], [2, 24, 8, 14], [11, 24, 8, 14], [20, 24, 8, 14]],
    sidebar: [[2, 2, 8, 11], [2, 15, 8, 11], [2, 28, 8, 10], [12, 2, 16, 18, 1], [12, 22, 7, 16], [21, 22, 7, 16]],
    flow: [[2, 2, 26, 8], [2, 12, 6, 10], [11, 12, 6, 10], [20, 12, 8, 10], [2, 24, 12, 14], [16, 24, 12, 14]],
    hero_bottom: [[2, 2, 8, 10], [11, 2, 8, 7], [20, 2, 8, 11], [2, 14, 8, 8], [11, 11, 8, 11], [20, 15, 8, 7], [2, 24, 26, 14, 1]],
    spotlight: [[2, 2, 12, 6], [16, 2, 12, 6], [2, 10, 6, 10], [2, 22, 6, 8], [10, 10, 10, 20, 1], [22, 10, 6, 8], [22, 20, 6, 10], [2, 32, 12, 6], [16, 32, 12, 6]],
    sandwich: [[2, 2, 26, 10, 1], [2, 14, 8, 12], [11, 14, 8, 12], [20, 14, 8, 12], [2, 28, 26, 10, 1]],
    features: [[2, 2, 17, 17, 1], [21, 2, 7, 8], [21, 12, 7, 7], [2, 21, 7, 8], [2, 31, 7, 7], [11, 21, 17, 17, 1]],
    mosaic: [[2, 2, 16, 14], [20, 2, 8, 8], [20, 12, 8, 14], [2, 18, 7, 20], [11, 18, 7, 9], [11, 29, 7, 9], [20, 28, 8, 10]],
  };
  const STYLE_EXTRA = { flow: '<path d="M8.3 15.5l2.2 1.5-2.2 1.5z"/><path d="M17.3 15.5l2.2 1.5-2.2 1.5z"/>' };
  const USES_COLUMNS = new Set(["auto", "columns", "columns_span", "hero", "hero_bottom", "sandwich", "flow"]);
  const EXTRA_SECTION_NAMES = ["Background", "Materials", "Data", "Analysis", "Key findings", "Outlook", "Future work", "Contact"];
  const FIG_LABEL = { auto: "Fig: auto", yes: "Fig: on", no: "Fig: off" };
  const FIG_NEXT = { auto: "yes", yes: "no", no: "auto" };
  let selected = -1;       // section selected on the preview / in the list
  let layoutKey = null;    // identifies the current generated layout (sizes are stored per layout)
  const UNITS = { corner_radius: " mm", margin: " mm", gutter: " mm", logo_size: " mm", qr_size: " mm" };

  // ------------------------------------------------------------ utils
  const storage = {
    get() { try { return JSON.parse(localStorage.getItem(STORE) || "null"); } catch { return null; } },
    set(v) { try { localStorage.setItem(STORE, JSON.stringify(v)); } catch { /* quota / private mode */ } },
  };
  function toast(msg, action) {   // action: optional {label, fn}, e.g. Undo
    const t = $("#toast");
    t.textContent = msg;
    t.classList.toggle("has-action", !!action);
    if (action) {
      const b = document.createElement("button");
      b.textContent = action.label;
      b.onclick = () => { t.classList.remove("on"); action.fn(); };
      t.appendChild(b);
    }
    t.classList.add("on");
    clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("on"), action ? 6000 : 2200);
  }
  function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
  async function api(url, opts = {}) {
    const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
    return r;
  }

  // ------------------------------------------------------------ form <-> settings
  function writeForm() {
    $$("[data-key]").forEach((el) => {
      const k = el.dataset.key; if (!(k in S)) return;
      if (el.type === "checkbox") el.checked = !!S[k]; else el.value = S[k];
    });
    $$("[data-seg]").forEach((seg) => $$("button", seg).forEach((b) => b.classList.toggle("on", b.dataset.val === S[seg.dataset.seg])));
    $$("input[type=range][data-key]").forEach(showRange);
    $("#customSize").style.display = S.size === "Custom" ? "" : "none";
    renderColors(); markPalette(); markFooter(); markColumns(); markStyles(); renderSections(); renderArrows(); applyMode();
  }

  // ------------------------------------------------------------ layout styles
  function renderStyles() {
    // fixed order (the JSON from Flask arrives alphabetically sorted)
    const all = [["auto", "Auto (varies)"], ...Object.keys(STYLE_ICONS).filter((k) => k in CFG.layout_styles).map((k) => [k, CFG.layout_styles[k]])];
    $("#layoutStyles").innerHTML = all.map(([k, name]) => {
      const icon = k === "auto"
        ? '<text x="15" y="27" text-anchor="middle" font-size="20" font-weight="700" fill="#9fb3d1">?</text>'
        : STYLE_ICONS[k].map(([x, y, w, h, key]) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="1"${key ? ' class="k"' : ""}/>`).join("") + (STYLE_EXTRA[k] || "");
      return `<button class="sty" data-style="${k}" title="${name}"><svg viewBox="0 0 30 40">${icon}</svg><small>${name}</small>${k === "auto" ? '<span class="used" id="autoUsed"></span>' : ""}</button>`;
    }).join("");
  }
  function markStyles() {
    $$(".sty").forEach((b) => b.classList.toggle("on", b.dataset.style === S.layout_style));
    $("#columnsBox").style.display = USES_COLUMNS.has(S.layout_style) ? "" : "none";
  }

  // ------------------------------------------------------------ sections editor
  function newId() { return Math.random().toString(36).slice(2, 10); }
  function normSections(v) {
    if (typeof v === "string") v = v.split("\n").filter((t) => t.trim()).map((t) => ({ title: t.trim() }));
    return (Array.isArray(v) ? v : []).map((s) => (typeof s === "string" ? { title: s } : s))
      .map((s) => ({ id: s.id || newId(), title: String(s.title ?? ""), figure: FIG_LABEL[s.figure] ? s.figure : "auto",
                     body: String(s.body ?? ""), figs: s.figs && typeof s.figs === "object" && !Array.isArray(s.figs) ? s.figs : {} }));
  }
  function renderSections() {
    $("#sectionCount").value = S.sections.length;
    if (typeof renderArrows === "function" && $("#arrowStyles")) renderArrows();
    $("#sectionList").innerHTML = S.sections.map((s, i) => `
      <li class="sec${i === selected ? " selected" : ""}" data-i="${i}">
        <span class="handle" title="Drag to reorder">⋮⋮</span>
        <span class="num">${i + 1}</span>
        <span class="title">${escapeHtml(s.title)}</span>
        <button class="fig" data-fig="${i}" data-mode="${s.figure}" title="Figure placeholder: automatic → always → never">${FIG_LABEL[s.figure]}</button>
        <button data-remove="${i}" title="Remove section">✕</button>
      </li>`).join("");
  }
  function addSections(want) {   // titles are fixed sample names (no text editing in the app)
    const used = new Set(S.sections.map((s) => s.title));
    const pool = EXTRA_SECTION_NAMES.filter((t) => !used.has(t));
    for (let i = S.sections.length; i < want; i++) S.sections.push({ id: newId(), title: pool.shift() || `Section ${i + 1}`, figure: "auto" });
    renderSections(); changed();
  }
  function selectSection(i, focus) {
    selected = i;
    $$(".sec").forEach((li) => li.classList.toggle("selected", +li.dataset.i === i));
    $$(".sheet rect.hot").forEach((r) => r.classList.toggle("sel", +r.dataset.idx === i));
    const li = $(`.sec[data-i="${i}"]`);
    if (li && focus) {
      const det = li.closest("details"); if (det) det.open = true;
      li.scrollIntoView({ block: "center", behavior: "smooth" });
      li.classList.remove("flash"); void li.offsetWidth; li.classList.add("flash");
    }
  }
  // Moving a section takes its box size along: the server rewrites the layout's size weights accordingly.
  async function requestMove(from, to) {
    const r = await api("/api/move", { method: "POST", body: JSON.stringify({ settings: payload(), from, to }) });
    return r.json();
  }
  function applyMove(res, from) {
    const before = { sections: S.sections.slice(), sizes: structuredClone(S.split_sizes || {}),
                     trees: structuredClone(S.layout_trees || {}), selected };
    const title = before.sections[from]?.title;
    S.sections = res.order.map((i) => before.sections[i]);
    S.split_sizes = S.split_sizes || {};
    S.layout_trees = S.layout_trees || {};
    if (res.tree_key) S.layout_trees[res.tree_key] = res.tree;      // the rearranged layout
    if (res.clear_key) delete S.split_sizes[res.clear_key];          // its sizes are now part of the tree
    if (res.sizes_key) { delete S.split_sizes[res.sizes_key]; S.split_sizes[res.sizes_key] = res.sizes; }
    if (selected >= 0) selected = res.order.indexOf(selected);
    renderSections(); changed();
    toast(`Moved “${title || "section"}”`, {
      label: "Undo",
      fn: () => { S.sections = before.sections; S.split_sizes = before.sizes; S.layout_trees = before.trees; selected = before.selected; renderSections(); changed(); },
    });
  }
  async function moveSection(from, to, res) {
    if (from === to || from < 0 || to < 0) return;
    try { applyMove(res || await requestMove(from, to), from); }
    catch (err) { toast("Could not move the section: " + err.message); }
  }

  // live preview of the arrangement while a section is dragged over another position
  const SVGNS = "http://www.w3.org/2000/svg";
  function showMovePreview(res) {   // the poster as it will look after the drop, laid over the current one
    const svg = $("#sheet svg"); if (!svg || !res.svg) return;
    let ov = $("#movePreview");
    if (!ov) { ov = document.createElement("div"); ov.id = "movePreview"; ov.className = "move-preview"; $("#stage").appendChild(ov); }
    const b = svg.getBoundingClientRect(), sb = $("#stage").getBoundingClientRect();
    Object.assign(ov.style, { left: b.left - sb.left + "px", top: b.top - sb.top + "px", width: b.width + "px", height: b.height + "px" });
    ov.innerHTML = res.svg;
    const p = $("svg", ov);
    p.removeAttribute("width"); p.removeAttribute("height");
    if (res.moved) {
      const [x, y, w, h] = res.moved;
      p.insertAdjacentHTML("beforeend", `<rect class="moved-box" x="${x}" y="${y}" width="${w}" height="${h}"/>`);
    }
  }
  function hideMovePreview() { const ov = $("#movePreview"); if (ov) ov.parentNode.removeChild(ov); }
  function deleteSection(i) {
    if (S.sections.length <= 1) { toast("A poster needs at least one section"); return; }
    const [removed] = S.sections.splice(i, 1);
    selected = -1;
    renderSections(); changed();
    toast(`Deleted “${removed.title || "Untitled section"}”`, {
      label: "Undo",
      fn: () => { S.sections.splice(i, 0, removed); renderSections(); changed(); },
    });
  }

  // ✕ button floating over the hovered (or selected) section in the preview
  let placeDeleteBtn = () => {};
  function bindDeleteButton() {
    const stage = $("#stage"), btn = $("#secDelete");
    let hoverIdx = -1;
    const busy = () => resize || $("#sheet").classList.contains("dragging") || isEdit() || connecting;
    const place = (idx) => {
      const r = idx >= 0 ? $(`#sheet rect.hot[data-idx="${idx}"]`) : null;
      if (!r || busy()) { btn.hidden = true; return; }
      const b = r.getBoundingClientRect(), sb = stage.getBoundingClientRect();
      btn.style.left = (b.right - sb.left - 30) + "px";
      btn.style.top = (b.top - sb.top + 6) + "px";
      btn.dataset.idx = idx;
      btn.title = `Delete “${S.sections[idx]?.title || "section"}”`;
      btn.hidden = false;
    };
    placeDeleteBtn = () => place(hoverIdx >= 0 ? hoverIdx : selected);
    stage.addEventListener("pointermove", (e) => {
      if (e.target === btn) return;
      const hot = e.target.closest && e.target.closest("rect.hot");
      hoverIdx = hot ? +hot.dataset.idx : -1;
      placeDeleteBtn();
    });
    stage.addEventListener("pointerleave", () => { hoverIdx = -1; placeDeleteBtn(); });
    btn.addEventListener("pointerdown", (e) => e.stopPropagation());
    btn.addEventListener("click", () => { const i = +btn.dataset.idx; hoverIdx = -1; btn.hidden = true; deleteSection(i); });
  }

  // draggable divider between the settings panel and the preview
  function bindPaneResizer() {
    const rz = $("#paneResizer"), app = $(".app"), KEY = "posterGen.panelWidth";
    const clamp = (px) => Math.max(320, Math.min(window.innerWidth - 360, px));
    const refit = () => { if (fitSheet.aspect) fitSheet(fitSheet.aspect); placeDeleteBtn(); };
    const apply = (px) => { if (px) app.style.setProperty("--panel-w", clamp(px) + "px"); else app.style.removeProperty("--panel-w"); refit(); };
    try { const v = +localStorage.getItem(KEY); if (v) apply(v); } catch { /* storage unavailable */ }
    let dragging = false;
    rz.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault(); dragging = true; rz.classList.add("active"); document.body.classList.add("pane-resizing");
    });
    document.addEventListener("pointermove", (e) => { if (dragging) apply(e.clientX); });
    document.addEventListener("pointerup", () => {
      if (!dragging) return;
      dragging = false; rz.classList.remove("active"); document.body.classList.remove("pane-resizing");
      try { localStorage.setItem(KEY, Math.round($(".panel").getBoundingClientRect().width)); } catch { /* ignore */ }
    });
    rz.addEventListener("dblclick", () => { try { localStorage.removeItem(KEY); } catch { /* ignore */ } apply(0); });
    window.addEventListener("resize", () => { const v = parseFloat(app.style.getPropertyValue("--panel-w")); if (v) apply(v); });
  }

  // font pickers: installed families, each option shown in its own typeface
  function renderFontSelects() {
    const groups = { "sans-serif": "Sans-serif", serif: "Serif" };
    const html = Object.entries(groups).map(([g, label]) =>
      `<optgroup label="${label}">${CFG.fonts.filter((f) => f.generic === g)
        .map((f) => `<option value="${escapeHtml(f.name)}" style="font-family:'${escapeHtml(f.name)}'">${escapeHtml(f.name)}</option>`).join("")}</optgroup>`).join("");
    $$(".font-select").forEach((sel) => (sel.innerHTML = html));
  }

  function bindSectionList() {
    const list = $("#sectionList");
    list.addEventListener("click", (e) => {
      const li = e.target.closest(".sec");
      if (li && !e.target.closest("button, .handle")) selectSection(+li.dataset.i, false);
      const f = e.target.closest("[data-fig]");
      if (f) { const s = S.sections[+f.dataset.fig]; s.figure = FIG_NEXT[s.figure]; f.dataset.mode = s.figure; f.textContent = FIG_LABEL[s.figure]; changed(); }
      const r = e.target.closest("[data-remove]");
      if (r) deleteSection(+r.dataset.remove);
    });
    // drag & drop reordering with pointer events (only from the handle, so text inputs stay selectable)
    let ldrag = null;
    const clearMarks = () => $$(".sec", list).forEach((li) => li.classList.remove("drop-before", "drop-after"));
    list.addEventListener("pointerdown", (e) => {
      const h = e.target.closest(".handle"); if (!h || e.button !== 0) return;
      e.preventDefault();
      const li = h.closest(".sec");
      ldrag = { from: +li.dataset.i, li, to: null };
      li.classList.add("dragging");
      document.body.style.cursor = "grabbing";
    });
    document.addEventListener("pointermove", (e) => {
      if (!ldrag) return;
      const rows = $$(".sec", list);
      let to = rows.length;                       // insertion slot 0..n
      for (const [i, li] of rows.entries()) {
        const r = li.getBoundingClientRect();
        if (e.clientY < r.top + r.height / 2) { to = i; break; }
      }
      clearMarks();
      if (to < rows.length) rows[to].classList.add("drop-before"); else rows[rows.length - 1].classList.add("drop-after");
      ldrag.to = to;
    });
    document.addEventListener("pointerup", () => {
      if (!ldrag) return;
      const d = ldrag; ldrag = null;
      clearMarks(); d.li.classList.remove("dragging"); document.body.style.cursor = "";
      if (d.to === null) return;
      moveSection(d.from, d.to > d.from ? d.to - 1 : d.to);
    });
    $("#btnAddSection").addEventListener("click", () => {
      addSections(S.sections.length + 1); selectSection(S.sections.length - 1, true);
    });
    $("#sectionCount").addEventListener("change", (e) => {
      const want = Math.max(1, Math.min(20, Math.round(+e.target.value) || 1));
      const n = S.sections.length;
      if (want > n) {
        selected = -1; addSections(want);
      } else if (want < n) {
        const removed = S.sections.splice(want);
        selected = -1; renderSections(); changed();
        toast(`Removed ${removed.length} section${removed.length > 1 ? "s" : ""} from the end`, {
          label: "Undo", fn: () => { S.sections.push(...removed); renderSections(); changed(); },
        });
      } else e.target.value = n;
    });
    $("#btnFigAll").addEventListener("click", () => { S.sections.forEach((s) => (s.figure = "auto")); renderSections(); changed(); });
  }

  // ------------------------------------------------------------ drag sections on the preview (swap)
  // ------------------------------------------------------------ resize sections by dragging the gaps
  let resize = null;
  let live = { busy: false, pending: false };
  async function liveRender() {
    if (live.busy) { live.pending = true; return; }
    live.busy = true;
    try { await render(); } finally { live.busy = false; }
    if (live.pending) { live.pending = false; liveRender(); }
  }
  function sizesFor(key) { return (S.split_sizes && S.split_sizes[key]) || null; }
  let treeKey = null, treeActive = false;   // rearranged layout (sections moved by dragging)
  function updateResetSizes() {
    const ov = sizesFor(layoutKey);
    $("#btnResetSizes").hidden = !((ov && Object.keys(ov).length) || treeActive);
    $("#btnResetSizes .lbl-t").textContent = treeActive ? "Reset layout" : "Reset sizes";
    $("#btnResetSizes").title = treeActive ? "Undo all moving and resizing of sections for this layout" : "Undo all section resizing for this layout";
  }
  function svgPoint(e) {
    const svg = $("#sheet svg"); if (!svg) return null;
    const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }
  function startResize(el) {
    const sizes = el.dataset.sizes.split(",").map(Number);
    const i = +el.dataset.i, start = +el.dataset.start, end = +el.dataset.end;
    resize = { key: layoutKey, id: el.dataset.split, i, dir: el.dataset.dir, start, sizes,
               gap: end - start - sizes[i] - sizes[i + 1], moved: false };
    document.body.classList.add("resizing", "resizing-" + resize.dir);
    el.classList.add("active");
  }
  function moveResize(e) {
    const p = svgPoint(e); if (!p) return;
    const r = resize, pos = r.dir === "h" ? p.x : p.y;
    const pair = r.sizes[r.i] + r.sizes[r.i + 1], min = pair * 0.12;
    const a = Math.min(pair - min, Math.max(min, pos - r.gap / 2 - r.start));
    const next = r.sizes.slice();
    next[r.i] = +a.toFixed(2); next[r.i + 1] = +(pair - a).toFixed(2);
    S.split_sizes = S.split_sizes || {};
    const store = (S.split_sizes[r.key] = S.split_sizes[r.key] || {});
    store[r.id] = next;
    r.moved = true;
    liveRender();
  }
  function endResize() {
    const r = resize; resize = null;
    document.body.classList.remove("resizing", "resizing-h", "resizing-v");
    $$(".sheet rect.split.active").forEach((x) => x.classList.remove("active"));
    if (!r.moved) return;
    // mark this layout as most recently edited, then keep only the 40 latest layouts' sizes
    const v = S.split_sizes[r.key]; delete S.split_sizes[r.key]; S.split_sizes[r.key] = v;
    const keys = Object.keys(S.split_sizes);
    keys.slice(0, Math.max(0, keys.length - 40)).forEach((k) => delete S.split_sizes[k]);
    storage.set(S); liveRender();
  }
  function resetSplit(el) {
    const ov = sizesFor(layoutKey); if (!ov || !(el.dataset.split in ov)) return;
    delete ov[el.dataset.split];
    if (!Object.keys(ov).length) delete S.split_sizes[layoutKey];
    changed(); toast("Size reset to automatic");
  }

  function bindPreviewDrag() {
    const sheet = $("#sheet");
    let drag = null;
    const hotAt = (x, y) => { const el = document.elementFromPoint(x, y); return el && el.classList && el.classList.contains("hot") ? el : null; };
    sheet.addEventListener("pointerdown", (e) => {
      const sp = e.target.closest("rect.split");
      if (sp && e.button === 0) { e.preventDefault(); startResize(sp); return; }
    });
    document.addEventListener("pointermove", (e) => { if (resize) moveResize(e); });
    document.addEventListener("pointerup", () => { if (resize) endResize(); });
    sheet.addEventListener("dblclick", (e) => { const sp = e.target.closest("rect.split"); if (sp) resetSplit(sp); });
    $("#btnResetSizes").addEventListener("click", () => {
      const before = { sizes: structuredClone(S.split_sizes || {}), trees: structuredClone(S.layout_trees || {}) };
      if (S.split_sizes) delete S.split_sizes[layoutKey];
      if (treeActive && S.layout_trees) delete S.layout_trees[treeKey];
      changed();
      toast(treeActive ? "Layout reset" : "Section sizes reset for this layout", {
        label: "Undo", fn: () => { S.split_sizes = before.sizes; S.layout_trees = before.trees; changed(); },
      });
    });

    sheet.addEventListener("pointerdown", (e) => {
      const hot = e.target.closest("rect.hot"); if (!hot || e.button !== 0) return;
      if (connecting) { e.preventDefault(); connectClick(+hot.dataset.idx); return; }
      e.preventDefault();
      drag = { idx: +hot.dataset.idx, hot, x: e.clientX, y: e.clientY, moving: false, target: null };
    });
    document.addEventListener("pointermove", (e) => {
      if (!drag) return;
      if (!drag.moving) {
        if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 6) return;
        drag.moving = true; sheet.classList.add("dragging"); drag.hot.classList.add("src");
        drag.ghost = Object.assign(document.createElement("div"), { className: "drag-ghost", textContent: S.sections[drag.idx]?.title || "Section" });
        document.body.appendChild(drag.ghost);
      }
      drag.ghost.style.left = e.clientX + "px"; drag.ghost.style.top = e.clientY + "px";
      const t = hotAt(e.clientX, e.clientY);
      const tgt = t && +t.dataset.idx !== drag.idx ? t : null;
      if (tgt !== drag.target) {
        if (drag.target) drag.target.classList.remove("target");
        if (tgt) tgt.classList.add("target");
        drag.target = tgt;
        drag.ghost.textContent = (S.sections[drag.idx]?.title || "Section") + (tgt ? `  →  ${S.sections[+tgt.dataset.idx]?.title || "here"}` : "");
        const seq = (drag.seq = (drag.seq || 0) + 1);
        drag.preview = null;
        if (!tgt) { hideMovePreview(); return; }
        const to = +tgt.dataset.idx, d0 = drag;
        requestMove(d0.idx, to).then((res) => {
          if (drag !== d0 || d0.seq !== seq) return;      // pointer moved on meanwhile
          d0.preview = { to, res };
          showMovePreview(res);
        }).catch(() => {});
      }
    });
    document.addEventListener("pointerup", () => {
      if (!drag) return;
      const d = drag; drag = null;
      sheet.classList.remove("dragging");
      if (d.ghost) d.ghost.remove();
      $$("rect.hot", sheet).forEach((r) => r.classList.remove("src", "target"));
      hideMovePreview();
      if (!d.moving) { selectSection(d.idx, true); return; }   // plain click: select that section
      if (d.target) {
        const to = +d.target.dataset.idx;
        selected = d.idx;
        moveSection(d.idx, to, d.preview && d.preview.to === to ? d.preview.res : null).then(() => {
          const li = $(`.sec[data-i="${selected}"]`); if (li) li.classList.add("flash", "selected");
        });
      }
    });
  }
  function showRange(el) {
    const k = el.dataset.key, v = parseFloat(el.value);
    let txt = v + (UNITS[k] || "");
    if (k === "font_scale" || k === "arrow_size") txt = Math.round(v * 100) + " %";
    el.parentElement.querySelector("output").textContent = txt;
  }
  function onInput(e) {
    const el = e.target, k = el.dataset.key; if (!k) return;
    if (el.type === "checkbox") S[k] = el.checked;
    else if (el.type === "number" || el.type === "range") { const v = parseFloat(el.value); if (isNaN(v)) return; S[k] = v; }
    else S[k] = el.value;
    if (el.type === "range") showRange(el);
    if (k === "size") $("#customSize").style.display = S.size === "Custom" ? "" : "none";
    if (k === "columns") markColumns();
    if (k === "bottom_enabled") markFooter();
    changed();
  }

  // ------------------------------------------------------------ palette UI
  function palStrip(p) {
    return `<div class="strip">${["primary", "secondary", "accent", "background", "text"].map((k) => `<span style="background:${p[k]}"></span>`).join("")}</div>`;
  }
  function renderPalettes() {
    $("#presetPalettes").innerHTML = Object.entries(CFG.presets).map(([n, p]) =>
      `<button class="pal" data-pal="${n}" data-src="preset" title="${n}">${palStrip(p)}<div class="name">${n}</div></button>`).join("")
      + `<button class="pal pal-custom" id="palCustom" title="Pick your own colours"><div class="strip"></div><div class="name">✎ Custom</div></button>`;
    const u = Object.entries(userPalettes);
    $("#userPalTitle").style.display = u.length ? "" : "none";
    $("#userPalettes").innerHTML = u.map(([n, p]) =>
      `<button class="pal" data-pal="${escapeHtml(n)}" data-src="user" title="${escapeHtml(n)}">${palStrip(p)}<div class="name">${escapeHtml(n)}</div><span class="del" data-del="${escapeHtml(n)}" title="Delete">✕</span></button>`).join("");
    markPalette();
  }
  function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  let customOpen = false;          // colour editor is hidden until "Custom" is clicked
  let activeColor = "primary";     // palette entry the colour picker edits
  function markPalette() {
    let any = false;
    $$(".pal[data-pal]").forEach((b) => {
      const src = b.dataset.src === "user" ? userPalettes : CFG.presets;
      const p = src[b.dataset.pal];
      const match = !!p && CFG.palette_keys.every((k) => (S["c_" + k] || "").toUpperCase() === p[k].toUpperCase());
      any = any || match;
      b.classList.toggle("on", match && !customOpen);
    });
    const c = $("#palCustom");
    if (c) {   // the Custom tile shows the colours currently in use
      c.classList.toggle("on", customOpen || !any);
      c.querySelector(".strip").outerHTML = palStrip(Object.fromEntries(CFG.palette_keys.map((k) => [k, S["c_" + k]])));
    }
    $("#customColors").hidden = !customOpen;
  }
  function applyPalette(p) { CFG.palette_keys.forEach((k) => (S["c_" + k] = p[k])); renderColors(); markPalette(); changed(); }
  function renderColors() {
    const box = $("#colorInputs");
    if (!box.children.length) {
      box.innerHTML = CFG.palette_keys.map((k) => `<button class="color" data-color="${k}" title="Edit ${CFG.palette_labels[k]}"><span class="sw"></span><span class="lbl-c">${CFG.palette_labels[k]}</span><code></code></button>`).join("");
    }
    CFG.palette_keys.forEach((k) => {
      const b = $(`[data-color="${k}"]`);
      $(".sw", b).style.background = S["c_" + k]; $("code", b).textContent = S["c_" + k];
      b.classList.toggle("on", k === activeColor);
    });
    syncPicker();
  }

  // ------------------------------------------------------------ colour picker (saturation/value square + hue)
  const hexToRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const rgbToHex = (r, g, b) => "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("").toUpperCase();
  function rgbToHsv(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    let h = 0;
    if (d) h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return [(h * 60 + 360) % 360, mx ? d / mx : 0, mx];
  }
  function hsvToRgb(h, s, v) {
    const f = (n) => { const k = (n + h / 60) % 6; return v - v * s * Math.max(0, Math.min(k, 4 - k, 1)); };
    return [f(5) * 255, f(3) * 255, f(1) * 255];
  }
  let hsv = [0, 0, 0];
  function syncPicker() {   // picker follows the active palette entry
    const hex = S["c_" + activeColor] || "#000000";
    const nh = rgbToHsv(...hexToRgb(hex));
    if (rgbToHex(...hsvToRgb(...hsv)) !== hex) hsv = nh[1] === 0 || nh[2] === 0 ? [hsv[0], nh[1], nh[2]] : nh;   // keep hue on greys
    drawPicker(hex);
  }
  function drawPicker(hex) {
    $("#svBox").style.background = `linear-gradient(to top, #000, transparent), linear-gradient(to right, #fff, hsl(${hsv[0]} 100% 50%))`;
    $("#svThumb").style.left = hsv[1] * 100 + "%";
    $("#svThumb").style.top = (1 - hsv[2]) * 100 + "%";
    $("#svThumb").style.background = hex;
    $("#hueSlider").value = Math.round(hsv[0]);
    $("#cpSwatch").style.background = hex;
    $("#cpTarget").textContent = CFG.palette_labels[activeColor];
    if (document.activeElement !== $("#hexInput")) $("#hexInput").value = hex;
  }
  function setActiveColor(hex) {
    S["c_" + activeColor] = hex;
    const b = $(`[data-color="${activeColor}"]`);
    $(".sw", b).style.background = hex; $("code", b).textContent = hex;
    drawPicker(hex); markPalette(); changed();
  }
  function bindColorPicker() {
    $("#colorInputs").addEventListener("click", (e) => {
      const b = e.target.closest("[data-color]"); if (!b) return;
      activeColor = b.dataset.color; hsv = [0, 0, 0]; renderColors();
    });
    const sv = $("#svBox");
    const pick = (e) => {
      const r = sv.getBoundingClientRect();
      hsv[1] = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
      hsv[2] = 1 - Math.max(0, Math.min(1, (e.clientY - r.top) / r.height));
      setActiveColor(rgbToHex(...hsvToRgb(...hsv)));
    };
    sv.addEventListener("pointerdown", (e) => { sv.setPointerCapture(e.pointerId); pick(e); });
    sv.addEventListener("pointermove", (e) => { if (sv.hasPointerCapture(e.pointerId)) pick(e); });
    $("#hueSlider").addEventListener("input", (e) => { hsv[0] = +e.target.value; setActiveColor(rgbToHex(...hsvToRgb(...hsv))); });
    $("#hexInput").addEventListener("input", (e) => {
      let v = e.target.value.trim(); if (!/^#?[0-9a-f]{6}$/i.test(v)) return;
      v = (v.startsWith("#") ? v : "#" + v).toUpperCase();
      hsv = rgbToHsv(...hexToRgb(v)); setActiveColor(v);
    });
    // eyedropper: picks any colour on screen (Chrome / Edge, which the desktop window uses)
    if ("EyeDropper" in window) {
      const eb = $("#btnEyedrop"); eb.hidden = false;
      eb.addEventListener("click", async () => {
        try {
          const { sRGBHex } = await new window.EyeDropper().open();
          const v = sRGBHex.startsWith("#") ? sRGBHex.toUpperCase() : rgbToHex(...sRGBHex.match(/\d+/g).map(Number));
          hsv = rgbToHsv(...hexToRgb(v)); setActiveColor(v);
        } catch { /* cancelled with Esc */ }
      });
    }
    $("#hexInput").addEventListener("blur", () => drawPicker(S["c_" + activeColor]));
  }

  // ------------------------------------------------------------ footer
  function markFooter() {   // QR settings only apply when the footer bar is shown
    $("#footerOpts").classList.toggle("off", !S.bottom_enabled);
  }

  // ------------------------------------------------------------ column presets
  function renderColumnPresets() {
    $("#colPresets").innerHTML = COLUMN_PRESETS.map((r) => {
      const parts = r.split(":").map(Number);
      return `<button class="colp" data-cols="${r}"><div class="bars">${parts.map((p) => `<span style="flex:${p}"></span>`).join("")}</div><small>${r.replace(/:/g, " : ")}</small></button>`;
    }).join("");
  }
  function markColumns() {
    const norm = (s) => String(s).replace(/\s/g, "");
    $$(".colp").forEach((b) => b.classList.toggle("on", norm(b.dataset.cols) === norm(S.columns)));
  }

  // ------------------------------------------------------------ preview
  const changed = debounce(() => { storage.set(S); render(); }, 220);
  // what the server sees: blank titles become "Untitled" so list index == poster box index
  const payload = () => ({ ...S, sections: S.sections.map((s) => ({ ...s, title: s.title.trim() || "Untitled section" })) });
  async function render() {
    const id = ++reqId;
    $("#busy").classList.add("on");
    try {
      const r = await api("/api/preview", { method: "POST", body: JSON.stringify(payload()) });
      const data = await r.json();
      if (id !== reqId) return;
      $("#sheet").innerHTML = data.svg;
      const svg = $("#sheet svg");
      svg.removeAttribute("width"); svg.removeAttribute("height");
      const aspect = data.width / data.height;
      fitSheet(aspect);
      if (selected >= 0) $$("rect.hot", svg).forEach((r) => r.classList.toggle("sel", +r.dataset.idx === selected));
      layoutKey = data.layout_key;
      treeKey = data.tree_key; treeActive = !!data.tree_active;
      updateResetSizes();
      placeDeleteBtn();
      if (resize) { const a = $(`rect.split[data-split="${resize.id}"][data-i="${resize.i}"]`, svg); if (a) a.classList.add("active"); }
      const au = $("#autoUsed"); if (au) au.textContent = S.layout_style === "auto" ? "→ " + data.style_name : "";
      lastInfo = data; updateStatus(); markConnectFrom();
      targets = new Set($$("rect.tgt", svg).map((r) => r.dataset.key));
      if (isEdit()) {
        renderEditPanel();
        if (popKey) { const t = $(`rect.tgt[data-key="${CSS.escape(popKey)}"]`, svg); if (t) t.classList.add("sel"); placePop(); }
      }
      $("#sizeInfo").textContent = `${Math.round(data.width)} × ${Math.round(data.height)} mm (${(data.width / 25.4).toFixed(1)} × ${(data.height / 25.4).toFixed(1)} in)`;
    } catch (err) {
      if (id === reqId) toast("Preview failed: " + err.message);
    } finally {
      if (id === reqId) $("#busy").classList.remove("on");
    }
  }
  function fitSheet(aspect) {
    const svg = $("#sheet svg"); if (!svg) return;
    const box = $("#stage").getBoundingClientRect();
    const W = box.width - 48, H = box.height - 48;
    let w = W, h = W / aspect;
    if (h > H) { h = H; w = H * aspect; }
    svg.style.width = w + "px"; svg.style.height = h + "px";
    fitSheet.aspect = aspect;
  }
  window.addEventListener("resize", debounce(() => fitSheet.aspect && fitSheet(fitSheet.aspect), 80));

  function setSeed(v) { S.seed = Math.max(1, Math.round(v)); $('[data-key="seed"]').value = S.seed; changed(); }

  // ------------------------------------------------------------ export
  async function doExport(fmt) {
    closeExportMenu();
    const btn = $("#btnExport");
    btn.disabled = true; btn.classList.add("working");
    toast(`Preparing ${fmt === "pptx" ? "PowerPoint" : fmt.toUpperCase()}…`);
    try {
      const r = await api("/api/export/" + fmt, { method: "POST", body: JSON.stringify({ settings: payload(), dpi: +$("#pngDpi").value }) });
      const blob = await r.blob();
      const cd = r.headers.get("Content-Disposition") || "";
      const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
      download(blob, m ? decodeURIComponent(m[1]) : "poster." + fmt);
      toast(`${fmt.toUpperCase()} exported – check your Downloads folder`);
    } catch (err) { toast("Export failed: " + err.message); }
    finally { btn.disabled = false; btn.classList.remove("working"); }
  }
  function openExportMenu() {
    $("#exportMenu").hidden = false; $("#btnExport").setAttribute("aria-expanded", "true");
    $("#exportMenu button").focus();
  }
  function closeExportMenu() {
    $("#exportMenu").hidden = true; $("#btnExport").setAttribute("aria-expanded", "false");
  }
  function download(blob, name) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }

  // ------------------------------------------------------------ events
  function bind() {
    document.addEventListener("input", (e) => { if (e.target.dataset.key) onInput(e); });
    document.addEventListener("change", (e) => { if (e.target.dataset.key && e.target.tagName === "SELECT") onInput(e); });

    $$("[data-seg]").forEach((seg) => seg.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      S[seg.dataset.seg] = b.dataset.val;
      $$("button", seg).forEach((x) => x.classList.toggle("on", x === b));
      changed();
    }));

    // palettes
    document.addEventListener("click", async (e) => {
      const del = e.target.closest("[data-del]");
      if (del) {
        e.stopPropagation();
        if (!confirm(`Delete palette "${del.dataset.del}"?`)) return;
        userPalettes = await (await api("/api/palettes/" + encodeURIComponent(del.dataset.del), { method: "DELETE" })).json();
        renderPalettes(); return;
      }
      if (e.target.closest("#palCustom")) { customOpen = !customOpen; markPalette(); return; }
      const pal = e.target.closest(".pal");
      if (pal) {
        customOpen = false;
        const src = pal.dataset.src === "user" ? userPalettes : CFG.presets;
        S.palette_name = pal.dataset.pal; applyPalette(src[pal.dataset.pal]);
        if (pal.dataset.src === "user") $("#paletteName").value = pal.dataset.pal;
      }
      const sty = e.target.closest(".sty");
      if (sty) { S.layout_style = sty.dataset.style; markStyles(); changed(); }
      const cp = e.target.closest(".colp");
      if (cp) { S.columns = cp.dataset.cols; $('[data-key="columns"]').value = S.columns; markColumns(); changed(); }
    });
    $("#btnSavePalette").addEventListener("click", async () => {
      const name = $("#paletteName").value.trim();
      if (!name) { toast("Give your palette a name first"); $("#paletteName").focus(); return; }
      const colors = Object.fromEntries(CFG.palette_keys.map((k) => [k, S["c_" + k]]));
      try {
        userPalettes = await (await api("/api/palettes", { method: "POST", body: JSON.stringify({ name, colors }) })).json();
        renderPalettes(); toast(`Palette "${name}" saved`);
      } catch (err) { toast(err.message); }
    });

    // toolbar
    $("#btnRegen").addEventListener("click", () => setSeed(Math.floor(Math.random() * 99999) + 1));
    $("#btnPrev").addEventListener("click", () => setSeed(S.seed - 1));
    $("#btnNext").addEventListener("click", () => setSeed(S.seed + 1));
    $$("[data-export]").forEach((b) => b.addEventListener("click", () => doExport(b.dataset.export)));
    $("#btnExport").addEventListener("click", (e) => { e.stopPropagation(); $("#exportMenu").hidden ? openExportMenu() : closeExportMenu(); });
    document.addEventListener("pointerdown", (e) => { if (!e.target.closest(".menu-wrap")) closeExportMenu(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeExportMenu(); });
    document.addEventListener("keydown", (e) => {
      if (e.target.matches?.("input, textarea, select") || e.ctrlKey || e.metaKey || e.altKey) return;
      if (isEdit()) return;   // layout shortcuts only in layout mode
      if (!$("#exportMenu").hidden) return;   // arrow keys belong to the open menu
      if (e.key === "r" || e.key === "R") $("#btnRegen").click();
      if (e.key === "ArrowLeft") $("#btnPrev").click();
      if (e.key === "ArrowRight") $("#btnNext").click();
    });

    // project files
    $("#btnSaveProject").addEventListener("click", async () => {   // settings + the pictures they use
      try {
        const r = await api("/api/project/pack", { method: "POST", body: JSON.stringify(S) });
        download(await r.blob(), "poster_project.json");
      } catch (err) { toast("Could not save: " + err.message); }
    });
    $("#btnLoadProject").addEventListener("click", () => $("#projectFile").click());
    $("#projectFile").addEventListener("change", async (e) => {
      const f = e.target.files[0]; if (!f) return;
      try {
        const r = await api("/api/project/unpack", { method: "POST", body: await f.text() });
        const { settings } = await r.json();
        S = fixup({ ...structuredClone(CFG.defaults), ...settings }); selected = -1; closePop(); writeForm(); changed(); toast("Project loaded");
      } catch { toast("Could not read that file"); }
      e.target.value = "";
    });
    $("#btnReset").addEventListener("click", () => {
      if (!confirm("Reset all settings to defaults?")) return;
      S = fixup(structuredClone(CFG.defaults)); selected = -1; writeForm(); changed();
    });
  }



  // ============================================================ PROCESS FLOW: arrows between sections (layout mode)
  const ARROW_STYLES = {
    chevron: ["Chevron", '<path d="M5 5l8 7-8 7 3-7z"/>'],
    triangle: ["Triangle", '<path d="M6 5l12 7-12 7z"/>'],
    block: ["Block", '<path d="M3 9.5h9V5l9 7-9 7v-4.5H3z"/>'],
    circle: ["Circle", '<circle cx="12" cy="12" r="9"/><path d="M10 8l5 4-5 4z" fill="#fff"/>'],
    line: ["Line", '<path d="M3 11h12v2H3z"/><path d="M14 7l7 5-7 5z"/>'],
  };
  let connecting = false;
  let connectFrom = null;      // section id the next arrow starts from

  function renderArrows() {
    $("#arrowStyles").innerHTML = Object.entries(ARROW_STYLES).map(([k, [name, icon]]) =>
      `<button class="ast${S.arrow_style === k ? " on" : ""}" data-astyle="${k}" title="${name}"><svg viewBox="0 0 24 24">${icon}</svg><small>${name}</small></button>`).join("");
    const ids = new Set(S.sections.map((s) => s.id));
    const name = (id) => escapeHtml(secById(id)?.title || "Untitled section");
    const list = S.flow_arrows.map((a, i) => [a, i]).filter(([a]) => ids.has(a[0]) && ids.has(a[1]));
    $("#arrowList").innerHTML = list.map(([a, i]) =>
      `<li><span>${name(a[0])}</span><b>→</b><span>${name(a[1])}</span><button class="ghost small" data-rmarrow="${i}" title="Remove this arrow">✕</button></li>`).join("")
      + (list.length > 1 ? `<li class="all"><button class="ghost small" id="btnArrowsClear">Remove all arrows</button></li>` : "");
  }
  function setConnecting(on) {
    connecting = on; connectFrom = null;
    document.body.classList.toggle("connecting", on);
    $("#btnConnect").classList.toggle("on", on);
    $("#btnConnect span").textContent = on ? "Done connecting" : "Connect sections with arrows";
    if (on) $("#secDelete").hidden = true;
    markConnectFrom();
    if (on) toast("Click a section, then the one the arrow points to");
    updateStatus();
  }
  function markConnectFrom() {
    $$("#sheet rect.hot.cfrom").forEach((r) => r.classList.remove("cfrom"));
    if (!connecting || !connectFrom) return;
    const i = S.sections.findIndex((s) => s.id === connectFrom);
    const r = $(`#sheet rect.hot[data-idx="${i}"]`); if (r) r.classList.add("cfrom");
  }
  function connectClick(idx) {
    const id = S.sections[idx]?.id; if (!id) return;
    if (!connectFrom || connectFrom === id) { connectFrom = connectFrom === id ? null : id; markConnectFrom(); return; }
    const from = connectFrom;
    S.flow_arrows = S.flow_arrows.filter((a) => !(a[0] === id && a[1] === from));   // reverse arrow is replaced
    if (!S.flow_arrows.some((a) => a[0] === from && a[1] === id)) S.flow_arrows.push([from, id]);
    connectFrom = null;            // start fresh: the next arrow needs two new clicks
    renderArrows(); markConnectFrom(); changed();
  }
  function removeArrow(i) {
    const [a] = S.flow_arrows.splice(i, 1); if (!a) return;
    renderArrows(); changed();
    toast("Arrow removed", { label: "Undo", fn: () => { S.flow_arrows.splice(i, 0, a); renderArrows(); changed(); } });
  }
  function bindFlow() {
    $("#btnConnect").addEventListener("click", () => setConnecting(!connecting));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && connecting) setConnecting(false); });
    document.addEventListener("click", (e) => {
      const st = e.target.closest("[data-astyle]");
      if (st) { S.arrow_style = st.dataset.astyle; renderArrows(); changed(); return; }
      const rm = e.target.closest("[data-rmarrow]");
      if (rm) { removeArrow(+rm.dataset.rmarrow); return; }
      if (e.target.closest("#btnArrowsClear")) {
        const old = S.flow_arrows; S.flow_arrows = []; renderArrows(); changed();
        toast("All arrows removed", { label: "Undo", fn: () => { S.flow_arrows = old; renderArrows(); changed(); } });
      }
    });
    $("#sheet").addEventListener("pointerdown", (e) => {
      const ah = e.target.closest("rect.arrowhot"); if (!ah || !connecting || e.button !== 0) return;
      e.preventDefault(); e.stopPropagation(); removeArrow(+ah.dataset.arrow);
    }, true);
  }

  // ============================================================ EDIT MODE: the poster's own content
  // Field keys (shared with the server's edit targets):
  //   c.<title|authors|affiliations|footer_left|footer_center|qr_label|logo_left>, c.logos_right.<i>,
  //   s.<section id>.<title|body>, s.<section id>.fig.<slot> (picture id), s.<section id>.cap.<slot>, qr_url
  const SUPS = ["¹", "²", "³", "⁴", "⁵", "⁶", "*", "†"];
  let popKey = null;            // field edited in the popover on the preview
  let targets = new Set();      // edit targets present in the current preview
  let editSig = "";
  let lastInfo = null;          // last preview response (for the status line)
  let pendingImgKey = null;     // picture slot waiting for the file chooser
  let lastField = null;         // last focused text field (for the superscript buttons)

  const isEdit = () => S.mode === "edit";
  const secById = (id) => S.sections.find((s) => s.id === id);
  const supButtons = () => `<div class="sup-help">Insert: ${SUPS.map((c) => `<button class="chip" data-ins="${c}" tabindex="-1">${c}</button>`).join("")}</div>`;

  function getField(key) {
    const p = key.split(".");
    if (p[0] === "c") return (p[1] === "logos_right" ? (S.content.logos_right || [])[+p[2]] : S.content[p[1]]) || "";
    if (p[0] === "s") {
      const sec = secById(p[1]); if (!sec) return "";
      if (p[2] === "title" || p[2] === "body") return sec[p[2]] || "";
      const f = (sec.figs || {})[p[3]] || {};
      return (p[2] === "fig" ? f.img : f.caption) || "";
    }
    return S[key] ?? "";
  }
  function setField(key, val, src) {
    const p = key.split(".");
    if (p[0] === "c") {
      if (p[1] === "logos_right") {
        const a = (S.content.logos_right = S.content.logos_right || []);
        while (a.length <= +p[2]) a.push("");
        a[+p[2]] = val;
      } else S.content[p[1]] = val;
    } else if (p[0] === "s") {
      const sec = secById(p[1]); if (!sec) return;
      if (p[2] === "title" || p[2] === "body") sec[p[2]] = val;
      else {
        sec.figs = sec.figs || {};
        const f = (sec.figs[p[3]] = sec.figs[p[3]] || { img: "", caption: "" });
        f[p[2] === "fig" ? "img" : "caption"] = val;
      }
      if (p[2] === "title") { renderSections(); renderArrows(); }
    } else {
      S[key] = val;
      const el = $(`[data-key="${key}"]`); if (el) el.value = val;
    }
    $$(`[data-field="${key}"]`).forEach((el) => { if (el !== src) el.value = val; });
    $$(`.imgslot[data-img="${key}"]`).forEach(paintSlot);
    changed();
  }

  // ---- picture slots (panel and popover)
  function slotHTML(key, label) {
    return `<div class="imgslot" data-img="${key}" tabindex="0" title="Click to choose a picture, or drop one here">
      <div class="thumb"></div><div class="meta"><b>${escapeHtml(label)}</b><small></small></div>
      <button class="ghost small rm" data-rmimg="${key}" title="Remove picture">✕</button></div>`;
  }
  function paintSlot(el) {
    const id = getField(el.dataset.img);
    $(".thumb", el).style.backgroundImage = id ? `url(/api/image/${id})` : "";
    el.classList.toggle("has", !!id);
    $("small", el).textContent = id ? "Click to replace, or drop a file" : "Click to choose, or drop a picture";
  }
  async function uploadImage(file) {
    if (!file || !file.type.startsWith("image/")) { toast("That is not a picture file"); return null; }
    const fd = new FormData(); fd.append("file", file);
    $("#busy").classList.add("on");
    try {
      const r = await fetch("/api/image", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || r.statusText);
      return j.id;
    } catch (err) { toast("Could not add the picture: " + err.message); return null; }
    finally { $("#busy").classList.remove("on"); }
  }
  async function putImage(key, file) { const id = await uploadImage(file); if (id) setField(key, id); }

  // ---- content panel
  function figSlots(sec) {   // figure places this section has on the poster (plus any holding a picture)
    const out = new Set();
    targets.forEach((k) => { const m = /^s\.(.+)\.fig\.(\d)$/.exec(k); if (m && m[1] === sec.id) out.add(m[2]); });
    Object.entries(sec.figs || {}).forEach(([i, f]) => { if (f && f.img) out.add(i); });
    return [...out].sort();
  }
  function editSignature() {
    return JSON.stringify([S.logo_left, S.logos_right, S.bottom_enabled, S.sections.map((s) => [s.id, s.figure, figSlots(s)])]);
  }
  function renderEditPanel(force) {
    const sig = editSignature();
    if (!force && sig === editSig) return;
    editSig = sig;
    const focused = document.activeElement && document.activeElement.closest("#editPanel") ? document.activeElement.dataset.field : null;
    const slots = [];
    if (S.logo_left) slots.push(["c.logo_left", "Top-left logo"]);
    for (let i = 0; i < S.logos_right; i++) slots.push([`c.logos_right.${i}`, `Top-right logo ${i + 1}`]);
    $("#logoSlots").innerHTML = slots.map(([k, l]) => slotHTML(k, l)).join("");
    $("#logoHint").textContent = slots.length ? "" : "There are no logo places – add them under Header & logos in Layout mode.";
    $("#contentSections").innerHTML = S.sections.map((sec, i) => {
      const fs = figSlots(sec);
      return `<div class="csec" data-sid="${sec.id}">
        <div class="csec-head"><span class="num">${i + 1}</span><input type="text" data-field="s.${sec.id}.title" placeholder="Section title"></div>
        <textarea data-field="s.${sec.id}.body" rows="5" placeholder="Text of this section (empty = sample text)"></textarea>
        ${fs.map((j) => `<div class="cfig">${slotHTML(`s.${sec.id}.fig.${j}`, fs.length > 1 ? `Figure ${+j + 1}` : "Figure")}
          <input type="text" data-field="s.${sec.id}.cap.${j}" placeholder="Caption (empty = sample caption)"></div>`).join("")}
        ${fs.length ? "" : `<button class="ghost small add-fig" data-addfig="${sec.id}">+ Add a figure</button>`}
      </div>`;
    }).join("");
    $$("#editPanel [data-field]").forEach((el) => { if (el !== document.activeElement) el.value = getField(el.dataset.field); });
    $$("#editPanel .imgslot").forEach(paintSlot);
    $("#footerContent").classList.toggle("off", !S.bottom_enabled);
    $("#footerHint").hidden = !!S.bottom_enabled;
    if (focused) { const el = $(`#editPanel [data-field="${focused}"]`); if (el && el !== document.activeElement) el.focus(); }
  }

  // ---- mode
  function applyMode() {
    const edit = isEdit();
    document.body.classList.toggle("mode-edit", edit);
    $$("#modeSwitch button").forEach((b) => { b.classList.toggle("on", b.dataset.mode === S.mode); b.setAttribute("aria-selected", b.dataset.mode === S.mode); });
    $("#layoutPanel").hidden = edit;
    if (edit) setConnecting(false);
    $("#editPanel").hidden = !edit;
    closePop();
    $("#secDelete").hidden = true;
    if (edit) renderEditPanel(true);
    updateStatus();
  }
  function updateStatus() {
    const d = lastInfo; if (!d) return;
    const warn = (d.warnings || []).length ? "⚠ " + d.warnings.join(" · ") + " · " : "";
    const base = `${S.size === "Custom" ? "Custom" : S.size} · ${S.orientation} · ${Math.round(d.width)} × ${Math.round(d.height)} mm`;
    $("#status").textContent = warn + base + (connecting
      ? " · Connecting: click a section, then the one the arrow points to · click an arrow to remove it · Esc when done"
      : isEdit()
      ? " · Edit mode: click any text or picture to edit it · drop pictures or text onto the poster · drag a picture onto another to swap them"
      : ` · ${d.style_name} · layout #${d.seed} · click a section to select it · drag it onto another to move it there · drag the gaps to resize`);
    $("#status").classList.toggle("warn", !!warn);
  }

  // ---- popover editor on the preview
  function openPop(key) {
    const t = $(`#sheet rect.tgt[data-key="${CSS.escape(key)}"]`); if (!t) return;
    popKey = key;
    const kind = t.dataset.kind, label = t.querySelector("title")?.textContent || "";
    let body;
    if (kind === "image") {
      body = slotHTML(key, "Picture");
      const m = /^s\.(.+)\.fig\.(\d)$/.exec(key);
      if (m) body += `<label>Caption<textarea data-field="s.${m[1]}.cap.${m[2]}" rows="2" placeholder="Caption (empty = sample caption)"></textarea></label>`;
    } else if (kind === "qr") {
      body = `<label>QR code link<input type="url" data-field="qr_url" placeholder="https://doi.org/…"></label>`;
    } else {
      const big = /\.body$/.test(key), single = /\.title$|qr_label$/.test(key) && key !== "c.title";
      body = single ? `<input type="text" data-field="${key}">` : `<textarea data-field="${key}" rows="${big ? 10 : 3}"></textarea>`;
      if (/^c\.(authors|affiliations)$/.test(key)) body += supButtons();
      if (big) body += `<p class="hint">Each line break starts a new paragraph. Text that is too long shrinks a little to fit.</p>`;
    }
    const pop = $("#editPop");
    pop.innerHTML = `<div class="pop-head"><b>${escapeHtml(label)}</b><button class="ghost small" data-popclose title="Close (Esc)">✕</button></div>${body}`;
    $$("[data-field]", pop).forEach((el) => { el.value = getField(el.dataset.field); el.placeholder = el.placeholder || "Empty = sample text"; });
    $$(".imgslot", pop).forEach(paintSlot);
    pop.hidden = false;
    placePop();
    $$("#sheet rect.tgt.sel").forEach((r) => r.classList.remove("sel"));
    t.classList.add("sel");
    const f = $("textarea, input", pop);
    if (f) { f.focus(); const n = f.value.length; try { f.setSelectionRange(n, n); } catch { /* url inputs */ } }
  }
  function placePop() {
    const pop = $("#editPop"); if (pop.hidden || !popKey) return;
    const t = $(`#sheet rect.tgt[data-key="${CSS.escape(popKey)}"]`); if (!t) { closePop(); return; }
    const b = t.getBoundingClientRect(), sb = $("#stage").getBoundingClientRect();
    const pw = pop.offsetWidth, ph = pop.offsetHeight;
    const left = Math.max(8, Math.min(sb.width - pw - 8, b.left - sb.left + b.width / 2 - pw / 2));
    let top = b.bottom - sb.top + 8;                                   // below the element …
    if (top + ph > sb.height - 8) top = b.top - sb.top - ph - 8;       // … else above it …
    if (top < 8) top = Math.max(8, Math.min(sb.height - ph - 8, b.top - sb.top + 8));   // … else over it
    pop.style.left = left + "px"; pop.style.top = top + "px";
  }
  function closePop() {
    popKey = null;
    $("#editPop").hidden = true;
    $$("#sheet rect.tgt.sel").forEach((r) => r.classList.remove("sel"));
  }

  // ---- moving content around on the preview
  const labelOf = (t) => t.querySelector("title")?.textContent || "";
  const isBody = (k) => /^s\..+\.body$/.test(k);
  const canDrag = (key, kind) => (kind === "image" && !!getField(key)) || (isBody(key) && !!getField(key).trim());
  const fits = (a, aKind, b, bKind) => (aKind === "image" && bKind === "image") || (isBody(a) && isBody(b));
  function swapContent(a, b) {
    const va = getField(a), vb = getField(b);
    setField(a, vb); setField(b, va);
    const fa = /\.fig\.\d$/.test(a), fb = /\.fig\.\d$/.test(b);
    if (fa && fb) {   // figures keep their captions
      const ca = a.replace(".fig.", ".cap."), cb = b.replace(".fig.", ".cap.");
      const x = getField(ca), y = getField(cb); setField(ca, y); setField(cb, x);
    }
    toast(isBody(a) ? "Texts swapped" : "Pictures swapped");
  }
  async function dropInto(key, kind, dt) {
    const files = [...(dt.files || [])];
    const img = files.find((f) => f.type.startsWith("image/"));
    if (img) {
      if (kind === "image") return putImage(key, img);
      const m = /^s\.([^.]+)\./.exec(key);
      if (m) {   // dropped onto a section's text: use its first free figure place, or give it one
        const sec = secById(m[1]); if (!sec) return;
        const slots = figSlots(sec);
        const free = slots.find((j) => !getField(`s.${sec.id}.fig.${j}`)) ?? (slots[0] || "0");
        if (!slots.length) { sec.figure = "yes"; renderSections(); }
        return putImage(`s.${sec.id}.fig.${free}`, img);
      }
      toast("Drop pictures onto a figure, a logo or a section"); return;
    }
    let txt = dt.getData ? dt.getData("text/plain") : "";
    const tf = files.find((f) => /^text\//.test(f.type) || /\.(txt|md)$/i.test(f.name));
    if (!txt && tf) txt = await tf.text();
    txt = (txt || "").replace(/\r\n?/g, "\n").trim();
    if (!txt) return;
    if (kind === "text") { setField(key, txt); toast("Text placed"); }
    else if (/\.fig\.\d$/.test(key)) { setField(key.replace(".fig.", ".cap."), txt); toast("Caption set"); }
    else toast("Drop text onto a text on the poster");
  }

  function bindEditMode() {
    $("#modeSwitch").addEventListener("click", (e) => {
      const b = e.target.closest("[data-mode]"); if (!b || b.dataset.mode === S.mode) return;
      S.mode = b.dataset.mode; storage.set(S); applyMode();
    });
    $$(".sup-btns").forEach((el) => (el.outerHTML = supButtons().replace(/^<div class="sup-help">Insert: |<\/div>$/g, "")));
    // typing in any content field (panel or popover)
    document.addEventListener("input", (e) => { const k = e.target.dataset && e.target.dataset.field; if (k) setField(k, e.target.value, e.target); });
    document.addEventListener("focusin", (e) => { if (e.target.dataset && e.target.dataset.field && e.target.matches("textarea, input[type=text]")) lastField = e.target; });
    document.addEventListener("mousedown", (e) => { if (e.target.closest("[data-ins]")) e.preventDefault(); });   // keep the text cursor
    document.addEventListener("click", (e) => {
      const ins = e.target.closest("[data-ins]");
      if (ins) {
        const el = lastField; if (!el || !document.body.contains(el)) { toast("Click into a text field first"); return; }
        const a = el.selectionStart ?? el.value.length, b = el.selectionEnd ?? a;
        el.value = el.value.slice(0, a) + ins.dataset.ins + el.value.slice(b);
        el.focus(); el.selectionStart = el.selectionEnd = a + ins.dataset.ins.length;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        return;
      }
      const rm = e.target.closest("[data-rmimg]");
      if (rm) { e.stopPropagation(); setField(rm.dataset.rmimg, ""); return; }
      const slot = e.target.closest(".imgslot");
      if (slot) { pendingImgKey = slot.dataset.img; $("#imgFile").click(); return; }
      const add = e.target.closest("[data-addfig]");
      if (add) { const sec = secById(add.dataset.addfig); if (sec) { sec.figure = "yes"; renderSections(); changed(); } return; }
      if (e.target.closest("[data-popclose]")) closePop();
    });
    $("#imgFile").addEventListener("change", async (e) => {
      const f = e.target.files[0]; e.target.value = "";
      if (f && pendingImgKey) await putImage(pendingImgKey, f);
      pendingImgKey = null;
    });
    // dropping files onto a picture slot in the panel / popover
    document.addEventListener("dragover", (e) => {
      const slot = e.target.closest && e.target.closest(".imgslot");
      $$(".imgslot.drop").forEach((s) => s !== slot && s.classList.remove("drop"));
      if (!slot) return;
      e.preventDefault(); slot.classList.add("drop");
    });
    document.addEventListener("drop", (e) => {
      const slot = e.target.closest && e.target.closest(".imgslot");
      $$(".imgslot.drop").forEach((s) => s.classList.remove("drop"));
      if (!slot) { if (!e.target.closest || !e.target.closest("#stage")) e.preventDefault(); return; }   // never open dropped files in the window
      e.preventDefault();
      const f = [...e.dataTransfer.files].find((x) => x.type.startsWith("image/"));
      if (f) putImage(slot.dataset.img, f); else toast("Drop a picture file here");
    });

    // ---- the preview: click to edit, drag pictures / texts onto each other, drop files and text
    const sheet = $("#sheet"), stage = $("#stage");
    let d = null;
    sheet.addEventListener("pointerdown", (e) => {
      const t = e.target.closest("rect.tgt"); if (!t || e.button !== 0 || !isEdit()) return;
      e.preventDefault();
      d = { key: t.dataset.key, kind: t.dataset.kind, t, x: e.clientX, y: e.clientY, moving: false, over: null };
    });
    document.addEventListener("pointermove", (e) => {
      if (!d) return;
      if (!d.moving) {
        if (Math.hypot(e.clientX - d.x, e.clientY - d.y) < 6 || !canDrag(d.key, d.kind)) return;
        d.moving = true; closePop(); sheet.classList.add("dragging");
        d.ghost = Object.assign(document.createElement("div"), { className: "drag-ghost", textContent: labelOf(d.t) });
        document.body.appendChild(d.ghost);
      }
      d.ghost.style.left = e.clientX + "px"; d.ghost.style.top = e.clientY + "px";
      const el = document.elementFromPoint(e.clientX, e.clientY);
      const over = el && el.closest ? el.closest("rect.tgt") : null;
      const ok = over && over.dataset.key !== d.key && fits(d.key, d.kind, over.dataset.key, over.dataset.kind) ? over : null;
      if (ok !== d.over) { if (d.over) d.over.classList.remove("drop"); if (ok) ok.classList.add("drop"); d.over = ok; }
      d.ghost.textContent = labelOf(d.t) + (ok ? "  ⇄  " + labelOf(ok) : "");
    });
    document.addEventListener("pointerup", () => {
      if (!d) return;
      const x = d; d = null;
      sheet.classList.remove("dragging");
      if (x.ghost) x.ghost.remove();
      if (x.over) x.over.classList.remove("drop");
      if (!x.moving) { openPop(x.key); return; }
      if (x.over) swapContent(x.key, x.over.dataset.key);
    });
    document.addEventListener("pointerdown", (e) => {   // click elsewhere closes the popover
      if (!popKey || e.target.closest("#editPop") || e.target.closest("rect.tgt")) return;
      closePop();
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && popKey) closePop(); });
    window.addEventListener("resize", debounce(placePop, 80));

    const tgtAt = (e) => { const el = document.elementFromPoint(e.clientX, e.clientY); return el && el.closest ? el.closest("rect.tgt") : null; };
    let dropOver = null;
    const mark = (t) => { if (t !== dropOver) { if (dropOver) dropOver.classList.remove("drop"); if (t) t.classList.add("drop"); dropOver = t; } };
    stage.addEventListener("dragover", (e) => {
      if (e.target.closest(".pop")) return;
      e.preventDefault();
      if (!isEdit()) { e.dataTransfer.dropEffect = "none"; return; }
      e.dataTransfer.dropEffect = "copy";
      mark(tgtAt(e));
    });
    stage.addEventListener("dragleave", (e) => { if (!stage.contains(e.relatedTarget)) mark(null); });
    stage.addEventListener("drop", async (e) => {
      if (e.target.closest(".pop")) return;
      e.preventDefault();
      const t = tgtAt(e); mark(null);
      if (!isEdit()) { toast("Switch to Edit mode to drop pictures or text onto the poster"); return; }
      if (!t) { toast("Drop onto a text, a figure or a logo"); return; }
      await dropInto(t.dataset.key, t.dataset.kind, e.dataTransfer);
    });
  }

  // ------------------------------------------------------------ init
  async function init() {
    CFG = await (await api("/api/config")).json();
    userPalettes = CFG.user_palettes || {};
    $("#sizeSelect").innerHTML = CFG.sizes.map((s) => `<option>${s}</option>`).join("");
    S = fixup({ ...structuredClone(CFG.defaults), ...(storage.get() || {}) });
    storage.set(S);   // persist migrated settings (e.g. new section ids) so reloads look identical
    renderPalettes(); renderColumnPresets(); renderStyles(); renderFontSelects(); writeForm();
    bind(); bindColorPicker(); bindEditMode(); bindFlow(); bindSectionList(); bindPreviewDrag(); bindDeleteButton(); bindPaneResizer(); render();
  }
  function fixup(s) {   // migrate settings saved by older versions
    // logos used to be uploaded images; they are placeholders now (on/off + count)
    if (typeof s.logo_left !== "boolean") s.logo_left = CFG.defaults.logo_left;
    if (typeof s.logos_right !== "number") s.logos_right = CFG.defaults.logos_right;
    s.sections = normSections(s.sections);
    if (!s.sections.length) s.sections = normSections(structuredClone(CFG.defaults.sections));
    if (!s.layout_style || !(s.layout_style in CFG.layout_styles)) s.layout_style = "auto";   // removed styles
    if (s.mode !== "edit") s.mode = "layout";
    if (!Array.isArray(s.flow_arrows)) s.flow_arrows = [];
    if (!s.layout_trees || typeof s.layout_trees !== "object" || Array.isArray(s.layout_trees)) s.layout_trees = {};
    const c = s.content && typeof s.content === "object" ? s.content : {};
    s.content = { title: "", authors: "", affiliations: "", footer_left: "", footer_center: "", qr_label: "", logo_left: "",
                  ...c, logos_right: Array.isArray(c.logos_right) ? c.logos_right : [] };
    if (!s.split_sizes || typeof s.split_sizes !== "object" || Array.isArray(s.split_sizes)) s.split_sizes = {};
    // keys from older versions (content text is no longer edited here)
    ["allow_span", "font", "title", "authors", "affiliations", "footer_left", "footer_center", "qr_label", "key_message"]
      .forEach((k) => delete s[k]);
    const names = CFG.fonts.map((f) => f.name);
    ["font_heading", "font_body"].forEach((k) => { if (!names.includes(s[k])) s[k] = names.includes("Arial") ? "Arial" : names[0]; });
    return s;
  }
  init().catch((e) => toast("Startup failed: " + e.message));
})();
