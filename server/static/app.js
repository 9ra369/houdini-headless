// houdini-headless の画面
// サーバー（hython + hwebserver）の /api/* を呼んで、ノードツリー・ネットワーク図・パラメータを表示する

"use strict";

const $ = (id) => document.getElementById(id);
const SVG_NS = "http://www.w3.org/2000/svg";
const SCALE = 80; // ネットワークの 1 単位を何 px で描くか

const state = {
  status: null,
  networkPath: "/obj",
  nodes: [],
  selectedPath: null,
  node: null, // 選んでいるノードの詳細（パラメータ付き）
  edits: {}, // { parm tuple 名: [値 or undefined, ...] }
  view: { x: 0, y: 0, k: 1 },
  busy: 0,
};

// --- 共通 --------------------------------------------------------------------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== undefined && value !== null && value !== false) node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children) {
    if (child !== null && child !== undefined) node.append(child);
  }
  return node;
}

function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

function log(message, level = "") {
  const time = new Date().toLocaleTimeString();
  const item = el("li", { class: level }, el("span", { class: "time" }, time), message);
  $("log").append(item);
  item.scrollIntoView({ block: "end" });
}

async function api(path, body) {
  state.busy++;
  $("busy").hidden = false;
  try {
    const options = body === undefined
      ? {}
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    let response;
    try {
      response = await fetch(path, options);
    } catch (e) {
      throw new Error("サーバーにつながりません。サーバーが起動しているか確認してください");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
    return data;
  } finally {
    state.busy--;
    $("busy").hidden = state.busy === 0;
  }
}

// 例外をログに出すだけのラッパー（ボタンのクリックなどで使う）
function guarded(fn) {
  return async (...args) => {
    try {
      await fn(...args);
    } catch (e) {
      log(e.message, "error");
    }
  };
}

function hasEdits() {
  return Object.keys(state.edits).length > 0;
}

function confirmDiscard(message) {
  if (state.status && state.status.unsaved) {
    return confirm(`保存していない変更があります。${message}`);
  }
  return true;
}

// --- hip ファイル ------------------------------------------------------------

function showStatus(status) {
  state.status = status;
  $("hip-name").textContent = status.isNewFile ? "（新規）" : status.hipName;
  $("hip-path").textContent = status.isNewFile ? "" : status.hipPath;
  $("hip-unsaved").hidden = !status.unsaved;
  $("server-info").textContent = `Houdini ${status.houdini} (${status.license})`;
  document.title = `${status.unsaved ? "● " : ""}${status.hipName} - houdini-headless`;
}

async function refreshStatus() {
  showStatus(await api("/api/status"));
}

async function openHip(path) {
  if (!confirmDiscard("破棄して開きますか？")) return;
  $("file-dialog").close();
  log(`開いています: ${path}`);
  showStatus(await api("/api/hip/open", { path }));
  log(`開きました: ${state.status.hipPath}`, "ok");
  selectNode(null);
  await loadTree();
  await showNetwork("/obj");
}

async function saveHip(path) {
  showStatus(await api("/api/hip/save", path ? { path } : {}));
  log(`保存しました: ${state.status.hipPath}`, "ok");
}

// --- ファイル選択ダイアログ ---------------------------------------------------

async function browse(dir) {
  const data = await api(`/api/files?dir=${encodeURIComponent(dir)}`);
  $("file-dir").value = data.dir;
  const list = $("file-list");
  list.replaceChildren();
  if (data.parent !== null) {
    list.append(el("li", { onclick: guarded(() => browse(data.parent)) }, "↑ 上のフォルダ"));
  }
  for (const name of data.dirs) {
    const path = data.dir ? `${data.dir}\\${name}` : name;
    list.append(el("li", { onclick: guarded(() => browse(path)) }, `📁 ${name}`));
  }
  for (const name of data.files) {
    list.append(el("li", { class: "hipfile", onclick: guarded(() => openHip(`${data.dir}\\${name}`)) }, `◆ ${name}`));
  }
  if (!data.dirs.length && !data.files.length) {
    list.append(el("li", { class: "muted" }, "（フォルダも hip もありません）"));
  }
}

async function openFileDialog() {
  const status = state.status;
  const dir = status.isNewFile ? status.samplesDir : status.hipPath.replace(/[\\/][^\\/]*$/, "");
  $("file-dialog").showModal();
  await browse(dir);
}

// --- ノードツリー（左） --------------------------------------------------------

function treeItem(node) {
  const children = el("ul", { hidden: true });
  const caret = el("span", { class: "tree-caret" }, node.hasChildren ? "▸" : "");
  const row = el("div", { class: "tree-row", "data-path": node.path },
    caret,
    el("span", {}, node.name),
    el("span", { class: "tree-type" }, node.type),
  );
  let loaded = false;

  caret.addEventListener("click", guarded(async (event) => {
    event.stopPropagation();
    if (!node.hasChildren) return;
    if (!loaded) {
      const data = await api(`/api/nodes?path=${encodeURIComponent(node.path)}`);
      children.replaceChildren(...data.children.map(treeItem));
      loaded = true;
    }
    children.hidden = !children.hidden;
    caret.textContent = children.hidden ? "▸" : "▾";
  }));
  row.addEventListener("click", guarded(async () => {
    const parent = node.path.replace(/\/[^/]+$/, "") || "/";
    if (parent !== state.networkPath) await showNetwork(parent);
    await selectNode(node.path);
  }));
  row.addEventListener("dblclick", guarded(async () => {
    if (node.hasChildren) await showNetwork(node.path);
  }));

  return el("li", {}, row, children);
}

async function loadTree() {
  const data = await api("/api/nodes?path=/");
  $("tree").replaceChildren(...data.children.map(treeItem));
}

function markTreeSelection() {
  for (const row of document.querySelectorAll(".tree-row")) {
    row.classList.toggle("selected", row.dataset.path === state.selectedPath);
  }
}

// --- ネットワーク図（中央） ----------------------------------------------------

// スクリプトで作った hip では、ノードがみな同じ位置にあることがある。
// そのときは、入力の深さで段を決めて並べ直す（hip は変えない。表示だけ）
function layoutPositions(nodes) {
  const keys = new Set(nodes.map((n) => n.position.join(",")));
  const positions = new Map(nodes.map((n) => [n.path, { x: n.position[0], y: n.position[1] }]));
  if (keys.size === nodes.length) return positions;

  const byPath = new Map(nodes.map((n) => [n.path, n]));
  const depth = new Map();
  const visiting = new Set();
  const depthOf = (node) => {
    if (depth.has(node.path)) return depth.get(node.path);
    if (visiting.has(node.path)) return 0; // ループしていたら打ち切る
    visiting.add(node.path);
    let d = 0;
    for (const input of node.inputs) {
      const src = byPath.get(input.from);
      if (src) d = Math.max(d, depthOf(src) + 1);
    }
    visiting.delete(node.path);
    depth.set(node.path, d);
    return d;
  };
  const columns = new Map();
  for (const node of nodes) {
    const d = depthOf(node);
    const col = columns.get(d) || 0;
    columns.set(d, col + 1);
    positions.set(node.path, { x: col * 3, y: -d * 1.2 });
  }
  return positions;
}

function portX(node, pos, index, count) {
  const w = node.size[0];
  return (pos.x + (w * (index + 1)) / (count + 1)) * SCALE;
}

function drawNetwork() {
  const nodesLayer = $("nodes");
  const edgesLayer = $("edges");
  nodesLayer.replaceChildren();
  edgesLayer.replaceChildren();
  $("graph-empty").hidden = state.nodes.length > 0;

  const positions = layoutPositions(state.nodes);
  const byPath = new Map(state.nodes.map((n) => [n.path, n]));
  const inputCount = (n) => Math.max(1, Math.min(n.maxInputs, 4), ...n.inputs.map((i) => i.toIndex + 1));
  const outputCount = (n) => Math.max(1, n.maxOutputs, ...state.nodes.flatMap((m) => m.inputs.filter((i) => i.from === n.path).map((i) => i.fromIndex + 1)));

  // つながり（上のノードの出力 → 下のノードの入力）
  for (const node of state.nodes) {
    const pos = positions.get(node.path);
    for (const input of node.inputs) {
      const src = byPath.get(input.from);
      if (!src) continue;
      const srcPos = positions.get(src.path);
      const x1 = portX(src, srcPos, input.fromIndex, outputCount(src));
      const y1 = -srcPos.y * SCALE;
      const x2 = portX(node, pos, input.toIndex, inputCount(node));
      const y2 = -(pos.y + node.size[1]) * SCALE;
      const bend = Math.max(30, Math.abs(y2 - y1) / 2);
      edgesLayer.append(svg("path", {
        class: "edge",
        d: `M${x1},${y1} C${x1},${y1 + bend} ${x2},${y2 - bend} ${x2},${y2}`,
      }));
    }
  }

  // ノード
  for (const node of state.nodes) {
    const pos = positions.get(node.path);
    const x = pos.x * SCALE;
    const y = -(pos.y + node.size[1]) * SCALE;
    const w = node.size[0] * SCALE;
    const h = node.size[1] * SCALE;
    const [r, g, b] = node.color.map((c) => Math.round(c * 255));

    const group = svg("g", { class: "gnode", "data-path": node.path });
    group.classList.toggle("selected", node.path === state.selectedPath);
    group.classList.toggle("has-error", node.errors > 0);
    group.classList.toggle("has-warning", node.errors === 0 && node.warnings > 0);

    const title = svg("title");
    title.textContent = `${node.path}\n${node.typeLabel} (${node.type})` +
      (node.errors ? `\nエラー ${node.errors} 件` : "") + (node.warnings ? `\n警告 ${node.warnings} 件` : "");
    group.append(title);
    group.append(svg("rect", { class: "body", x, y, width: w, height: h, rx: 4, fill: `rgb(${r},${g},${b})` }));
    if (node.flags.bypass) group.append(svg("rect", { class: "bypass", x, y, width: w, height: h, rx: 4 }));
    if (node.flags.render) group.append(svg("rect", { class: "flag-render", x: x + w - 16, y, width: 8, height: h }));
    if (node.flags.display) group.append(svg("rect", { class: "flag-display", x: x + w - 8, y, width: 8, height: h, rx: 3 }));

    const nIn = inputCount(node);
    for (let i = 0; i < (node.maxInputs ? nIn : 0); i++) {
      group.append(svg("circle", { class: "port", cx: portX(node, pos, i, nIn), cy: y, r: 3 }));
    }
    const nOut = outputCount(node);
    for (let i = 0; i < (node.maxOutputs ? nOut : 0); i++) {
      group.append(svg("circle", { class: "port", cx: portX(node, pos, i, nOut), cy: y + h, r: 3 }));
    }

    const label = svg("text", { class: "label", x: x + w + 8, y: y + h / 2 - 1 });
    label.textContent = node.name;
    const sub = svg("text", { class: "sublabel", x: x + w + 8, y: y + h / 2 + 11 });
    sub.textContent = node.typeLabel + (node.hasChildren ? "  ▸" : "") + (node.isRop ? "  [ROP]" : "");
    group.append(label, sub);

    group.addEventListener("click", guarded(() => selectNode(node.path)));
    group.addEventListener("dblclick", guarded(async () => {
      if (node.hasChildren) await showNetwork(node.path);
    }));
    nodesLayer.append(group);
  }
}

function drawBreadcrumb() {
  const crumbs = $("breadcrumb");
  crumbs.replaceChildren();
  const parts = state.networkPath.split("/").filter(Boolean);
  crumbs.append(el("button", { onclick: guarded(() => showNetwork("/")) }, "/"));
  parts.forEach((part, i) => {
    const path = "/" + parts.slice(0, i + 1).join("/");
    if (i > 0) crumbs.append(el("span", { class: "sep" }, "/"));
    crumbs.append(el("button", { onclick: guarded(() => showNetwork(path)) }, part));
  });
  $("btn-up").disabled = state.networkPath === "/";
}

async function showNetwork(path, { fit = true } = {}) {
  const data = await api(`/api/nodes?path=${encodeURIComponent(path)}`);
  state.networkPath = data.path;
  state.nodes = data.children;
  drawBreadcrumb();
  drawNetwork();
  if (fit) fitView();
}

function applyView() {
  const { x, y, k } = state.view;
  $("viewport").setAttribute("transform", `translate(${x},${y}) scale(${k})`);
}

function fitView() {
  const graph = $("graph");
  const box = $("viewport").getBBox();
  const width = graph.clientWidth;
  const height = graph.clientHeight;
  if (!box.width || !box.height || !width || !height) {
    state.view = { x: width / 2, y: height / 2, k: 1 };
  } else {
    const k = Math.min(1.5, (width - 80) / box.width, (height - 80) / box.height);
    state.view = {
      k,
      x: width / 2 - (box.x + box.width / 2) * k,
      y: height / 2 - (box.y + box.height / 2) * k,
    };
  }
  applyView();
}

function setupPanZoom() {
  const graph = $("graph");
  let drag = null;
  graph.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".gnode")) return;
    drag = { x: event.clientX, y: event.clientY, vx: state.view.x, vy: state.view.y };
    graph.setPointerCapture(event.pointerId);
    graph.classList.add("panning");
  });
  graph.addEventListener("pointermove", (event) => {
    if (!drag) return;
    state.view.x = drag.vx + event.clientX - drag.x;
    state.view.y = drag.vy + event.clientY - drag.y;
    applyView();
  });
  const end = () => {
    drag = null;
    graph.classList.remove("panning");
  };
  graph.addEventListener("pointerup", end);
  graph.addEventListener("pointercancel", end);
  graph.addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = graph.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const factor = Math.exp(-event.deltaY * 0.0015);
    const k = Math.min(4, Math.max(0.1, state.view.k * factor));
    // カーソルの下の点が動かないように拡大縮小する
    state.view.x = px - ((px - state.view.x) * k) / state.view.k;
    state.view.y = py - ((py - state.view.y) * k) / state.view.k;
    state.view.k = k;
    applyView();
  }, { passive: false });
}

