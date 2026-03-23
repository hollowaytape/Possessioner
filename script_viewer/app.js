(function () {
  const data = window.PSSR_VIEWER_DATA;
  if (!data) {
    document.body.innerHTML = "<p style='color:white;padding:2rem'>Viewer data was not loaded. Run build_script_viewer_data.py first.</p>";
    return;
  }

  const recordsById = new Map(data.records.map((record) => [record.id, record]));
  const leadRecords = data.records.filter((record) => record.id === record.windowLeadId);
  const displayWindows = buildDisplayWindows(leadRecords);

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
  };

  const state = {
    filters: {
      file: "",
      query: "",
    },
    filteredWindows: [],
    currentIndex: 0,
    currentPage: 0,
  };

  populateSelect(els.fileFilter, data.meta.files, "All files", formatFileLabel);

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

  if (data.meta?.defaultFile && data.meta.files.includes(data.meta.defaultFile)) {
    state.filters.file = data.meta.defaultFile;
    els.fileFilter.value = data.meta.defaultFile;
  }

  document.documentElement.style.setProperty(
    "--typeset-chars-per-line",
    String(data.meta?.screen?.typesetCharsPerLine || 39),
  );

  updateFilters({});

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
    const speakers = [...new Set(records.map((record) => record.dialogueMetadata?.speaker || "").filter(Boolean))];
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
    const options = [`<option value="">${defaultLabel}</option>`]
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
    const speaker = (record.dialogueMetadata?.speaker || "").trim();
    if (!speaker || speaker === "Narration") {
      return "";
    }
    return speaker;
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
})();
