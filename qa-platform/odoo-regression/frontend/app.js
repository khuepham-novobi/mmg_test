/* Odoo Regression Test Runner — dashboard SPA (no build step).
   Views: #/ (tests) · #/run/<id> (live execution) · #/result/<id> (detail)
   · #/compare/<group> (Odoo 15 ↔ 19) · #/runs (history).
   All numbers come from the backend's persisted results — nothing is faked. */
"use strict";

const app = document.getElementById("app");
const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail;
    // 409 from /api/runs carries {message, active_run_id}
    if (detail && typeof detail === "object") {
      const err = new Error(detail.message || r.statusText);
      err.activeRunId = detail.active_run_id;
      throw err;
    }
    throw new Error(detail || r.statusText);
  }
  return r.json();
};
const chip = st => `<span class="status st-${esc(st || "NOTRUN").replace(" ", "")}">${esc(st || "NOT RUN")}</span>`;
const fmtMs = ms => ms == null ? "—" : (ms / 1000).toFixed(1) + "s";
let liveES = null;

/* ------------------------------------------------------- run helpers */
/* The selected environment is remembered across views so a RUN button is
   always one click. Every RUN posts to /api/runs — the same registered
   automation the runner executes, never ad-hoc code. */
const ENV_KEY = "qa.env";
const envGet = () => localStorage.getItem(ENV_KEY) || "odoo15";
const envSet = v => localStorage.setItem(ENV_KEY, v);

async function envPicker(id = "envpick") {
  const { environments } = await api("/api/environments");
  const cur = envGet();
  const opts = environments.map(e =>
    `<option value="${esc(e.key)}"${e.key === cur ? " selected" : ""}>
       ${esc(e.name)} — ${esc(e.db)}</option>`).join("");
  return `<label class="envsel">TARGET
    <select id="${id}">${opts}
      <option value="both"${cur === "both" ? " selected" : ""}>Compare Odoo 15 ↔ Odoo 19</option>
    </select></label>`;
}

function bindEnvPicker(id = "envpick") {
  const el = document.getElementById(id);
  if (el) el.onchange = () => envSet(el.value);
}

/** Start a run from any view. body = {features|test_ids|test_case_ids|scope}. */
async function startRun(body, buttonEl) {
  const environment = document.getElementById("envpick")?.value || envGet();
  envSet(environment);
  if (buttonEl) { buttonEl.disabled = true; buttonEl.textContent = "STARTING…"; }
  try {
    const res = await api("/api/runs", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ environment, ...body }) });
    location.hash = res.mode === "compare"
      ? `#/run/${res.run_ids[0]}?group=${res.group_id}`
      : `#/run/${res.run_ids[0]}`;
  } catch (err) {
    if (err.activeRunId) {
      if (confirm(err.message + " Open the run that is already in progress?"))
        location.hash = `#/run/${err.activeRunId}`;
    } else {
      alert("Could not start run: " + err.message);
    }
    if (buttonEl) { buttonEl.disabled = false; buttonEl.textContent = "▶ RUN"; }
  }
}

/* -------------------------------------------------- feature dashboard */
const PRIO = ["P0", "P1", "P2", "P3"];
const rollup = (m, keys) => keys.map(k =>
  m[k] ? `<span class="mini st-${esc(k).replace(" ", "")}">${m[k]} ${esc(k.replace("_", " "))}</span>` : "").join("");

