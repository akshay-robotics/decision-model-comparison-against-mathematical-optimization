"use strict";

const element = (id) => document.getElementById(id);
const canvas = element("canvas");
const ctx = canvas.getContext("2d");
const state = { replay: null, replays: new Map(), index: 0, playing: false, busy: false, fraction: 0, lastTick: 0 };
const controllerNames = { fixed: "Fixed time", adaptive: "Gap adaptive", gurobi: "Gurobi signal MILP", microsoft: "Microsoft-Decision-1", jev: "Jev 1.13", luna: "GPT-6 Luna Decisions", "sol-medium": "GPT-6.1 Sol · medium reasoning" };
const inputIds = ["controller", "seed", "inflow", "cav", "horizon"];
const optimizationData = JSON.parse(element("optimization-data").textContent);
const scoresOnly = new URLSearchParams(window.location.search).get("scores") === "1";
let optimizationKey = null;
let optimizationRuns = [];
let optimizationAttempts = [];

function scoreNumber(value) {
  return Number.isFinite(value) ? value.toFixed(2) : "Unavailable";
}

function showOptimizationAttempt() {
  const row = optimizationAttempts.find((item) => item.identity === element("optimization-case").value);
  const dataset = optimizationRuns.find((item) => item.identity === element("optimization-run").value);
  const fullPlan = row?.mode === "full-plan";
  element("optimization-score-label").textContent = fullPlan || !row ? "Independent plan score" : "First-action regret";
  element("optimization-score").textContent = scoreNumber(row?.score);
  element("optimization-gap").textContent = fullPlan ? scoreNumber(row.objective_gap) : "N/A";
  element("optimization-validity").textContent = !row ? "N/A" : row.valid
    ? (fullPlan ? "Feasible plan" : "Legal action") : "Failed";
  element("optimization-reference").textContent = !row ? "N/A" : row.reference_certified ? "Certified" : "Unproven";
  element("optimization-source").textContent = row
    ? `${controllerNames[row.controller] || row.controller} · ${row.horizon} s horizon · ${row.case_id} · attempt ${row.repeat + 1} · ${dataset.name}`
    : "No saved optimization benchmark matches this controller, horizon, and objective version.";
  element("optimization-explanation").textContent = !row
    ? "A traffic replay alone cannot supply a full-plan optimization score. No benchmark is run automatically."
    : row.error || (fullPlan
      ? "Independently recomputed from the saved full plan: summed end-of-second queues + 0.5 per switch. The gap is extra cost above the certified optimum. These are objective units, not seconds of travel."
      : "Extra objective cost caused by the first choice, assuming the best possible continuation. Zero means an optimal first choice. No full plan was returned, so a full-plan score and plan gap are unavailable.");
  element("optimization-updated").textContent = optimizationData.exported_at
    ? `Saved benchmark snapshot: ${new Date(optimizationData.exported_at).toLocaleString()}. Compare the same case, horizon, and benchmark run.` : "";
}

function selectOptimizationRun() {
  const dataset = optimizationRuns.find((item) => item.identity === element("optimization-run").value);
  const result = scoresOnly ? { controller: element("controller").value,
    config: { planning_horizon: Number(element("horizon").value) } } : state.replay?.result;
  optimizationAttempts = dataset && result ? dataset.attempts.filter((row) =>
    row.controller === result.controller && row.horizon === (result.config.planning_horizon ?? 15)) : [];
  const select = element("optimization-case");
  select.replaceChildren(...optimizationAttempts.map((row) =>
    new Option(`${row.case_id} · attempt ${row.repeat + 1}`, row.identity)));
  select.disabled = optimizationAttempts.length === 0;
  showOptimizationAttempt();
}