// --- パラメータ（右） ----------------------------------------------------------

async function selectNode(path) {
  if (path !== state.selectedPath && hasEdits() && !confirm("適用していないパラメータの変更があります。破棄しますか？")) {
    return;
  }
  state.selectedPath = path;
  state.edits = {};
  for (const g of document.querySelectorAll(".gnode")) {
    g.classList.toggle("selected", g.dataset.path === path);
  }
  markTreeSelection();
  if (!path) {
    state.node = null;
    $("parm-view").hidden = true;
    $("parm-empty").hidden = false;
    return;
  }
  const node = await api(`/api/node?path=${encodeURIComponent(path)}`);
  showParms(node);
}

function setEdit(parm, index, value, row) {
  const comps = state.edits[parm.name] || new Array(parm.components.length).fill(undefined);
  const original = parm.components[index].value;
  comps[index] = value === original ? undefined : value;
  if (comps.every((v) => v === undefined)) delete state.edits[parm.name];
  else state.edits[parm.name] = comps;
  row.classList.toggle("dirty", parm.name in state.edits);
  updateParmButtons();
}

function updateParmButtons() {
  $("btn-apply").disabled = !hasEdits();
  $("btn-revert").disabled = !hasEdits();
}

function parmInput(parm, index, row) {
  const comp = parm.components[index];
  const locked = comp.locked;
  const onChange = (value) => setEdit(parm, index, value, row);

  switch (parm.type) {
    case "float":
    case "int": {
      const input = el("input", { type: "number", step: parm.type === "int" ? "1" : "any", value: comp.value, readonly: locked });
      input.addEventListener("change", () => {
        if (input.value === "") return;
        onChange(parm.type === "int" ? parseInt(input.value, 10) : parseFloat(input.value));
      });
      return input;
    }
    case "toggle": {
      const input = el("input", { type: "checkbox", disabled: locked });
      input.checked = comp.value;
      input.addEventListener("change", () => onChange(input.checked));
      return input;
    }
    case "menu": {
      const select = el("select", { disabled: locked });
      for (const item of parm.menu || []) {
        select.append(el("option", { value: item.value }, item.label || item.value));
      }
      select.value = comp.value;
      select.addEventListener("change", () => onChange(select.value));
      return select;
    }
    case "string": {
      // $HIP などが入っているときは、評価前の文字列を編集する
      const shown = comp.raw !== null && !locked ? comp.raw : comp.value;
      const input = el("input", { type: "text", value: shown, readonly: locked, spellcheck: "false" });
      if (parm.menu) {
        const listId = `menu-${parm.name}-${index}`;
        input.setAttribute("list", listId);
        row.append(el("datalist", { id: listId }, ...parm.menu.map((m) => el("option", { value: m.value }, m.label))));
      }
      input.addEventListener("change", () => {
        if (input.value !== shown) setEdit(parm, index, input.value, row);
        else onChange(comp.value);
      });
      return input;
    }
    default:
      return null;
  }
}