async function viewFeatures() {
  const { features } = await api("/api/features");
  const tot = f => Object.values(f).reduce((a, b) => a + b, 0);
  const sum = key => features.reduce((a, f) => a + (f[key] || 0), 0);
  const sumMap = key => features.reduce((a, f) => {
    Object.entries(f[key] || {}).forEach(([k, v]) => a[k] = (a[k] || 0) + v);
    return a; }, {});
  const v19 = sumMap("v19"), v15 = sumMap("v15");
  const executedKeys = ["PASS", "FAIL", "BLOCKED", "ERROR"];

  app.innerHTML = `
    <h1>Feature Groups — FG-01 → FG-14 <span class="muted small">(workbook v3.0)</span></h1>
    <div class="panel row">
      ${await envPicker()}
      <div class="grow"></div>
      <button id="runAllFg">▶ RUN FG-01 → FG-14</button>
    </div>
    <div class="counters">
      <div class="counter"><b>${sum("total")}</b><span>test cases</span></div>
      <div class="counter"><b>${sum("automatable")}</b><span>automatable</span></div>
      <div class="counter c-run"><b>${sum("automated")}</b><span>automated</span></div>
      <div class="counter c-pass"><b>${v19.PASS || 0}</b><span>v19 pass</span></div>
      <div class="counter c-fail"><b>${(v19.FAIL || 0) + (v19.ERROR || 0)}</b><span>v19 fail/error</span></div>
      <div class="counter c-skip"><b>${v19.BLOCKED || 0}</b><span>v19 blocked</span></div>
      <div class="counter"><b>${sum("total") - executedKeys.reduce((a, k) => a + (v19[k] || 0), 0)}</b><span>v19 not run</span></div>
    </div>
    <div class="panel"><table class="matrix">
      <tr><th>Group</th><th>Feature</th><th>TCs</th><th>Priorities</th>
          <th>Automation coverage</th><th>Odoo 15</th><th>Odoo 19</th><th></th></tr>
      ${features.map(f => `
        <tr>
          <td class="mono"><a href="#/feature/${esc(f.feature_id)}">${esc(f.feature_id)}</a></td>
          <td><a href="#/feature/${esc(f.feature_id)}"><b>${esc(f.name)}</b></a>
              <div class="small muted">${esc((f.business_purpose || "").slice(0, 90))}</div></td>
          <td><b>${f.total}</b></td>
          <td class="small">${PRIO.map(p => f.priorities[p] ? `${p}:${f.priorities[p]}` : "").filter(Boolean).join(" ")}</td>
          <td>
            <div class="covbar" title="${f.automated}/${f.automatable} automatable TCs automated">
              <div style="width:${f.coverage_pct}%"></div></div>
            <span class="small muted">${f.automated}/${f.automatable} (${f.coverage_pct}%)
              · ${(f.automation_types.MANUAL || 0)} manual</span>
          </td>
          <td class="small">${rollup(f.v15, executedKeys) || "<span class='muted'>not run</span>"}</td>
          <td class="small">${rollup(f.v19, executedKeys) || "<span class='muted'>not run</span>"}</td>
          <td>${f.automated ? `<button class="secondary small runfeature"
                data-fg="${esc(f.feature_id)}">▶ RUN</button>` :
              `<span class="muted small" title="no registered automation yet">—</span>`}</td>
        </tr>`).join("")}
    </table></div>
    <p class="muted small">Counts come from the test-case registry
      (<span class="mono">data/test_registry.json</span>, synced read-only from the Excel
      workbook) joined with persisted execution results. Click a row for its test cases;
      RUN executes that feature's registered automation against the selected target.</p>`;

  bindEnvPicker();
  document.getElementById("runAllFg").onclick = e =>
    startRun({ scope: "in_scope", label: "FG-01→FG-14 regression suite" },
             e.currentTarget);
  document.querySelectorAll(".runfeature").forEach(b => b.onclick = e => {
    e.stopPropagation();
    startRun({ features: [b.dataset.fg], label: `${b.dataset.fg} suite` }, b);
  });
}

async function viewFeature(fgId) {
  const [{ test_cases }, { features }] = await Promise.all([
    api(`/api/testcases?feature=${encodeURIComponent(fgId)}`), api("/api/features")]);
  const f = features.find(x => x.feature_id === fgId) || {};
  app.innerHTML = `
    <a class="crumb" href="#/">← feature groups</a>
    <h1><span class="mono">${esc(fgId)}</span> ${esc(f.name || "")}</h1>
    <div class="panel small muted">${esc(f.business_purpose || "")}<br>
      <b>Modules:</b> ${esc(f.key_modules || "")} · <b>Roles:</b> ${esc(f.primary_roles || "")}</div>
    <div class="panel row">
      ${await envPicker()}
      <div class="grow"></div>
      <button id="runFeature">▶ RUN ${esc(fgId)}</button>
    </div>
    <div class="counters">
      <div class="counter"><b>${test_cases.length}</b><span>test cases</span></div>
      <div class="counter c-run"><b>${f.automated || 0}</b><span>automated</span></div>
      <div class="counter"><b>${f.automatable || 0}</b><span>automatable</span></div>
      <div class="counter"><b>${(f.automation_types || {}).MANUAL || 0}</b><span>manual</span></div>
    </div>
    <div class="panel"><table class="matrix">
      <tr><th>TC</th><th>Title</th><th>Prio</th><th>Automation</th>
          <th>Status</th><th>v15</th><th>v19</th><th>Last execution</th><th></th></tr>
      ${test_cases.map(t => `
        <tr>
          <td class="mono small"><a href="#/testcase/${esc(t.test_case_id)}">${esc(t.test_case_id)}</a></td>
          <td><a href="#/testcase/${esc(t.test_case_id)}">${esc(t.title)}</a></td>
          <td><span class="tag ${t.priority === "P0" ? "p0" : ""}">${esc(t.priority)}</span></td>
          <td class="small">${esc(t.automation_type)}</td>
          <td class="small muted">${esc(t.automation_status)}</td>
          <td>${chip(t.v15_status)}</td>
          <td>${chip(t.v19_status)}</td>
          <td class="mono small">${t.last_execution_id
              ? `<a href="#/result/${esc(t.last_execution_id)}">${esc(t.last_execution_id)}</a>`
              : "<span class='muted'>—</span>"}</td>
          <td style="white-space:nowrap">
            ${t.automated_test_ids.length
              ? `<button class="secondary small runtc" data-tc="${esc(t.test_case_id)}">▶ RUN</button>`
              : `<span class="muted small">—</span>`}
            <a href="#/testcase/${esc(t.test_case_id)}"><button class="secondary small">HISTORY</button></a>
          </td>
        </tr>`).join("")}
    </table></div>`;

  bindEnvPicker();
  document.getElementById("runFeature").onclick = e =>
    startRun({ features: [fgId], label: `${fgId} suite` }, e.currentTarget);
  document.querySelectorAll(".runtc").forEach(b => b.onclick = () =>
    startRun({ test_case_ids: [b.dataset.tc], label: b.dataset.tc }, b));
}