function renderOptimization(result) {
  const horizon = result.config.planning_horizon ?? 15;
  const objectiveVersion = result.planning_objective?.version ?? "end-step-queues-plus-switches-v1";
  const key = `${result.controller}:${horizon}:${objectiveVersion}`;
  if (key === optimizationKey) return;
  optimizationKey = key;
  const previous = element("optimization-run").value;
  optimizationRuns = optimizationData.datasets.filter((dataset) =>
    (dataset.objective?.version ?? "end-step-queues-plus-switches-v1") === objectiveVersion && dataset.attempts.some((row) =>
    row.controller === result.controller && row.horizon === horizon));
  // Prefer a full-plan score when available; otherwise use the broadest saved
  // first-action dataset. Every selected dataset and case remains explicit.
  optimizationRuns.sort((a, b) => Number(b.mode === "full-plan") - Number(a.mode === "full-plan")
    || b.attempts.length - a.attempts.length);
  const select = element("optimization-run");
  select.replaceChildren(...optimizationRuns.map((dataset) =>
    new Option(`${dataset.name} · ${dataset.mode}`, dataset.identity)));
  if (optimizationRuns.some((dataset) => dataset.identity === previous)) select.value = previous;
  select.disabled = optimizationRuns.length === 0;
  selectOptimizationRun();
}

element("optimization-run").addEventListener("change", selectOptimizationRun);
element("optimization-case").addEventListener("change", showOptimizationAttempt);
const query = new URLSearchParams(window.location.search);
const savedOnly = query.get("saved") === "1";
if (query.has("controller") && Object.hasOwn(controllerNames, query.get("controller"))) {
  element("controller").value = query.get("controller");
} else if (query.get("models") === "5") {
  element("controller").value = "gurobi";
}
const requestedHorizon = Number(query.get("horizon"));
if (Number.isInteger(requestedHorizon) && requestedHorizon >= 1 && requestedHorizon <= 600) {
  element("horizon").value = requestedHorizon;
}
if (savedOnly) {
  element("generate").textContent = "Load replay";
  element("generate").closest("section").querySelector("h2").textContent = "Recorded horizon comparison";
  element("generate").closest("section").querySelector("p.note").textContent =
    "Saved traffic runs for the current objective. Choose a controller and an available planning horizon, then load its recording. Viewing saved replays makes no model calls.";
  for (const id of ["seed", "inflow", "cav"]) element(id).disabled = true;
}

function parameters() {
  return {
    controller: element("controller").value,
    seed: Number(element("seed").value),
    inflow: Number(element("inflow").value),
    cav_share: Number(element("cav").value),
    duration: 120,
    horizon: Number(element("horizon").value),
    saved_only: savedOnly,
  };
}

function cacheKey(values) {
  return JSON.stringify(values);
}

function status(message, error = false) {
  element("status").textContent = message;
  element("status").classList.toggle("error", error);
}

function draw(frame) {
  const { width, height } = canvas;
  const cx = width / 2;
  const cy = height / 2;
  const scale = 2.8;
  ctx.fillStyle = "#10283b";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#1d394b";
  for (let x = 16; x < width; x += 54) {
    for (let y = 16; y < height; y += 54) ctx.fillRect(x, y, 2, 2);
  }
  ctx.fillStyle = "#314758";
  ctx.fillRect(cx - 24, 0, 48, height);
  ctx.fillRect(0, cy - 24, width, 48);
  ctx.fillStyle = "#415a6a";
  ctx.fillRect(cx - 24, cy - 24, 48, 48);
  ctx.strokeStyle = "#a7bac6";
  ctx.lineWidth = 2;
  ctx.setLineDash([12, 10]);
  ctx.beginPath();
  ctx.moveTo(cx, 0);
  ctx.lineTo(cx, cy - 24);
  ctx.moveTo(cx, cy + 24);
  ctx.lineTo(cx, height);
  ctx.moveTo(0, cy);
  ctx.lineTo(cx - 24, cy);
  ctx.moveTo(cx + 24, cy);
  ctx.lineTo(width, cy);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#83a8bd";
  ctx.font = "bold 13px system-ui";
  ctx.fillText("N", cx - 5, 29);
  ctx.fillText("S", cx - 5, height - 17);
  ctx.fillText("W", 20, cy - 34);
  ctx.fillText("E", width - 29, cy - 34);

  if (!frame) return;
  const labels = {
    NS: ["North–South green", "#58dca2"],
    EW: ["East–West green", "#58dca2"],
    YELLOW: ["Yellow clearance", "#f9c36b"],
    ALL_RED: ["All red", "#ed7480"],
  };
  const [label, color] = labels[frame.signal] || [frame.signal, "#ed7480"];
  element("signal").textContent = label;
  element("signal").style.borderColor = color;
  for (const vehicle of frame.vehicles) {
    const x = cx + (vehicle.x - 100) * scale;
    const y = cy - (vehicle.y - 100) * scale;
    ctx.beginPath();
    ctx.arc(x, y, 5.5, 0, Math.PI * 2);
    ctx.fillStyle = vehicle.kind === "CAV" ? "#faaf55" : "#70affa";
    ctx.shadowColor = ctx.fillStyle;
    ctx.shadowBlur = 6;
    ctx.fill();
    ctx.shadowBlur = 0;
  }
}

