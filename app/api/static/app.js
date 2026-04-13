const tabEls = Array.from(document.querySelectorAll(".tab"));
const panelEls = Array.from(document.querySelectorAll(".tab-panel"));

const sessionLabelEl = document.getElementById("sessionLabel");
const debugModeEl = document.getElementById("debugMode");
const newChatBtn = document.getElementById("newChatBtn");

const toneEl = document.getElementById("tone");
const focusAreaEl = document.getElementById("focusArea");
const summaryFrequencyEl = document.getElementById("summaryFrequency");
const trackedLiftsEl = document.getElementById("trackedLifts");
const trackedMetricsEl = document.getElementById("trackedMetrics");
const prefsStatusEl = document.getElementById("prefsStatus");
const savePrefsBtn = document.getElementById("savePrefs");
const refreshPrefsBtn = document.getElementById("refreshPrefs");

const compareExerciseEl = document.getElementById("compareExercise");
const compareWindowEl = document.getElementById("compareWindow");
const compareMetricEl = document.getElementById("compareMetric");
const compareResultEl = document.getElementById("compareResult");
const compareStatusEl = document.getElementById("compareStatus");
const compareChartEl = document.getElementById("compareChart");
const compareFollowupEl = document.getElementById("compareFollowup");
const compareFollowupResultEl = document.getElementById("compareFollowupResult");
const compareFollowupStatusEl = document.getElementById("compareFollowupStatus");
const runCompareFollowupBtn = document.getElementById("runCompareFollowup");
const runCompareBtn = document.getElementById("runCompare");

const plannerQueryEl = document.getElementById("plannerQuery");
const plannerResultEl = document.getElementById("plannerResult");
const runPlannerBtn = document.getElementById("runPlanner");

const recoveryModeEl = document.getElementById("recoveryMode");
const recoveryResultEl = document.getElementById("recoveryResult");
const runRecoveryBtn = document.getElementById("runRecovery");
const dataTotalWorkoutsEl = document.getElementById("dataTotalWorkouts");
const dataRecoveryDaysEl = document.getElementById("dataRecoveryDays");
const dataStrengthRangeEl = document.getElementById("dataStrengthRange");
const dataRecoveryRangeEl = document.getElementById("dataRecoveryRange");
const dataLatestFeatureDateEl = document.getElementById("dataLatestFeatureDate");

const SESSION_STORAGE_KEY = "hai-current-session-id";
let currentSessionId = null;
let lastComparePayload = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function setActiveTab(tabName) {
  for (const tabEl of tabEls) {
    tabEl.classList.toggle("is-active", tabEl.dataset.tab === tabName);
  }
  for (const panelEl of panelEls) {
    panelEl.classList.toggle("is-active", panelEl.dataset.panel === tabName);
  }
}

function renderResult(container, data, debugEnabled) {
  let html = "";

  if (data.answer) {
    html += `<p>${escapeHtml(data.answer).replaceAll("\n", "<br />")}</p>`;
  } else if (data.message) {
    html += `<p>${escapeHtml(data.message)}</p>`;
  } else {
    html += `<p>No answer returned yet.</p>`;
  }

  html += `<p class="muted">Confidence: ${escapeHtml(data.confidence || "unknown")}</p>`;
  if (Array.isArray(data.quality_flags) && data.quality_flags.length) {
    html += `<p class="muted warn">Flags: ${escapeHtml(data.quality_flags.join(", "))}</p>`;
  }
  if (debugEnabled && data.debug) {
    html += `<pre>${escapeHtml(JSON.stringify(data.debug, null, 2))}</pre>`;
  }

  container.innerHTML = html;
}

function setSessionLabel(session) {
  const title = session && session.title ? session.title : "New Chat";
  sessionLabelEl.textContent = `Session: ${title}`;
}

function loadStoredSessionId() {
  currentSessionId = localStorage.getItem(SESSION_STORAGE_KEY);
}

function saveStoredSessionId(sessionId) {
  currentSessionId = sessionId;
  if (sessionId) {
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  } else {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  }
}

function currentPreferences() {
  return {
    tone: toneEl.value,
    focus_area: focusAreaEl.value,
    summary_frequency: summaryFrequencyEl.value,
    tracked_lifts: trackedLiftsEl.value.split(",").map((x) => x.trim()).filter(Boolean),
    tracked_metrics: trackedMetricsEl.value.split(",").map((x) => x.trim()).filter(Boolean),
    debug_default: debugModeEl.checked,
  };
}

