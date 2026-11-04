/* Paper preparation uses committed boxes and independent, retryable PDF downloads. */
const paperInstructions = "A4, actual size or 100%, single sided. Cut along the guides and tape one label on the top and one on the side.";
const bulkDraftKey = () => "bulk-boxes:" + me.namespace;
let bulkBusy = false;

function paperDiagram(boxes) {
  const cells = boxes.slice(0, 12).flatMap((box) => [box, box]);
  return `<div class="paper-preview" aria-label="A4 layout preview, four columns and six rows. Each box appears twice in adjacent cells.">${Array.from({ length: 24 }, (_, n) => cells[n] ? `<div class="paper-cell"><strong>${esc(cells[n].name)}</strong><b>${esc(cells[n].code)}</b><span class="paper-qr" aria-hidden="true">QR</span><small>Stash · Room ______</small></div>` : '<div></div>').join("")}</div><p class="muted">Layout preview. The downloaded PDF contains the actual scannable QR codes.</p>`;
}

async function downloadPaper(url, fallback = "stash-box-labels.pdf") {
  const response = await fetch(url, { credentials: "same-origin", headers: { "X-Stash-User": String(me.id) } });
  if (!response.ok) throw Error(response.status === 401 ? "Sign in again, then retry the PDF. Your saved boxes remain in Box batches." : "The PDF could not be downloaded. Your boxes are saved. Retry Download A4 labels.");
  const blob = await response.blob();
  const name = response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] || fallback;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 60000);
}

async function bulkBoxesPanel() {
  const pending = (await drafts()).find((d) => d.id === bulkDraftKey());
  if (pending) {
    modal(`<h2>Resume box creation</h2><p>This device retained a request for ${pending.payload.count} boxes. It may already have reached Stash. Resume checks the same request and cannot create a second batch.</p><button id="bulk-resume" class="primary full">Resume the same request</button><button id="bulk-history" class="secondary full">View saved box batches</button><p id="form-error" role="alert"></p>`);
    $("#bulk-resume").onclick = guard(() => submitBoxBatch(pending));
    $("#bulk-history").onclick = guard(boxBatchesPanel);
    return;
  }
  places = (await api("locations")).locations;
  let proposal, previewVersion = 0;
  modal(`<h2>Create boxes in bulk</h2><p>Twelve boxes fill one A4 sheet with two matching labels per box. Maximum 240 boxes per batch.</p><form id="box-bulk-form"><label>Box quantity<select id="bulk-quantity"><option value="12">12 boxes</option><option value="24">24 boxes</option><option value="36">36 boxes</option><option value="custom">Custom quantity</option></select></label><label id="bulk-custom-label" hidden>Custom box quantity<input id="bulk-custom" type="number" min="1" max="240" value="1"></label><details id="bulk-defaults"><summary>Batch name and shared defaults, optional</summary><label>Batch name, optional<input id="bulk-name" maxlength="160" placeholder="Moving week one"></label><label>Shared current physical location, optional<select id="bulk-place">${options(places, "", "Not set")}</select></label><label>Intended destination room, optional<input id="bulk-destination" maxlength="160"></label></details><p id="bulk-summary" role="status">Loading the preview…</p><button id="bulk-create" class="primary full" disabled>Create 12 boxes and download labels</button><p>Names and numbers shown below are proposed, not reserved. Stash allocates final values when you create the boxes. You can edit any proposed name.</p><div id="bulk-preview"></div><details><summary>Review or change proposed names</summary><div id="bulk-names"></div></details><p>${paperInstructions}</p><p id="form-error" role="alert"></p></form>`);
  const count = () => Number($("#bulk-quantity").value === "custom" ? $("#bulk-custom").value : $("#bulk-quantity").value);
  const summary = () => {
    const n = count();
    const place = places.find((x) => x.id === $("#bulk-place").value)?.path || "Not set";
    $("#bulk-summary").textContent = `${n} boxes · ${n * 2} labels · ${Math.ceil(n / 12)} A4 ${n <= 12 ? "sheet" : "sheets"}. Current location: ${place}. Destination room: ${$("#bulk-destination").value.trim() || "Not set"}.`;
  };
  const preview = async () => {
    const version = ++previewVersion, n = count();
    $("#bulk-custom-label").hidden = $("#bulk-quantity").value !== "custom";
    $("#bulk-create").disabled = true;
    if (!Number.isInteger(n) || n < 1 || n > 240) {
      $("#bulk-summary").textContent = "Choose a whole number from 1 to 240.";
      return;
    }
    const result = await api("box-preview?count=" + n);
    if (version !== previewVersion || !$("#bulk-create")) return;
    proposal = result;
    summary();
    $("#bulk-preview").innerHTML = paperDiagram(result.boxes);
    $("#bulk-names").innerHTML = result.boxes.map((box, index) => `<label>${esc(box.code)} proposed<input data-box-name="${index}" value="${esc(box.name)}" maxlength="160"></label>`).join("");
    $("#bulk-names").oninput = () => {
      const shown = result.boxes.map((box, index) => ({ ...box, name: document.querySelector(`[data-box-name="${index}"]`).value.trim() || box.name }));
      $("#bulk-preview").innerHTML = paperDiagram(shown);
    };
    $("#bulk-create").textContent = `Create ${n} boxes and download labels`;
    $("#bulk-create").disabled = false;
  };
  $("#bulk-quantity").onchange = guard(preview);
  $("#bulk-custom").oninput = guard(preview);
  $("#bulk-place").onchange = summary;
  $("#bulk-destination").oninput = summary;
  $("#box-bulk-form").onsubmit = guard(async (event) => {
    event.preventDefault();
    if (bulkBusy || !proposal || proposal.count !== count()) return;
    const overrides = {};
    document.querySelectorAll("[data-box-name]").forEach((input) => {
      const index = Number(input.dataset.boxName);
      if (input.value.trim() && input.value.trim() !== proposal.boxes[index].name) overrides[index] = input.value.trim();
    });
    const requestId = crypto.randomUUID();
    const pending = { id: bulkDraftKey(), namespace: me.namespace, kind: "box-batch", state: "pending", created: Date.now(),
      payload: { request_id: requestId, count: proposal.count, name: $("#bulk-name").value.trim(), physical_location_id: $("#bulk-place").value || null, destination: $("#bulk-destination").value.trim(), proposed_names: proposal.boxes.map((b) => b.name), name_overrides: overrides } };
    // Save before the first network write. A response loss retains this exact payload and ID.
    bulkBusy = true;
    $("#bulk-create").disabled = true;
    try { await store("put", pending); }
    catch (error) { bulkBusy = false; $("#bulk-create").disabled = false; throw Error("Device storage failed. No boxes were submitted. Try again after allowing browser storage."); }
    bulkBusy = false;
    await submitBoxBatch(pending);
  });
  await preview();
}