function render() {
  if (!state.replay || !state.replay.frames.length) {
    draw(null);
    return;
  }
  const frame = state.replay.frames[state.index];
  const result = state.replay.result;
  renderOptimization(result);
  element("scrub").value = state.index;
  element("clock").textContent = `${frame.time.toFixed(1)} s · ${frame.vehicles.length} active · ${frame.completed} completed`;
  element("duration").textContent = `${result.config.duration.toFixed(1)} s`;
  element("completed").textContent = result.completed;
  element("completion-demand").textContent = `of ${result.generated} generated · at cutoff`;
  element("completion-score").textContent = result.generated > 0
    ? `${(100 * result.completed / result.generated).toFixed(1)}%` : "N/A";
  const evaluation = result.evaluation;
  const unfinished = result.generated - result.completed;
  element("unfinished").textContent = unfinished;
  element("system-time").textContent = evaluation?.mean_time_in_system == null
    ? "Unavailable" : `${evaluation.mean_time_in_system.toFixed(1)} s`;
  const approaches = evaluation?.by_approach;
  element("approach-completion").textContent = approaches
    ? `Completed by approach: ${Object.entries(approaches).map(([name, counts]) => `${name} ${counts.completed}/${counts.generated}`).join(" · ")}`
    : "Approach completion unavailable for this saved run.";
  const unserved = approaches ? Object.entries(approaches)
    .filter(([, counts]) => counts.generated > 0 && counts.completed === 0).map(([name]) => name) : [];
  element("outcome-warning").textContent = unfinished > 0
    ? `${unfinished} cars unfinished at cutoff. ${unserved.length ? `No completed trips from ${unserved.join(" / ")}. ` : ""}Completed-only averages exclude them.`
    : "";
  element("travel").textContent = result.mean_travel_time == null ? "—" : `${result.mean_travel_time.toFixed(1)} s`;
  element("wait").textContent = result.mean_waiting_time == null ? "—" : `${result.mean_waiting_time.toFixed(1)} s`;
  element("backlog").textContent = result.entry_backlog;
  element("collisions").textContent = result.colliding_vehicles;
  element("switches").textContent = result.switches;
  const objective = result.planning_objective;
  const objectiveLabel = objective?.terminal_queue_penalty > 0 ? ` · final queue penalty ${objective.terminal_queue_penalty}/car` : "";
  element("metric-source").textContent = `${controllerNames[result.controller]} · ${result.config.planning_horizon ?? 15} s planning horizon · seed ${result.config.seed} · ${result.config.duration.toFixed(0)} simulated s${objectiveLabel}`;
  const model = result.decision_model;
  const modelDetails = model ? ` · ${model.information_mode} state · ${model.request_count} API calls · $${model.cost_usd.toFixed(5)} API cost` : "";
  const choiceP95 = result.p95_choice_ms ?? result.p95_decision_ms;
  element("details").textContent = `${result.sumo_version} · ${result.generated} generated · ${result.departed} departed · ${result.active} unfinished · ${choiceP95.toFixed(2)} ms p95 choice time${modelDetails}`;
  draw(frame);
}

function setPlaying(playing) {
  state.playing = playing;
  state.fraction = 0;
  state.lastTick = performance.now();
  element("play").textContent = playing ? "Pause" : "Play";
}