function parmRow(parm) {
  const row = el("div", { class: "parm-row" });
  row.classList.toggle("is-hidden", parm.hidden);
  row.classList.toggle("is-disabled", parm.disabled);
  row.append(el("div", { class: "parm-label", title: parm.name }, parm.label));

  const inputs = el("div", { class: "parm-inputs" });
  if (parm.type === "button") {
    inputs.append(el("span", { class: "muted small" }, "（ボタン）"));
  } else if (parm.type === "ramp" || parm.type === "other") {
    inputs.append(el("span", { class: "muted small" }, "（この種類は表示できません）"));
  } else {
    parm.components.forEach((_, i) => {
      const input = parmInput(parm, i, row);
      if (!input) return;
      const suffix = parm.components.length > 1 ? ` ${i + 1}` : "";
      input.setAttribute("aria-label", `${parm.label}${suffix}`);
      inputs.append(input);
    });
  }
  row.append(inputs);

  // エクスプレッションや、$HIP などを展開した値を下に出す
  parm.components.forEach((comp) => {
    if (comp.raw === null) return;
    if (comp.locked) {
      row.append(el("div", { class: "parm-note expr", title: "エクスプレッション／アニメーションが付いているので、ここでは変更できません" }, `ƒ ${comp.raw}`));
    } else if (parm.type === "string") {
      row.append(el("div", { class: "parm-note" }, `→ ${comp.value}`));
    }
  });
  return row;
}