async function viewTestCase(tcId) {
  const t = await api(`/api/testcases/${encodeURIComponent(tcId)}`);
  const pre = s => `<div class="prebox">${esc(s || "—")}</div>`;
  const execs = (t.executions || []).map(e => `
    <tr>
      <td class="mono small">${esc(e.id)}</td>
      <td>${esc(e.env_name || e.environment)}</td>
      <td>${chip(e.canonical)}</td>
      <td class="small">${esc(e.failure_class || "")}</td>
      <td class="mono small">${fmtMs(e.duration_ms)}</td>
      <td class="small muted">${e.finished_at ? new Date(e.finished_at * 1000).toLocaleString() : "—"}</td>
      <td><a href="#/result/${esc(e.id)}"><button class="secondary small">EVIDENCE</button></a></td>
    </tr>`).join("");

  app.innerHTML = `
    <a class="crumb" href="#/feature/${esc(t.feature_id)}">← ${esc(t.feature_id)} ${esc(t.feature_name)}</a>
    <h1><span class="mono">${esc(t.test_case_id)}</span> ${esc(t.title)}</h1>
    <div class="panel row">
      ${await envPicker()}
      <div class="grow"></div>
      ${t.automated_test_ids.length
        ? `<button id="runTc">▶ RUN ${esc(t.test_case_id)}</button>`
        : `<span class="muted small">No registered automation for this test case
             (${esc(t.automation_status)}) — nothing to run yet.</span>`}
    </div>
    <div class="panel row">
      <div><span class="muted small">PRIORITY</span><br><b>${esc(t.priority)}</b></div>
      <div><span class="muted small">TYPE</span><br>${esc(t.test_type)}</div>
      <div><span class="muted small">ROLE</span><br>${esc(t.role || "—")}</div>
      <div><span class="muted small">SUITE</span><br>${esc(t.suite || "—")}</div>
      <div><span class="muted small">PHASE</span><br>${esc(t.execution_phase || "—")}</div>
      <div class="grow"></div>
      <div><span class="muted small">ODOO 15</span><br>${chip(t.v15_status)}</div>
      <div><span class="muted small">ODOO 19</span><br>${chip(t.v19_status)}</div>
    </div>
    <div class="panel">
      <h2 style="margin-top:0">Automation</h2>
      <div class="row">
        <div><span class="muted small">TYPE</span><br><b>${esc(t.automation_type)}</b></div>
        <div><span class="muted small">STATUS</span><br>${esc(t.automation_status)}</div>
        <div><span class="muted small">WAVE (workbook)</span><br>${esc(t.automation_wave || "—")}</div>
      </div>
      <p class="small muted">Workbook approach: ${esc(t.automation_approach || "—")}</p>
      ${t.automated_test_ids.length ? `<p class="small">Automated by:
        <b>${t.automated_test_ids.map(esc).join(", ")}</b></p>` : ""}
      ${t.related_test_ids.length ? `<p class="small muted">Related automation:
        ${t.related_test_ids.map(esc).join(", ")}</p>` : ""}
    </div>
    <div class="panel"><h2 style="margin-top:0">User story</h2>${pre(t.description)}</div>
    <div class="panel"><h2 style="margin-top:0">Preconditions</h2>${pre(t.preconditions)}</div>
    <div class="panel"><h2 style="margin-top:0">Steps</h2>${pre(t.steps)}</div>
    <div class="panel"><h2 style="margin-top:0">Expected result
      <span class="muted small">(verbatim from workbook — source of truth)</span></h2>
      ${pre(t.expected_result)}</div>
    ${t.v19_watch ? `<div class="panel"><h2 style="margin-top:0">v19 watch</h2>${pre(t.v19_watch)}</div>` : ""}
    <div class="panel"><h2 style="margin-top:0">Execution history
      <span class="muted small">(every run of this test case, newest first)</span></h2>
      <table class="matrix"><tr><th>Execution</th><th>Environment</th><th>Status</th>
        <th>Failure class</th><th>Duration</th><th>Finished</th><th></th></tr>
        ${execs || "<tr><td colspan=7 class='muted'>no executions yet</td></tr>"}</table></div>
    <div class="panel small muted">Source: ${esc(t.source_workbook)} ·
      sheet “${esc(t.source_sheet)}” row ${esc(t.source_row)}
      ${t.test_execution_row ? ` · “Test Execution” row ${esc(t.test_execution_row)}` : ""}
      ${t.automated_test_ids.length ? ` · automation: <span class="mono">${
        t.automated_test_ids.map(esc).join(", ")}</span>` : ""}</div>`;

  bindEnvPicker();
  const runBtn = document.getElementById("runTc");
  if (runBtn) runBtn.onclick = e =>
    startRun({ test_case_ids: [tcId], label: tcId }, e.currentTarget);
}