function showReplay(data, saved) {
  state.replay = data;
  const firstVehicle = data.frames.findIndex((frame) => frame.vehicles.length > 0);
  state.index = firstVehicle < 0 ? 0 : firstVehicle;
  element("scrub").max = data.frames.length - 1;
  element("scrub").disabled = false;
  element("play").disabled = false;
  element("step").disabled = false;
  render();
  if (firstVehicle < 0) {
    status("No vehicles entered the network. Increase inflow and press Run SUMO.");
  } else {
    setPlaying(true);
    status(`${saved ? "Loaded saved run" : "Playing new run"} · ${data.frames.length} recorded SUMO frames`);
  }
}

async function generate() {
  if (state.busy) return;
  const values = parameters();
  if (scoresOnly) {
    renderOptimization({ controller: values.controller, config: { planning_horizon: values.horizon } });
    status("Viewing saved optimization scores only. No simulation or model call.");
    return;
  }
  const key = cacheKey(values);
  if (state.replays.has(key)) {
    showReplay(state.replays.get(key), true);
    return;
  }
  state.busy = true;
  setPlaying(false);
  element("generate").disabled = true;
  for (const id of inputIds) element(id).disabled = true;
  const name = controllerNames[values.controller];
  const previous = state.replay?.result;
  element("metric-source").textContent = previous
    ? `Running ${name}… Previous result: ${controllerNames[previous.controller]}`
    : `Running ${name}…`;
  status(savedOnly ? `Loading ${name} · ${values.horizon} s planning horizon…` : `Running ${name} in SUMO and collecting positions…`);
  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "SUMO run failed");
    if (!data.result || !Array.isArray(data.frames) || !data.frames.length) {
      throw new Error("SUMO returned no replay frames");
    }
    state.replays.set(key, data);
    showReplay(data, data.cache_hit);
  } catch (error) {
    if (state.replay) render();
    const message = error instanceof TypeError
      ? "Local server unavailable. Restart with .venv/bin/python -m trafficlab --web, then press Run SUMO."
      : error.message;
    status(message, true);
  } finally {
    state.busy = false;
    element("generate").disabled = false;
    for (const id of inputIds) element(id).disabled = false;
    if (savedOnly) for (const id of ["seed", "inflow", "cav"]) element(id).disabled = true;
  }
}

element("generate").addEventListener("click", generate);
element("controller").addEventListener("change", generate);
for (const id of ["seed", "inflow", "cav", "horizon"]) {
  element(id).addEventListener("input", () => {
    if (state.busy) return;
    if (scoresOnly) { generate(); return; }
    const saved = state.replays.get(cacheKey(parameters()));
    if (saved) showReplay(saved, true);
    else if (state.replay) status(`Settings changed. Press ${savedOnly ? "Load replay" : "Run SUMO"} to update the displayed metrics.`);
  });
}
element("play").addEventListener("click", () => {
  if (!state.replay) return;
  if (state.playing) {
    setPlaying(false);
    status("Paused");
    return;
  }
  if (state.index === state.replay.frames.length - 1) state.index = 0;
  render();
  setPlaying(true);
  status("Playing recorded SUMO positions");
});
element("step").addEventListener("click", () => {
  if (!state.replay) return;
  setPlaying(false);
  state.index = Math.min(state.replay.frames.length - 1, state.index + 1);
  render();
  status("Paused");
});
element("scrub").addEventListener("input", () => {
  if (!state.replay) return;
  setPlaying(false);
  state.index = Number(element("scrub").value);
  render();
  status("Paused");
});

function tick(now) {
  if (state.playing && state.replay) {
    const elapsed = Math.min((now - state.lastTick) / 1000, 0.25);
    const frames = state.replay.frames;
    const frameSeconds = frames.length > 1 ? frames[1].time - frames[0].time : 0.5;
    state.fraction += elapsed * Number(element("speed").value) / frameSeconds;
    const steps = Math.floor(state.fraction);
    if (steps > 0) {
      state.fraction -= steps;
      state.index = Math.min(frames.length - 1, state.index + steps);
      render();
      if (state.index === frames.length - 1) {
        setPlaying(false);
        status("Replay complete. Press Play to restart.");
      }
    }
  }
  state.lastTick = now;
  requestAnimationFrame(tick);
}

element("play").disabled = true;
element("step").disabled = true;
element("scrub").disabled = true;
draw(null);
requestAnimationFrame(tick);
generate();
