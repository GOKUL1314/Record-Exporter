(() => {
  const MAX_BYTES = 10 * 1024 * 1024;
  const NO_LINK_VALUE = "__none__";

  const state = {
    sessionId: null,
    filename: "",
    sheets: [],
    activeSheet: "",
    columns: [],
    totalRecords: 0,
    linkColumn: NO_LINK_VALUE,
    selectedRecordNumbers: [],
    detailsAbortController: null,
  };

  const els = {
    dropZone: document.getElementById("drop-zone"),
    fileInput: document.getElementById("file-input"),
    browseBtn: document.getElementById("browse-btn"),
    uploadError: document.getElementById("upload-error"),
    uploadLoading: document.getElementById("upload-loading"),
    workbookSummary: document.getElementById("workbook-summary"),
    metaFilename: document.getElementById("meta-filename"),
    sheetSelect: document.getElementById("sheet-select"),
    metaTotalRecords: document.getElementById("meta-total-records"),
    previewTableWrap: document.getElementById("preview-table-wrap"),
    stepConfigure: document.getElementById("step-configure"),
    linkColumnSelect: document.getElementById("link-column-select"),
    selectionForm: document.getElementById("selection-form"),
    selectionInput: document.getElementById("selection-input"),
    showRecordsBtn: document.getElementById("show-records-btn"),
    selectionError: document.getElementById("selection-error"),
    stepDownload: document.getElementById("step-download"),
    downloadHint: document.getElementById("download-hint"),
    downloadLoading: document.getElementById("download-loading"),
    downloadError: document.getElementById("download-error"),
    stepRecords: document.getElementById("step-records"),
    fetchProgressWrap: document.getElementById("fetch-progress-wrap"),
    fetchProgressText: document.getElementById("fetch-progress-text"),
    fetchProgressFill: document.getElementById("fetch-progress-fill"),
    recordsContainer: document.getElementById("records-container"),
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function isHttpUrl(value) {
    return /^https?:\/\/\S+$/i.test(String(value ?? "").trim());
  }

  function formatCellHtml(value) {
    const text = String(value ?? "");
    if (!text) return "<span class=\"muted-empty\">-</span>";
    if (isHttpUrl(text)) {
      const safe = escapeHtml(text.trim());
      return `<a href="${safe}" target="_blank" rel="noopener noreferrer">${safe}</a>`;
    }
    return escapeHtml(text);
  }

  function showBanner(el, message) {
    el.textContent = message;
    el.classList.remove("hidden");
  }

  function hideBanner(el) {
    el.textContent = "";
    el.classList.add("hidden");
  }

  function renderPreviewTable(columns, rows) {
    if (!columns.length) {
      els.previewTableWrap.innerHTML = "<p style=\"padding:12px;margin:0;\">This sheet is empty.</p>";
      return;
    }
    const headerHtml = columns.map((col) => `<th>${escapeHtml(col)}</th>`).join("");
    const bodyHtml = rows.length
      ? rows
          .map((row) => {
            const cells = columns
              .map((col) => `<td>${formatCellHtml(row[col] ?? "")}</td>`)
              .join("");
            return `<tr>${cells}</tr>`;
          })
          .join("")
      : `<tr><td colspan="${columns.length}">No data rows found after header.</td></tr>`;

    els.previewTableWrap.innerHTML = `
      <table>
        <thead><tr>${headerHtml}</tr></thead>
        <tbody>${bodyHtml}</tbody>
      </table>
    `;
  }

  function populateLinkColumns(columns, detected) {
    const options = columns.map(
      (col) => `<option value="${escapeHtml(col)}">${escapeHtml(col)}</option>`
    );
    options.push(`<option value="${NO_LINK_VALUE}">No link column</option>`);
    els.linkColumnSelect.innerHTML = options.join("");
    const target = detected && columns.includes(detected) ? detected : NO_LINK_VALUE;
    els.linkColumnSelect.value = target;
    state.linkColumn = target;
  }

  function applySheetState(sheetName, data) {
    state.activeSheet = sheetName;
    state.columns = data.columns || [];
    state.totalRecords = data.total_records || 0;
    els.metaTotalRecords.textContent = String(state.totalRecords);
    renderPreviewTable(state.columns, data.preview_rows || []);
    populateLinkColumns(state.columns, data.detected_link_column);

    // Clear previous results when sheet changes.
    state.selectedRecordNumbers = [];
    els.recordsContainer.innerHTML = "";
    els.stepRecords.classList.add("hidden");
    els.stepDownload.classList.add("hidden");
    hideBanner(els.selectionError);
  }

  async function handleFileUpload(file) {
    hideBanner(els.uploadError);
    if (!file) return;

    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".xlsx") && !lower.endsWith(".xls")) {
      showBanner(els.uploadError, "Please choose an .xlsx or .xls file.");
      return;
    }
    if (file.size > MAX_BYTES) {
      showBanner(els.uploadError, "File exceeds the 10 MB size limit.");
      return;
    }

    if (state.detailsAbortController) {
      state.detailsAbortController.abort();
    }

    const formData = new FormData();
    formData.append("file", file);

    els.uploadLoading.classList.remove("hidden");
    try {
      const resp = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const payload = await resp.json();
      if (!resp.ok) {
        throw new Error(payload.detail || "Upload failed.");
      }

      state.sessionId = payload.session_id;
      state.filename = payload.filename;
      state.sheets = payload.sheets || [];

      els.metaFilename.textContent = payload.filename;
      els.sheetSelect.innerHTML = state.sheets
        .map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`)
        .join("");
      els.sheetSelect.value = payload.default_sheet;

      applySheetState(payload.default_sheet, payload);

      els.workbookSummary.classList.remove("hidden");
      els.stepConfigure.classList.remove("hidden");
    } catch (err) {
      showBanner(els.uploadError, err.message || "Could not upload file.");
    } finally {
      els.uploadLoading.classList.add("hidden");
    }
  }

  async function handleSheetChange() {
    if (!state.sessionId) return;
    const sheetName = els.sheetSelect.value;
    hideBanner(els.uploadError);

    if (state.detailsAbortController) {
      state.detailsAbortController.abort();
    }

    try {
      const resp = await fetch("/api/sheet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.sessionId,
          sheet_name: sheetName,
        }),
      });
      const payload = await resp.json();
      if (!resp.ok) {
        throw new Error(payload.detail || "Could not read sheet.");
      }
      applySheetState(sheetName, payload);
    } catch (err) {
      showBanner(els.uploadError, err.message || "Could not switch sheet.");
    }
  }

  function renderRecordCards(records, linkColumn) {
    els.recordsContainer.innerHTML = "";

    for (const rec of records) {
      const card = document.createElement("article");
      card.className = "record-card";
      card.id = `record-card-${rec.record_number}`;

      const rowsHtml = Object.entries(rec.fields)
        .map(
          ([field, value]) =>
            `<tr><th>${escapeHtml(field)}</th><td>${formatCellHtml(value)}</td></tr>`
        )
        .join("");

      const initialDetailHtml =
        !linkColumn || linkColumn === NO_LINK_VALUE
          ? "<p class=\"page-loading\">Skipped (no link column selected).</p>"
          : !rec.link_url
            ? "<p class=\"page-loading\">No link URL in this record.</p>"
            : "<p class=\"page-loading\">Loading page details...</p>";

      card.innerHTML = `
        <h3 class="record-card-title">Record ${rec.record_number}</h3>
        <div class="table-scroll">
          <table class="record-kv-table">
            <thead><tr><th>Field</th><th>Value</th></tr></thead>
            <tbody>${rowsHtml}</tbody>
          </table>
        </div>
        <div class="page-details-box" id="page-details-${rec.record_number}">
          <h4 class="page-details-heading">Details from the event page</h4>
          <div class="page-details-body">${initialDetailHtml}</div>
        </div>
      `;

      els.recordsContainer.appendChild(card);
    }
  }

  function updateCardDetails(recordNumber, details) {
    const container = document.querySelector(`#page-details-${recordNumber} .page-details-body`);
    if (!container) return;

    if (details.fetch_status === "skipped") {
      container.innerHTML = "<p class=\"page-loading\">No link provided for this record.</p>";
      return;
    }

    if (details.fetch_status && details.fetch_status.startsWith("Could not fetch:")) {
      container.innerHTML = `<div class="page-error">${escapeHtml(details.fetch_status)}</div>`;
      return;
    }

    const parts = [];
    if (details.title) {
      parts.push(`<p class="page-title-meta"><strong>Page title:</strong> ${escapeHtml(details.title)}</p>`);
    }

    if (details.sections && details.sections.length) {
      for (const sec of details.sections) {
        parts.push(`
          <div class="page-section">
            <h4>${escapeHtml(sec.heading)}</h4>
            <p class="page-section-body">${escapeHtml(sec.content)}</p>
          </div>
        `);
      }
    } else {
      parts.push("<p class=\"page-loading\">No sections found on this page.</p>");
    }

    container.innerHTML = parts.join("");
  }

  async function streamPageDetails(recordNumbers, linkColumn) {
    if (state.detailsAbortController) {
      state.detailsAbortController.abort();
    }
    const controller = new AbortController();
    state.detailsAbortController = controller;

    const total = recordNumbers.length;
    if (!linkColumn || linkColumn === NO_LINK_VALUE) {
      els.fetchProgressWrap.classList.add("hidden");
      return;
    }

    els.fetchProgressWrap.classList.remove("hidden");
    els.fetchProgressText.textContent = `Fetching 0 of ${total}`;
    els.fetchProgressFill.style.width = "0%";

    try {
      const resp = await fetch("/api/details", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.sessionId,
          sheet_name: state.activeSheet,
          record_numbers: recordNumbers,
          link_column: linkColumn,
        }),
        signal: controller.signal,
      });

      if (!resp.ok) {
        const errPayload = await resp.json().catch(() => ({}));
        throw new Error(errPayload.detail || "Failed to fetch page details.");
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          const event = JSON.parse(trimmed);
          if (event.type === "progress") {
            const pct = event.total ? Math.round((event.completed / event.total) * 100) : 100;
            els.fetchProgressText.textContent = `Fetching ${event.completed} of ${event.total}`;
            els.fetchProgressFill.style.width = `${pct}%`;
            updateCardDetails(event.record_number, event.details);
          } else if (event.type === "done") {
            els.fetchProgressText.textContent = `Completed ${event.total} of ${event.total}`;
            els.fetchProgressFill.style.width = "100%";
          }
        }
      }
    } catch (err) {
      if (err.name === "AbortError") return;
      showBanner(els.selectionError, err.message || "Error while fetching page details.");
    }
  }

  async function handleShowRecords(e) {
    e.preventDefault();
    hideBanner(els.selectionError);
    hideBanner(els.downloadError);

    if (!state.sessionId) return;

    const selection = els.selectionInput.value;
    const linkColumn = els.linkColumnSelect.value;
    state.linkColumn = linkColumn;

    els.showRecordsBtn.disabled = true;
    try {
      const resp = await fetch("/api/records", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.sessionId,
          sheet_name: state.activeSheet,
          selection,
          link_column: linkColumn,
        }),
      });
      const payload = await resp.json();
      if (!resp.ok) {
        throw new Error(payload.detail || "Invalid selection.");
      }

      const records = payload.records || [];
      state.selectedRecordNumbers = records.map((r) => r.record_number);

      renderRecordCards(records, payload.link_column);
      els.stepRecords.classList.remove("hidden");
      els.stepDownload.classList.remove("hidden");

      const count = state.selectedRecordNumbers.length;
      els.downloadHint.textContent =
        count === 1
          ? `1 record selected — downloads directly as ${state.selectedRecordNumbers[0]}.<ext>`
          : `${count} records selected — downloads as a ZIP bundle containing ${count} files.`;

      await streamPageDetails(state.selectedRecordNumbers, linkColumn);
    } catch (err) {
      showBanner(els.selectionError, err.message || "Could not load selected records.");
    } finally {
      els.showRecordsBtn.disabled = false;
    }
  }

  function extractDownloadFilename(headerValue, fallbackName) {
    if (!headerValue) return fallbackName;
    const match = /filename="([^"]+)"/i.exec(headerValue);
    return match ? match[1] : fallbackName;
  }

  async function handleDownload(fmt) {
    hideBanner(els.downloadError);
    if (!state.sessionId || !state.selectedRecordNumbers.length) return;

    const buttons = document.querySelectorAll(".btn-export");
    buttons.forEach((b) => (b.disabled = true));
    els.downloadLoading.classList.remove("hidden");

    try {
      const resp = await fetch(`/api/download/${encodeURIComponent(fmt)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.sessionId,
          sheet_name: state.activeSheet,
          record_numbers: state.selectedRecordNumbers,
          link_column: state.linkColumn,
        }),
      });

      if (!resp.ok) {
        const errPayload = await resp.json().catch(() => ({}));
        throw new Error(errPayload.detail || "Download failed.");
      }

      const blob = await resp.blob();
      const fallback =
        state.selectedRecordNumbers.length === 1
          ? `${state.selectedRecordNumbers[0]}.${fmt}`
          : `records_${fmt}.zip`;
      const filename = extractDownloadFilename(
        resp.headers.get("Content-Disposition"),
        fallback
      );

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      showBanner(els.downloadError, err.message || "Could not generate download.");
    } finally {
      els.downloadLoading.classList.add("hidden");
      buttons.forEach((b) => (b.disabled = false));
    }
  }

  // Event bindings
  els.browseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    els.fileInput.click();
  });

  els.dropZone.addEventListener("click", () => els.fileInput.click());
  els.dropZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      els.fileInput.click();
    }
  });

  els.fileInput.addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) handleFileUpload(file);
    e.target.value = "";
  });

  els.dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    els.dropZone.classList.add("drag-over");
  });

  els.dropZone.addEventListener("dragleave", () => {
    els.dropZone.classList.remove("drag-over");
  });

  els.dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    els.dropZone.classList.remove("drag-over");
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) handleFileUpload(file);
  });

  els.sheetSelect.addEventListener("change", handleSheetChange);
  els.linkColumnSelect.addEventListener("change", () => {
    state.linkColumn = els.linkColumnSelect.value;
  });
  els.selectionForm.addEventListener("submit", handleShowRecords);

  document.querySelectorAll(".btn-export").forEach((btn) => {
    btn.addEventListener("click", () => handleDownload(btn.dataset.format));
  });
})();