/* ------------------------------------------------------------ dashboard */
async function viewDashboard() {
  const [{ tests }, { environments }] = await Promise.all([
    api("/api/tests"), api("/api/environments")]);
  const envOptions = environments.map(e =>
    `<label><input type="radio" name="env" value="${esc(e.key)}"> ${esc(e.name)}
      <span class="muted small mono">${esc(e.base_url)} · ${esc(e.db)}</span></label>`
  ).join("") +
    `<label><input type="radio" name="env" value="both"> Compare Odoo 15 ↔ Odoo 19</label>`;

  app.innerHTML = `
    <h1>Test Cases</h1>
    <div class="panel envpick" id="envpick">
      <div class="muted small" style="margin-bottom:8px">ENVIRONMENT</div>
      ${envOptions}
    </div>
    <div class="panel">
      <div class="row" style="margin-bottom:6px">
        <label class="muted small"><input type="checkbox" id="selall"> select all</label>
        <div class="grow"></div>
        <button id="runSelected" class="secondary">▶ RUN SELECTED</button>
        <button id="runAll">▶ RUN ALL</button>
      </div>
      <div id="testlist"></div>
    </div>`;

  const list = document.getElementById("testlist");
  list.innerHTML = tests.map(t => {
    const latest = Object.entries(t.latest || {}).map(([env, l]) =>
      `<a href="#/result/${esc(l.result_id)}" title="latest on ${esc(env)}">
         <span class="tag">${esc(env)}</span>${chip(l.status)}</a>`).join(" ") || chip("NOT RUN");
    const trace = (t.traceability?.tc_ids || []).join(", ");
    return `<div class="testcard">
      <input type="checkbox" class="sel" value="${esc(t.id)}">
      <div class="grow">
        <div class="tc-id">${esc(t.id)}${trace ? ` · <span title="Excel traceability">${esc(trace)}</span>` : ""}</div>
        <div class="tc-name">${esc(t.name)}</div>
        <div class="tc-desc">${esc(t.description)}</div>
        <div class="tags">
          <span class="tag">${esc(t.workflow_name || t.workflow)}</span>
          <span class="tag ${t.priority === "P0" ? "p0" : ""}">${esc(t.priority)}</span>
          <span class="tag kind${esc(t.kind)}">${esc(t.kind)}</span>
          <span class="tag">${esc(t.module)}</span>
        </div>
      </div>
      <div style="text-align:right">${latest}<br>
        <button class="secondary small runone" data-id="${esc(t.id)}"
                style="margin-top:8px">▶ RUN</button></div>
    </div>`;
  }).join("");

  const envSel = () => document.querySelector("input[name=env]:checked")?.value;
  document.querySelectorAll("#envpick label").forEach(l =>
    l.addEventListener("click", () => setTimeout(() => {
      document.querySelectorAll("#envpick label").forEach(x =>
        x.classList.toggle("active", x.querySelector("input").checked));
    })));
  document.getElementById("selall").onchange = e =>
    document.querySelectorAll(".sel").forEach(c => c.checked = e.target.checked);

  async function start(ids) {
    const environment = envSel();
    if (!environment) { alert("Pick an environment first (Odoo 15, Odoo 19 or Compare)."); return; }
    try {
      const res = await api("/api/runs", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ environment, test_ids: ids }) });
      location.hash = res.mode === "compare"
        ? `#/run/${res.run_ids[0]}?group=${res.group_id}`
        : `#/run/${res.run_ids[0]}`;
    } catch (err) { alert("Could not start run: " + err.message); }
  }
  document.getElementById("runAll").onclick = () => start(null);
  document.getElementById("runSelected").onclick = () => {
    const ids = [...document.querySelectorAll(".sel:checked")].map(c => c.value);
    if (!ids.length) { alert("Select at least one test."); return; }
    start(ids);
  };
  document.querySelectorAll(".runone").forEach(b =>
    b.onclick = () => start([b.dataset.id]));
}

