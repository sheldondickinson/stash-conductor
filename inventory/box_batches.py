"""Persistent household box preparation batches, independent of NFC and printers."""

import hashlib
import json
import uuid

from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify

from .api import Problem, api, cdata, event, revision, text
from .box_allocation import create_box, next_number
from .box_names import NameAllocator
from .models import BoxBatch, BoxBatchMember, Container
from .paper_labels import render_pdf

MAX_BOXES = 240


def quantity(value):
    if type(value) is not int or not 1 <= value <= MAX_BOXES:
        raise Problem(f"Choose 1 to {MAX_BOXES} boxes")
    return value


def bdata(batch, details=True):
    members = list(batch.members.select_related("box"))
    return {
        "id": str(batch.id),
        "name": batch.name,
        "created": batch.created.isoformat(),
        "count": len(members),
        "pages": (len(members) + 11) // 12,
        "defaults": batch.defaults,
        "first_code": members[0].box.code if members else "",
        "last_code": members[-1].box.code if members else "",
        **({"boxes": [cdata(m.box) for m in members]} if details else {}),
    }


@api
def preview(r):
    if r.method != "GET":
        raise Problem("GET required", 405)
    count = quantity(int(r.GET.get("count", "12")))
    names = NameAllocator()
    start = next_number()
    return {
        "count": count,
        "pages": (count + 11) // 12,
        "labels": count * 2,
        "maximum": MAX_BOXES,
        "reserved": False,
        "boxes": [
            {"code": f"B{start + n:03d}", "name": names.allocate()}
            for n in range(count)
        ],
    }


@api
def batches(r, pk=None):
    if r.method == "GET":
        if pk:
            return bdata(BoxBatch.objects.get(pk=pk))
        if r.GET.get("request_id"):
            return bdata(
                BoxBatch.objects.get(request_id=r.GET["request_id"], actor=r.user)
            )
        rows = BoxBatch.objects.order_by("-created")
        query = r.GET.get("q", "").strip().casefold()[:160]
        if query:
            rows = rows.filter(
                Q(name__icontains=query)
                | Q(members__box__code__icontains=query)
                | Q(members__box__name__icontains=query)
            ).distinct()
        return {"batches": [bdata(batch, details=False) for batch in rows[:100]]}
    if r.method != "POST" or pk:
        raise Problem("POST required", 405)
    p = r.payload
    request_id = uuid.UUID(p["request_id"])
    digest = hashlib.sha256(
        json.dumps(p, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    previous = BoxBatch.objects.filter(request_id=request_id).first()
    if previous:
        if previous.actor_id != r.user.pk or previous.request_digest != digest:
            raise Problem("This creation request belongs to another batch", 409)
        return bdata(previous)
    count = quantity(p.get("count", 12))
    if any(key in p for key in ("code", "codes", "start_number")):
        raise Problem("Box numbers are allocated by Stash")
    defaults = {
        "physical_location_id": p.get("physical_location_id") or None,
        "destination": text(p.get("destination", ""), 160),
        "packing_state": "empty",
    }
    proposed = p.get("proposed_names", [])
    overrides = p.get("name_overrides", {})
    if (
        not isinstance(proposed, list)
        or len(proposed) not in (0, count)
        or not isinstance(overrides, dict)
    ):
        raise Problem("Invalid name preview")
    proposed = [text(n, 160) for n in proposed]
    if any(not k.isdigit() or not 0 <= int(k) < count for k in overrides):
        raise Problem("Invalid name position")
    overrides = {int(k): text(v, 160) for k, v in overrides.items()}
    allocator = NameAllocator(overrides.values())
    batch = BoxBatch.objects.create(
        request_id=request_id,
        request_digest=digest,
        actor=r.user,
        name=text(p.get("name", ""), 160),
        defaults=defaults,
    )
    for index in range(count):
        box = create_box(
            {
                **defaults,
                "name": overrides.get(index, ""),
                "proposed_name": proposed[index] if proposed else "",
            },
            allocator,
        )
        BoxBatchMember.objects.create(batch=batch, box=box, position=index)
        event(r, "container", box, "create", {})
    # The API wrapper commits this receipt and all boxes before any PDF request.
    return bdata(batch)


def selected_boxes(raw):
    if (
        not isinstance(raw, list)
        or not raw
        or len(raw) > MAX_BOXES
        or len(set(raw)) != len(raw)
    ):
        raise Problem(f"Choose 1 to {MAX_BOXES} different boxes")
    result = {str(c.id): c for c in Container.objects.filter(pk__in=raw)}
    if len(result) != len(raw):
        raise Problem("One of these boxes no longer exists", 404)
    return [result[str(uuid.UUID(x))] for x in raw]


@api
def labels(r, pk=None):
    if r.method != "GET":
        raise Problem("GET required", 405)
    batch = BoxBatch.objects.get(pk=pk) if pk else None
    if batch:
        boxes = [m.box for m in batch.members.select_related("box")]
        title = batch.name or "Box batch"
        date = batch.created.date()
    else:
        if "codes" in r.GET:
            codes = r.GET["codes"].split(",")
            quantity(len(codes))
            rows = {c.code: c for c in Container.objects.filter(code__in=codes)}
            if len(rows) != len(codes):
                raise Problem("Choose different, existing box codes", 404)
            boxes = [rows[code] for code in codes]
        else:
            boxes = selected_boxes(r.GET.get("boxes", "").split(","))
        title, date = "Selected boxes", timezone.localdate()
    try:
        content = render_pdf(boxes, title)
    except Exception:
        # Rendering cannot undo or repeat creation. Keep the retry at this read endpoint.
        return HttpResponse(
            "Labels could not be rendered. Your boxes are saved. Reopen the batch and retry Download A4 labels.",
            status=503,
            content_type="text/plain",
        )
    response = HttpResponse(content, content_type="application/pdf")
    suffix = "-" + str(batch.id)[:8] if batch else ""
    filename = f"stash-{slugify(title)[:60] or 'boxes'}-{date}{suffix}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


@api
def name_unnamed(r):
    if r.method != "POST":
        raise Problem("POST required", 405)
    chosen = r.payload.get("boxes", [])
    boxes = selected_boxes([x["id"] for x in chosen])
    allocator = NameAllocator()
    for box, requested in zip(boxes, chosen):
        revision(box, requested)
        if box.name.strip():
            raise Problem(
                "Select only unnamed boxes. Existing names are preserved.", 409
            )
        before = cdata(box)
        box.name = allocator.allocate()
        box.revision += 1
        box.save()
        event(r, "container", box, "name", before)
    return {"boxes": [cdata(c) for c in boxes]}
