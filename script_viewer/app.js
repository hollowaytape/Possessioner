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
    graphInspector: document.getElementById("graphInspector"),
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
  populateSelect(els.actionFileSelect, graphFiles, "Select file");
  populateSelect(els.graphFileSelect, graphFiles, "Select file");
  populateSelect(els.flagFileSelect, graphFiles, "Select file");
  populateSelect(els.routeFileSelect, graphFiles, "Select file");

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

    els.recordCounter.textContent = `${state.currentIndex + 1} / ${state.filteredWindows.length} · page ${state.currentPage + 1} / ${pages.length || 1}`;
    els.sceneLip.textContent = buildSceneLip(windowRecord, pages.length);
    els.previewText.innerHTML = renderPreviewLines(currentPage);

    els.recordMeta.innerHTML = [
      metaRow("File", windowRecord.file),
      metaRow("Lead offset", windowRecord.offset),
      metaRow("Command", windowRecord.command || "(continued window)"),
      metaRow("Window page", `${state.currentPage + 1} / ${pages.length || 1}`),
      metaRow("Visible lines", windowRecord.offsets.join(", ")),
      metaRow("Worksheet rows", windowRecord.windowOffsets.join(", ")),
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
    const targetBucket = actionBucket[state.action.target] || { nodes: [], destinations: [], handoffs: [], flags: [] };
    const fileGraph = stateGraph.files[state.action.file] || { edge_count: 0 };

    els.actionSummary.innerHTML = renderSummaryCards([
      summaryCard("File", state.action.file || "(none)"),
      summaryCard("Action", state.action.action || "(none)"),
      summaryCard("Target", state.action.target || "(none)"),
      summaryCard("Matching nodes", String(targetBucket.nodes.length)),
      summaryCard("File edges", String(fileGraph.edge_count || 0)),
      summaryCard("Outgoing destinations", String(targetBucket.destinations.length + targetBucket.handoffs.length)),
    ]);

    if (!targetBucket.nodes.length) {
      els.actionNodes.innerHTML = "<div class='record-subline'>No nodes for this action/target yet.</div>";
      return;
    }

    els.actionNodes.innerHTML = targetBucket.nodes
      .map((node) => renderNodeCard(node, {
        destinations: targetBucket.destinations,
        handoffs: targetBucket.handoffs,
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
      summaryCard("Handoff edges", String(summary.handoff_edge_count || 0)),
      summaryCard("Transition edges", String(summary.transition_edge_count || 0)),
    ]);

    els.fileMapCards.innerHTML = (acceptance.files || [])
      .map((fileSummary) => {
        const graphFile = stateGraph.files[fileSummary.file] || {};
        const matrixFile = commandMatrix[fileSummary.file] || { action_count: 0 };
        return `
          <article class="info-card readiness-${escapeHtml(fileSummary.readiness)}">
            <div class="card-header">
              <strong>${escapeHtml(fileSummary.file)}</strong>
              <span class="chip readiness-chip">${escapeHtml(fileSummary.readiness)}</span>
            </div>
            <div class="mini-meta">
              <span>${escapeHtml(String(graphFile.node_count || 0))} nodes</span>
              <span>${escapeHtml(String(graphFile.edge_count || 0))} edges</span>
              <span>${escapeHtml(String(matrixFile.action_count || 0))} actions</span>
            </div>
            <div class="mini-meta">
              <span>${escapeHtml(String(fileSummary.flagged_unattached_count || 0))} flagged hotspots</span>
              <span>${escapeHtml(String((fileSummary.destinations || []).length))} destinations</span>
            </div>
            <div class="tag-list">${(fileSummary.destinations || []).slice(0, 6).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("") || "<span class='record-subline'>(no known destinations)</span>"}</div>
          </article>
        `;
      })
      .join("");
  }

  function renderHeatmap() {
    els.heatmapSummary.innerHTML = renderSummaryCards([
      summaryCard("Strong", String((acceptance.ready_files || []).length), "strong"),
      summaryCard("Partial", String((acceptance.partial_files || []).length), "partial"),
      summaryCard("Weak", String((acceptance.weak_files || []).length), "weak"),
      summaryCard("Top weak file", acceptance.weak_files?.[0] || "(none)"),
    ]);

    els.heatmapGrid.innerHTML = (acceptance.files || [])
      .map((item) => {
        const intensity = Math.min(1, (item.flagged_unattached_count || 0) / 40);
        return `
          <article class="heatmap-cell readiness-${escapeHtml(item.readiness)}" style="--heat:${intensity.toFixed(2)}">
            <strong>${escapeHtml(item.file)}</strong>
            <div class="record-subline">${escapeHtml(item.readiness)}</div>
            <div class="mini-meta">
              <span>${escapeHtml(String(item.unattached_node_count || 0))} unattached</span>
              <span>${escapeHtml(String(item.flagged_unattached_count || 0))} flagged</span>
            </div>
            <div class="mini-meta">
              <span>${escapeHtml(String(item.transition_edge_count || 0))} transitions</span>
              <span>${escapeHtml(String(item.handoff_edge_count || 0))} handoffs</span>
            </div>
          </article>
        `;
      })
      .join("");
  }

  function renderGraphView() {
    const fileGraph = stateGraph.files[state.graph.file];
    if (!fileGraph) {
      els.graphSummary.innerHTML = "";
      els.graphSvg.innerHTML = "";
      els.graphInspector.innerHTML = "<div class='record-subline'>No graph data for this file.</div>";
      return;
    }

    const interestingNodes = fileGraph.nodes.filter((node) => node.dispatch_triggers.length || node.handoffs.length || node.transitions.length || node.flag_gates.length);
    const nodes = (interestingNodes.length ? interestingNodes : fileGraph.nodes).slice(0, 72);
    if (!state.graph.selectedNodeId || !nodes.some((node) => node.id === state.graph.selectedNodeId)) {
      state.graph.selectedNodeId = nodes[0]?.id || "";
    }

    els.graphSummary.innerHTML = renderSummaryCards([
      summaryCard("File", state.graph.file),
      summaryCard("Nodes", String(fileGraph.node_count || 0)),
      summaryCard("Edges", String(fileGraph.edge_count || 0)),
      summaryCard("Dispatch", String(fileGraph.dispatch_edge_count || 0)),
      summaryCard("Special", String((fileGraph.handoff_edge_count || 0) + (fileGraph.transition_edge_count || 0))),
      summaryCard("Shown", `${nodes.length}${fileGraph.nodes.length > nodes.length ? ` / ${fileGraph.nodes.length}` : ""}`),
    ]);

    renderGraphSvg(nodes);
    renderGraphInspector();
  }

  function renderGraphSvg(nodes) {
    const width = 1200;
    const rowHeight = 74;
    const top = 30;
    const left = 180;
    const rectWidth = 720;
    const rectHeight = 48;
    const totalHeight = Math.max(720, top + nodes.length * rowHeight + 40);
    els.graphSvg.setAttribute("viewBox", `0 0 ${width} ${totalHeight}`);

    const parts = [];
    parts.push(`<line x1="120" y1="${top - 12}" x2="120" y2="${top + nodes.length * rowHeight}" stroke="#32425f" stroke-width="2" />`);

    nodes.forEach((node, index) => {
      const y = top + index * rowHeight;
      const selected = node.id === state.graph.selectedNodeId;
      const classes = [
        "graph-node",
        node.handoffs.length || node.transitions.length ? "graph-node-special" : "",
        node.flag_gates.length ? "graph-node-flagged" : "",
        selected ? "graph-node-selected" : "",
      ].filter(Boolean).join(" ");

      parts.push(`<circle cx="120" cy="${y + rectHeight / 2}" r="7" fill="${selected ? "#87b4ff" : "#5a6e93"}" />`);
      parts.push(`<line x1="127" y1="${y + rectHeight / 2}" x2="${left}" y2="${y + rectHeight / 2}" stroke="#4e6184" stroke-width="2" />`);
      parts.push(`
        <g class="${classes}" data-node-id="${escapeAttribute(node.id)}">
          <rect x="${left}" y="${y}" rx="10" ry="10" width="${rectWidth}" height="${rectHeight}" />
          <text x="${left + 16}" y="${y + 20}" class="graph-node-title">${escapeHtmlText(node.block_command || "(unnamed block)")}</text>
          <text x="${left + 16}" y="${y + 36}" class="graph-node-subtitle">${escapeHtmlText(`${node.start_offset} · ${node.row_count} rows · ${node.display_types.join(" / ") || "no display type"}`)}</text>
          <text x="${left + rectWidth - 16}" y="${y + 20}" text-anchor="end" class="graph-node-badges">${escapeHtmlText(`${node.dispatch_triggers.length} dispatch · ${node.flag_gates.length} flags · ${node.handoffs.length + node.transitions.length} exits`)}</text>
        </g>
      `);
    });

    els.graphSvg.innerHTML = parts.join("");
    els.graphSvg.querySelectorAll("[data-node-id]").forEach((element) => {
      element.addEventListener("click", () => {
        state.graph.selectedNodeId = element.dataset.nodeId;
        renderGraphView();
      });
    });
  }

  function renderGraphInspector() {
    const fileGraph = stateGraph.files[state.graph.file];
    const node = (fileGraph?.nodes || []).find((item) => item.id === state.graph.selectedNodeId);
    if (!node) {
      els.graphInspector.innerHTML = "<div class='record-subline'>Select a node to inspect it.</div>";
      return;
    }

    els.graphInspector.innerHTML = renderNodeCard(node, {
      destinations: node.transitions.map((item) => item.destination_label),
      handoffs: node.handoffs.map((item) => item.destination_label),
      flags: node.flag_gates,
    });
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
        ...node.flag_gates.map((flag) => `${flag.kind} ${flag.arg1} ${flag.arg2}`),
      ].join(" ").toLowerCase();
      return haystack.includes(state.flags.query);
    });

    els.flagSummary.innerHTML = renderSummaryCards([
      summaryCard("File", state.flags.file),
      summaryCard("Flagged nodes", String(flaggedNodes.length)),
      summaryCard("Matches", String(filtered.length)),
      summaryCard("Search", state.flags.query || "(none)"),
    ]);

    els.flagList.innerHTML = filtered.length
      ? filtered.map((node) => renderNodeCard(node, {
        destinations: node.transitions.map((item) => item.destination_label),
        handoffs: node.handoffs.map((item) => item.destination_label),
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
    const currentBucket = ((matrix.actions || {})[state.route.action] || {})[state.route.target] || { nodes: [], destinations: [], handoffs: [], flags: [] };

    els.routeSummary.innerHTML = renderSummaryCards([
      summaryCard("Current file", state.route.file || "(none)"),
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
          <span>${escapeHtml(String((currentBucket.destinations || []).length))} transitions</span>
          <span>${escapeHtml(String((currentBucket.handoffs || []).length))} handoffs</span>
        </div>
        ${renderChipSection("Destinations", currentBucket.destinations)}
        ${renderChipSection("Handoffs", currentBucket.handoffs)}
      </article>
    `);

    state.route.steps.forEach((step, index) => {
      cards.push(`
        <article class="info-card">
          <div class="card-header">
            <strong>Step ${index + 1}</strong>
            <span class="chip">${escapeHtml(`${step.file} · ${step.action} / ${step.target}`)}</span>
          </div>
          <div class="mini-meta">
            <span>${escapeHtml(String(step.bucket.nodes.length))} nodes</span>
            <span>${escapeHtml(String((step.bucket.destinations || []).length))} transitions</span>
            <span>${escapeHtml(String((step.bucket.handoffs || []).length))} handoffs</span>
          </div>
          ${renderChipSection("Destinations", step.bucket.destinations)}
          ${renderChipSection("Handoffs", step.bucket.handoffs)}
          <div class="card-stack compact">
            ${step.bucket.nodes.slice(0, 4).map((node) => renderNodeCard(node, {
              destinations: step.bucket.destinations,
              handoffs: step.bucket.handoffs,
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
        </div>
        ${renderChipSection("Display", node.display_types)}
        ${renderChipSection("Commands", node.commands)}
        ${renderChipSection("Destinations", extra.destinations || node.transitions?.map((item) => item.destination_label) || [])}
        ${renderChipSection("Handoffs", extra.handoffs || node.handoffs?.map((item) => item.destination_label) || [])}
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
          ${flags.map((flag) => `<span class="tag">${escapeHtml(`${flag.kind} ${flag.arg1}:${flag.arg2}`)}</span>`).join("")}
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