/* ------------------------------------------------------------- live run */
async function viewRun(runId, groupId) {
  const run = await api(`/api/runs/${runId}`);
  const results = {};
  (run.results || []).forEach(r => results[r.test_id] = r);

  app.innerHTML = `
    <a class="crumb" href="#/">← tests</a>
    <h1>Run <span class="mono">${esc(runId)}</span>
        <span id="runstatus">${chip(run.status)}</span></h1>
    <div class="panel">
      <div class="row">
        <div><span class="muted small">ENVIRONMENT</span><br><b>${esc(run.env_name)}</b></div>
        <div><span class="muted small">MODE</span><br><b>${esc(run.mode)}</b></div>
        <div class="grow"></div>
        ${groupId ? `<a href="#/compare/${esc(groupId)}"><button class="secondary">15 ↔ 19 COMPARISON</button></a>` : ""}
        <button class="danger" id="cancel">✕ CANCEL</button>
      </div>
      <div class="counters" id="counters"></div>
      <div class="progress"><div id="bar" style="width:0%"></div></div>
      <div class="pct" id="pct">0%</div>
      <div class="current" id="current" style="display:none"></div>
    </div>
    <div class="panel"><h2 style="margin-top:0">Tests</h2><div id="results"></div></div>
    <h2>Live log</h2><div class="livelog" id="livelog"></div>`;

  document.getElementById("cancel").onclick = () =>
    api(`/api/runs/${runId}/cancel`, { method: "POST" });

  const state = { total: run.total || (run.results || []).length,
                  done: 0, passed: run.passed || 0, failed: run.failed || 0,
                  skipped: run.skipped || 0, errors: run.errors || 0,
                  blocked: run.blocked || 0,
                  status: run.status, running: null };

  function renderCounters() {
    const pending = Math.max(0, state.total - state.done - (state.running ? 1 : 0));
    document.getElementById("counters").innerHTML = `
      <div class="counter"><b>${state.done} / ${state.total}</b><span>tests done</span></div>
      <div class="counter c-pass"><b>${state.passed}</b><span>passed</span></div>
      <div class="counter c-fail"><b>${state.failed + state.errors}</b><span>failed / error</span></div>
      <div class="counter c-skip"><b>${state.skipped}</b><span>skipped</span></div>
      <div class="counter"><b>${state.blocked}</b><span>blocked</span></div>
      <div class="counter c-run"><b>${state.running ? 1 : 0}</b><span>running</span></div>
      <div class="counter"><b>${pending}</b><span>pending</span></div>`;
    const pct = state.total ? Math.round(100 * state.done / state.total) : 0;
    document.getElementById("bar").style.width = pct + "%";
    document.getElementById("pct").textContent = pct + "%";
  }

  function renderResults() {
    document.getElementById("results").innerHTML =
      Object.values(results).map(r => `
        <div class="runrow">
          <div class="grow">
            <span class="tc-id">${esc(r.test_id)}</span>
            <b>${esc(r.name)}</b>
            ${r.failed_step ? `<div class="small muted">failed step: ${esc(r.failed_step)}</div>` : ""}
            ${r.error ? `<div class="small" style="color:var(--fail)">${esc(r.error)}</div>` : ""}
            ${r.skip_reason ? `<div class="small muted">skip: ${esc(r.skip_reason)}</div>` : ""}
          </div>
          <span class="muted mono small">${fmtMs(r.duration_ms)}</span>
          ${chip(r.status)}
          ${r.id ? `<a href="#/result/${esc(r.id)}"><button class="secondary">DETAILS</button></a>` : ""}
        </div>`).join("");
  }

  const logEl = document.getElementById("livelog");
  const pushLog = line => {
    logEl.textContent += line + "\n";
    logEl.scrollTop = logEl.scrollHeight;
  };

  renderCounters(); renderResults();

  if (liveES) liveES.close();
  liveES = new EventSource(`/api/runs/${runId}/events`);
  liveES.onmessage = () => {};
  const on = (type, fn) => liveES.addEventListener(type, e =>
    fn(JSON.parse(e.data).payload, JSON.parse(e.data)));

  on("RUN_STARTED", p => { state.total = p.total; state.status = "RUNNING";
    document.getElementById("runstatus").innerHTML = chip("RUNNING");
    pushLog(`▶ RUN ${runId} started on ${p.env_name} (${p.total} tests)`);
    renderCounters(); });
  on("TEST_STARTED", p => {
    state.running = p.test_id;
    results[p.test_id] = { ...(results[p.test_id] || {}), test_id: p.test_id,
      name: p.name, id: p.result_id, status: "RUNNING" };
    document.getElementById("current").style.display = "";
    document.getElementById("current").innerHTML =
      `<b>${esc(p.test_id)}</b> — ${esc(p.name)} <span class="muted">(test ${p.index}/${p.total})</span>`;
    pushLog(`● TEST_STARTED ${p.test_id} — ${p.name}`);
    renderCounters(); renderResults(); });
  on("STEP_STARTED", p => {
    document.getElementById("current").innerHTML =
      `<b>${esc(p.test_id)}</b><br><span class="muted">step ${p.index}:</span> ${esc(p.name)}…`;
    pushLog(`  → step ${p.index}: ${p.name}`); });
  on("STEP_PASSED", p => pushLog(`  ✓ step ${p.index} (${fmtMs(p.duration_ms)})`));
  on("STEP_FAILED", p => pushLog(`  ✗ step ${p.index}: ${p.error}`));
  on("STEP_SKIPPED", p => pushLog(`  ⏭ step ${p.index}: ${p.reason}`));
  on("ASSERTION", p => pushLog(`  ${p.passed ? "✓" : "✗"} assert ${p.name}: expected ${p.expected}, got ${p.actual}`));
  on("LOG", p => pushLog("    " + p.message));
  const testDone = (p, st) => {
    state.running = null; state.done = (p.done ?? state.done + 1);
    state.passed = p.passed; state.failed = p.failed;
    state.skipped = p.skipped; state.errors = p.errors;
    state.blocked = p.blocked ?? state.blocked;
    results[p.test_id] = { ...(results[p.test_id] || {}), test_id: p.test_id,
      id: p.result_id, status: st, duration_ms: p.duration_ms,
      error: p.error, failed_step: p.failed_step, skip_reason: p.skip_reason,
      name: (results[p.test_id] || {}).name };
    pushLog(`■ ${st} ${p.test_id}${p.error ? " — " + p.error : ""}`);
    renderCounters(); renderResults();
  };
  on("TEST_PASSED", p => testDone(p, "PASSED"));
  on("TEST_FAILED", p => testDone(p, "FAILED"));
  on("TEST_SKIPPED", p => testDone(p, "SKIPPED"));
  on("TEST_BLOCKED", p => testDone(p, "BLOCKED"));
  on("TEST_ERROR", p => testDone(p, "ERROR"));
  on("RUN_COMPLETED", p => {
    state.status = p.status;
    document.getElementById("runstatus").innerHTML = chip(p.status);
    document.getElementById("current").style.display = "none";
    pushLog(`✔ RUN_COMPLETED — ${p.passed} passed, ${p.failed} failed, `
      + `${p.skipped} skipped, ${p.errors} errors in ${fmtMs(p.duration_ms)}`);
    if (groupId) {
      api(`/api/compare/${groupId}`).then(c => {
        if (c.runs.length >= 2 && c.runs.every(r =>
            ["COMPLETED", "CANCELLED"].includes(r.status)))
          location.hash = `#/compare/${groupId}`;
        else {
          const next = c.runs.find(r => r.status !== "COMPLETED");
          if (next && next.id !== runId)
            location.hash = `#/run/${next.id}?group=${groupId}`;
        }
      }).catch(() => {});
    }
    renderCounters(); });
  on("STREAM_END", () => liveES && liveES.close());
}