function showParms(node) {
  state.node = node;
  state.edits = {};
  $("parm-empty").hidden = true;
  $("parm-view").hidden = false;
  $("parm-node-name").textContent = node.name;
  $("parm-node-type").textContent = `${node.typeLabel} (${node.category}/${node.type})  ${node.path}`;
  $("btn-render").hidden = !node.isRop;
  updateParmButtons();

  const showHidden = $("show-hidden").checked;
  const container = $("parms");
  container.replaceChildren();
  const groups = new Map();
  for (const parm of node.parms) {
    if (parm.hidden && !showHidden) continue;
    const key = parm.folders.join(" › ");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(parm);
  }
  for (const [folder, parms] of groups) {
    const group = el("div", { class: "parm-group" });
    if (folder) group.append(el("h3", {}, folder));
    for (const parm of parms) group.append(parmRow(parm));
    container.append(group);
  }
  if (!groups.size) container.append(el("div", { class: "muted pad" }, "表示できるパラメータがありません"));
}

async function applyEdits() {
  const values = {};
  for (const [name, comps] of Object.entries(state.edits)) {
    values[name] = comps.map((v) => (v === undefined ? null : v));
  }
  const result = await api("/api/parms", { path: state.node.path, values });
  for (const message of result.setErrors) log(message, "warn");
  log(`${state.node.path}: ${Object.keys(values).join(", ")} を変更しました`, "ok");
  showStatus(result.status);
  showParms(result);
  // フラグやエラーの表示が変わることがあるので、図も描き直す
  await showNetwork(state.networkPath, { fit: false });
}