async function submitBoxBatch(pending) {
  if (bulkBusy) return;
  if (!navigator.onLine) throw Error("Reconnect, then resume this request. No shared creation is confirmed while offline.");
  bulkBusy = true;
  try {
    const batch = await api("box-batches", pending.payload, pending.payload.request_id);
    await store("delete", pending.id);
    await refresh();
    await showBoxBatch(batch.id);
    try { await downloadPaper(`/api/box-batches/${batch.id}/labels.pdf`); }
    catch (error) { $("#batch-status").textContent = error.message; }
  } catch (error) {
    // Frozen payload stays recoverable even when a timeout hides a committed batch.
    modal(`<h2>Check box creation</h2><p>${esc(error.message)}</p><p>The original request is retained. Resume it instead of starting another batch.</p><button id="bulk-resume" class="primary full">Resume the same request</button><button id="bulk-history" class="secondary full">View saved box batches</button><p id="form-error" role="alert"></p>`);
    $("#bulk-resume").onclick = guard(() => submitBoxBatch(pending));
    $("#bulk-history").onclick = guard(boxBatchesPanel);
    if ([400, 404].includes(error.status)) {
      $("#form-error").innerHTML = '<p>Stash rejected this request before creating any boxes.</p><button id="bulk-correct" class="secondary full">Review settings and try again</button>';
      $("#bulk-correct").onclick = guard(async () => { await store("delete", pending.id); await bulkBoxesPanel(); });
    }
  } finally { bulkBusy = false; }
}

