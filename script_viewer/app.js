(function () {
  const data = window.PSSR_VIEWER_DATA;
  if (!data) {
    document.body.innerHTML = "<p style='color:white;padding:2rem'>Viewer data was not loaded. Run build_script_viewer_data.py first.</p>";
    return;
  }

  const recordsById = new Map(data.records.map((record) => [record.id, record]));
  const leadRecords = data.records.filter((record) => record.id === record.windowLeadId);
  const displayWindows = buildDisplayWindows(leadRecords);

  const stateGraph = data.graph?.stateGraph || { global_summary: {}, files: {} };
  const acceptance = data.graph?.walkthroughAcceptance || { files: [], ready_files: [], partial_files: [], weak_files: [] };
  const commandMatrix = data.graph?.commandMatrix || {};
  const locationCaptureByDestinationLabel = new Map(Object.entries(data.graph?.locationCaptures?.byDestinationLabel || {}));
  const sceneCaptureByFile = new Map(Object.entries(data.graph?.locationCaptures?.byFile || {}));
  const sceneCaptureRangesByFile = new Map(Object.entries(data.graph?.locationCaptures?.byFileRanges || {}));
  const acceptanceByFile = new Map((acceptance.files || []).map((item) => [item.file, item]));
  const graphFiles = Object.keys(stateGraph.files || {});

  const els = {
    fileFilter: document.getElementById("fileFilter"),
    searchInput: document.getElementById("searchInput"),
    progressLabel: document.getElementById("progressLabel"),
    progressFill: document.getElementById("progressFill"),
    prevButton: document.getElementById("prevButton"),
    nextButton: document.getElementById("nextButton"),
    recordCounter: document.getElementById("recordCounter"),
    matchCount: document.getElementById("matchCount"),
    recordList: document.getElementById("recordList"),
    previewMode: document.getElementById("previewMode"),
    previewText: document.getElementById("previewText"),
    sceneImage: document.getElementById("sceneImage"),
    scenePlaceholder: document.getElementById("scenePlaceholder"),
    sceneLip: document.getElementById("sceneLip"),
    recordMeta: document.getElementById("recordMeta"),
    pointerContexts: document.getElementById("pointerContexts"),
    copyJsonButton: document.getElementById("copyJsonButton"),
    tabButtons: Array.from(document.querySelectorAll(".tab-button")),
    tabPanels: Array.from(document.querySelectorAll(".tab-panel")),
    scriptToolbar: document.getElementById("scriptToolbar"),
    fileMapSummary: document.getElementById("fileMapSummary"),
    fileMapCards: document.getElementById("fileMapCards"),
    actionFileSelect: document.getElementById("actionFileSelect"),
    actionSelect: document.getElementById("actionSelect"),
    targetSelect: document.getElementById("targetSelect"),
    actionSummary: document.getElementById("actionSummary"),
    actionNodes: document.getElementById("actionNodes"),
    heatmapSummary: document.getElementById("heatmapSummary"),
    heatmapGrid: document.getElementById("heatmapGrid"),
    graphFileSelect: document.getElementById("graphFileSelect"),
    graphSummary: document.getElementById("graphSummary"),
    graphSvg: document.getElementById("graphSvg"),
    flagFileSelect: document.getElementById("flagFileSelect"),
    flagSearchInput: document.getElementById("flagSearchInput"),
    flagSummary: document.getElementById("flagSummary"),
    flagList: document.getElementById("flagList"),
    routeFileSelect: document.getElementById("routeFileSelect"),
    routeActionSelect: document.getElementById("routeActionSelect"),
    routeTargetSelect: document.getElementById("routeTargetSelect"),
    routeAddStepButton: document.getElementById("routeAddStepButton"),
    routeResetButton: document.getElementById("routeResetButton"),
    routeSummary: document.getElementById("routeSummary"),
    routeTimeline: document.getElementById("routeTimeline"),
  };

  const state = {
    activeTab: "script",
    filters: {
      file: "",
      query: "",
    },
    filteredWindows: [],
    currentIndex: 0,
    currentPage: 0,
    action: {
      file: graphFiles[0] || "",
      action: "",
      target: "",
    },
    graph: {
      file: graphFiles[0] || "",
      selectedNodeId: "",
    },
    flags: {
      file: graphFiles[0] || "",
      query: "",
    },
    route: {
      file: graphFiles[0] || "",
      action: "",
      target: "",
      steps: [],
    },
  };

  populateSelect(els.fileFilter, data.meta.files, "All files", formatFileLabel);
  populateSelect(els.actionFileSelect, graphFiles, "Select file", formatFileLabel);
  populateSelect(els.graphFileSelect, graphFiles, "Select file", formatFileLabel);
  populateSelect(els.flagFileSelect, graphFiles, "Select file", formatFileLabel);
  populateSelect(els.routeFileSelect, graphFiles, "Select file", formatFileLabel);

  if (data.meta?.defaultFile && data.meta.files.includes(data.meta.defaultFile)) {
    state.filters.file = data.meta.defaultFile;
    els.fileFilter.value = data.meta.defaultFile;
  }
  if (state.action.file) {
    els.actionFileSelect.value = state.action.file;
  }
  if (state.graph.file) {
    els.graphFileSelect.value = state.graph.file;
  }
  if (state.flags.file) {
    els.flagFileSelect.value = state.flags.file;
  }
  if (state.route.file) {
    els.routeFileSelect.value = state.route.file;
  }

  document.documentElement.style.setProperty(
    "--typeset-chars-per-line",
    String(data.meta?.screen?.typesetCharsPerLine || 39),
  );

  bindEvents();
  updateFilters({});
  initializeGraphViews();

  function bindEvents() {
    els.fileFilter.addEventListener("change", () => updateFilters({ file: els.fileFilter.value }));
    els.searchInput.addEventListener("input", () => updateFilters({ query: els.searchInput.value.trim().toLowerCase() }));
    els.previewMode.addEventListener("change", () => {
      state.currentPage = 0;
      renderCurrent();
    });
    els.prevButton.addEventListener("click", () => moveSelection(-1));
    els.nextButton.addEventListener("click", () => moveSelection(1));
    els.copyJsonButton.addEventListener("click", copyCurrentJson);
    document.addEventListener("keydown", onKeyDown);

    els.tabButtons.forEach((button) => {
      button.addEventListener("click", () => switchTab(button.dataset.tab));
    });

    els.actionFileSelect.addEventListener("change", () => {
      state.action.file = els.actionFileSelect.value;
      refreshActionSelectors();
    });
    els.actionSelect.addEventListener("change", () => {
      state.action.action = els.actionSelect.value;
      refreshActionSelectors(false);
    });
    els.targetSelect.addEventListener("change", () => {
      state.action.target = els.targetSelect.value;
      renderActionExplorer();
    });

    els.graphFileSelect.addEventListener("change", () => {
      state.graph.file = els.graphFileSelect.value;
      state.graph.selectedNodeId = "";
      renderGraphView();
    });

    els.flagFileSelect.addEventListener("change", () => {
      state.flags.file = els.flagFileSelect.value;
      renderFlagInspector();
    });
    els.flagSearchInput.addEventListener("input", () => {
      state.flags.query = els.flagSearchInput.value.trim().toLowerCase();
      renderFlagInspector();
    });

    els.routeFileSelect.addEventListener("change", () => {
      state.route.file = els.routeFileSelect.value;
      refreshRouteSelectors();
    });
    els.routeActionSelect.addEventListener("change", () => {
      state.route.action = els.routeActionSelect.value;
      refreshRouteSelectors(false);
    });
    els.routeTargetSelect.addEventListener("change", () => {
      state.route.target = els.routeTargetSelect.value;
      renderRouteBuilder();
    });
    els.routeAddStepButton.addEventListener("click", addRouteStep);
    els.routeResetButton.addEventListener("click", () => {
      state.route.steps = [];
      renderRouteBuilder();
    });
  }

  function initializeGraphViews() {
    refreshActionSelectors();
    renderFileMap();
    renderHeatmap();
    renderGraphView();
    renderFlagInspector();
    refreshRouteSelectors();
  }

  function switchTab(tabId) {
    state.activeTab = tabId;
    els.tabButtons.forEach((button) => button.classList.toggle("active", button.dataset.tab === tabId));
    els.tabPanels.forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${tabId}`));
    els.scriptToolbar.classList.toggle("hidden", tabId !== "script");
  }

  function buildDisplayWindows(records) {
    const result = [];
    let current = [];

    for (const record of records) {
      if (!current.length) {
        current = [record];
        continue;
      }

      if (shouldStartNewDisplayWindow(record, current[current.length - 1])) {
        result.push(finalizeDisplayWindow(current));
        current = [record];
      } else {
        current.push(record);
      }
    }

    if (current.length) {
      result.push(finalizeDisplayWindow(current));
    }

    return result;
  }

  function shouldStartNewDisplayWindow(record, previousRecord) {
    if (!previousRecord) return true;
    if (record.file !== previousRecord.file) return true;
    if (record.command) return true;
    if (hasClear(record.ctrlCodes)) return true;
    return false;
  }

  function finalizeDisplayWindow(records) {
    const offsets = records.map((record) => record.offset);
    const windowOffsets = [...new Set(records.flatMap((record) => record.windowOffsets || [record.offset]))];
    const speakers = [...new Set(records.map((record) => getLineSpeaker(record)).filter(Boolean))];
    const pointerContexts = records.flatMap((record) => record.pointerContexts || []);

    return {
      id: records[0].id,
      file: records[0].file,
      offset: records[0].offset,
      command: records[0].command || "",
      comments: records.map((record) => record.comments).filter(Boolean).join(" | "),
      ctrlCodes: records.map((record) => record.ctrlCodes).filter(Boolean).join(" "),
      labels: [...new Set(records.flatMap((record) => record.labels || []))],
      speakers,
      offsets,
      windowOffsets,
      pointerCount: records.reduce((sum, record) => sum + (record.pointerCount || 0), 0),
      pointerContexts,
      records,
    };
  }

  function populateSelect(select, values, defaultLabel, labelFormatter = null) {
    const options = [`<option value="">${escapeHtml(defaultLabel)}</option>`]
      .concat(values.map((value) => {
        const label = labelFormatter ? labelFormatter(value) : value;
        return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
      }));
    select.innerHTML = options.join("");
  }

  function formatFileLabel(fileName) {
    return isAdultFile(fileName) ? `${fileName} (H)` : fileName;
  }

  function formatOptionalFileLabel(fileName) {
    return fileName ? formatFileLabel(fileName) : "(none)";
  }

  function isAdultFile(fileName) {
    return !(
      fileName.startsWith("P_") ||
      fileName.startsWith("POS1") ||
      fileName.startsWith("RASU") ||
      fileName.startsWith("END")
    );
  }

  function hasClear(ctrlCodes) {
    return String(ctrlCodes || "").includes("[Clear]");
  }

  function updateFilters(next) {
    const shouldResetIndex = Object.keys(next).length > 0;
    Object.assign(state.filters, next);

    state.filteredWindows = displayWindows.filter((windowRecord) => {
      if (state.filters.file && windowRecord.file !== state.filters.file) return false;

      if (state.filters.query) {
        const haystack = [
          windowRecord.file,
          windowRecord.offset,
          windowRecord.command,
          windowRecord.comments,
          windowRecord.ctrlCodes,
          windowRecord.labels.join(" "),
          windowRecord.offsets.join(" "),
          windowRecord.windowOffsets.join(" "),
          ...windowRecord.records.map((record) => getLinePreviewText(record, "japanese")),
          ...windowRecord.records.map((record) => getLinePreviewText(record, "english")),
          ...windowRecord.records.map((record) => getLinePreviewText(record, "typeset")),
        ].join("\n").toLowerCase();

        if (!haystack.includes(state.filters.query)) return false;
      }

      return true;
    });

    if (shouldResetIndex || state.currentIndex >= state.filteredWindows.length) {
      state.currentIndex = 0;
    }
    if (shouldResetIndex) {
      state.currentPage = 0;
    }

    updateProgress();
    renderList();
    renderCurrent();
  }

  function renderList() {
    els.matchCount.textContent = `${state.filteredWindows.length} / ${displayWindows.length}`;
    if (!state.filteredWindows.length) {
      els.recordList.innerHTML = "<div class='record-subline'>No matching rows.</div>";
      return;
    }

    els.recordList.innerHTML = state.filteredWindows
      .map((windowRecord, index) => {
        const active = index === state.currentIndex ? " active" : "";
        const speakerSummary = windowRecord.speakers.join(", ") || "Narration";
        const snippet = getDisplayWindowText(windowRecord, "typeset").replace(/\n/g, " ").slice(0, 96);
        return `
          <button class="record-list-item${active}" data-index="${index}" type="button">
            <div class="record-title">${escapeHtml(windowRecord.file)} ${escapeHtml(windowRecord.offset)}</div>
            <div class="record-subline">${escapeHtml(windowRecord.command || "(continued window)")} · ${escapeHtml(speakerSummary)}</div>
            <div class="record-snippet">${escapeHtml(snippet)}</div>
          </button>
        `;
      })
      .join("");

    els.recordList.querySelectorAll("[data-index]").forEach((button) => {
      button.addEventListener("click", () => {
        state.currentIndex = Number(button.dataset.index);
        state.currentPage = 0;
        renderList();
        renderCurrent();
      });
    });

    const activeButton = els.recordList.querySelector(".record-list-item.active");
    if (activeButton) {
      activeButton.scrollIntoView({ block: "nearest" });
    }
  }

  function updateProgress() {
    const selectedRecords = new Map();
    for (const windowRecord of state.filteredWindows) {
      for (const record of windowRecord.records) {
        selectedRecords.set(record.id, record);
      }
    }

    const total = selectedRecords.size;
    let translated = 0;
    for (const record of selectedRecords.values()) {
      if ((record.english || "").trim() || (record.englishTypeset || "").trim()) {
        translated += 1;
      }
    }

    const percent = total ? (translated / total) * 100 : 0;
    els.progressLabel.textContent = `${translated} / ${total} (${percent.toFixed(1)}%)`;
    els.progressFill.style.width = `${percent}%`;
  }

  function renderCurrent() {
    const windowRecord = currentWindow();
    if (!windowRecord) {
      els.recordCounter.textContent = "No record selected";
      els.previewText.innerHTML = "";
      clearSceneCapture();
      els.sceneLip.textContent = "";
      els.recordMeta.innerHTML = "";
      els.pointerContexts.innerHTML = "";
      return;
    }

    const pages = getWindowPages(windowRecord, els.previewMode.value);
    if (state.currentPage >= pages.length) {
      state.currentPage = Math.max(0, pages.length - 1);
    }
    const currentPage = pages[state.currentPage] || [];
    const sceneCapture = resolveSceneCapture(windowRecord);

    els.recordCounter.textContent = `${state.currentIndex + 1} / ${state.filteredWindows.length} · page ${state.currentPage + 1} / ${pages.length || 1}`;
    renderSceneCapture(sceneCapture, windowRecord.file);
    els.sceneLip.textContent = buildSceneLip(windowRecord, pages.length);
    els.previewText.innerHTML = renderPreviewLines(currentPage);

    els.recordMeta.innerHTML = [
      metaRow("File", windowRecord.file),
      metaRow("Lead offset", windowRecord.offset),
      metaRow("Command", windowRecord.command || "(continued window)"),
      metaRow("Window page", `${state.currentPage + 1} / ${pages.length || 1}`),
      metaRow("Visible lines", windowRecord.offsets.join(", ")),
      metaRow("Worksheet rows", windowRecord.windowOffsets.join(", ")),
      metaRow("Scene", sceneCapture?.label || "(unmapped)"),
      metaRow("Speakers", windowRecord.speakers.join(", ") || "Narration"),
      metaRow("Labels", windowRecord.labels.join(", ") || "(none)"),
      metaRow("Comments", windowRecord.comments || "(none)"),
      metaRow("Ctrl codes", windowRecord.ctrlCodes || "(none)"),
      metaRow("Pointer count", String(windowRecord.pointerCount)),
    ].join("");

    els.pointerContexts.innerHTML = renderPointerContexts(windowRecord.pointerContexts);
  }

  function renderPreviewLines(pageRows) {
    return pageRows
      .map((row) => {
        const text = escapeHtml(row.text).replace(/\n/g, "<br>");
        const colorClass = `preview-color-${String(row.color || "white").toLowerCase()}`;
        return `
          <div class="preview-line ${colorClass}">
            <div class="preview-speaker">${escapeHtml(row.speaker)}</div>
            <div class="preview-dialogue">${text}</div>
          </div>
        `;
      })
      .join("");
  }

  function resolveSceneCapture(windowRecord) {
    const offsetValue = parseSceneOffset(windowRecord.offset);
    const rules = sceneCaptureRangesByFile.get(windowRecord.file) || [];
    for (const rule of rules) {
      const start = rule.start ?? null;
      const end = rule.end ?? null;
      if ((start === null || offsetValue >= start) && (end === null || offsetValue <= end)) {
        return rule.capture || null;
      }
    }
    return sceneCaptureByFile.get(windowRecord.file) || null;
  }

  function parseSceneOffset(value) {
    const text = String(value || "").trim().toLowerCase();
    if (!text) {
      return Number.NaN;
    }
    return text.startsWith("0x") ? Number.parseInt(text.slice(2), 16) : Number.parseInt(text, 10);
  }

  function clearSceneCapture() {
    els.sceneImage.classList.add("hidden");
    els.sceneImage.removeAttribute("src");
    els.sceneImage.alt = "";
    els.scenePlaceholder.textContent = "Scene";
    els.scenePlaceholder.classList.remove("hidden");
  }

  function renderSceneCapture(capture, fileName) {
    if (!capture || !capture.image) {
      clearSceneCapture();
      return;
    }
    els.sceneImage.src = normalizeAssetPath(capture.image);
    els.sceneImage.alt = `${fileName} scene: ${capture.label || "mapped scene"}`;
    els.sceneImage.classList.remove("hidden");
    els.scenePlaceholder.classList.add("hidden");
  }

  function getWindowPages(windowRecord, previewMode) {
    const maxLinesPerPage = 6;
    const pages = [];
    let currentPage = [];
    let linesUsed = 0;

    for (const record of windowRecord.records) {
      const speaker = getLineSpeaker(record);
      const textLines = splitPreviewLines(getLinePreviewText(record, previewMode));
      let cursor = 0;

      while (cursor < textLines.length) {
        if (linesUsed >= maxLinesPerPage) {
          pages.push(currentPage);
          currentPage = [];
          linesUsed = 0;
        }

        const remaining = maxLinesPerPage - linesUsed;
        const take = Math.max(1, Math.min(remaining, textLines.length - cursor));
        const chunk = textLines.slice(cursor, cursor + take);
        currentPage.push({
          speaker: cursor === 0 || linesUsed === 0 ? speaker : "",
          text: chunk.join("\n"),
          offset: record.offset,
          color: getLineColor(record),
        });
        linesUsed += take;
        cursor += take;
      }
    }

    if (currentPage.length || !pages.length) {
      pages.push(currentPage);
    }

    return pages;
  }

  function getDisplayWindowText(windowRecord, previewMode) {
    return windowRecord.records
      .map((record) => {
        const speaker = getLineSpeaker(record);
        const text = getLinePreviewText(record, previewMode);
        return speaker ? `${speaker}: ${text}` : text;
      })
      .join("\n");
  }

  function buildSceneLip(windowRecord, pageCount) {
    const command = windowRecord.command || "(continued window)";
    if (pageCount > 1) {
      return `${command}    <${state.currentPage + 1}/${pageCount}>`;
    }
    return command;
  }

  function getLinePreviewText(record, previewMode) {
    if (previewMode === "japanese") {
      return normalizePreviewText(record.windowTextJapanese || record.japanese);
    }
    if (previewMode === "english") {
      return normalizePreviewText(record.windowTextEnglish || record.english || "");
    }
    return normalizePreviewText(record.windowTextTypeset || record.englishTypeset || record.english || "");
  }

  function getLineSpeaker(record) {
    const commandSpeaker = getCommandSpeaker(record.command);
    if (commandSpeaker) {
      return commandSpeaker;
    }
    const speaker = (record.dialogueMetadata?.speaker || "").trim();
    if (!speaker || speaker === "Narration") {
      return "";
    }
    return speaker;
  }

  function getCommandSpeaker(command) {
    const match = String(command || "").match(/Talk - ([^(]+)/);
    if (!match) {
      return "";
    }
    return match[1].trim();
  }

  function getLineColor(record) {
    return (record.dialogueMetadata?.text_color || "White").trim();
  }

  function currentWindow() {
    return state.filteredWindows[state.currentIndex] || null;
  }

  function renderPointerContexts(contexts) {
    if (!contexts.length) {
      return "<div class='record-subline'>No pointer contexts found for this window.</div>";
    }

    return contexts
      .map((context) => {
        const labels = context.heuristics?.labels || [];
        const ops = context.recognized_ops || [];
        return `
          <article class="pointer-card">
            <strong>${escapeHtml(context.pointer_location)}</strong>
            <div class="tag-list">${labels.map((label) => `<span class="tag">${escapeHtml(label)}</span>`).join("")}</div>
            <div class="record-subline">${escapeHtml(context.comments || "No extra note")}</div>
            <div><strong>Current:</strong> ${escapeHtml(formatOp(context.current_command))}</div>
            <div><strong>Recognized ops nearby:</strong></div>
            <ul class="op-list">
              ${ops.length ? ops.map((op) => `<li>${escapeHtml(formatOp(op))}</li>`).join("") : "<li>(none)</li>"}
            </ul>
            <div class="record-subline">Raw window: ${escapeHtml(context.raw_window || "")}</div>
          </article>
        `;
      })
      .join("");
  }

  function formatOp(op) {
    if (!op) return "(unparsed)";
    const details = op.details || {};
    if (op.kind === "text") {
      return `show text at ${details.text_location} (arg=${details.arg})`;
    }
    if (op.kind === "set_flag") {
      return `set flag offset=${details.arg1} bit=${details.arg2}`;
    }
    if (op.kind === "check_flag") {
      return `check flag offset=${details.arg1} bit=${details.arg2}`;
    }
    if (op.kind === "clear_flag") {
      return `clear flag payload=${(details.payload || []).join(", ")}`;
    }
    return `${op.kind}: ${op.raw || ""}`;
  }

  function refreshActionSelectors(resetTarget = true) {
    const matrix = commandMatrix[state.action.file] || { actions: {} };
    const actions = Object.keys(matrix.actions || {});
    populateSelect(els.actionSelect, actions, "Select action");

    if (!actions.includes(state.action.action)) {
      state.action.action = actions[0] || "";
    }
    els.actionSelect.value = state.action.action;

    const targets = Object.keys((matrix.actions || {})[state.action.action] || {});
    populateSelect(els.targetSelect, targets, "Select target");
    if (resetTarget || !targets.includes(state.action.target)) {
      state.action.target = targets[0] || "";
    }
    els.targetSelect.value = state.action.target;
    renderActionExplorer();
  }

  function renderActionExplorer() {
    const matrix = commandMatrix[state.action.file] || { actions: {} };
    const actionBucket = (matrix.actions || {})[state.action.action] || {};
    const targetBucket = actionBucket[state.action.target] || { nodes: [], room_transitions: [], event_transitions: [], flags: [] };
    const fileGraph = stateGraph.files[state.action.file] || { edge_count: 0 };

    els.actionSummary.innerHTML = renderSummaryCards([
      summaryCard("File", formatOptionalFileLabel(state.action.file)),
      summaryCard("Action", state.action.action || "(none)"),
      summaryCard("Target", state.action.target || "(none)"),
      summaryCard("Matching nodes", String(targetBucket.nodes.length)),
      summaryCard("File edges", String(fileGraph.edge_count || 0)),
      summaryCard("Outgoing transitions", String(targetBucket.room_transitions.length + targetBucket.event_transitions.length)),
    ]);

    if (!targetBucket.nodes.length) {
      els.actionNodes.innerHTML = "<div class='record-subline'>No nodes for this action/target yet.</div>";
      return;
    }

    els.actionNodes.innerHTML = targetBucket.nodes
      .map((node) => renderNodeCard(node, {
        roomTransitions: targetBucket.room_transitions,
        eventTransitions: targetBucket.event_transitions,
        flags: targetBucket.flags,
      }))
      .join("");
  }

  function renderFileMap() {
    const summary = stateGraph.global_summary || {};
    els.fileMapSummary.innerHTML = renderSummaryCards([
      summaryCard("Files", String(summary.file_count || 0)),
      summaryCard("Nodes", String(summary.node_count || 0)),
      summaryCard("Edges", String(summary.edge_count || 0)),
      summaryCard("Dispatch edges", String(summary.dispatch_edge_count || 0)),
      summaryCard("Event transitions", String(summary.event_transition_edge_count || 0)),
      summaryCard("Room transitions", String(summary.room_transition_edge_count || 0)),
    ]);

    const cards = (acceptance.files || [])
      .map((fileSummary) => {
        const graphFile = stateGraph.files[fileSummary.file] || {};
        const matrixFile = commandMatrix[fileSummary.file] || { action_count: 0 };
        return `
          <article class="info-card readiness-${escapeHtml(fileSummary.readiness)}">
            <div class="card-header">
              <strong>${escapeHtml(formatFileLabel(fileSummary.file))}</strong>
              <span class="chip readiness-chip">${escapeHtml(fileSummary.readiness)}</span>
            </div>
            <div class="mini-meta">
              <span>${escapeHtml(String(graphFile.node_count || 0))} nodes</span>
              <span>${escapeHtml(String(graphFile.edge_count || 0))} edges</span>
              <span>${escapeHtml(String(matrixFile.action_count || 0))} actions</span>
            </div>
            <div class="mini-meta">
              <span>${escapeHtml(formatRouteKnownCoverage(fileSummary))} route-known</span>
              <span>${escapeHtml(String(fileSummary.conditional_count || 0))} conditional</span>
              <span>${escapeHtml(String((fileSummary.destinations || []).length))} destinations</span>
            </div>
            <div class="tag-list">${(fileSummary.destinations || []).slice(0, 6).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("") || "<span class='record-subline'>(no known destinations)</span>"}</div>
          </article>
        `;
      });
    els.fileMapCards.innerHTML = renderFileBuckets(acceptance.files || [], cards, "No file summaries.");
  }

  function renderHeatmap() {
    els.heatmapSummary.innerHTML = renderSummaryCards([
      summaryCard("Strong", String((acceptance.ready_files || []).length), "strong"),
      summaryCard("Partial", String((acceptance.partial_files || []).length), "partial"),
      summaryCard("Weak", String((acceptance.weak_files || []).length), "weak"),
      summaryCard("Top weak file", acceptance.weak_files?.[0] || "(none)"),
    ]);

    const cards = (acceptance.files || [])
      .map((item) => {
        const intensity = Math.min(1, (item.trigger_unknown_count || 0) / 24);
        return `
          <article class="heatmap-cell readiness-${escapeHtml(item.readiness)}" style="--heat:${intensity.toFixed(2)}">
            <strong>${escapeHtml(formatFileLabel(item.file))}</strong>
            <div class="record-subline">${escapeHtml(item.readiness)}</div>
            <div class="mini-meta">
              <span>${escapeHtml(formatRouteKnownCoverage(item))} route-known</span>
              <span>${escapeHtml(String(item.conditional_count || 0))} conditional</span>
              <span>${escapeHtml(String(item.room_transition_edge_count || 0))} room transitions</span>
              <span>${escapeHtml(String(item.event_transition_edge_count || 0))} event transitions</span>
            </div>
          </article>
        `;
      });
    els.heatmapGrid.innerHTML = renderFileBuckets(acceptance.files || [], cards, "No readiness data.");
  }

  function renderGraphView() {
    const fileGraph = stateGraph.files[state.graph.file];
    if (!fileGraph) {
      els.graphSummary.innerHTML = "";
      els.graphSvg.innerHTML = "";
      return;
    }

    const graphModel = buildGraphRenderModel(fileGraph);
    if (!state.graph.selectedNodeId || !graphModel.nodes.some((node) => node.id === state.graph.selectedNodeId)) {
      state.graph.selectedNodeId = graphModel.nodes[0]?.id || "";
    }

    els.graphSummary.innerHTML = renderSummaryCards([
      summaryCard("File", formatOptionalFileLabel(state.graph.file)),
      summaryCard("Nodes", String(fileGraph.node_count || 0)),
      summaryCard("Edges", String(fileGraph.edge_count || 0)),
      summaryCard("Dispatch", String(fileGraph.dispatch_edge_count || 0)),
      summaryCard("Dependencies", String(graphModel.dependencyEdges.length)),
      summaryCard("Walkthrough hints", String(graphModel.walkthroughHintEdges.length)),
      summaryCard("Conditional", String(fileGraph.nodes.filter((node) => node.route_status === "conditional").length)),
      summaryCard("Trigger-unknown", String(fileGraph.nodes.filter((node) => node.route_status === "unknown").length)),
      summaryCard("Shown", `${graphModel.nodes.length}${fileGraph.nodes.length > graphModel.nodes.length ? ` / ${fileGraph.nodes.length}` : ""}`),
    ]);

    renderGraphSvg(graphModel);
  }

  function renderGraphSvg(graphModel) {
    const legendY = 42;
    const laneTop = 76;
    const lanePaddingX = 24;
    const lanePaddingY = 18;
    const laneHeaderHeight = 84;
    const sourceBox = { width: 300, height: 46 };
    const nodeBox = { width: 330, height: 74 };
    const destinationBox = { width: 320, height: 46 };
    const columnGap = 72;
    const levelGap = 44;
    const nodeGap = 18;
    const destinationGap = 14;
    const leftMargin = 56;
    const rightMargin = 56;
    const width = Math.max(1600, leftMargin + rightMargin + graphModel.columns.length * (nodeBox.width + columnGap));
    const laneLayouts = new Map();
    const blockPositions = new Map();
    const sourcePositions = new Map();
    const destinationPositions = new Map();
    let maxBottom = laneTop + 640;

    graphModel.columns.forEach((column, columnIndex) => {
      const laneX = leftMargin + columnIndex * (nodeBox.width + columnGap);
      const laneWidth = nodeBox.width + lanePaddingX * 2;
      const sourcePos = {
        x: laneX + (laneWidth - sourceBox.width) / 2,
        y: laneTop + lanePaddingY + 28,
        width: sourceBox.width,
        height: sourceBox.height,
      };
      sourcePositions.set(column.id, sourcePos);

      let currentY = sourcePos.y + sourcePos.height + 28;
      const nodesByLevel = new Map();
      column.nodes.forEach((node) => {
        const level = graphModel.levelByNode.get(node.id) || 0;
        if (!nodesByLevel.has(level)) {
          nodesByLevel.set(level, []);
        }
        nodesByLevel.get(level).push(node);
      });

      Array.from(nodesByLevel.keys()).sort((a, b) => a - b).forEach((level) => {
        if (currentY > sourcePos.y + sourcePos.height + 28) {
          currentY += levelGap;
        }
        for (const node of nodesByLevel.get(level)) {
          const pos = {
            x: laneX + lanePaddingX,
            y: currentY,
            width: nodeBox.width,
            height: nodeBox.height,
          };
          blockPositions.set(node.id, pos);
          currentY += nodeBox.height + nodeGap;
        }
      });

      currentY += 18;
      column.destinations.forEach((destination, destinationIndex) => {
        const pos = {
          x: laneX + (laneWidth - destinationBox.width) / 2,
          y: currentY + destinationIndex * (destinationBox.height + destinationGap),
          width: destinationBox.width,
          height: destinationBox.height,
        };
        destinationPositions.set(destination.id, pos);
      });

      const laneHeight = Math.max(
        620,
        (column.destinations.length
          ? currentY + column.destinations.length * (destinationBox.height + destinationGap) - destinationGap + lanePaddingY
          : currentY + lanePaddingY),
      );
      maxBottom = Math.max(maxBottom, laneTop + laneHeight);
      laneLayouts.set(column.id, {
        x: laneX,
        y: laneTop,
        width: laneWidth,
        height: laneHeight,
      });
    });

    const totalHeight = Math.max(760, maxBottom + 40);
    els.graphSvg.setAttribute("viewBox", `0 0 ${width} ${totalHeight}`);
    els.graphSvg.setAttribute("width", String(width));
    els.graphSvg.setAttribute("height", String(totalHeight));

    const parts = [];
    parts.push(renderGraphDefs());
    parts.push(`<text x="64" y="${legendY}" class="graph-column-title">Action lanes -> prerequisite stacks -> transitions</text>`);
    parts.push(`<text x="${Math.min(width - 620, 860)}" y="${legendY}" class="graph-legend">Lane = shared action/target group · Gold = flag dependency · Orange dashed = walkthrough hint · Green = room transition · Purple = event transition</text>`);

    graphModel.columns.forEach((column) => {
      const lane = laneLayouts.get(column.id);
      parts.push(`
        <g class="graph-lane">
          <rect x="${lane.x}" y="${lane.y}" rx="14" ry="14" width="${lane.width}" height="${lane.height}" />
          <text x="${lane.x + 18}" y="${lane.y + 24}" class="graph-lane-title">${escapeHtmlText(column.action)}</text>
          <text x="${lane.x + 18}" y="${lane.y + 42}" class="graph-lane-subtitle">${escapeHtmlText(column.target)}</text>
          <text x="${lane.x + 18}" y="${lane.y + 62}" class="graph-lane-subtitle">${escapeHtmlText(`${column.nodes.length} blocks · ${column.destinations.length} exits`)}</text>
        </g>
      `);
    });

    for (const edge of graphModel.dependencyEdges) {
      const fromPos = blockPositions.get(edge.from_node);
      const toPos = blockPositions.get(edge.to_node);
      if (!fromPos || !toPos) continue;
      const selected = edge.from_node === state.graph.selectedNodeId || edge.to_node === state.graph.selectedNodeId;
      parts.push(renderGraphEdgeVertical(
        fromPos.x + fromPos.width / 2,
        fromPos.y + fromPos.height,
        toPos.x + toPos.width / 2,
        toPos.y,
        selected ? "#ffd97a" : "#e2b85f",
        "graph-arrow-dependency",
        selected ? "graph-edge-dependency graph-edge-selected" : "graph-edge-dependency",
      ));
      const label = summarizeDependencyLabel(edge.flags);
      if (label) {
        const midX = (fromPos.x + fromPos.width / 2 + toPos.x + toPos.width / 2) / 2;
        const midY = (fromPos.y + fromPos.height + toPos.y) / 2 - 8;
        parts.push(`<text x="${midX}" y="${midY}" text-anchor="middle" class="graph-edge-label">${escapeHtmlText(label)}</text>`);
      }
    }

    for (const edge of graphModel.walkthroughHintEdges) {
      const fromPos = blockPositions.get(edge.from_node);
      const toPos = blockPositions.get(edge.to_node);
      if (!fromPos || !toPos) continue;
      const selected = edge.from_node === state.graph.selectedNodeId || edge.to_node === state.graph.selectedNodeId;
      parts.push(renderGraphEdgeVertical(
        fromPos.x + fromPos.width / 2,
        fromPos.y + fromPos.height,
        toPos.x + toPos.width / 2,
        toPos.y,
        selected ? "#ffd1a3" : "#ffb566",
        "graph-arrow-walkthrough",
        selected ? "graph-edge-walkthrough graph-edge-selected" : "graph-edge-walkthrough",
      ));
    }

    for (const edge of graphModel.transitionEdges) {
      const block = blockPositions.get(edge.from_node);
      const destination = destinationPositions.get(edge.destination_id);
      if (!block || !destination) continue;
      parts.push(renderGraphEdgeVertical(
        block.x + block.width / 2,
        block.y + block.height,
        destination.x + destination.width / 2,
        destination.y,
        edge.type === "room_transition" ? "#70d79d" : "#d79bff",
        edge.type === "room_transition" ? "graph-arrow-room" : "graph-arrow-event",
      ));
    }

    graphModel.columns.forEach((column) => {
      const pos = sourcePositions.get(column.id);
      parts.push(`
        <g class="graph-side-node">
          <rect x="${pos.x}" y="${pos.y}" rx="10" ry="10" width="${pos.width}" height="${pos.height}" />
          <text x="${pos.x + 14}" y="${pos.y + 18}" class="graph-side-title">${escapeHtmlText(column.action)}</text>
          <text x="${pos.x + 14}" y="${pos.y + 34}" class="graph-side-subtitle">${escapeHtmlText(column.target)}</text>
        </g>
      `);
    });

    graphModel.nodes.forEach((node) => {
      const pos = blockPositions.get(node.id);
      const selected = node.id === state.graph.selectedNodeId;
      const classes = [
        "graph-node",
        node.event_transitions.length || node.room_transitions.length ? "graph-node-special" : "",
        node.flag_gates.length ? "graph-node-flagged" : "",
        (
          graphModel.prereqMap.get(node.id)?.length ||
          graphModel.unlockMap.get(node.id)?.length ||
          graphModel.hintPrereqMap.get(node.id)?.length ||
          graphModel.hintUnlockMap.get(node.id)?.length
        ) ? "graph-node-dependent" : "",
        selected ? "graph-node-selected" : "",
      ].filter(Boolean).join(" ");
      const triggerSummary = summarizeNodeTriggerLine(node);
      const flowSummary = summarizeNodeFlowLine(node, graphModel);
      const triggerBadge = summarizeNodeTriggerBadge(node);

      parts.push(`
        <g class="${classes}" data-node-id="${escapeAttribute(node.id)}">
          <rect x="${pos.x}" y="${pos.y}" rx="10" ry="10" width="${pos.width}" height="${pos.height}" />
          <text x="${pos.x + 16}" y="${pos.y + 20}" class="graph-node-title">${escapeHtmlText(node.block_command || "(unnamed block)")}</text>
          <text x="${pos.x + 16}" y="${pos.y + 38}" class="graph-node-subtitle">${escapeHtmlText(triggerSummary)}</text>
          <text x="${pos.x + 16}" y="${pos.y + 56}" class="graph-node-flow">${escapeHtmlText(flowSummary)}</text>
          <text x="${pos.x + pos.width - 16}" y="${pos.y + 20}" text-anchor="end" class="graph-node-badges">${escapeHtmlText(`${node.start_offset} · ${node.route_status} / ${node.route_role}`)}</text>
          <text x="${pos.x + pos.width - 16}" y="${pos.y + 56}" text-anchor="end" class="graph-node-trigger-badge">${escapeHtmlText(triggerBadge)}</text>
        </g>
      `);
    });

    graphModel.columns.forEach((column) => {
      column.destinations.forEach((destination) => {
        const pos = destinationPositions.get(destination.id);
        parts.push(`
          <g class="graph-side-node ${destination.kind === "room_transition" ? "graph-side-room" : "graph-side-event"}">
            <rect x="${pos.x}" y="${pos.y}" rx="10" ry="10" width="${pos.width}" height="${pos.height}" />
            <text x="${pos.x + 14}" y="${pos.y + 18}" class="graph-side-title">${escapeHtmlText(destination.kind === "room_transition" ? "Room transition" : "Event transition")}</text>
            <text x="${pos.x + 14}" y="${pos.y + 34}" class="graph-side-subtitle">${escapeHtmlText(destination.label)}</text>
          </g>
        `);
      });
    });

    els.graphSvg.innerHTML = parts.join("");
    els.graphSvg.querySelectorAll("[data-node-id]").forEach((element) => {
      element.addEventListener("click", () => {
        state.graph.selectedNodeId = element.dataset.nodeId;
        renderGraphView();
      });
    });
  }

  function renderGraphDefs() {
    return `
      <defs>
        <marker id="graph-arrow-dependency" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#e2b85f" />
        </marker>
        <marker id="graph-arrow-walkthrough" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#ffb566" />
        </marker>
        <marker id="graph-arrow-room" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#70d79d" />
        </marker>
        <marker id="graph-arrow-event" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#d79bff" />
        </marker>
      </defs>
    `;
  }

  function renderGraphEdgeVertical(x1, y1, x2, y2, color, markerId, extraClass = "") {
    const midY = y1 + (y2 - y1) * 0.5;
    return `<path d="M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}" class="${extraClass}" fill="none" stroke="${color}" stroke-width="2.6" stroke-linecap="round" opacity="0.92" marker-end="url(#${markerId})" />`;
  }

  function buildGraphRenderModel(fileGraph) {
    const allNodes = fileGraph.nodes || [];
    const dependencyEdges = buildFlagDependencyEdges(allNodes);
    const walkthroughHintEdges = (fileGraph.walkthrough_hint_edges || []).slice();
    const dependencyNodeIds = new Set(dependencyEdges.flatMap((edge) => [edge.from_node, edge.to_node]));
    const walkthroughNodeIds = new Set(walkthroughHintEdges.flatMap((edge) => [edge.from_node, edge.to_node]));
    const interestingNodes = allNodes.filter((node) => (
      node.dispatch_triggers.length ||
      node.event_transitions.length ||
      node.room_transitions.length ||
      node.flag_gates.length ||
      node.route_status === "unknown" ||
      dependencyNodeIds.has(node.id) ||
      walkthroughNodeIds.has(node.id) ||
      (node.walkthrough_steps || []).length
    ));
    const nodes = (interestingNodes.length ? interestingNodes : allNodes).slice(0, 72);
    const nodeIds = new Set(nodes.map((node) => node.id));
    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    const relevantEdges = (fileGraph.edges || []).filter((edge) => {
      if (edge.type === "dispatch") {
        return nodeIds.has(edge.to_node);
      }
      return nodeIds.has(edge.from_node);
    });

    const dispatchGroups = buildDispatchGroups(nodes);
    const sourceMap = new Map(dispatchGroups.map((group) => [group.id, group]));

    const filteredDependencyEdges = dependencyEdges.filter((edge) => nodeIds.has(edge.from_node) && nodeIds.has(edge.to_node));
    const filteredWalkthroughHintEdges = walkthroughHintEdges.filter((edge) => nodeIds.has(edge.from_node) && nodeIds.has(edge.to_node));
    const prereqMap = new Map();
    const unlockMap = new Map();
    filteredDependencyEdges.forEach((edge) => {
      if (!prereqMap.has(edge.to_node)) prereqMap.set(edge.to_node, []);
      if (!unlockMap.has(edge.from_node)) unlockMap.set(edge.from_node, []);
      prereqMap.get(edge.to_node).push(edge);
      unlockMap.get(edge.from_node).push(edge);
    });
    const hintPrereqMap = new Map();
    const hintUnlockMap = new Map();
    filteredWalkthroughHintEdges.forEach((edge) => {
      if (!hintPrereqMap.has(edge.to_node)) hintPrereqMap.set(edge.to_node, []);
      if (!hintUnlockMap.has(edge.from_node)) hintUnlockMap.set(edge.from_node, []);
      hintPrereqMap.get(edge.to_node).push(edge);
      hintUnlockMap.get(edge.from_node).push(edge);
    });

    const layoutEdges = filteredDependencyEdges.concat(filteredWalkthroughHintEdges);
    const levelInfo = computeNodeLevels(nodes, layoutEdges);
    const columnAssignments = assignGraphColumns(nodes, layoutEdges, sourceMap, dispatchGroups);
    const columns = columnAssignments.columns.map((column) => ({
      ...column,
      nodes: column.nodes
        .slice()
        .sort((a, b) => {
          const sequenceDiff = compareNodeSequence(a, b);
          if (sequenceDiff) return sequenceDiff;
          const levelDiff = (levelInfo.levelByNode.get(a.id) || 0) - (levelInfo.levelByNode.get(b.id) || 0);
          if (levelDiff) return levelDiff;
          return parseHexOffset(a.start_offset) - parseHexOffset(b.start_offset);
        }),
      destinations: [],
    }));
    const columnById = new Map(columns.map((column) => [column.id, column]));
    const transitionEdges = [];
    relevantEdges.forEach((edge) => {
      if (edge.type !== "room_transition" && edge.type !== "event_transition") {
        return;
      }
      const columnId = columnAssignments.columnByNode.get(edge.from_node) || columns[0]?.id;
      const destinationId = `${columnId}:${edge.type}:${edge.destination_label || "(unknown destination)"}`;
      const destination = {
        id: destinationId,
        label: edge.destination_label || "(unknown destination)",
        kind: edge.type,
      };
      const column = columnById.get(columnId);
      if (column && !column.destinations.some((item) => item.id === destinationId)) {
        column.destinations.push(destination);
      }
      transitionEdges.push({ ...edge, destination_id: destinationId, column_id: columnId });
    });

    return {
      nodes,
      nodeById,
      dependencyEdges: filteredDependencyEdges,
      walkthroughHintEdges: filteredWalkthroughHintEdges,
      transitionEdges,
      prereqMap,
      unlockMap,
      hintPrereqMap,
      hintUnlockMap,
      columns,
      levelByNode: levelInfo.levelByNode,
    };
  }

  function assignGraphColumns(nodes, dependencyEdges, sourceMap, dispatchGroups) {
    const sourceIds = Array.from(sourceMap.keys()).sort((a, b) => a.localeCompare(b));
    const columnByNode = new Map();
    dispatchGroups.forEach((group) => {
      group.nodeIds.forEach((nodeId) => {
        if (!columnByNode.has(nodeId)) {
          columnByNode.set(nodeId, group.id);
        }
      });
    });

    let changed = true;
    while (changed) {
      changed = false;
      dependencyEdges.forEach((edge) => {
        if (columnByNode.has(edge.to_node)) {
          return;
        }
        const sourceColumn = columnByNode.get(edge.from_node);
        if (sourceColumn) {
          columnByNode.set(edge.to_node, sourceColumn);
          changed = true;
        }
      });
    }

    const ungroupedNodes = nodes.filter((node) => !columnByNode.has(node.id));
    if (ungroupedNodes.length) {
      const fallbackId = "source:(ambiguous)";
      if (!sourceMap.has(fallbackId)) {
        sourceMap.set(fallbackId, {
          id: fallbackId,
          label: "(Ambiguous) / (No unique action)",
          action: "(Ambiguous)",
          target: "(No unique action)",
          nodeIds: [],
        });
        sourceIds.push(fallbackId);
      }
      ungroupedNodes.forEach((node) => {
        columnByNode.set(node.id, fallbackId);
        sourceMap.get(fallbackId).nodeIds.push(node.id);
      });
    }

    const columns = sourceIds.map((sourceId) => ({
      id: sourceId,
      action: sourceMap.get(sourceId)?.action || "(unknown action)",
      target: sourceMap.get(sourceId)?.target || "(unknown target)",
      nodes: nodes.filter((node) => columnByNode.get(node.id) === sourceId),
    })).filter((column) => column.nodes.length);

    return { columns, columnByNode };
  }

  function buildDispatchGroups(nodes) {
    const groups = new Map();
    nodes.forEach((node) => {
      const uniquePairs = getUniqueDispatchPairs(node);
      if (uniquePairs.length !== 1) {
        return;
      }
      const pair = uniquePairs[0];
      const sourceId = `source:${pair.action} / ${pair.target}`;
      if (!groups.has(sourceId)) {
        groups.set(sourceId, {
          id: sourceId,
          label: `${pair.action} / ${pair.target}`,
          action: pair.action,
          target: pair.target,
          nodeIds: [],
        });
      }
      groups.get(sourceId).nodeIds.push(node.id);
    });
    return Array.from(groups.values());
  }

  function getUniqueDispatchPairs(node) {
    const pairMap = new Map();
    (node.dispatch_triggers || []).forEach((trigger) => {
      const action = trigger.action || "(unknown action)";
      const target = trigger.target || "(unknown target)";
      const key = `${action}:::${target}`;
      if (!pairMap.has(key)) {
        pairMap.set(key, { action, target });
      }
    });
    return Array.from(pairMap.values());
  }

  function buildFlagDependencyEdges(nodes) {
    const settersByFlag = new Map();
    nodes.forEach((node) => {
      (node.flag_gates || []).forEach((flag) => {
        if (flag.kind !== "set_flag") return;
        const key = `${flag.arg1}:${flag.arg2}`;
        if (!settersByFlag.has(key)) settersByFlag.set(key, []);
        settersByFlag.get(key).push({ node, flag });
      });
    });

    const edges = [];
    const edgeMap = new Map();
    nodes.forEach((node) => {
      (node.flag_gates || []).forEach((flag) => {
        if (flag.kind !== "check_flag") return;
        const key = `${flag.arg1}:${flag.arg2}`;
        const setters = settersByFlag.get(key) || [];
        setters.forEach(({ node: sourceNode, flag: sourceFlag }) => {
          if (sourceNode.id === node.id) return;
          if (parseHexOffset(sourceNode.start_offset) > parseHexOffset(node.start_offset)) return;
          const edgeKey = `${sourceNode.id}->${node.id}`;
          if (!edgeMap.has(edgeKey)) {
            edgeMap.set(edgeKey, {
              from_node: sourceNode.id,
              to_node: node.id,
              flags: [],
            });
            edges.push(edgeMap.get(edgeKey));
          }
          edgeMap.get(edgeKey).flags.push({
            arg1: flag.arg1,
            arg2: flag.arg2,
            friendly_name: flag.friendly_name || sourceFlag.friendly_name || "",
            confidence: flag.confidence || sourceFlag.confidence || "",
          });
        });
      });
    });
    return edges;
  }

  function computeNodeLevels(nodes, dependencyEdges) {
    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    const indegree = new Map(nodes.map((node) => [node.id, 0]));
    const outgoing = new Map(nodes.map((node) => [node.id, []]));
    dependencyEdges.forEach((edge) => {
      if (!nodeById.has(edge.from_node) || !nodeById.has(edge.to_node)) return;
      indegree.set(edge.to_node, (indegree.get(edge.to_node) || 0) + 1);
      outgoing.get(edge.from_node).push(edge.to_node);
    });

    const levelByNode = new Map();
    const queue = nodes
      .filter((node) => !indegree.get(node.id))
      .sort((a, b) => parseHexOffset(a.start_offset) - parseHexOffset(b.start_offset))
      .map((node) => node.id);

    while (queue.length) {
      const nodeId = queue.shift();
      const currentLevel = levelByNode.get(nodeId) || 0;
      for (const targetId of outgoing.get(nodeId) || []) {
        levelByNode.set(targetId, Math.max(levelByNode.get(targetId) || 0, currentLevel + 1));
        indegree.set(targetId, (indegree.get(targetId) || 0) - 1);
        if (indegree.get(targetId) === 0) {
          queue.push(targetId);
        }
      }
    }

    nodes.forEach((node) => {
      if (!levelByNode.has(node.id)) {
        levelByNode.set(node.id, 0);
      }
    });

    return { levelByNode };
  }

  function summarizeNodeTriggerLine(node) {
    const pairs = getUniqueDispatchPairs(node);
    const triggerLabel = pairs.length === 1
      ? `${pairs[0].action} / ${pairs[0].target}`
      : pairs.length > 1
        ? "Multiple trigger candidates"
        : "No unique action trigger";
    return `${triggerLabel} · ${node.row_count} rows`;
  }

  function summarizeNodeTriggerBadge(node) {
    const pairs = getUniqueDispatchPairs(node);
    if (pairs.length > 1) {
      return "ambiguous trigger";
    }
    if (pairs.length === 1) {
      return "shared trigger lane";
    }
    return "no unique trigger";
  }

  function summarizeNodeFlowLine(node, graphModel) {
    const prereqs = graphModel.prereqMap.get(node.id)?.length || 0;
    const hintPrereqs = graphModel.hintPrereqMap.get(node.id)?.length || 0;
    const unlocks = graphModel.unlockMap.get(node.id)?.length || 0;
    const exits = (node.event_transitions.length || 0) + (node.room_transitions.length || 0);
    return `${prereqs} prerequisite${prereqs === 1 ? "" : "s"} · ${hintPrereqs} walkthrough hint${hintPrereqs === 1 ? "" : "s"} · unlocks ${unlocks} · exits ${exits}`;
  }

  function summarizeDependencyLabel(flags) {
    const label = (flags || [])
      .map((flag) => flag.friendly_name || `${flag.arg1}:${flag.arg2}`)
      .filter(Boolean)[0] || "";
    return truncateText(label.replace(/^STATE_FOR_/, ""), 28);
  }

  function summarizeDependencyPeers(edges, nodeById, key) {
    return edges.map((edge) => {
      const node = nodeById.get(edge[key]);
      const label = summarizeDependencyLabel(edge.flags);
      const name = node?.block_command || node?.start_offset || "(unknown block)";
      return label ? `${name} via ${label}` : name;
    });
  }

  function summarizeWalkthroughPeers(edges, nodeById, key) {
    return edges.map((edge) => {
      const node = nodeById.get(edge[key]);
      const name = node?.block_command || node?.start_offset || "(unknown block)";
      const label = edge.to_step || edge.from_step || "walkthrough";
      return `${name} via ${label}`;
    });
  }

  function parseHexOffset(value) {
    return Number.parseInt(String(value || "0").replace(/^0x/i, ""), 16) || 0;
  }

  function truncateText(text, maxLength) {
    const normalized = String(text || "");
    if (normalized.length <= maxLength) {
      return normalized;
    }
    return `${normalized.slice(0, Math.max(0, maxLength - 1))}\u2026`;
  }

  function compareNodeSequence(a, b) {
    const hintA = getNodeSequenceHint(a);
    const hintB = getNodeSequenceHint(b);
    if (hintA.order !== hintB.order) {
      return hintA.order - hintB.order;
    }
    return hintA.label.localeCompare(hintB.label);
  }

  function getNodeSequenceHint(node) {
    const text = String(node?.block_command || "").trim();
    const numbered = text.match(/\((\d+)\)\s*$/);
    if (numbered) {
      return { order: Number(numbered[1]), label: text };
    }
    const after = text.match(/\bafter\s+(\d+)\b/i);
    if (after) {
      return { order: Number(after[1]) + 0.5, label: text };
    }
    const unused = /\bunused\b/i.test(text);
    if (unused) {
      return { order: 9000, label: text };
    }
    return { order: 1000 + parseHexOffset(node?.start_offset), label: text };
  }

  function renderFlagInspector() {
    const fileGraph = stateGraph.files[state.flags.file];
    if (!fileGraph) {
      els.flagSummary.innerHTML = "";
      els.flagList.innerHTML = "<div class='record-subline'>No flag data for this file.</div>";
      return;
    }

    const flaggedNodes = fileGraph.nodes.filter((node) => node.flag_gates.length);
    const filtered = flaggedNodes.filter((node) => {
      if (!state.flags.query) return true;
      const haystack = [
        node.block_command,
        node.start_offset,
        node.english_preview.join(" "),
        ...node.flag_gates.map((flag) => `${flag.kind} ${flag.arg1} ${flag.arg2} ${flag.friendly_name || ""} ${flag.evidence_summary || ""}`),
      ].join(" ").toLowerCase();
      return haystack.includes(state.flags.query);
    });

    els.flagSummary.innerHTML = renderSummaryCards([
      summaryCard("File", formatOptionalFileLabel(state.flags.file)),
      summaryCard("Flagged nodes", String(flaggedNodes.length)),
      summaryCard("Matches", String(filtered.length)),
      summaryCard("Search", state.flags.query || "(none)"),
    ]);

    els.flagList.innerHTML = filtered.length
      ? filtered.map((node) => renderNodeCard(node, {
        roomTransitions: node.room_transitions.map((item) => item.destination_label),
        eventTransitions: node.event_transitions.map((item) => item.destination_label),
        flags: node.flag_gates,
      })).join("")
      : "<div class='record-subline'>No flag-gated nodes match the current search.</div>";
  }

  function refreshRouteSelectors(resetTarget = true) {
    const matrix = commandMatrix[state.route.file] || { actions: {} };
    const actions = Object.keys(matrix.actions || {});
    populateSelect(els.routeActionSelect, actions, "Select action");
    if (!actions.includes(state.route.action)) {
      state.route.action = actions[0] || "";
    }
    els.routeActionSelect.value = state.route.action;

    const targets = Object.keys((matrix.actions || {})[state.route.action] || {});
    populateSelect(els.routeTargetSelect, targets, "Select target");
    if (resetTarget || !targets.includes(state.route.target)) {
      state.route.target = targets[0] || "";
    }
    els.routeTargetSelect.value = state.route.target;
    renderRouteBuilder();
  }

  function addRouteStep() {
    if (!state.route.file || !state.route.action || !state.route.target) {
      return;
    }
    const matrix = commandMatrix[state.route.file] || { actions: {} };
    const bucket = ((matrix.actions || {})[state.route.action] || {})[state.route.target];
    if (!bucket) {
      return;
    }
    state.route.steps.push({
      file: state.route.file,
      action: state.route.action,
      target: state.route.target,
      bucket,
    });
    renderRouteBuilder();
  }

  function renderRouteBuilder() {
    const matrix = commandMatrix[state.route.file] || { actions: {} };
    const currentBucket = ((matrix.actions || {})[state.route.action] || {})[state.route.target] || { nodes: [], room_transitions: [], event_transitions: [], flags: [] };

    els.routeSummary.innerHTML = renderSummaryCards([
      summaryCard("Current file", formatOptionalFileLabel(state.route.file)),
      summaryCard("Current action", state.route.action || "(none)"),
      summaryCard("Current target", state.route.target || "(none)"),
      summaryCard("Candidate nodes", String(currentBucket.nodes.length)),
      summaryCard("Route steps", String(state.route.steps.length)),
    ]);

    const cards = [];
    cards.push(`
      <article class="info-card">
        <div class="card-header">
          <strong>Current selection</strong>
          <span class="chip">${escapeHtml(`${state.route.action || "(action)"} / ${state.route.target || "(target)"}`)}</span>
        </div>
        <div class="mini-meta">
          <span>${escapeHtml(String(currentBucket.nodes.length))} nodes</span>
          <span>${escapeHtml(String((currentBucket.room_transitions || []).length))} room transitions</span>
          <span>${escapeHtml(String((currentBucket.event_transitions || []).length))} event transitions</span>
        </div>
        ${renderTransitionSection("Room transitions", currentBucket.room_transitions)}
        ${renderTransitionSection("Event transitions", currentBucket.event_transitions)}
      </article>
    `);

    state.route.steps.forEach((step, index) => {
      cards.push(`
        <article class="info-card">
            <div class="card-header">
              <strong>Step ${index + 1}</strong>
              <span class="chip">${escapeHtml(`${formatFileLabel(step.file)} · ${step.action} / ${step.target}`)}</span>
            </div>
          <div class="mini-meta">
            <span>${escapeHtml(String(step.bucket.nodes.length))} nodes</span>
            <span>${escapeHtml(String((step.bucket.room_transitions || []).length))} room transitions</span>
            <span>${escapeHtml(String((step.bucket.event_transitions || []).length))} event transitions</span>
          </div>
          ${renderTransitionSection("Room transitions", step.bucket.room_transitions)}
          ${renderTransitionSection("Event transitions", step.bucket.event_transitions)}
          <div class="card-stack compact">
            ${step.bucket.nodes.slice(0, 4).map((node) => renderNodeCard(node, {
              roomTransitions: step.bucket.room_transitions,
              eventTransitions: step.bucket.event_transitions,
              flags: step.bucket.flags,
            })).join("")}
          </div>
        </article>
      `);
    });

    els.routeTimeline.innerHTML = cards.join("");
  }

  function renderNodeCard(node, extra = {}) {
    return `
      <article class="info-card">
        <div class="card-header">
          <strong>${escapeHtml(node.block_command || "(unnamed block)")}</strong>
          <span class="chip">${escapeHtml(node.start_offset || node.id || "")}</span>
        </div>
        <div class="mini-meta">
          <span>${escapeHtml(String(node.row_count || 0))} rows</span>
          <span>${escapeHtml(String((node.dispatch_triggers || []).length || 0))} dispatch</span>
          <span>${escapeHtml(String((extra.flags || node.flag_gates || []).length || 0))} flags</span>
          <span>${escapeHtml(String((node.walkthrough_steps || []).length || 0))} walkthrough</span>
          <span>${escapeHtml(node.route_status || "")}</span>
          <span>${escapeHtml(node.route_role || "")}</span>
        </div>
        ${renderChipSection("Display", node.display_types)}
        ${renderChipSection("Commands", node.commands)}
        ${renderChipSection("Walkthrough", (node.walkthrough_steps || []).map((item) => `${item.heading_en || item.heading_jp}: ${item.step_label}`))}
        ${renderChipSection("Walkthrough prior steps", node.walkthrough_prior_steps || [])}
        ${renderTransitionSection("Room transitions", extra.roomTransitions || node.room_transitions || [])}
        ${renderTransitionSection("Event transitions", extra.eventTransitions || node.event_transitions || [])}
        ${renderChipSection("Unlocked by", extra.prerequisites || [])}
        ${renderChipSection("Unlocks", extra.unlocks || [])}
        ${renderFlagSection(extra.flags || node.flag_gates || [])}
        ${renderPreviewSection(node.english_preview || [])}
      </article>
    `;
  }

  function renderChipSection(label, values) {
    const items = (values || []).filter(Boolean);
    return `
      <div class="section-block">
        <strong>${escapeHtml(label)}</strong>
        <div class="tag-list">
          ${items.length ? items.map((item) => `<span class="tag">${escapeHtml(typeof item === "string" ? item : JSON.stringify(item))}</span>`).join("") : "<span class='record-subline'>(none)</span>"}
        </div>
      </div>
    `;
  }

  function renderTransitionSection(label, values) {
    const items = normalizeTransitionEntries(values);
    const previews = items.filter((item) => item.capture);
    return `
      <div class="section-block">
        <strong>${escapeHtml(label)}</strong>
        <div class="tag-list">
          ${items.length ? items.map((item) => `<span class="tag">${escapeHtml(item.label)}</span>`).join("") : "<span class='record-subline'>(none)</span>"}
        </div>
        ${previews.length ? `
          <div class="transition-preview-list">
            ${previews.map((item) => `
              <figure class="transition-preview">
                <img src="${escapeAttribute(normalizeAssetPath(item.capture.image))}" alt="${escapeAttribute(item.label)}">
                <figcaption>${escapeHtml(item.label)}</figcaption>
              </figure>
            `).join("")}
          </div>
        ` : ""}
      </div>
    `;
  }

  function normalizeTransitionEntries(values) {
    return (values || [])
      .filter(Boolean)
      .map((item) => {
        const label = typeof item === "string"
          ? item
          : item.destination_label || item.label || JSON.stringify(item);
        return {
          label,
          capture: locationCaptureByDestinationLabel.get(label) || null,
        };
      });
  }

  function normalizeAssetPath(path) {
    const text = String(path || "");
    return text.startsWith("script_viewer/") ? text.slice("script_viewer/".length) : text;
  }

  function renderFlagSection(flags) {
    if (!flags.length) {
      return `
        <div class="section-block">
          <strong>Flags</strong>
          <div class="record-subline">(none)</div>
        </div>
      `;
    }
    return `
      <div class="section-block">
        <strong>Flags</strong>
        <div class="tag-list">
          ${flags.map((flag) => `<span class="tag">${escapeHtml(`${flag.kind} ${flag.friendly_name || `${flag.arg1}:${flag.arg2}`}`)}</span>`).join("")}
        </div>
        <div class="card-stack compact">
          ${flags.map((flag) => `
            <div class="record-subline">
              <strong>${escapeHtml(flag.friendly_name || `${flag.arg1}:${flag.arg2}`)}</strong>
              (${escapeHtml(flag.kind)}, confidence=${escapeHtml(flag.confidence || "unknown")})
              ${flag.evidence_summary ? `<br>${escapeHtml(flag.evidence_summary)}` : ""}
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }

  function renderPreviewSection(lines) {
    const items = (lines || []).filter(Boolean);
    return `
      <div class="section-block">
        <strong>Preview</strong>
        ${items.length ? items.map((line) => `<div class="record-subline">${escapeHtml(line)}</div>`).join("") : "<div class='record-subline'>(none)</div>"}
      </div>
    `;
  }

  function renderSummaryCards(cards) {
    return cards.map((card) => `
      <article class="summary-card ${card.variant ? `summary-${card.variant}` : ""}">
        <span>${escapeHtml(card.label)}</span>
        <strong>${escapeHtml(card.value)}</strong>
      </article>
    `).join("");
  }

  function summaryCard(label, value, variant = "") {
    return { label, value, variant };
  }

  function formatRouteKnownCoverage(item) {
    const routeKnown = Number(item?.route_known_count || 0);
    const total = Number(item?.node_count || 0);
    return `${routeKnown} / ${total || routeKnown}`;
  }

  function renderFileBuckets(files, cards, emptyMessage) {
    if (!files.length) {
      return `<div class='record-subline'>${escapeHtml(emptyMessage)}</div>`;
    }
    const adventureCards = [];
    const adultCards = [];
    files.forEach((file, index) => {
      if (isAdultFile(file.file)) {
        adultCards.push(cards[index]);
      } else {
        adventureCards.push(cards[index]);
      }
    });
    return [
      renderFileBucketSection("Adventure scenes", adventureCards),
      renderFileBucketSection("H scenes", adultCards),
    ].filter(Boolean).join("");
  }

  function renderFileBucketSection(title, cards) {
    if (!cards.length) {
      return "";
    }
    return `
      <section class="file-bucket">
        <div class="file-bucket-header">
          <h3>${escapeHtml(title)}</h3>
          <span class="record-subline">${escapeHtml(String(cards.length))} files</span>
        </div>
        <div class="card-grid">
          ${cards.join("")}
        </div>
      </section>
    `;
  }

  function metaRow(label, value) {
    return `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`;
  }

  function normalizePreviewText(text) {
    return String(text || "")
      .replace(/\[LN\]/g, "\n")
      .replace(/\[BLANK\]/g, "\n")
      .split("\n")
      .map((line) => line.replace(/\s+$/g, ""))
      .join("\n");
  }

  function splitPreviewLines(text) {
    const lines = normalizePreviewText(text).split("\n");
    return lines.length ? lines : [""];
  }

  function moveSelection(delta) {
    if (!state.filteredWindows.length) return;
    state.currentIndex = (state.currentIndex + delta + state.filteredWindows.length) % state.filteredWindows.length;
    state.currentPage = 0;
    renderList();
    renderCurrent();
  }

  function movePage(delta) {
    const windowRecord = currentWindow();
    if (!windowRecord) return;
    const pages = getWindowPages(windowRecord, els.previewMode.value);
    if (pages.length <= 1) return;
    state.currentPage = (state.currentPage + delta + pages.length) % pages.length;
    renderCurrent();
  }

  async function copyCurrentJson() {
    const windowRecord = currentWindow();
    if (!windowRecord) return;

    const payload = {
      ...windowRecord,
      records: windowRecord.records.map((record) => ({
        ...record,
        windowRecords: (record.windowRecordIds || []).map((id) => recordsById.get(id)).filter(Boolean),
      })),
    };
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
  }

  function onKeyDown(event) {
    if (event.target && ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) {
      return;
    }
    if (state.activeTab !== "script") {
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveSelection(1);
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveSelection(-1);
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      movePage(1);
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      movePage(-1);
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replaceAll("'", "&#39;");
  }

  function escapeHtmlText(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }
})();