/* -------------------------------------------------------- result detail */
async function viewResult(resultId) {
  const r = await api(`/api/results/${resultId}`);
  const t = r.traceability || {};
  const steps = r.steps.map(s => `
    <li><span class="stepmark ${s.status === "PASSED" ? "ok" : s.status === "SKIPPED" ? "muted" : "ko"}">
      ${s.status === "PASSED" ? "✓" : s.status === "FAILED" ? "✗" : s.status === "SKIPPED" ? "⏭" : "…"}</span>
      <span class="grow">${esc(s.name)}</span>
      <span class="muted mono small">${fmtMs(s.duration_ms)}</span>
      ${s.error ? `<span class="small" style="color:var(--fail)">${esc(s.error)}</span>` : ""}</li>`).join("");
  const asserts = r.assertions.map(a => `
    <tr><td class="${a.passed ? "ok" : "ko"}">${a.passed ? "✓" : "✗"}</td>
      <td>${esc(a.name)}</td><td class="mono">${esc(a.expected)}</td>
      <td class="mono">${esc(a.actual)}</td></tr>`).join("");
  const shots = r.artifacts.filter(a => a.type === "screenshot");
  const others = r.artifacts.filter(a => a.type !== "screenshot");

  app.innerHTML = `
    <a class="crumb" href="#/run/${esc(r.run_id)}">← run ${esc(r.run_id)}</a>
    <h1><span class="mono">${esc(r.test_id)}</span> ${chip(r.status)}</h1>
    <div class="panel row">
      <div><span class="muted small">TEST</span><br><b>${esc(r.name)}</b></div>
      <div><span class="muted small">WORKFLOW</span><br>${esc(r.workflow)}</div>
      <div><span class="muted small">ENVIRONMENT</span><br>${esc(r.run?.env_name || "")}</div>
      <div><span class="muted small">DURATION</span><br>${fmtMs(r.duration_ms)}</div>
      <div><span class="muted small">KIND</span><br>${esc(r.kind)}</div>
    </div>
    ${r.status === "FAILED" || r.status === "ERROR" ? `
      <div class="panel">
        <h2 style="margin-top:0">Failure</h2>
        ${r.failed_step ? `<p>Failed step: <b>${esc(r.failed_step)}</b></p>` : ""}
        ${r.expected || r.actual ? `
        <div class="expected-actual">
          <div class="panel"><span class="muted small">EXPECTED</span>
            <div class="mono">${esc(r.expected)}</div></div>
          <div class="panel"><span class="muted small">ACTUAL</span>
            <div class="mono">${esc(r.actual)}</div></div>
        </div>` : ""}
        <div class="errbox" style="margin-top:10px">${esc(r.error)}</div>
      </div>` : ""}
    ${r.skip_reason ? `<div class="panel"><h2 style="margin-top:0">Skipped</h2>
      <p>${esc(r.skip_reason)}</p></div>` : ""}
    <div class="panel"><h2 style="margin-top:0">Steps</h2>
      <ul class="steps">${steps || "<li class='muted'>no steps recorded</li>"}</ul></div>
    <div class="panel"><h2 style="margin-top:0">Assertions</h2>
      <table class="matrix"><tr><th></th><th>Assertion</th><th>Expected</th>
      <th>Actual</th></tr>${asserts || "<tr><td colspan=4 class='muted'>none</td></tr>"}</table></div>
    <div class="panel"><h2 style="margin-top:0">Artifacts</h2>
      <div class="artifacts">${others.map(a =>
        `<a href="/api/artifacts/${a.id}" target="_blank">📄 ${esc(a.name)}</a>`).join("") || ""}
      </div>
      ${shots.map(a => `<p class="muted small">${esc(a.name)}</p>
        <img class="shot" src="/api/artifacts/${a.id}" loading="lazy">`).join("")}
    </div>
    <div class="panel"><h2 style="margin-top:0">Excel traceability</h2>
      <div class="tracebox">
        <div><span class="muted">Workbook test cases:</span>
          <b>${esc((t.tc_ids || []).join(", ") || "—")}</b></div>
        <div><span class="muted">Feature:</span> ${esc(t.feature || "—")}</div>
        <div><span class="muted">User story:</span> ${esc(t.user_story || "—")}</div>
        <div class="small muted" style="margin-top:6px">${esc(t.source || "")}</div>
      </div></div>`;
}