async function boxBatchesPanel() {
  modal('<h2>Box batches</h2><form id="batch-search-form"><label>Find a batch, box code or name<input id="batch-search" type="search"></label><button>Search batches</button></form><div id="box-batch-list"></div><button id="new-box-batch" class="primary full">Create boxes in bulk</button>');
  const search = async () => {
    const data = await api("box-batches?q=" + encodeURIComponent($("#batch-search").value));
    $("#box-batch-list").innerHTML = data.batches.map((b) => `<button class="secondary full" data-box-batch="${b.id}">${esc(b.name || "Box batch")} · ${b.count} boxes<small>${esc(new Date(b.created).toLocaleDateString("en-AU"))} · ${b.pages} A4 sheets · ${esc(b.first_code)} to ${esc(b.last_code)}</small></button>`).join("") || "<p>No saved batches match.</p>";
    document.querySelectorAll("[data-box-batch]").forEach((button) => button.onclick = guard(() => showBoxBatch(button.dataset.boxBatch)));
  };
  $("#batch-search-form").onsubmit = guard(async (e) => { e.preventDefault(); await search(); });
  $("#new-box-batch").onclick = guard(bulkBoxesPanel);
  await search();
}

async function showBoxBatch(id) {
  const batch = await api("box-batches/" + id);
  modal(`<h2>${esc(batch.name || "Box batch")}</h2><p>${batch.count} saved boxes · ${batch.count * 2} labels · ${batch.pages} A4 sheets</p><p id="batch-status" role="status">These boxes are saved and shared with the household. Downloading labels creates no additional boxes.</p><p>${paperInstructions}</p><button id="batch-download" class="primary full">Download A4 labels</button><div class="actions"><button id="batch-reprint">Reprint selected boxes</button><button id="batch-pack">Open packing mode</button><button id="batch-list">All box batches</button></div>${paperDiagram(batch.boxes)}<div class="batch-boxes">${batch.boxes.map((b) => `<label class="check"><input type="checkbox" data-batch-box="${b.id}" checked> ${esc(b.name)} · ${esc(b.code)} <a href="/c/${encodeURIComponent(b.code)}">Open box</a></label>`).join("")}</div>`);
  $("#batch-download").onclick = guard(async () => {
    try { await downloadPaper(`/api/box-batches/${id}/labels.pdf`); $("#batch-status").textContent = "PDF downloaded. Print at actual size."; }
    catch (error) { $("#batch-status").textContent = error.message; }
  });
  $("#batch-reprint").onclick = guard(() => paperSelection([...document.querySelectorAll("[data-batch-box]:checked")].map((x) => x.dataset.batchBox)));
  $("#batch-pack").onclick = () => { closeDialog(); nav("packing"); };
  $("#batch-list").onclick = guard(boxBatchesPanel);
}

async function paperSelection(ids) {
  if (!ids.length || ids.length > 240) throw Error("Select 1 to 240 boxes");
  const boxes = ids.map((id) => tub(id));
  if (boxes.some((b) => !b)) throw Error("Refresh the box list before printing");
  modal(`<h2>A4 labels for saved boxes</h2><p>${boxes.length} boxes · ${boxes.length * 2} labels · ${Math.ceil(boxes.length / 12)} A4 sheets. No boxes will be created.</p><p>${paperInstructions}</p>${paperDiagram(boxes)}<button id="selected-paper-download" class="primary full">Download A4 labels</button><p id="form-error" role="alert"></p>`);
  $("#selected-paper-download").onclick = guard(() => downloadPaper("/api/box-labels.pdf?codes=" + boxes.map((b) => encodeURIComponent(b.code)).join(",")));
}

async function nameSelectedBoxes(ids) {
  const boxes = ids.map((id) => tub(id)).filter((b) => b && !b.name.trim());
  if (!boxes.length) throw Error("None of the selected boxes is unnamed. Existing names are preserved.");
  const key = crypto.randomUUID();
  modal(`<h2>Name ${boxes.length} unnamed boxes</h2><p>Only selected boxes with an empty name will receive a random given name. Existing names and permanent codes stay the same.</p><button id="confirm-box-names" class="primary full">Assign random names</button><p id="form-error" role="alert"></p>`);
  $("#confirm-box-names").onclick = guard(async () => {
    await api("name-unnamed-boxes", { boxes: boxes.map((b) => ({id: b.id, revision: b.revision})) }, key);
    closeDialog();
    await renderPacking();
    notice("Names saved. Existing printed QR codes still work.");
  });
}
