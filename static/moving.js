/* Packing, independent tags and the household print queue extend the original app. */
let places = [],
  tagRows = [],
  batchId = "",
  boxSelection = new Set();
const packingNames = {
  empty: "Empty",
  partly_packed: "Partly packed",
  sealed: "Sealed",
  in_transit: "In transit",
  stored: "Stored",
  unpacked: "Unpacked",
};
const guard =
  (fn) =>
  async (...args) => {
    try {
      await fn(...args);
    } catch (e) {
      notice(e.message, true);
      if ($("#form-error")) $("#form-error").textContent = e.message;
    }
  };
const options = (rows, chosen, label = "Choose") =>
  `<option value="">${label}</option>` +
  rows
    .map(
      (x) =>
        `<option value="${esc(x.id)}" ${chosen === x.id ? "selected" : ""}>${esc(x.path || x.name || x.code)}</option>`,
    )
    .join("");
const download = (name, value) => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
async function renderPacking() {
  await refresh();
  places = (await api("locations")).locations;
  $("#view").innerHTML =
    `<div class="section-head"><div><p class="eyebrow">Moving and storage</p><h1>One box at a time.</h1></div><button id="pack-new" class="primary">New box</button></div><div class="actions"><button id="bulk-boxes" class="primary">Create boxes in bulk</button><button id="box-batches" class="secondary">Box batches</button><button id="prepare-tags">Prepare tags</button><button id="packing-scan">Scan next box</button><button id="manage-locations" class="secondary">Locations and moves</button><button id="printer-panel" class="secondary">Printer and queue</button><button id="manifest" class="secondary">Moving manifest</button><button id="recent" class="secondary">Recent changes</button></div><div class="pack-filters"><label>Show<select id="pack-filter"><option value="">All boxes</option><option value="packing">Still packing</option><option value="priority">Essentials and priority</option>${Object.entries(
      packingNames,
    )
      .map(([k, v]) => `<option value="${k}">${v}</option>`)
      .join(
        "",
      )}</select></label><label>Find a box, item or room<input id="pack-search" type="search"></label></div><div id="pack-selection"></div><div id="pack-boxes" class="grid"></div>`;
  $("#pack-new").onclick = guard(() => boxEditor());
  $("#bulk-boxes").onclick = guard(bulkBoxesPanel);
  $("#box-batches").onclick = guard(boxBatchesPanel);
  $("#prepare-tags").onclick = guard(tagPanel);
  $("#packing-scan").onclick = () => scanAny();
  $("#manage-locations").onclick = guard(locationsPanel);
  $("#printer-panel").onclick = guard(printerPanel);
  $("#manifest").onclick = guard(manifestPanel);
  $("#recent").onclick = guard(recentPanel);
  const list = () => {
    const f = $("#pack-filter").value,
      q = $("#pack-search").value.toLowerCase();
    const rows = tubs.filter(
      (c) =>
        (!f ||
          (f === "packing"
            ? ["empty", "partly_packed"].includes(c.packing_state)
            : f === "priority"
              ? c.priority
              : c.packing_state === f)) &&
        JSON.stringify([c, items.filter((i) => i.container_id === c.id)])
          .toLowerCase()
          .includes(q),
    );
    $("#pack-boxes").innerHTML =
      rows
        .map(
          (c) =>
            `<article class="card pack-card"><label class="check"><input type="checkbox" data-box-select="${c.id}" ${boxSelection.has(c.id) ? "checked" : ""}> Select ${esc(c.code)}</label><h2>${esc(c.code)}</h2><h3>${esc(c.name || "Box")}</h3><span class="badge">${packingNames[c.packing_state]}</span><p>${esc(c.effective_location || "Location not set")}</p><p>Destination: ${esc(c.destination || "Not set")}</p><p>${[c.fragile ? "Fragile" : "", c.heavy ? "Heavy" : "", c.priority ? "Priority" : ""].filter(Boolean).join(" · ")}</p><p>${esc(c.description)}</p><button data-pack-box="${c.id}" class="primary full">Pack or edit</button><button data-pack-add="${c.id}" class="secondary full">Add items and photos</button></article>`,
        )
        .join("") ||
      "<p>No boxes match. Prepare a tag or create your first box.</p>";
    document
      .querySelectorAll("[data-pack-box]")
      .forEach((b) => (b.onclick = guard(() => boxEditor(b.dataset.packBox))));
    document
      .querySelectorAll("[data-pack-add]")
      .forEach(
        (b) => (b.onclick = () => selectTub(tub(b.dataset.packAdd).code)),
      );
    document.querySelectorAll("[data-box-select]").forEach(
      (b) =>
        (b.onchange = () => {
          b.checked
            ? boxSelection.add(b.dataset.boxSelect)
            : boxSelection.delete(b.dataset.boxSelect);
          selection();
        }),
    );
  };
  const selection = () => {
    const ids = [...boxSelection].filter((id) => tub(id));
    $("#pack-selection").innerHTML = ids.length
      ? `<p>${ids.length} selected</p><div class="actions"><button id="paper-boxes">Download A4 labels</button><button id="print-boxes">Brother labels</button><button id="name-boxes" class="secondary">Name unnamed boxes</button><button id="move-boxes">Move selected</button><button id="clear-boxes" class="secondary">Clear</button></div>`
      : "";
    if (ids.length) {
      $("#paper-boxes").onclick = guard(() => paperSelection(ids));
      $("#name-boxes").onclick = guard(() => nameSelectedBoxes(ids));
      $("#print-boxes").onclick = guard(() =>
        printLabels(ids.map((id) => "box:" + id)),
      );
      $("#move-boxes").onclick = guard(() => locationMove(null, ids));
      $("#clear-boxes").onclick = () => {
        boxSelection.clear();
        selection();
        list();
      };
    }
  };
  $("#pack-filter").onchange = list;
  $("#pack-search").oninput = list;
  list();
  selection();
}
async function boxEditor(id = null, tag = null) {
  places = (await api("locations")).locations;
  let current = id
    ? await api("containers/" + id)
    : {
        code: "",
        name: "",
        revision: 0,
        packing_state: "empty",
        physical_location_id:
          localStorage.getItem("stash-place:" + me.namespace) || "",
        destination: "",
        description: "",
      };
  const draftKey = "box:" + (id || tag?.token || "new") + ":" + me.namespace;
  let saved = (await drafts()).find((d) => d.id === draftKey),
    c = saved?.value || current;
  let key = saved?.operation_id || crypto.randomUUID();
  let submittedPayload = saved?.submitted_payload || null;
  modal(
    `<p class="eyebrow">${tag ? "Prepared tag " + esc(tag.code) : "Packing"}</p><h2>${id ? esc(current.code) : "New box"}</h2>${saved ? '<p role="status">Recovered a local draft. It has not been synchronised.</p>' : ""}<form id="box-form">${!id ? `<label>Box code<input name="code" value="${esc(c.code)}" placeholder="Leave empty for an automatic code" maxlength="24"></label>` : ""}<label>Box name<input name="name" value="${esc(c.name)}" placeholder="Random given name when left empty" maxlength="160"></label><label>Whole box contents<textarea name="description">${esc(c.description)}</textarea></label><label>Photo<input id="packing-photo" type="file" accept="image/jpeg,image/png,image/webp" capture="environment"></label><div id="packing-photo-preview">${c.photo?.startsWith("data:") ? `<img class="preview" src="${c.photo}" alt="Draft box photo">` : current.photo ? `<img class="preview" src="${thumb(current.photo)}" alt="Box photo">` : ""}</div><label>Current physical location<select name="physical_location_id">${options(places, c.physical_location_id, "Not set")}</select></label><label>Inside another box<select name="parent_id">${options(
      tubs.filter((b) => b.id !== id),
      c.parent_id,
      "No parent box",
    )}</select></label><label>Intended destination room<input name="destination" value="${esc(c.destination)}"></label><label>Packing state<select name="packing_state">${Object.entries(
      packingNames,
    )
      .map(
        ([k, v]) =>
          `<option value="${k}" ${c.packing_state === k ? "selected" : ""}>${v}</option>`,
      )
      .join(
        "",
      )}</select></label><div class="actions">${["fragile", "heavy", "priority"].map((f) => `<label class="check"><input type="checkbox" name="${f}" ${c[f] ? "checked" : ""}>${f === "priority" ? "Priority unpacking" : f[0].toUpperCase() + f.slice(1)}</label>`).join("")}</div><details><summary>Storage details</summary><label>Category<input name="category" value="${esc(c.category)}"></label><label>Keywords<input name="keywords" value="${esc(c.keywords)}"></label><label>Storage notes<textarea name="storage_notes">${esc(c.storage_notes)}</textarea></label><label>Review date, optional<input name="review_date" type="date" value="${esc(c.review_date)}"></label></details><p id="box-draft-status" role="status">Draft saves on this device as you type.</p><button id="box-save" class="primary full">Save box</button><p id="form-error" role="alert"></p></form>${id ? '<div class="actions"><button id="box-paper">Download A4 labels</button><button id="box-label">Brother label</button><button id="box-tags" class="secondary">Tags</button><button id="box-history" class="secondary">History</button></div>' : ""}`,
  );
  let photoData = c.photo?.startsWith("data:") ? c.photo : "";
  const value = () => {
    const v = Object.fromEntries(new FormData($("#box-form")));
    for (const f of ["fragile", "heavy", "priority"])
      v[f] = $("#box-form").elements[f].checked;
    v.revision = c.revision;
    if (photoData) v.photo = photoData;
    return v;
  };
  let writes = Promise.resolve();
  const retain = () => {
    const v = value();
    writes = writes
      .then(async () => {
        await store("put", {
          id: draftKey,
          namespace: me.namespace,
          kind: "box",
          state: "editing",
          value: submittedPayload || v,
          operation_id: key,
          submitted_payload: submittedPayload,
          created: Date.now(),
        });
        if ($("#box-draft-status"))
          $("#box-draft-status").textContent =
            "Draft retained on this device. Save to synchronise.";
      })
      .catch(() => {
        if ($("#box-draft-status"))
          $("#box-draft-status").textContent =
            "Device storage failed. Keep this page open.";
      });
    return writes;
  };
  $("#box-form").oninput = retain;
  $("#packing-photo").onchange = guard(async () => {
    const f = $("#packing-photo").files[0];
    if (!f) return;
    if (f.size > 20 * 1024 * 1024) throw Error("Use a photo under 20 MB");
    photoData = await fileData(f);
    await retain();
    $("#packing-photo-preview").innerHTML =
      `<img class="preview" src="${photoData}" alt="Draft box photo">`;
  });
  $("#box-form").onsubmit = guard(async (e) => {
    e.preventDefault();
    await retain();
    const p = submittedPayload || value();
    if (!navigator.onLine)
      throw Error(
        "Offline. Draft retained here. Reconnect and save to confirm this shared change.",
      );
    submittedPayload = p;
    await retain();
    $("#box-save").disabled = true;
    try {
      let out, box;
      if (id) {
        out = await api("containers/" + id, p, key);
        box = out.record;
      } else if (tag) {
        out = await api(
          "tags/" + tag.token,
          {
            action: "assign",
            revision: tag.revision,
            create_box: p,
          },
          key,
        );
        box = await api("containers/" + out.tag.container_id);
      } else {
        out = await api("containers", p, key);
        box = out.created[0].record;
      }
      await store("delete", draftKey);
      localStorage.setItem(
        "stash-place:" + me.namespace,
        p.physical_location_id || "",
      );
      await refresh();
      modal(
        `<h2>${esc(box.name)} · ${esc(box.code)} saved</h2><p>Saved on the server. Ready for the next step.</p><div class="actions"><button id="saved-add" class="primary">Add items and photos</button><button id="saved-print">Print label</button><button id="saved-scan">Scan next box</button><button id="saved-pack" class="secondary">Packing view</button></div>`,
      );
      $("#saved-add").onclick = () => {
        closeDialog();
        selectTub(box.code);
      };
      $("#saved-print").onclick = guard(() =>
        printLabels([tag ? "tag:" + tag.token : "box:" + box.id]),
      );
      $("#saved-scan").onclick = () => scanAny();
      $("#saved-pack").onclick = () => {
        closeDialog();
        nav("packing");
      };
    } catch (e) {
      if ($("#box-save")) $("#box-save").disabled = false;
      if (id && e.message.includes("changed elsewhere")) {
        const server = await api("containers/" + id);
        $("#form-error").textContent =
          "Someone else changed this box. Your draft is retained. Compare the current server version before saving.";
        $("#form-error").insertAdjacentHTML(
          "beforeend",
          `<pre>${esc(JSON.stringify(server, null, 2))}</pre><button type="button" id="keep-mine">Use my draft over this version</button><button type="button" id="use-server">Use server version</button>`,
        );
        $("#keep-mine").onclick = () => {
          submittedPayload = null;
          key = crypto.randomUUID();
          c.revision = server.revision;
          retain();
          $("#form-error").textContent =
            "Reviewed. Press Save box to apply your draft.";
        };
        $("#use-server").onclick = guard(async () => {
          await store("delete", draftKey);
          await boxEditor(id);
        });
        return;
      }
      if (e.status && [400, 403, 409].includes(e.status)) {
        submittedPayload = null;
        key = crypto.randomUUID();
        await retain();
      } else if ($("#form-error"))
        $("#form-error").textContent =
          "Save outcome is unknown. Retry Save to resolve the same operation before editing again.";
      throw e;
    }
  });
  if (id) {
    $("#box-paper").onclick = guard(() => paperSelection([id]));
    $("#box-label").onclick = guard(() => printLabels(["box:" + id]));
    $("#box-tags").onclick = guard(() => boxTags(id));
    $("#box-history").onclick = guard(() => recentPanel(id));
  }
}
async function openTag(value) {
  const t = (await api("tags/" + encodeURIComponent(value))).tag;
  if (t.state === "active" && t.container_id) {
    closeDialog();
    await boxEditor(t.container_id);
    return;
  }
  if (t.state === "active" && t.location_id) {
    const l = (await api("locations")).locations.find(
      (x) => x.id === t.location_id,
    );
    await locationMove(l.code);
    return;
  }
  modal(
    `<p class="eyebrow">Prepared tag</p><h2>${esc(t.code)}</h2><p>${t.state === "active" ? "This tag is ready to assign." : `This tag is ${esc(t.state)}. Its old mapping is retained in history.`}</p><p>Scanning does not change an assignment.</p>${t.state === "active" ? '<button id="tag-create" class="primary full">Create a new box</button><label>Existing box<select id="tag-box">' + tubOptions(null) + '</select></label><button id="tag-link" class="secondary full">Link selected box</button>' : ""}<button id="tag-manage" class="secondary full">Tag details</button>`,
  );
  if (t.state === "active") {
    $("#tag-create").onclick = guard(() => boxEditor(null, t));
    $("#tag-link").onclick = guard(async () => {
      const id = $("#tag-box").value;
      if (!id) throw Error("Select a box");
      await api("tags/" + t.token, {
        action: "assign",
        revision: t.revision,
        container_id: id,
      });
      await boxEditor(id);
    });
  }
  $("#tag-manage").onclick = () => tagDetail(t);
}
async function boxTags(id) {
  const rows = (await api("tags?box=" + id)).tags;
  modal(
    `<h2>Box tags</h2><p>Multiple tags can open the same box.</p><div id="box-tag-list">${rows.map((t) => `<button data-tag-token="${t.token}" class="secondary full">${esc(t.code)} · ${esc(t.state)}</button>`).join("")}</div><label>Prepared tag code or URL<input id="link-prepared"></label><button id="link-prepared-save">Link tag</button>`,
  );
  document
    .querySelectorAll("[data-tag-token]")
    .forEach(
      (b) =>
        (b.onclick = guard(async () =>
          tagDetail((await api("tags/" + b.dataset.tagToken)).tag),
        )),
    );
  $("#link-prepared-save").onclick = guard(async () => {
    const t = (
      await api("tags/" + encodeURIComponent($("#link-prepared").value))
    ).tag;
    await api("tags/" + t.token, {
      action: "assign",
      revision: t.revision,
      container_id: id,
    });
    await boxTags(id);
  });
}
async function tagDetail(t) {
  places = (await api("locations")).locations;
  modal(
    `<h2>${esc(t.code)}</h2><p>${esc(t.state)} · ${esc(t.encoding)}</p><p class="wrap">${esc(t.url)}</p><img class="label-preview" src="/api/label-preview?ref=tag:${t.token}" alt="Matching QR label"><div class="actions"><button id="tag-print">Print matching label</button><button id="tag-copy">Copy URL</button></div><label>Assign or reassign to box<select id="tag-new-box">${tubOptions(t.container_id)}</select></label><label>Or assign to location<select id="tag-new-place">${options(places, t.location_id)}</select></label><button id="tag-assign">Confirm assignment</button><details><summary>Replace, retire or mark lost</summary><label>Old tag to replace with this tag<input id="old-tag-code"></label><button id="tag-replace">Replace old tag</button><div class="actions"><button id="tag-retire">Retire</button><button id="tag-lost">Mark lost</button><button id="tag-reactivate">Reactivate</button></div></details><button id="tag-phone-resume" class="secondary full">Resume phone preparation</button><button id="tag-history" class="secondary full">History</button>`,
  );
  $("#tag-print").onclick = guard(() => printLabels(["tag:" + t.token]));
  $("#tag-copy").onclick = guard(async () => {
    await navigator.clipboard.writeText(t.url);
    notice("URL copied");
  });
  $("#tag-assign").onclick = guard(async () => {
    const box = $("#tag-new-box").value,
      loc = $("#tag-new-place").value;
    if (!confirm("Confirm this tag assignment?")) return;
    const out = await api("tags/" + t.token, {
      action: t.container_id || t.location_id ? "reassign" : "assign",
      revision: t.revision,
      container_id: box,
      location_id: loc,
      confirm: true,
    });
    await tagDetail(out.tag);
  });
  for (const a of ["retire", "lost", "reactivate"])
    $("#tag-" + a).onclick = guard(async () => {
      if (!confirm("Confirm " + a + " for " + t.code + "?")) return;
      const out = await api("tags/" + t.token, {
        action: a,
        revision: t.revision,
        confirm: true,
      });
      await tagDetail(out.tag);
    });
  $("#tag-replace").onclick = guard(async () => {
    const old = (
      await api("tags/" + encodeURIComponent($("#old-tag-code").value))
    ).tag;
    if (
      !confirm(
        "Retire " +
          old.code +
          " and use " +
          t.code +
          " for its existing box or location?",
      )
    )
      return;
    await tagDetail(
      (
        await api("tags/" + t.token, {
          action: "replace",
          revision: t.revision,
          replace_code: old.token,
          replace_revision: old.revision,
          confirm: true,
        })
      ).tag,
    );
  });
  $("#tag-phone-resume").onclick = guard(async () => {
    await api("tags/" + t.token, {
      action: "phone_prepare",
      revision: t.revision,
    });
    batchId = t.batch_id;
    await tagPanel();
  });
  $("#tag-history").onclick = guard(() => recentPanel(t.token));
}
async function tagPanel() {
  const batches = (await api("batches")).batches;
  modal(
    `<h2>Prepare tags</h2><p>Each sticker gets its own permanent URL. Tags can be assigned to boxes later.</p><form id="batch-create"><label>Batch name<input name="name" value="Packing tags"></label><label>Number of tags<input name="count" type="number" min="1" max="200" value="20"></label><button class="primary full">Create unassigned tags</button></form><label>Batch<select id="batch-select">${options(batches, batchId, "Select a batch")}</select></label><div id="batch-body"></div>`,
  );
  $("#batch-create").onsubmit = guard(async (e) => {
    e.preventDefault();
    const p = Object.fromEntries(new FormData(e.target));
    p.count = Number(p.count);
    batchId = (await api("batches", p)).id;
    await tagPanel();
  });
  $("#batch-select").onchange = guard(async () => {
    batchId = $("#batch-select").value;
    await batchBody();
  });
  if (batchId) await batchBody();
}
async function batchBody() {
  if (!batchId) return;
  tagRows = (await api("tags?batch=" + batchId)).tags;
  const pending = tagRows.find(
    (t) =>
      ["unwritten", "phone_pending"].includes(t.encoding) &&
      !t.container_id &&
      !t.location_id &&
      t.state === "active",
  );
  $("#batch-body").innerHTML =
    `<p>${tagRows.filter((t) => ["verified", "phone_verified"].includes(t.encoding)).length} of ${tagRows.length} read back verified</p><div class="actions"><button id="phone-next" ${pending ? "" : "disabled"}>Copy next tag URL</button><button id="station-open">Encoding station</button><button id="batch-labels">Print batch labels</button><button id="batch-export">Export results</button></div><p>On iPhone, use NFC Tools: Write, Add a record, URL, paste, then Write. Read the sticker again and verify its URL here. No CSV import is assumed.</p><div id="phone-step"></div><div class="tag-list">${tagRows.map((t) => `<button data-tag="${t.token}" class="secondary">${esc(t.code)}<small>${esc(t.encoding)} · ${t.container_id ? "Assigned" : "Unassigned"}</small></button>`).join("")}</div>`;
  document
    .querySelectorAll("[data-tag]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          tagDetail(tagRows.find((t) => t.token === b.dataset.tag))),
    );
  $("#batch-export").onclick = () =>
    download("stash-tag-batch-" + batchId + ".json", {
      batch_id: batchId,
      tags: tagRows,
    });
  $("#batch-labels").onclick = guard(() =>
    printLabels(
      tagRows.filter((t) => t.state === "active").map((t) => "tag:" + t.token),
    ),
  );
  $("#station-open").onclick = guard(stationPanel);
  $("#phone-next").onclick = guard(async () => {
    let t = pending;
    if (t.encoding === "unwritten")
      t = (
        await api("tags/" + t.token, {
          action: "phone_prepare",
          revision: t.revision,
        })
      ).tag;
    Object.assign(pending, t);
    const verifyKey = crypto.randomUUID();
    $("#phone-step").innerHTML =
      `<h3>${esc(t.code)}</h3><label>URL to write<input id="phone-url" readonly value="${esc(t.url)}"></label><button id="phone-copy-again">Copy URL</button><p>Write this URL, then use the NFC app Read tab to read it back.</p><label>Paste the URL read from the physical sticker<input id="phone-readback" type="url"></label><label class="check"><input id="phone-read-confirm" type="checkbox">I read this URL from the physical sticker</label><label class="check"><input id="phone-print-after" type="checkbox">Queue one matching label after verification</label><button id="phone-verify">Verify and continue</button><button id="phone-skip" class="secondary">Skip this tag for now</button>`;
    $("#phone-verify").onclick = guard(async () => {
      const print = $("#phone-print-after").checked;
      await api(
        "tags/" + t.token,
        {
          action: "phone_verify",
          revision: t.revision,
          readback: $("#phone-readback").value.trim(),
          confirm: $("#phone-read-confirm").checked,
        },
        verifyKey,
      );
      if (print)
        await api(
          "print-jobs",
          { refs: ["tag:" + t.token], copies: 1 },
          "phone-label-" + t.token,
        );
      await batchBody();
      notice("Physical readback recorded. Printing has its own queue state.");
    });
    $("#phone-copy-again").onclick = guard(() =>
      navigator.clipboard.writeText(t.url),
    );
    try {
      await navigator.clipboard.writeText(t.url);
    } catch {
      notice("URL ready. Tap Copy URL or select and copy the URL field.");
    }
    $("#phone-skip").onclick = guard(async () => {
      await api("tags/" + t.token, {
        action: "phone_skip",
        revision: t.revision,
      });
      await batchBody();
    });
  });
}
async function stationPanel() {
  const rows = (await api("stations")).stations;
  modal(
    `<h2>Encoding station</h2><p>Writing is armed for five minutes. Verified tags extend the active period. Inspect mode never writes.</p>${me.owner ? '<label>New station name<input id="station-name" value="Packing station"></label><button id="station-create">Create station credential</button>' : ""}<div id="station-secret"></div><div id="station-rows">${rows.map((s) => `<article class="c313-card"><h3>${esc(s.name)}</h3><p>${s.revoked ? "Revoked" : s.armed ? "Armed" : "Disarmed"}</p><p>${esc(s.last_result || "No report yet")}</p><small>Last contact: ${esc(s.last_seen || "Not connected")}</small><label class="check"><input type="checkbox" id="print-after-${s.id}" ${s.print_after ? "checked" : ""}>Print matching label after readback</label><div class="actions"><button data-arm="${s.id}" ${batchId && !s.revoked ? "" : "disabled"}>Arm selected batch</button><button data-disarm="${s.id}">Disarm</button>${me.owner ? `<button data-revoke="${s.id}">Revoke credential</button>` : ""}</div><details><summary>Recovery and deliberate overwrite</summary><label>Inspected UID<input id="uid-${s.id}" placeholder="14 hexadecimal characters"></label><button data-overwrite="${s.id}">Allow this nonblank tag once</button><label>Reservation<select id="skip-${s.id}">${s.reservations.map((v) => `<option value="${v.id}">${esc(v.code)} · ${esc(v.state)}</option>`).join("")}</select></label><button data-skip="${s.id}">Skip reserved tag</button><button data-resume="${s.id}">Resume skipped tag</button></details></article>`).join("")}</div><button id="station-refresh" class="secondary full">Refresh station status</button>`,
  );
  if (me.owner)
    $("#station-create").onclick = guard(async () => {
      const out = await api("stations", { name: $("#station-name").value });
      $("#station-secret").innerHTML =
        `<p>Save this revocable credential into the station over its USB serial setup. It is shown once.</p><pre>${esc(JSON.stringify({ station_id: out.station.id, credential: out.credential, origin: location.origin }, null, 2))}</pre><p>It grants only station allocation and verification. Keep it out of source files.</p>`;
    });
  for (const a of ["arm", "disarm", "revoke", "overwrite", "skip", "resume"])
    document.querySelectorAll("[data-" + a + "]").forEach(
      (b) =>
        (b.onclick = guard(async () => {
          const s = rows.find((x) => x.id === b.dataset[a]);
          if (
            ["overwrite", "revoke", "skip", "resume"].includes(a) &&
            !confirm("Confirm " + a + " for this station?")
          )
            return;
          const p = {
            action: a,
            revision: s.revision,
            batch_id: batchId,
            print_after: $("#print-after-" + s.id).checked,
            uid: $("#uid-" + s.id).value.toUpperCase(),
            reservation_id: $("#skip-" + s.id).value,
            confirm: true,
          };
          await api("stations/" + s.id, p);
          await stationPanel();
        })),
    );
  $("#station-refresh").onclick = guard(stationPanel);
}
async function printLabels(refs) {
  if (!refs.length) throw Error("Select at least one label");
  const p = await api("printer");
  modal(
    `<h2>Print labels</h2><p>${refs.length} labels · ${p.tape_mm} mm tape · ${p.print_height_mm} mm printable height · ${p.dpi} dpi</p><p>Preview is the raster sent to the printer. Use the PNG in P touch Editor or the exact size SVG when direct printing is unavailable.</p><img id="print-preview" class="label-preview" src="/api/label-preview?ref=${encodeURIComponent(refs[0])}" alt="Actual label preview"><label>Copies of each label<input id="label-copies" type="number" value="1" min="1" max="20"></label><p>Saved box names are included on every box label.</p><div class="actions"><button id="queue-labels" class="primary">Queue labels</button><a id="png-export" href="/api/label-preview?ref=${encodeURIComponent(refs[0])}&download=1">Download PNG</a><a id="svg-export" href="/api/label-preview?ref=${encodeURIComponent(refs[0])}&format=svg">Exact size SVG</a><button id="labels-queue" class="secondary">Printer and queue</button></div><p id="form-error" role="alert"></p>`,
  );
  const key = crypto.randomUUID();
  let submitted = false,
    printPlan = null;
  $("#queue-labels").onclick = guard(async () => {
    if (submitted) return;
    submitted = true;
    $("#queue-labels").disabled = true;
    try {
      const copies = printPlan?.copies || Number($("#label-copies").value);
      if (!Number.isInteger(copies) || copies < 1 || copies > 20)
        throw Error("Choose 1 to 20 copies");
      printPlan ||= { copies, include_title: true };
      $("#label-copies").disabled = true;
      let j;
      const chunkSize = Math.floor(50 / copies);
      for (let offset = 0; offset < refs.length; offset += chunkSize)
        j = await api(
          "print-jobs",
          {
            refs: refs.slice(offset, offset + chunkSize),
            copies,
            include_title: printPlan.include_title,
          },
          key + "-" + offset,
        );
      await printerPanel();
      notice("Job queued: " + j.id);
    } catch (e) {
      submitted = false;
      if ($("#queue-labels")) $("#queue-labels").disabled = false;
      throw e;
    }
  });
  $("#labels-queue").onclick = guard(printerPanel);
}
async function printerPanel() {
  const [p, q] = await Promise.all([api("printer"), api("print-jobs")]);
  modal(
    `<h2>Brother PT-P750W</h2><p>${p.configured ? "Private printer connection configured" : "Printer connection awaits commissioning"}</p><p>24 mm is the maximum tape width. The print head is 128 dots, about 18 mm high.</p><div class="actions"><button id="printer-check">Check connection and cassette</button><button id="printer-test">Preview test label</button><button id="queue-refresh" class="secondary">Refresh</button></div><p role="status">${esc(p.status.detail || (p.status.status?.Status ? "Reported tape: " + p.status.status.Status.MediaWidthMM + " mm. " + (p.status.status.Status.Errors?.length ? p.status.status.Status.Errors.join(", ").replaceAll("-", " ") : "No device error reported.") : "Connection and cassette have not been checked."))}</p>${
      me.owner
        ? `<form id="printer-settings"><label>TZe tape width<select name="tape_mm"><option value="24" ${p.tape_mm === 24 ? "selected" : ""}>24 mm</option><option value="18" ${p.tape_mm === 18 ? "selected" : ""}>18 mm</option></select></label><label>Cut option<select name="finishing">${[
            ["single-full", "Cut each label"],
            ["single-half", "Half cut each label"],
            ["batch-half", "Chain with half cuts, final full cut"],
          ]
            .map(
              ([k, v]) =>
                `<option value="${k}" ${p.finishing === k ? "selected" : ""}>${v}</option>`,
            )
            .join(
              "",
            )}</select></label><button>Save tape settings</button></form>`
        : ""
    }<h3>Print queue</h3><p>Queued jobs can be cancelled. Sending cannot reliably be cancelled. An uncertain job is never automatically printed again.</p>${q.jobs.map((j) => `<article class="c313-card"><h3>${j.labels.map((x) => esc(x.code)).join(", ")}</h3><p><strong>${esc(j.state.replaceAll("_", " "))}</strong></p><p>${esc(j.detail)}</p><small>${esc(j.created)}</small><div class="actions">${["queued", "held"].includes(j.state) ? `<button data-job="${j.id}" data-action="cancel">Cancel</button>` : ""}${j.state === "held" ? `<button data-job="${j.id}" data-action="resume">Resume</button>` : ""}${["sent_unconfirmed", "outcome_unknown"].includes(j.state) ? `<button data-job="${j.id}" data-action="confirm">I checked all labels</button>` : ""}${!["queued", "sending", "held"].includes(j.state) ? `<button data-job="${j.id}" data-action="reprint">Reprint deliberately</button>` : ""}</div></article>`).join("") || "<p>No jobs yet.</p>"}`,
  );
  $("#printer-check").onclick = guard(async () => {
    await api("printer", { action: "check" });
    await printerPanel();
  });
  $("#printer-test").onclick = guard(() => printLabels(["test"]));
  $("#queue-refresh").onclick = guard(printerPanel);
  if (me.owner)
    $("#printer-settings").onsubmit = guard(async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(e.target));
      d.tape_mm = Number(d.tape_mm);
      await api("printer", { ...d, revision: p.revision });
      await printerPanel();
    });
  document.querySelectorAll("[data-job]").forEach(
    (b) =>
      (b.onclick = guard(async () => {
        if (
          ["reprint", "confirm"].includes(b.dataset.action) &&
          !confirm(
            b.dataset.action === "reprint"
              ? "Inspect the printer first. Print another physical copy?"
              : "Have you inspected every physical label in this job?",
          )
        )
          return;
        await api("print-jobs/" + b.dataset.job, {
          action: b.dataset.action,
          confirm: true,
        });
        await printerPanel();
      })),
  );
}
async function locationsPanel() {
  places = (await api("locations")).locations;
  modal(
    `<h2>Physical locations</h2><p>Build a hierarchy such as property, garage, shelf and position. Moving a parent changes the effective location of everything inside.</p><div class="actions"><button id="new-place">New location</button><button id="move-flow">Scan location and boxes</button></div>${places.map((l) => `<button data-place="${l.id}" class="secondary full">${esc(l.path)} · ${esc(l.code)}</button>`).join("")}`,
  );
  $("#new-place").onclick = () => placeEditor();
  $("#move-flow").onclick = guard(() => locationMove());
  document
    .querySelectorAll("[data-place]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          placeEditor(places.find((l) => l.id === b.dataset.place))),
    );
}
function placeEditor(l = {}) {
  modal(
    `<h2>${l.id ? "Edit" : "New"} location</h2><form id="place-form"><label>Name<input name="name" value="${esc(l.name)}" required></label>${!l.id ? '<label>Readable code, optional<input name="code"></label>' : ""}<label>Parent location<select name="parent_id">${options(
      places.filter((p) => p.id !== l.id),
      l.parent_id,
      "Top level site",
    )}</select></label><label>Storage notes<textarea name="notes">${esc(l.notes)}</textarea></label><button class="primary full">Save location</button><p id="form-error"></p></form>${l.id ? `<p>Code: ${esc(l.code)}</p><p>Assign a prepared tag to this location from Tag details. It can then start a batch move.</p>` : ""}`,
  );
  $("#place-form").onsubmit = guard(async (e) => {
    e.preventDefault();
    const p = Object.fromEntries(new FormData(e.target));
    if (!p.code) delete p.code;
    if (l.id) p.revision = l.revision;
    await api("locations" + (l.id ? "/" + l.id : ""), p);
    await locationsPanel();
  });
}
async function locationMove(code = null, ids = []) {
  places = (await api("locations")).locations;
  await refresh();
  let chosen = places.find((l) => l.code === code),
    selectedBoxes = new Map(ids.map((id) => [id, tub(id)]));
  const draw = () => {
    modal(
      `<h2>Move several boxes</h2><label>Physical destination<select id="move-location">${options(places, chosen?.id)}</select></label><button id="move-scan-location">Scan location tag</button><label>State on arrival<select id="move-state"><option value="stored">Stored or arrived</option><option value="in_transit">In transit</option><option value="unpacked">Unpacked</option></select></label><div class="actions"><button id="move-scan-box">Scan box</button><button id="move-add-box" class="secondary">Choose box</button></div><div>${[...selectedBoxes.values()].map((c) => `<p>${esc(c.code)} · ${esc(c.effective_location)} <button data-remove="${c.id}" class="link">Remove</button></p>`).join("")}</div><button id="move-confirm" class="primary full">Confirm move of ${selectedBoxes.size} boxes</button><p id="form-error"></p>`,
    );
    $("#move-location").onchange = () => {
      chosen = places.find((l) => l.id === $("#move-location").value);
    };
    $("#move-scan-location").onclick = () =>
      scanAny(async (raw) => {
        const target = await resolveScan(raw);
        if (!target.location) throw Error("Scan a location tag");
        chosen = target.location;
        draw();
      });
    const add = (c) => {
      if (selectedBoxes.has(c.id)) {
        notice("Already scanned " + c.code, true);
        draw();
        return;
      }
      selectedBoxes.set(c.id, c);
      draw();
    };
    $("#move-scan-box").onclick = () =>
      scanAny(async (raw) => {
        const target = await resolveScan(raw);
        if (!target.box) throw Error("Scan an assigned box tag or box QR");
        add(target.box);
      });
    $("#move-add-box").onclick = () => {
      modal(
        `<h2>Choose box</h2><select id="move-box-pick">${tubOptions(null)}</select><button id="move-pick">Add box</button>`,
      );
      $("#move-pick").onclick = () => {
        const c = tub($("#move-box-pick").value);
        if (c) add(c);
      };
    };
    document.querySelectorAll("[data-remove]").forEach(
      (b) =>
        (b.onclick = () => {
          selectedBoxes.delete(b.dataset.remove);
          draw();
        }),
    );
    $("#move-confirm").onclick = guard(async () => {
      if (!chosen || !selectedBoxes.size)
        throw Error("Choose a location and scan at least one box");
      const boxes = [...selectedBoxes.values()].map((c) => ({
        id: c.id,
        revision: c.revision,
      }));
      await api("moves", {
        location_id: chosen.id,
        location_revision: chosen.revision,
        boxes,
        packing_state: $("#move-state").value,
      });
      boxSelection.clear();
      closeDialog();
      await renderPacking();
      notice("Move confirmed on the server. History retained.");
    });
  };
  draw();
}
async function recentPanel(entity) {
  const events = (
    await api(
      "activity" + (entity ? "?entity_id=" + encodeURIComponent(entity) : ""),
    )
  ).events;
  modal(
    `<h2>Recent changes</h2><ol class="c313-feed">${events.map((e) => `<li><strong>${esc(e.actor)}</strong> · ${esc(e.action)} · ${esc(e.after.code || e.after.title || e.entity)}<br><time>${esc(new Date(e.created).toLocaleString())}</time>${e.before.effective_location || e.after.effective_location ? `<p>${esc(e.before.effective_location)} → ${esc(e.after.effective_location)}</p>` : ""}</li>`).join("")}</ol>`,
  );
}
async function manifestPanel() {
  const data = await api("moving-manifest");
  modal(
    `<div class="manifest"><h2>Stash moving manifest</h2><p>Generated ${esc(new Date().toLocaleString())}. Keep a protected copy for an outage.</p><div class="actions no-print"><button id="manifest-print">Print manifest</button><a href="/api/moving-manifest?format=csv">Download CSV</a><button id="manifest-json">Download JSON</button></div>${data.boxes.map((c) => `<article><h3>${esc(c.code)} · ${esc(c.name)} ${c.priority ? "· PRIORITY" : ""}</h3><p>${esc(c.location)} → ${esc(c.destination)} · ${esc(c.state)}</p><p>${esc(c.description)}</p><p>${esc(c.contents)}</p></article>`).join("") || "<p>No boxes yet.</p>"}</div>`,
  );
  $("#manifest-print").onclick = () => window.print();
  $("#manifest-json").onclick = () =>
    download("stash-moving-manifest.json", data);
}
async function resolveScan(raw) {
  raw = raw.trim();
  let route = "";
  if (raw.startsWith("http")) {
    const u = new URL(raw);
    if (u.origin !== location.origin) throw Error("Use a Stash URL");
    route = u.pathname;
  }
  if (route.startsWith("/t/") || (!route && /^T[0-9A-F]{8}$/i.test(raw))) {
    const t = (
      await api("tags/" + encodeURIComponent(route ? route.slice(3) : raw))
    ).tag;
    if (t.state !== "active") throw Error("This tag is " + t.state);
    return {
      tag: t,
      box: tubs.find((c) => c.id === t.container_id),
      location: places.find((l) => l.id === t.location_id),
    };
  }
  if (route.startsWith("/l/"))
    return {
      location: places.find(
        (l) => l.code === decodeURIComponent(route.slice(3)),
      ),
    };
  const code = (
    route.startsWith("/c/") ? decodeURIComponent(route.slice(3)) : raw
  ).toUpperCase();
  return {
    box: tubs.find((c) => c.code === code),
    location: places.find((l) => l.code === code),
  };
}
async function scanAny(callback = null) {
  places = (await api("locations")).locations;
  const open = guard(async (raw) => {
    stopScan();
    if (callback) {
      await callback(raw);
      return;
    }
    const x = await resolveScan(raw);
    if (x.tag) await openTag(x.tag.token);
    else if (x.box) {
      closeDialog();
      await boxEditor(x.box.id);
    } else if (x.location) await locationMove(x.location.code);
    else throw Error("Box or tag not found");
  });
  modal(
    '<h2>Scan next box or location</h2><video id="camera" playsinline muted></video><p id="camera-status"></p><form id="code-form"><label>Readable code or Stash URL<input id="manual-code" required></label><button class="primary full">Open</button></form>',
  );
  $("#code-form").onsubmit = (e) => {
    e.preventDefault();
    open($("#manual-code").value);
  };
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
    });
    const video = $("#camera");
    if (!video) {
      stopScan();
      return;
    }
    video.srcObject = stream;
    await video.play();
    const canvas = document.createElement("canvas"),
      ctx = canvas.getContext("2d", { willReadFrequently: true });
    const tick = () => {
      if (!stream || !$("#camera")) return;
      if (video.readyState >= 2) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0);
        const img = ctx.getImageData(0, 0, canvas.width, canvas.height),
          q = jsQR(img.data, img.width, img.height);
        if (q) {
          open(q.data);
          return;
        }
      }
      requestAnimationFrame(tick);
    };
    tick();
  } catch (e) {
    if ($("#camera-status"))
      $("#camera-status").textContent =
        "Camera unavailable. Enter the code or URL above.";
  }
}
$("#scan").onclick = guard(() => scanAny());
// The page remains account gated. Only public shell resources go into the service worker cache.
window.addEventListener(
  "pageshow",
  guard(async () => {
    if (me) {
      const live = await api("me");
      if (live.id !== me.id) {
        $("#view").textContent =
          "Account changed. Reload to open this account.";
        closeDialog();
        location.reload();
      }
    }
  }),
);