function renderDateRange(range) {
  if (!range || (!range.start && !range.end)) {
    return "No data";
  }
  return `${range.start || "unknown"} to ${range.end || "unknown"}`;
}

async function createNewSession() {
  const response = await fetch("/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "New Chat" }),
  });
  const session = await response.json();
  saveStoredSessionId(session.session_id);
  setSessionLabel(session);
}

async function loadCurrentSession() {
  loadStoredSessionId();

  if (!currentSessionId) {
    const response = await fetch("/sessions");
    const data = await response.json();
    const sessions = Array.isArray(data.sessions) ? data.sessions : [];
    if (sessions.length) {
      saveStoredSessionId(sessions[0].session_id);
    }
  }

  if (!currentSessionId) {
    setSessionLabel({ title: "New Chat" });
    return;
  }

  const response = await fetch(`/sessions/${currentSessionId}`);
  if (!response.ok) {
    saveStoredSessionId(null);
    setSessionLabel({ title: "New Chat" });
    return;
  }

  const session = await response.json();
  saveStoredSessionId(session.session_id);
  setSessionLabel(session);
}

async function loadPreferences() {
  prefsStatusEl.textContent = "Loading...";
  const response = await fetch("/preferences");
  const data = await response.json();

  toneEl.value = data.tone || "standard";
  focusAreaEl.value = data.focus_area || "balanced";
  summaryFrequencyEl.value = data.summary_frequency || "weekly";
  trackedLiftsEl.value = Array.isArray(data.tracked_lifts) ? data.tracked_lifts.join(", ") : "";
  trackedMetricsEl.value = Array.isArray(data.tracked_metrics) ? data.tracked_metrics.join(", ") : "";
  debugModeEl.checked = Boolean(data.debug_default);

  prefsStatusEl.textContent = "Preferences loaded.";
}

async function savePreferences() {
  prefsStatusEl.textContent = "Saving...";
  const response = await fetch("/preferences", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(currentPreferences()),
  });
  const data = await response.json();
  prefsStatusEl.textContent = response.ok ? "Preferences saved." : `Error: ${data.error || "unknown error"}`;
}

async function loadDataStatus() {
  try {
    const response = await fetch("/data/status");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "status unavailable");
    }

    dataTotalWorkoutsEl.textContent = String(data.total_workouts ?? 0);
    dataRecoveryDaysEl.textContent = String(data.total_recovery_days ?? 0);
    dataStrengthRangeEl.textContent = renderDateRange(data.strength_data_date_range);
    dataRecoveryRangeEl.textContent = renderDateRange(data.recovery_data_date_range);
    dataLatestFeatureDateEl.textContent = data.latest_available_feature_date || "No data";
  } catch (error) {
    dataTotalWorkoutsEl.textContent = "Unavailable";
    dataRecoveryDaysEl.textContent = "Unavailable";
    dataStrengthRangeEl.textContent = "Unavailable";
    dataRecoveryRangeEl.textContent = "Unavailable";
    dataLatestFeatureDateEl.textContent = "Unavailable";
  }
}

async function runAgentQuery(query, targetEl, statusEl = null) {
  if (!query) {
    return;
  }

  if (statusEl) {
    statusEl.textContent = "Thinking...";
  }

  try {
    const response = await fetch("/agent/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_query: query,
        call_llm: true,
        debug: debugModeEl.checked,
        preferences: currentPreferences(),
        session_id: currentSessionId,
      }),
    });

    const data = await response.json();
    if (data.session_id) {
      saveStoredSessionId(data.session_id);
    }
    renderResult(targetEl, data, debugModeEl.checked);

    if (statusEl) {
      statusEl.textContent = "";
    }

    if (currentSessionId) {
      const sessionResponse = await fetch(`/sessions/${currentSessionId}`);
      if (sessionResponse.ok) {
        const session = await sessionResponse.json();
        setSessionLabel(session);
      }
    }
    return data;
  } catch (error) {
    targetEl.innerHTML = "<p>Request failed. Check the server and try again.</p>";
    if (statusEl) {
      statusEl.textContent = "";
    }
    return null;
  }
}

