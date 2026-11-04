"use strict";
const $ = (s) => document.querySelector(s),
  esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
let me,
  tubs = [],
  items = [],
  tab = "find",
  active = null,
  db,
  currentDraft = null,
  sending = false,
  selected = new Set(),
  stream = null;
const statusNames = {
  stored: "In its tub",
  in_use: "In use",
  missing: "Not found here",
  unknown: "Location unconfirmed",
  used_up: "Used up",
  removed: "Removed",
};
const installation = () => {
  let x = localStorage.getItem("stash-installation");
  if (!x) {
    x = crypto.randomUUID();
    localStorage.setItem("stash-installation", x);
  }
  return x;
};
function notice(message, error = false) {
  $("#notice").textContent = message;
  $("#notice").className = error ? "error" : "";
}
async function api(path, data, key) {
  const r = await fetch("/api/" + path, {
    method: data ? "POST" : "GET",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": me?.csrf || "",
      "X-Stash-User": me ? String(me.id) : "",
      "Idempotency-Key": key || crypto.randomUUID(),
    },
    ...(data ? { body: JSON.stringify(data) } : {}),
  });
  let out = await r.json();
  if (!r.ok) {
    if (r.status === 401) {
      notice(
        "Sign in again to save. Pending drafts remain on this device.",
        true,
      );
    }
    const error = Error(out.error || "Request failed");
    error.status = r.status;
    throw error;
  }
  return out;
}
function openDB() {
  return new Promise((resolve, reject) => {
    const q = indexedDB.open("stash-drafts", 1);
    q.onupgradeneeded = () =>
      q.result.createObjectStore("drafts", { keyPath: "id" });
    q.onsuccess = () => resolve(q.result);
    q.onerror = () => reject(q.error);
  });
}
function store(method, arg) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(
      "drafts",
      method === "getAll" ? "readonly" : "readwrite",
    );
    const q = tx.objectStore("drafts")[method](arg);
    tx.oncomplete = () => resolve(q.result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}
const drafts = async () =>
  (await store("getAll")).filter((d) => d.namespace === me.namespace);