/* -------------------------------------------------------------- compare */
async function viewCompare(groupId) {
  const c = await api(`/api/compare/${groupId}`);
  const running = c.runs.some(r => !["COMPLETED", "CANCELLED"].includes(r.status));
  const head = c.envs.map(e => `<th>${esc(e)}</th>`).join("");
  const CLS_STYLE = { SAME_BEHAVIOR: "var(--pass)", REGRESSION_CANDIDATE: "var(--fail)",
    FIXED: "var(--run)", SAME_FAILURE: "var(--err)", BLOCKED: "#d29bff",
    NOT_COMPARED: "var(--muted)" };
  const rows = c.tests.map(t => {
    const cells = c.envs.map(e => {
      const cell = t.by_env[e];
      return `<td>${cell ? `<a href="#/result/${esc(cell.result_id)}">${chip(cell.status)}</a>` : chip("NOT RUN")}</td>`;
    }).join("");
    const cls = t.classification || "";
    return `<tr class="${t.regression ? "regression" : ""}">
      <td><span class="tc-id">${esc(t.test_id)}</span><br>${esc(t.name)}</td>
      ${cells}<td><b style="color:${CLS_STYLE[cls] || "var(--muted)"}">${esc(cls.replace(/_/g, " "))}</b>
      ${cls === "REGRESSION_CANDIDATE" ? "<div class='small muted'>needs failure triage</div>" : ""}</td></tr>`;
  }).join("");
  const runLinks = c.runs.map(r =>
    `<a href="#/run/${esc(r.id)}?group=${esc(groupId)}">${esc(r.env_name)} ${chip(r.status)}</a>`).join(" · ");

  app.innerHTML = `
    <a class="crumb" href="#/">← tests</a>
    <h1>Comparison <span class="mono">${esc(groupId)}</span></h1>
    <div class="panel row">${runLinks}
      <div class="grow"></div>
      <div class="counter c-fail"><b>${c.regressions.length}</b><span>regressions</span></div>
    </div>
    ${running ? `<div class="panel muted">Still running — this page refreshes automatically.</div>` : ""}
    <div class="panel"><table class="matrix">
      <tr><th>Test</th>${head}<th>Classification</th></tr>${rows}</table></div>`;
  if (running) setTimeout(() => {
    if (location.hash.includes(groupId)) viewCompare(groupId);
  }, 2500);
}