async function runCompareQuery(query, targetEl, statusEl = null) {
  if (!query) {
    return null;
  }

  if (statusEl) {
    statusEl.textContent = "Thinking...";
  }

  try {
    const response = await fetch("/agent/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_query: query,
        call_llm: true,
        debug: true,
        preferences: currentPreferences(),
        session_id: currentSessionId,
      }),
    });

    const data = await response.json();
    if (data.session_id) {
      saveStoredSessionId(data.session_id);
    }
    renderResult(targetEl, data, debugModeEl.checked);
    if (statusEl) {
      statusEl.textContent = "";
    }
    return data;
  } catch (error) {
    targetEl.innerHTML = "<p>Request failed. Check the server and try again.</p>";
    if (statusEl) {
      statusEl.textContent = "";
    }
    return null;
  }
}

function compareSeriesFromDebug(data, metric) {
  const toolOutputs = data && data.debug && Array.isArray(data.debug.tool_outputs) ? data.debug.tool_outputs : [];
  const compareOutput = toolOutputs.find((item) => item && item.tool_name === "strength_analysis");
  const payload = compareOutput && compareOutput.payload ? compareOutput.payload : null;
  if (!payload || payload.mode !== "compare") {
    return null;
  }

  const previous = payload.previous || {};
  const current = payload.current || {};
  const metricLabel = metric === "best_estimated_max" ? "Best Estimated Max" : "Volume";
  const previousValue = previous[metric];
  const currentValue = current[metric];

  if (previousValue == null && currentValue == null) {
    return null;
  }

  return {
    label: metricLabel,
    points: [
      { label: "Previous Window", value: Number(previousValue || 0) },
      { label: "Current Window", value: Number(currentValue || 0) },
    ],
  };
}

function comparePayloadFromDebug(data) {
  const toolOutputs = data && data.debug && Array.isArray(data.debug.tool_outputs) ? data.debug.tool_outputs : [];
  const compareOutput = toolOutputs.find((item) => item && item.tool_name === "strength_analysis");
  const payload = compareOutput && compareOutput.payload ? compareOutput.payload : null;
  return payload && payload.mode === "compare" ? payload : null;
}

function isCompareReasonFollowup(query) {
  const q = query.toLowerCase();
  return q.includes("why") || q.includes("what drove") || q.includes("what caused");
}

function renderCompareReasonFollowup(payload, targetEl) {
  if (!payload) {
    targetEl.innerHTML = "<p>Run a comparison first so I can explain what drove the change.</p>";
    return;
  }

  const drivers = [];
  if (payload.volume_change != null && payload.volume_change !== 0) {
    drivers.push(
      payload.volume_change > 0
        ? `volume was higher by ${payload.volume_change.toFixed(1)}`
        : `volume was lower by ${Math.abs(payload.volume_change).toFixed(1)}`,
    );
  }
  if (payload.best_estimated_max_change != null && payload.best_estimated_max_change !== 0) {
    drivers.push(
      payload.best_estimated_max_change > 0
        ? `best estimated max improved by ${payload.best_estimated_max_change.toFixed(1)}`
        : `best estimated max dropped by ${Math.abs(payload.best_estimated_max_change).toFixed(1)}`,
    );
  }
  if (payload.set_change != null && payload.set_change !== 0) {
    drivers.push(
      payload.set_change > 0
        ? `you completed ${payload.set_change} more sets`
        : `you completed ${Math.abs(payload.set_change)} fewer sets`,
    );
  }
  if (payload.pr_change != null && payload.pr_change !== 0) {
    drivers.push(
      payload.pr_change > 0
        ? `you hit more PRs`
        : `you hit fewer PRs`,
    );
  }

  const summary = drivers.length
    ? `The main drivers were that ${drivers.slice(0, 2).join(" and ")}.`
    : "The current and previous windows look fairly similar, so there is not one clear driver in the compare payload.";

  targetEl.innerHTML = `<p>${escapeHtml(summary)}</p><p class="muted">Based on the current window comparison only.</p>`;
}