function tub(id) {
  return tubs.find((c) => c.id === id);
}
function thumb(name) {
  return name ? "/api/media/" + name.split(".")[0] + ".thumb.jpg" : "";
}
function closeDialog() {
  stopScan();
  $("#dialog").close();
}
function modal(html) {
  $("#dialog-content").innerHTML = html;
  $("#dialog").showModal();
}
function nav(t) {
  notice("");
  tab = t;
  document
    .querySelectorAll("[data-tab]")
    .forEach((b) => b.classList.toggle("active", b.dataset.tab === t));
  render();
}
async function refresh() {
  const [c, i] = await Promise.all([api("containers"), api("items")]);
  tubs = c.containers;
  items = i.items;
}
function header(kicker, title, subtitle) {
  return `<div class="hero"><div><p class="eyebrow">${kicker}</p><h1>${title}</h1><p>${subtitle}</p></div><img class="hero-art" src="/static/brand/stash-conductor-onboarding-transparent.png" alt=""></div>`;
}
function empty() {
  return `<div class="empty"><img src="/static/brand/stash-conductor-onboarding-transparent.png" alt="Two storage tubs with workshop bits"><h2>A little less “where did I put it?”</h2><p>Make a tub, take a photo, put it away.<br>The details can wait.</p><button id="empty-start" class="primary">${tubs.length ? "Start adding" : "Create your first tub"}</button></div>`;
}
function itemCard(i) {
  let c = tub(i.container_id),
    last = tub(i.last_container_id);
  return `<article class="card"><button class="open-item" data-item="${i.id}">${i.photo ? `<img class="item-photo" loading="lazy" src="${thumb(i.photo)}" alt="${esc(i.title)}">` : '<div class="placeholder" aria-hidden="true">▤</div>'}<div class="card-content"><span class="badge ${i.status === "stored" ? "" : "warning"}">${esc(statusNames[i.status])}</span><h3>${esc(i.title)}</h3><p class="location">${c ? esc(c.code + " · " + (c.effective_location || c.location || "Location not set")) : last ? "Last in " + esc(last.code) : "No confirmed location"}</p><small>${i.quantity === null ? "Quantity unknown" : i.quantity + " " + esc(i.unit)}</small></div></button><label class="check card-content"><input type="checkbox" data-select="${i.id}" ${selected.has(i.id) ? "checked" : ""}> Select</label></article>`;
}
function bindCards() {
  document
    .querySelectorAll("[data-item]")
    .forEach((b) => (b.onclick = () => showItem(b.dataset.item)));
  document.querySelectorAll("[data-select]").forEach(
    (b) =>
      (b.onchange = () => {
        b.checked
          ? selected.add(b.dataset.select)
          : selected.delete(b.dataset.select);
        renderSelection();
      }),
  );
}
function renderSelection() {
  const el = $("#selection");
  if (!el) return;
  el.innerHTML = selected.size
    ? `<div class="selected-bar row"><span>${selected.size} selected</span><button id="bulk-take">Take out</button><button id="bulk-move" class="secondary">Move / return</button><button id="clear-selection" class="secondary">Clear</button></div>`
    : "";
  if (selected.size) {
    $("#clear-selection").onclick = () => {
      selected.clear();
      render();
    };
    $("#bulk-take").onclick = () => bulkAction("take");
    $("#bulk-move").onclick = () => bulkAction("move");
  }
}
function render() {
  if (!me) return;
  $("#view").ariaBusy = "false";
  if (tab === "find") renderFind();
  else if (tab === "add") renderAdd();
  else if (tab === "packing")
    renderPacking().catch((e) => notice(e.message, true));
  else renderContainers();
}
function renderFind() {
  $("#view").innerHTML =
    header(
      "Room to make things",
      "Put it anywhere.<br>Find it when you need it.",
      "Your shared workshop memory, one small tidy at a time.",
    ) +
    `<div class="searchbox"><input id="search" type="search" placeholder="Try ‘blue board’ or ‘bag of screws’" aria-label="Search inventory" autocomplete="off"></div><div class="section-head"><h2>Your stash</h2><span id="result-count" class="muted">${items.length} records</span></div><div id="box-search-results" class="grid"></div><div id="selection"></div><div id="results" class="grid">${items.map(itemCard).join("")}</div>${!items.length && !tubs.length ? empty() : ""}`;
  bindCards();
  renderSelection();
  if ($("#empty-start"))
    $("#empty-start").onclick = () => (tubs.length ? nav("add") : newTub());
  const boxResults = (query) => {
    const terms = query.trim().toLocaleLowerCase().split(/\s+/);
    const boxes = tubs.filter((c) => terms.every((term) => [c.code, c.name, c.effective_location, c.destination].join(" ").toLocaleLowerCase().includes(term)));
    $("#box-search-results").innerHTML = boxes.map((c) => `<article class="card"><h3>${esc(c.name || "Box")} · ${esc(c.code)}</h3><p>${esc(c.effective_location || "Location not set")}</p><button data-search-box="${c.id}" class="secondary full">Open box</button></article>`).join("");
    document.querySelectorAll("[data-search-box]").forEach((button) => button.onclick = guard(() => boxEditor(button.dataset.searchBox)));
    return boxes.length;
  };
  boxResults("");
  let timer;
  $("#search").oninput = () => {
    clearTimeout(timer);
    const q = $("#search").value;
    timer = setTimeout(async () => {
      try {
        const out = await api("items?q=" + encodeURIComponent(q));
        if ($("#search")?.value !== q) return;
        $("#results").innerHTML = out.items.map(itemCard).join("");
        $("#result-count").textContent = out.items.length + boxResults(q) + " results";
        bindCards();
      } catch (e) {
        notice(e.message, true);
      }
    }, 180);
  };
}
function tubOptions(chosen) {
  return (
    `<option value="">Choose a tub…</option>` +
    tubs
      .map(
        (c) =>
          `<option value="${c.id}" ${chosen === c.id ? "selected" : ""}>${esc(c.code + " · " + (c.name || c.location || "Tub"))}</option>`,
      )
      .join("")
  );
}
async function renderAdd() {
  if (!tubs.length) {
    $("#view").innerHTML =
      header(
        "Quick tidy",
        "First, give a tub a code.",
        "Any suitable container will do.",
      ) + empty();
    $("#empty-start").onclick = newTub;
    return;
  }
  $("#view").innerHTML =
    `<div class="capture"><p class="eyebrow">Quick tidy</p><h1>A photo. A few words.<br>Back to your day.</h1><label>Choose your tub<select id="active-tub">${tubOptions(active)}</select></label><div id="capture-area"></div><div class="section-head"><h2>On this device</h2><button id="retry" class="link">Retry pending</button></div><div id="draft-list"></div></div>`;
  $("#active-tub").onchange = async () => {
    active = $("#active-tub").value || null;
    localStorage.setItem("stash-tub:" + me.namespace, active || "");
    currentDraft = null;
    await captureForm();
  };
  $("#retry").onclick = flushDrafts;
  await captureForm();
  renderDrafts();
}
async function captureForm() {
  const c = tub(active);
  if (!c) {
    $("#capture-area").innerHTML =
      '<p class="muted">Select or scan a tub to start. Your saved drafts keep their original tub.</p>';
    return;
  }
  const all = (await drafts()).filter((d) => !d.kind);
  currentDraft = all.find(
    (d) => d.container_id === active && d.state === "editing",
  ) || {
    id: crypto.randomUUID(),
    namespace: me.namespace,
    container_id: active,
    title: "",
    photo: "",
    state: "editing",
    created: Date.now(),
  };
  $("#capture-area").innerHTML =
    `<div class="tub-banner"><div><small>Adding to</small><br><strong>${esc(c.name)} · ${esc(c.code)}</strong><button id="capture-box-location" class="secondary">Set location or box photo</button></div><span>${esc(c.effective_location || c.location || c.name || "Your selected tub")}</span></div><form id="capture-form" class="capture-form"><label class="photo-input">📷 Take a photo or choose one<input id="photo" type="file" accept="image/jpeg,image/png,image/webp" capture="environment"></label><div id="photo-preview">${currentDraft.photo ? `<img class="preview" src="${currentDraft.photo}" alt="Pending capture">` : ""}</div><label>A rough description is plenty<textarea id="description" placeholder="Mixed cables, little blue board…">${esc(currentDraft.title)}</textarea></label><label>Quantity, if known<input id="capture-quantity" type="number" min="1" value="${currentDraft.quantity || ""}"></label><p class="muted"><small>Use your keyboard microphone to dictate. No category or count needed.</small></p><button class="orange full" id="save-next">Save & next →</button><small id="draft-state">${currentDraft.title || currentDraft.photo ? "Draft retained on this device" : "Photo or words — either is enough."}</small></form>`;
  $("#capture-box-location").onclick = guard(() => boxEditor(c.id));
  const draft = currentDraft;
  $("#capture-quantity").oninput = async () => {
    draft.quantity = Number($("#capture-quantity").value) || null;
    await persist(draft);
  };
  $("#description").oninput = async () => {
    draft.title = $("#description").value;
    await persist(draft);
  };
  $("#photo").onchange = async () => {
    let file = $("#photo").files[0];
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) {
      notice("Please use a photo under 20 MB.", true);
      return;
    }
    $("#save-next").disabled = true;
    try {
      draft.photo = await new Promise((resolve, reject) => {
        let fr = new FileReader();
        fr.onload = () => resolve(fr.result);
        fr.onerror = reject;
        fr.readAsDataURL(file);
      });
      await persist(draft);
      $("#photo-preview").innerHTML =
        `<img class="preview" src="${draft.photo}" alt="Pending capture">`;
    } catch (e) {
      notice(
        "Photo could not be retained. Keep this page open and try again.",
        true,
      );
    } finally {
      $("#save-next").disabled = false;
    }
  };
  $("#capture-form").onsubmit = async (e) => {
    e.preventDefault();
    if (!draft.title.trim() && !draft.photo) {
      notice("Add a photo or a few words.", true);
      return;
    }
    $("#save-next").disabled = true;
    draft.state = "pending";
    if (!(await persist(draft))) {
      draft.state = "editing";
      $("#save-next").disabled = false;
      return;
    }
    currentDraft = null;
    await captureForm();
    renderDrafts();
    flushDrafts();
  };
}
async function persist(d) {
  try {
    await store("put", structuredClone(d));
    if ($("#draft-state"))
      $("#draft-state").textContent = "Pending on this device";
    return true;
  } catch (e) {
    notice(
      "Device storage failed. This draft is NOT safely retained; do not close the page.",
      true,
    );
    return false;
  }
}
async function renderDrafts() {
  const el = $("#draft-list");
  if (!el) return;
  const all = (await drafts())
    .filter((d) => !d.kind && d.state !== "editing")
    .sort((a, b) => b.created - a.created);
  el.innerHTML =
    all
      .map(
        (d) =>
          `<div class="saved-row">${d.photo ? `<img src="${d.photo}" alt="">` : ""}<div><strong>${esc(d.title || "Unidentified item")}</strong><br><small>${esc(tub(d.container_id)?.code || "Original tub")} · ${d.state === "saved" ? "Saved on server" : d.state === "failed" ? "Failed — " + esc(d.error) : "Pending on this device"}</small></div>${d.state === "saved" ? `<button class="link" data-undo="${d.event}" data-draft="${d.id}">Undo</button>` : ""}</div>`,
      )
      .join("") || '<p class="muted">Your captures will appear here.</p>';
  el.querySelectorAll("[data-undo]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          await api("undo/" + b.dataset.undo, {});
          await store("delete", b.dataset.draft);
          await refresh();
          renderDrafts();
          notice("Capture removed. Its history and photo are retained.");
        } catch (e) {
          notice(e.message, true);
        }
      }),
  );
}
async function flushDrafts() {
  if (sending || !navigator.onLine) return;
  sending = true;
  try {
    for (const d of await drafts()) {
      if (d.kind || !["pending", "failed"].includes(d.state)) continue;
      try {
        const live = await api("me");
        if (live.id !== me.id)
          throw Error(
            "Account changed. Sign back in to the original account to send these drafts.",
          );
        const out = await api(
          "items",
          {
            title: d.title,
            photo: d.photo,
            container_id: d.container_id,
            quantity: d.quantity || null,
          },
          d.id,
        );
        d.state = "saved";
        d.event = out.event;
        await store("put", d);
      } catch (e) {
        d.state = "failed";
        d.error = e.message;
        await store("put", d);
      }
      await renderDrafts();
    }
    if (navigator.onLine) await refresh();
  } catch (e) {
    if (navigator.onLine) notice("Drafts retained. " + e.message, true);
  } finally {
    sending = false;
  }
}
function renderContainers() {
  $("#view").innerHTML =
    header(
      "A home for the odds & ends",
      "Good things come<br>in ordinary tubs.",
      "Move a tub once. Everything inside follows its location.",
    ) +
    `<div class="section-head"><h2>${tubs.length} containers</h2><button class="primary" id="new-tub">＋ New tub</button></div><div class="actions"><button id="container-bulk" class="primary">Create boxes in bulk</button><button id="container-batches">Box batches</button></div><div class="grid">${tubs.map((c) => `<article class="card container-card"><span class="code">${esc(c.code)}</span><h3>${esc(c.name || "Storage tub")}</h3><p class="location">${esc(c.effective_location || c.location || "Set a shelf or location")}</p><small>${items.filter((i) => i.container_id === c.id && i.status === "stored").length} records stored</small><button class="primary full" data-add-tub="${c.id}">Add here</button><button class="secondary full" data-tub="${c.id}">Details & label</button></article>`).join("")}</div>`;
  $("#new-tub").onclick = newTub;
  $("#container-bulk").onclick = guard(bulkBoxesPanel);
  $("#container-batches").onclick = guard(boxBatchesPanel);
  document
    .querySelectorAll("[data-add-tub]")
    .forEach((b) => (b.onclick = () => selectTub(tub(b.dataset.addTub).code)));
  document
    .querySelectorAll("[data-tub]")
    .forEach((b) => (b.onclick = () => showTub(b.dataset.tub)));
}
function newTub() {
  guard(() => boxEditor())();
}
function showTub(id) {
  const c = tub(id);
  modal(
    `<p class="eyebrow">Container</p><h2>${esc(c.code)}</h2><form id="edit-tub"><label>Name<input name="name" value="${esc(c.name)}"></label><p>Current physical location: ${esc(c.effective_location || c.location || "Not set")}</p><button type="button" id="packing-details" class="secondary">Packing and location details</button>${!c.physical_location_id && !c.parent_id ? `<label>Location note<input name="location" value="${esc(c.location)}"></label>` : ""}<label>Optional tub photo<input id="tub-photo" type="file" accept="image/jpeg,image/png,image/webp"></label><button class="primary full">Save location</button><p id="form-error"></p></form><div class="label-print"><img class="label-preview" src="/api/label/${encodeURIComponent(c.code)}" alt="QR code for ${esc(c.code)}"><strong>${esc(c.name)}</strong><strong class="code">${esc(c.code)}</strong><p>Stash Conductor</p><small>${esc(location.origin + "/c/" + c.code)}</small></div><div class="row no-print"><button id="paper-print" class="secondary">Download A4 labels</button><button id="print" class="secondary">Brother label</button><button id="contents" class="secondary">View contents</button><button id="add-here" class="primary">Add here</button></div>`,
  );
  $("#packing-details").onclick = guard(() => boxEditor(c.id));
  $("#paper-print").onclick = guard(() => paperSelection([c.id]));
  $("#print").onclick = guard(() => printLabels(["box:" + c.id]));
  $("#add-here").onclick = () => {
    closeDialog();
    selectTub(c.code);
  };
  $("#contents").onclick = () => {
    closeDialog();
    nav("find");
    $("#results").innerHTML = items
      .filter((i) => i.container_id === id)
      .map(itemCard)
      .join("");
    $("#result-count").textContent = c.code;
    bindCards();
  };
  $("#edit-tub").onsubmit = async (e) => {
    e.preventDefault();
    let p = Object.fromEntries(new FormData(e.target));
    p.revision = c.revision;
    const f = $("#tub-photo").files[0];
    if (f) p.photo = await fileData(f);
    try {
      await api("containers/" + c.id, p);
      await refresh();
      closeDialog();
      render();
      notice("Location updated for this tub and everything inside.");
    } catch (e) {
      $("#form-error").textContent = e.message;
    }
  };
}
function fileData(f) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(f);
  });
}
async function showItem(id) {
  try {
    const out = await api("items/" + id),
      i = out.item,
      c = tub(i.container_id);
    modal(
      `<p class="eyebrow">${esc(statusNames[i.status])}</p><h2>${esc(i.title)}</h2>${i.photo ? `<a href="/api/media/${i.photo}" target="_blank" rel="noopener"><img class="detail-photo" src="${thumb(i.photo)}" alt="${esc(i.title)}"></a>` : ""}<p>${c ? esc(c.code + " · " + (c.effective_location || c.location || "Location not set")) : "Last tub: " + esc(tub(i.last_container_id)?.code || "Unknown")}<br><small>Last confirmed ${esc(new Date(i.confirmed).toLocaleString())}</small></p><div class="detail-actions"><button data-action="take" class="orange">Take out</button><button data-action="return" class="primary">Return / move</button><button data-action="missing" class="secondary">Not found here</button><button data-action="unknown" class="secondary">Unknown location</button><button data-action="used" class="secondary">Used up</button><button id="edit-item" class="secondary">Edit details</button>${i.quantity > 1 ? '<button data-action="split" class="secondary">Split count</button>' : ""}<button data-action="remove" class="secondary">Remove record</button></div><p class="muted">${i.quantity === null ? "Quantity unknown" : i.quantity + " " + esc(i.unit)}. Removal can be undone; originals are retained.</p><details><summary>Identity & device details</summary><p>Original words: ${esc(i.original || "Photo-only capture")}</p><p>Aliases: ${esc(i.aliases || "None yet")}</p><pre>${esc(JSON.stringify(i.metadata, null, 2))}</pre><h3>Unconfirmed suggestions</h3><pre>${esc(JSON.stringify(i.suggestions, null, 2))}</pre><p>Review suggestions, then use Edit details to confirm only supported facts.</p><p>Specifications need confirmed sources and units. Guesses are not electrical advice. Do not store passwords here.</p></details><details><summary>History (${out.history.length})</summary><ol class="history">${out.history.map((h, n) => `<li><strong>${esc(h.action)}</strong> · ${esc(h.actor)}<small>${esc(new Date(h.at).toLocaleString())}</small>${n === 0 ? `<button class="link" id="undo-latest" data-event="${h.id}">Undo latest</button>` : ""}</li>`).join("")}</ol></details><p id="form-error" role="alert"></p>`,
    );
    document
      .querySelectorAll("[data-action]")
      .forEach((b) => (b.onclick = () => itemAction(i, b.dataset.action)));
    $("#edit-item").onclick = () => editItem(i);
    if ($("#undo-latest"))
      $("#undo-latest").onclick = async () => {
        try {
          await api("undo/" + $("#undo-latest").dataset.event, {});
          await refresh();
          closeDialog();
          render();
          notice("Latest change undone.");
        } catch (e) {
          $("#form-error").textContent = e.message;
        }
      };
  } catch (e) {
    notice(e.message, true);
  }
}
function editItem(i) {
  modal(
    `<h2>Details can grow with you.</h2><form id="edit-item-form"><label>Name<input name="title" value="${esc(i.title)}" required></label><label>Aliases / visible markings<textarea name="aliases">${esc(i.aliases)}</textarea></label><div class="row"><label>Count · blank if unknown<input name="quantity" type="number" min="1" value="${i.quantity ?? ""}"></label><label>Unit<input name="unit" value="${esc(i.unit)}"></label></div><details open><summary>Optional electronics & device details</summary>${["manufacturer", "model", "input_voltage", "logic_voltage", "interfaces", "ratings", "pinout", "datasheet", "source", "serial", "mac", "firmware", "test_status", "test_notes", "test_date", "installed_location", "project", "device_link"].map((k) => `<label>${esc(k.replaceAll("_", " "))}<input name="meta_${k}" value="${esc(typeof i.metadata[k] === "string" ? i.metadata[k] : "")}" placeholder="${k.includes("voltage") ? "Include units and source; leave unknown if unsure" : ""}"></label>`).join("")}<p class="muted">Record only confirmed facts. Include units and provenance in each specification or source field.</p></details><button class="primary full">Save details</button><p id="form-error"></p></form>`,
  );
  $("#edit-item-form").onsubmit = async (e) => {
    e.preventDefault();
    let f = Object.fromEntries(new FormData(e.target));
    let meta = { ...i.metadata };
    for (const [k, v] of Object.entries(f))
      if (k.startsWith("meta_")) {
        meta[k.slice(5)] = v;
        delete f[k];
      }
    f.metadata = meta;
    f.quantity = f.quantity ? Number(f.quantity) : null;
    f.revision = i.revision;
    try {
      await api("items/" + i.id, f);
      await refresh();
      closeDialog();
      render();
      showItem(i.id);
    } catch (e) {
      $("#form-error").textContent = e.message;
    }
  };
}
async function itemAction(i, action) {
  if (["return", "split"].includes(action)) {
    modal(
      `<h2>${action === "split" ? "Split a counted batch" : "Return or move"}</h2><form id="move-form"><label>Destination tub<select name="container_id" required>${tubOptions(i.last_container_id)}</select></label>${action === "split" ? `<label>Count to move<input name="quantity" type="number" min="1" max="${i.quantity - 1}" required></label>` : ""}<button class="primary full">Confirm</button><p id="form-error"></p></form>`,
    );
    $("#move-form").onsubmit = async (e) => {
      e.preventDefault();
      let p = Object.fromEntries(new FormData(e.target));
      if (p.quantity) p.quantity = Number(p.quantity);
      await doAction(i, action, p);
    };
    return;
  }
  if (action === "take") {
    modal(
      `<h2>Take out</h2><form id="take-form"><label>Project, person or workbench · optional<input name="destination" placeholder="Workbench / weekend repair"></label><button class="orange full">Mark in use</button><p id="form-error"></p></form>`,
    );
    $("#take-form").onsubmit = (e) => {
      e.preventDefault();
      doAction(i, action, Object.fromEntries(new FormData(e.target)));
    };
    return;
  }
  await doAction(i, action, {});
}
async function doAction(i, action, p) {
  try {
    const out = await api("items/" + i.id, {
      ...p,
      action,
      revision: i.revision,
    });
    await refresh();
    closeDialog();
    render();
    notice("Saved on server.");
    $("#notice").insertAdjacentHTML(
      "beforeend",
      ` <button class="link" id="action-undo">Undo</button>`,
    );
    $("#action-undo").onclick = async () => {
      try {
        await api("undo/" + out.event, {});
        await refresh();
        render();
        notice("Undone.");
      } catch (e) {
        notice(e.message, true);
      }
    };
  } catch (e) {
    if ($("#form-error")) $("#form-error").textContent = e.message;
    else notice(e.message, true);
  }
}
function bulkAction(action) {
  modal(
    `<h2>${action === "take" ? "Take out" : "Move"} ${selected.size} records</h2><form id="bulk-form">${action === "move" ? `<label>Destination<select name="container_id" required>${tubOptions(null)}</select></label>` : '<label>Project / person · optional<input name="destination"></label>'}<button class="primary full">Confirm</button><p id="form-error"></p></form>`,
  );
  $("#bulk-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("bulk", {
        ...Object.fromEntries(new FormData(e.target)),
        action,
        items: items
          .filter((i) => selected.has(i.id))
          .map((i) => ({ id: i.id, revision: i.revision })),
      });
      selected.clear();
      await refresh();
      closeDialog();
      render();
      notice("All selected records updated together.");
    } catch (e) {
      $("#form-error").textContent = e.message;
    }
  };
}
async function selectTub(code) {
  const c = tubs.find((c) => c.code === code.toUpperCase());
  if (!c) {
    notice("That tub is not in your inventory.", true);
    return;
  }
  active = c.id;
  localStorage.setItem("stash-tub:" + me.namespace, active);
  history.replaceState({}, "", "/c/" + c.code);
  nav("add");
}
function parseCode(raw) {
  try {
    if (raw.startsWith("http")) {
      const u = new URL(raw);
      if (u.origin !== location.origin) throw Error();
      raw = decodeURIComponent(u.pathname.split("/c/")[1] || "");
    }
  } catch (e) {
    return null;
  }
  return /^[A-Za-z0-9][A-Za-z0-9_-]{0,23}$/.test(raw.trim())
    ? raw.trim().toUpperCase()
    : null;
}
function stopScan() {
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }
}
async function scan() {
  modal(
    '<h2>Open a tub</h2><p>Scan its QR label or type its code.</p><video id="camera" playsinline muted></video><p id="camera-status"></p><form id="code-form"><label>Tub code<input id="manual-code" placeholder="B014" required autocapitalize="characters"></label><button class="primary full">Open tub</button></form>',
  );
  $("#code-form").onsubmit = (e) => {
    e.preventDefault();
    const code = parseCode($("#manual-code").value);
    if (code) {
      closeDialog();
      selectTub(code);
    } else $("#camera-status").textContent = "Use the printed tub code.";
  };
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
    const video = $("#camera");
    if (!video) {
      stopScan();
      return;
    }
    video.srcObject = stream;
    await video.play();
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    function frame() {
      if (!stream || !$("#dialog").open) return;
      if (video.readyState >= 2) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0);
        const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const qr = jsQR(img.data, img.width, img.height, {
          inversionAttempts: "dontInvert",
        });
        const code = qr && parseCode(qr.data);
        if (code) {
          closeDialog();
          selectTub(code);
          return;
        }
      }
      requestAnimationFrame(frame);
    }
    frame();
  } catch (e) {
    $("#camera-status").textContent =
      "Camera unavailable. Type the code below.";
  }
}
async function settings() {
  modal(
    `<h2>Your Stash</h2><p>Signed in as <strong>${esc(me.name)}</strong> · ${me.owner ? "Owner" : "Member"}</p><p>One shared inventory. Selected tubs and pending drafts belong to this device and account.</p><button id="removed" class="secondary full">Removed records & recovery</button><button id="pair" class="secondary full">Pair OpenTub Shortcut</button><div id="pair-list"></div>${me.owner ? '<button id="export" class="secondary full">Export inventory JSON</button><button id="access" class="secondary full">User access</button><button id="integration" class="secondary full">Integration credentials</button>' : ""}${me.conductor_url ? `<p><a href="${esc(me.conductor_url)}">Open Chaos Conductor ↗</a></p>` : ""}<details><summary>Install on iPhone</summary><p>Open this site in Safari, Share → Add to Home Screen → Open as Web App. Photo upload, keyboard dictation and QR scanning use your phone’s own controls.</p><p>NFC and Shortcut launching need a real-phone test. HTTPS labels and manual code entry always remain available.</p></details><button id="clear-saved" class="secondary full">Clear saved draft copies on this device</button><button id="logout" class="full">Sign out</button><p id="form-error"></p>`,
  );
  $("#removed").onclick = async () => {
    const out = await api("items?status=removed");
    modal(
      `<h2>Removed records</h2><p>Originals and history are retained. Open a record and undo its latest removal.</p>${out.items.map((i) => `<button class="secondary full" data-removed="${i.id}">${esc(i.title)}</button>`).join("") || "<p>No removed records.</p>"}`,
    );
    document
      .querySelectorAll("[data-removed]")
      .forEach((b) => (b.onclick = () => showItem(b.dataset.removed)));
  };
  $("#pair").onclick = async () => {
    const result = await api("pairings", {
      installation: installation(),
      label: "OpenTub on this device",
    });
    modal(
      `<h2>Pair this installation</h2><p>Keep this credential in your private Shortcut. Never write it to a tag. It can only select a tub for this installation.</p><label>POST endpoint<input readonly value="${esc(result.endpoint)}"></label><label>Authorization header<input readonly value="Bearer ${esc(result.credential)}"></label><p>Send JSON <code>{"code":"B014"}</code>, then open Stash. Destination expires after 60 seconds and is consumed once.</p><p>Install the PWA first and pair from inside it; Safari and the PWA may have separate storage.</p>`,
    );
  };
  const pairs = await api("pairings");
  $("#pair-list").innerHTML = pairs.pairings
    .map(
      (p) =>
        `<p>${esc(p.label)} <button class="link" data-revoke="${p.id}">Revoke</button></p>`,
    )
    .join("");
  document.querySelectorAll("[data-revoke]").forEach(
    (b) =>
      (b.onclick = async () => {
        await api("pairings", { revoke: b.dataset.revoke });
        b.parentElement.remove();
      }),
  );
  $("#clear-saved").onclick = async () => {
    for (const d of await drafts())
      if (d.state === "saved") await store("delete", d.id);
    notice(
      "Saved local copies cleared. Server records and pending drafts remain.",
    );
  };
  $("#logout").onclick = async () => {
    const pending = (await drafts()).filter((d) => d.state !== "saved");
    if (
      pending.length &&
      !confirm(
        "Signing out clears this device's drafts and photos. Save them first, or confirm you want to discard these local drafts and sign out.",
      )
    )
      return;
    for (const d of await drafts()) await store("delete", d.id);
    localStorage.removeItem("stash-tub:" + me.namespace);
    localStorage.removeItem("stash-place:" + me.namespace);
    if ("caches" in window)
      for (const k of await caches.keys()) await caches.delete(k);
    await fetch("/auth/logout", {
      method: "POST",
      headers: { "X-CSRFToken": me.csrf },
    });
    location.href = "/auth/login";
  };
  if (me.owner) {
    $("#export").onclick = async () => {
      const out = await api("export");
      let u = URL.createObjectURL(
        new Blob([JSON.stringify(out, null, 2)], { type: "application/json" }),
      );
      let a = document.createElement("a");
      a.href = u;
      a.download = "stash-inventory.json";
      a.click();
      URL.revokeObjectURL(u);
    };
    $("#access").onclick = access;
    $("#integration").onclick = integrations;
  }
}
async function access() {
  const out = await api("users");
  modal(
    `<h2>User access</h2><p>${me.auth_mode === "oidc" ? "Membership is managed by the identity provider. Existing sessions expire within one hour." : "Owner-managed local accounts. Password recovery uses the documented interactive account command."}</p>${out.users.map((u) => `<p>${esc(u.first_name || u.username)} · ${u.is_staff ? "Owner" : "Member"} · ${u.is_active ? "Active" : "Disabled"}</p>`).join("")}${me.auth_mode === "local" ? '<form id="new-user"><label>Username<input name="username" required></label><label>Initial password<input name="password" type="password" minlength="12" required autocomplete="new-password"></label><button class="primary full">Add member</button><p id="form-error"></p></form>' : ""}`,
  );
  if ($("#new-user"))
    $("#new-user").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api("users", Object.fromEntries(new FormData(e.target)));
        access();
      } catch (e) {
        $("#form-error").textContent = e.message;
      }
    };
}
async function integrations() {
  const out = await api("tokens");
  modal(
    `<h2>Integration credentials</h2><p>Tokens expire after 30 days. Keep them out of browsers, URLs and notes.</p>${out.tokens.map((t) => `<p>${esc(t.label)} · ${t.write ? "Read/write" : "Read only"} <button class="link" data-token-revoke="${t.id}">Revoke</button></p>`).join("")}<form id="token-form"><label>Label<input name="label" required></label><label class="check"><input type="checkbox" name="write"> Allow inventory writes</label><button class="primary full">Create credential</button></form>`,
  );
  document.querySelectorAll("[data-token-revoke]").forEach(
    (b) =>
      (b.onclick = async () => {
        await api("tokens", { revoke: Number(b.dataset.tokenRevoke) });
        b.parentElement.remove();
      }),
  );
  $("#token-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const t = await api("tokens", {
      label: f.get("label"),
      write: f.has("write"),
    });
    modal(
      `<h2>Store this securely</h2><input readonly value="${esc(t.token)}"><p>Use an Authorization: Bearer header. Expires in 30 days.</p>`,
    );
  };
}
async function consume() {
  if (!me || !navigator.onLine) return;
  try {
    const out = await api("consume", { installation: installation() });
    if (out.code) {
      if (currentDraft && (currentDraft.title || currentDraft.photo)) {
        await persist(currentDraft);
        notice("Your unfinished capture remains bound to its original tub.");
      }
      await selectTub(out.code);
    }
  } catch (e) {
    /* Retry on next foreground; never discard drafts. */
  }
}
window.addEventListener("online", () => {
  updateOnline();
  flushDrafts();
  consume();
});
window.addEventListener("offline", updateOnline);
function updateOnline() {
  $("#offline").hidden = navigator.onLine;
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    flushDrafts();
    consume();
  }
});
window.addEventListener("pagehide", stopScan);
$("#close-dialog").onclick = closeDialog;
$("#dialog").addEventListener("cancel", stopScan);
$("#scan").onclick = scan;
$("#settings").onclick = () => settings().catch((e) => notice(e.message, true));
document.querySelectorAll("[data-tab]").forEach(
  (b) =>
    (b.onclick = () => {
      history.replaceState({}, "", "/");
      nav(b.dataset.tab);
    }),
);
(async () => {
  try {
    me = await api("me");
    db = await openDB();
    await refresh();
    active = localStorage.getItem("stash-tub:" + me.namespace);
    const match = location.pathname.match(/^\/c\/([^/]+)$/),
      item = location.pathname.match(/^\/i\/([^/]+)$/);
    if (location.pathname.startsWith("/t/")) {
      await renderPacking();
      await openTag(location.pathname.slice(3));
    } else if (location.pathname.startsWith("/l/")) {
      nav("packing");
      await locationMove(location.pathname.slice(3));
    } else if (location.pathname === "/packing") nav("packing");
    else if (match) await selectTub(decodeURIComponent(match[1]));
    else {
      render();
      if (item) showItem(item[1]);
    }
    updateOnline();
    await flushDrafts();
    await consume();
    if ("serviceWorker" in navigator)
      navigator.serviceWorker.register("/sw.js");
  } catch (e) {
    notice(e.message, true);
  }
})();