async function renderRop() {
  if (hasEdits() && !confirm("適用していないパラメータの変更があります。変更前の状態で実行しますか？")) return;
  const path = state.node.path;
  log(`実行しています: ${path}`);
  $("btn-render").disabled = true;
  try {
    const result = await api("/api/render", { path });
    const level = result.ok ? "ok" : "error";
    log(`${result.ok ? "完了" : "失敗"}: ${path}（${result.elapsed} 秒）`, level);
    if (result.failure) log(result.failure, "error");
    for (const message of result.errors) log(message, "error");
    for (const message of result.warnings) log(message, "warn");
    for (const output of result.outputs) {
      log(`出力 ${output.parm}: ${output.path}${output.exists ? "" : "（ファイルが見つかりません）"}`, output.exists ? "" : "warn");
    }
    showStatus(result.status);
    await showNetwork(state.networkPath, { fit: false });
  } finally {
    $("btn-render").disabled = false;
  }
}

// --- 起動 ------------------------------------------------------------------

async function shutdown() {
  const message = state.status && state.status.unsaved
    ? "保存していない変更があります。破棄してサーバーを停止しますか？"
    : "サーバー（hython）を停止しますか？ライセンスが返されます";
  if (!confirm(message)) return;
  await api("/api/shutdown", {});
  $("stopped").hidden = false;
}