function renderCompareChart(series) {
  if (!series) {
    compareChartEl.innerHTML = "Chart unavailable for this comparison yet.";
    return;
  }

  const width = 420;
  const height = 220;
  const padding = 28;
  const maxValue = Math.max(...series.points.map((point) => point.value), 1);
  const stepX = (width - padding * 2) / Math.max(series.points.length - 1, 1);

  const coords = series.points.map((point, index) => {
    const x = padding + index * stepX;
    const y = height - padding - ((point.value / maxValue) * (height - padding * 2));
    return { ...point, x, y };
  });

  const path = coords.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const circles = coords
    .map((point) => `<circle cx="${point.x}" cy="${point.y}" r="5" fill="#1d6b57"></circle>`)
    .join("");
  const labels = coords
    .map(
      (point) =>
        `<text x="${point.x}" y="${height - 8}" text-anchor="middle" font-size="12" fill="#6b665f">${escapeHtml(point.label)}</text>
         <text x="${point.x}" y="${point.y - 12}" text-anchor="middle" font-size="12" fill="#1f1d1a">${escapeHtml(point.value.toFixed(1))}</text>`,
    )
    .join("");

  compareChartEl.innerHTML = `
    <div class="chart-meta">${escapeHtml(series.label)}</div>
    <svg viewBox="0 0 ${width} ${height}" class="line-chart" role="img" aria-label="${escapeHtml(series.label)} progress chart">
      <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" stroke="#d7cfbf" stroke-width="1.5"></line>
      <line x1="${padding}" y1="${padding}" x2="${padding}" y2="${height - padding}" stroke="#d7cfbf" stroke-width="1.5"></line>
      <path d="${path}" fill="none" stroke="#1d6b57" stroke-width="3" stroke-linecap="round"></path>
      ${circles}
      ${labels}
    </svg>
  `;
}

function compareQuery() {
  const exercise = compareExerciseEl.value.trim() || "Bench Press";
  const windowText = compareWindowEl.value;
  return `How did my ${exercise} progress over ${windowText}?`;
}

function compareFollowupQuery() {
  const followup = compareFollowupEl.value.trim();
  if (!followup) {
    return "";
  }
  return `${compareQuery()} ${followup}`;
}

tabEls.forEach((tabEl) => {
  tabEl.addEventListener("click", () => {
    setActiveTab(tabEl.dataset.tab);
  });
});

runCompareBtn.addEventListener("click", async () => {
  compareChartEl.textContent = `Preparing comparison view for ${compareExerciseEl.value.trim() || "your selected lift"}...`;
  const data = await runCompareQuery(compareQuery(), compareResultEl, compareStatusEl);
  if (data) {
    lastComparePayload = comparePayloadFromDebug(data);
    renderCompareChart(compareSeriesFromDebug(data, compareMetricEl.value));
  }
});

runCompareFollowupBtn.addEventListener("click", async () => {
  const query = compareFollowupQuery();
  if (!query) {
    return;
  }
  if (isCompareReasonFollowup(compareFollowupEl.value.trim())) {
    compareFollowupStatusEl.textContent = "Explaining...";
    renderCompareReasonFollowup(lastComparePayload, compareFollowupResultEl);
    compareFollowupStatusEl.textContent = "";
    return;
  }
  await runAgentQuery(query, compareFollowupResultEl, compareFollowupStatusEl);
});

runPlannerBtn.addEventListener("click", () => runAgentQuery(plannerQueryEl.value.trim(), plannerResultEl));
runRecoveryBtn.addEventListener("click", () => runAgentQuery(recoveryModeEl.value, recoveryResultEl));

savePrefsBtn.addEventListener("click", savePreferences);
refreshPrefsBtn.addEventListener("click", loadPreferences);
newChatBtn.addEventListener("click", async () => {
  compareStatusEl.textContent = "Starting new chat...";
  try {
    await createNewSession();
    compareResultEl.innerHTML = "Ask Hai to compare a lift and the summary will appear here.";
    compareFollowupResultEl.innerHTML = "Follow-up answers will appear here.";
    compareFollowupEl.value = "";
    lastComparePayload = null;
    plannerResultEl.innerHTML = "Planner recommendation will appear here.";
    recoveryResultEl.innerHTML = "Recovery summary will appear here.";
  } finally {
    compareStatusEl.textContent = "";
  }
});

loadPreferences().catch(() => {
  prefsStatusEl.textContent = "Could not load preferences.";
});

loadCurrentSession().catch(() => {
  setSessionLabel({ title: "New Chat" });
});

loadDataStatus();