/* ---------------------------------------------------------- run history */
async function viewRuns() {
  const { runs } = await api("/api/runs");
  app.innerHTML = `<h1>Run history</h1><div class="panel">` +
    (runs.map(r => `<div class="runrow">
        <span class="mono">${esc(r.id)}</span>
        <span>${esc(r.env_name)}</span>
        <span class="muted small">${new Date(r.started_at * 1000).toLocaleString()}</span>
        <div class="grow"></div>
        <span class="muted small">✓${r.passed} ✗${r.failed + r.errors} ⏭${r.skipped}</span>
        ${chip(r.status)}
        ${r.group_id ? `<a href="#/compare/${esc(r.group_id)}"><button class="secondary">COMPARE</button></a>` : ""}
        <a href="#/run/${esc(r.id)}${r.group_id ? `?group=${esc(r.group_id)}` : ""}"><button class="secondary">OPEN</button></a>
      </div>`).join("") || "<p class='muted'>No runs yet.</p>") + `</div>`;
}

/* --------------------------------------------------------------- router */
async function route() {
  if (liveES) { liveES.close(); liveES = null; }
  const [path, query] = location.hash.slice(2).split("?");
  const q = new URLSearchParams(query || "");
  const parts = (path || "").split("/").filter(Boolean);
  try {
    if (!parts.length) await viewFeatures();
    else if (parts[0] === "tests") await viewDashboard();
    else if (parts[0] === "feature") await viewFeature(parts[1]);
    else if (parts[0] === "testcase") await viewTestCase(parts[1]);
    else if (parts[0] === "run") await viewRun(parts[1], q.get("group"));
    else if (parts[0] === "result") await viewResult(parts[1]);
    else if (parts[0] === "compare") await viewCompare(parts[1]);
    else if (parts[0] === "runs") await viewRuns();
    else await viewFeatures();
  } catch (err) {
    app.innerHTML = `<div class="panel errbox">Error: ${esc(err.message)}</div>`;
  }
}
window.addEventListener("hashchange", route);
route();