function setupEvents() {
  $("btn-open").addEventListener("click", guarded(openFileDialog));
  $("btn-save").addEventListener("click", guarded(async () => {
    if (state.status.isNewFile) return saveAs();
    await saveHip();
  }));
  const saveAs = async () => {
    const path = prompt("保存先のパス", state.status.isNewFile ? `${state.status.samplesDir}\\untitled.hip` : state.status.hipPath);
    if (path) await saveHip(path);
  };
  $("btn-save-as").addEventListener("click", guarded(saveAs));
  $("btn-shutdown").addEventListener("click", guarded(shutdown));

  $("btn-up").addEventListener("click", guarded(() => showNetwork(state.networkPath.replace(/\/[^/]+$/, "") || "/")));
  $("btn-fit").addEventListener("click", fitView);
  $("btn-reload").addEventListener("click", guarded(async () => {
    await refreshStatus();
    await loadTree();
    await showNetwork(state.networkPath, { fit: false });
    if (state.selectedPath) await selectNode(state.selectedPath);
  }));

  $("btn-apply").addEventListener("click", guarded(applyEdits));
  $("btn-revert").addEventListener("click", () => showParms(state.node));
  $("btn-render").addEventListener("click", guarded(renderRop));
  $("show-hidden").addEventListener("change", () => {
    if (state.node && (!hasEdits() || confirm("適用していない変更を破棄しますか？"))) showParms(state.node);
  });

  $("file-dir").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      guarded(browse)($("file-dir").value);
    }
  });

  window.addEventListener("beforeunload", (event) => {
    if (hasEdits()) event.preventDefault();
  });
}

async function init() {
  setupEvents();
  setupPanZoom();
  try {
    await refreshStatus();
    log(`接続しました: ${state.status.isNewFile ? "（新規）" : state.status.hipPath}`, "ok");
    await loadTree();
    await showNetwork("/obj");
  } catch (e) {
    log(e.message, "error");
  }
}

init();
