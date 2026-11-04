"""Household packing and location operations. All shared writes are transactional."""

import csv
import io
import secrets
from datetime import date
from urllib.parse import urlsplit

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse

from .api import Problem, api, cdata, event, photo, revision, text
from .models import Container, Event, Location, Tag, TagBatch

STATES = ("empty", "partly_packed", "sealed", "in_transit", "stored", "unpacked")


def ancestry(obj, field="parent"):
    seen = set()
    while obj:
        if obj.pk in seen:
            raise Problem("Containment cycle", 409)
        seen.add(obj.pk)
        yield obj
        obj = getattr(obj, field)


def location_path(obj):
    return " / ".join(reversed([x.name for x in ancestry(obj)])) if obj else ""


def whereabouts(box):
    for b in ancestry(box):
        if b.physical_location_id:
            return location_path(b.physical_location)
        if b.location:
            return b.location
    return ""


def ldata(obj):
    return {
        "id": str(obj.id),
        "code": obj.code,
        "name": obj.name,
        "parent_id": str(obj.parent_id) if obj.parent_id else None,
        "notes": obj.notes,
        "revision": obj.revision,
        "path": location_path(obj),
    }


def audit(r, entity, obj, action, before, after):
    Event.objects.create(
        entity=entity,
        entity_id=str(obj.pk),
        actor=r.user,
        action=action,
        before=before,
        after=after,
    )


def apply_box(c, p):
    for field, limit in [
        ("destination", 160),
        ("description", 10000),
        ("category", 160),
        ("keywords", 500),
        ("storage_notes", 10000),
    ]:
        if field in p:
            setattr(c, field, text(p[field], limit))
    for field in ("fragile", "heavy", "priority"):
        if field in p:
            if type(p[field]) is not bool:
                raise Problem("Use a true or false marker")
            setattr(c, field, p[field])
    if "packing_state" in p:
        if p["packing_state"] not in STATES:
            raise Problem("Unknown packing state")
        c.packing_state = p["packing_state"]
    if "review_date" in p:
        c.review_date = (
            date.fromisoformat(p["review_date"]) if p["review_date"] else None
        )
    if "physical_location_id" in p:
        c.physical_location = (
            Location.objects.get(pk=p["physical_location_id"])
            if p["physical_location_id"]
            else None
        )
        c.parent = None
        c.location = ""
    if "parent_id" in p:
        parent = Container.objects.get(pk=p["parent_id"]) if p["parent_id"] else None
        if parent and any(x.pk == c.pk for x in ancestry(parent)):
            raise Problem("A box cannot contain itself", 409)
        c.parent = parent
        if parent:
            c.physical_location = None
            c.location = ""


@api
def locations(r, pk=None):
    if r.method == "GET":
        return {"locations": [ldata(x) for x in Location.objects.order_by("name")]}
    if r.method != "POST":
        raise Problem("POST required", 405)
    p = r.payload
    obj = (
        Location.objects.get(pk=pk)
        if pk
        else Location(code=text(p.get("code", "L" + secrets.token_hex(3)), 24).upper())
    )
    before = ldata(obj) if pk else {}
    if pk:
        revision(obj, p)
    obj.name = text(p.get("name", obj.name), 160)
    if not obj.name:
        raise Problem("Give the location a name")
    obj.notes = text(p.get("notes", obj.notes), 10000)
    if "parent_id" in p:
        parent = Location.objects.get(pk=p["parent_id"]) if p["parent_id"] else None
        if parent and any(x.pk == obj.pk for x in ancestry(parent)):
            raise Problem("A location cannot contain itself", 409)
        obj.parent = parent
    if pk:
        obj.revision += 1
    obj.save()
    after = ldata(obj)
    audit(r, "location", obj, "edit" if pk else "create", before, after)
    return after


@api
def moves(r):
    if r.method != "POST":
        raise Problem("POST required", 405)
    p = r.payload
    entries = p.get("boxes", [])
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise Problem("Select 1 to 100 boxes")
    if len({x["id"] for x in entries}) != len(entries):
        raise Problem("The same box was scanned twice")
    loc = Location.objects.get(pk=p["location_id"])
    revision(loc, {"revision": p.get("location_revision")})
    results = []
    for x in entries:
        c = Container.objects.get(pk=x["id"])
        revision(c, x)
        before = cdata(c)
        apply_box(
            c,
            {
                "physical_location_id": str(loc.id),
                "packing_state": p.get("packing_state", "stored"),
            },
        )
        c.revision += 1
        c.save()
        results.append(event(r, "container", c, "move", before))
    return {"moved": results, "location": ldata(loc)}


@api
def activity(r):
    rows = Event.objects.select_related("actor").order_by("-created")
    if r.GET.get("entity_id"):
        rows = rows.filter(entity_id=r.GET["entity_id"])
    return {
        "events": [
            {
                "id": str(x.id),
                "entity": x.entity,
                "entity_id": x.entity_id,
                "action": x.action,
                "actor": x.actor.first_name or x.actor.username,
                "created": x.created.isoformat(),
                "before": x.before,
                "after": x.after,
            }
            for x in rows[:100]
        ]
    }


def tdata(t):
    return {
        "token": t.token,
        "code": t.code,
        "url": settings.ORIGIN + "/t/" + t.token,
        "batch_id": str(t.batch_id),
        "state": t.state,
        "encoding": t.encoding,
        "encoded_at": t.encoded_at.isoformat() if t.encoded_at else None,
        "container_id": str(t.container_id) if t.container_id else None,
        "location_id": str(t.location_id) if t.location_id else None,
        "revision": t.revision,
    }


def find_tag(value):
    value = text(value, 500)
    if value.startswith("https://"):
        u = urlsplit(value)
        if u.netloc != urlsplit(settings.ORIGIN).netloc or not u.path.startswith("/t/"):
            raise Problem("Use a Stash tag URL")
        value = u.path[3:]
    return Tag.objects.get(Q(token=value) | Q(code=value.upper()))


@api
def batches(r):
    if r.method == "GET":
        return {
            "batches": [
                {
                    "id": str(b.id),
                    "name": b.name,
                    "created": b.created.isoformat(),
                    "count": b.tag_set.count(),
                    "verified": b.tag_set.filter(
                        encoding__in=["verified", "phone_verified"]
                    ).count(),
                }
                for b in TagBatch.objects.order_by("-created")
            ]
        }
    if r.method != "POST":
        raise Problem("POST required", 405)
    p = r.payload
    n = p.get("count", 10)
    if type(n) is not int or not 1 <= n <= 200:
        raise Problem("Choose 1 to 200 tags")
    b = TagBatch.objects.create(name=text(p.get("name", "Prepared tags"), 160))
    tags = [Tag.objects.create(batch=b) for _ in range(n)]
    audit(r, "batch", b, "create", {}, {"count": n, "name": b.name})
    return {"id": str(b.id), "tags": [tdata(t) for t in tags]}


@api
def tags(r, token=None):
    if r.method == "GET":
        if token:
            return {"tag": tdata(find_tag(token))}
        rows = Tag.objects.order_by("code")
        if r.GET.get("batch"):
            rows = rows.filter(batch_id=r.GET["batch"])
        if r.GET.get("box"):
            rows = rows.filter(container_id=r.GET["box"])
        return {"tags": [tdata(t) for t in rows[:1000]]}
    if r.method != "POST" or not token:
        raise Problem("POST required", 405)
    t = find_tag(token)
    p = r.payload
    revision(t, p)
    before = tdata(t)
    action = p.get("action", "assign")
    if action.startswith("phone_") and t.state != "active":
        raise Problem("Only active tags can be prepared", 409)
    if action in ("assign", "reassign", "replace"):
        if t.state != "active":
            raise Problem("Reactivate this tag deliberately before assigning it", 409)
        if action == "assign" and (t.container_id or t.location_id):
            raise Problem("This tag is already assigned", 409)
        if action in ("reassign", "replace") and p.get("confirm") is not True:
            raise Problem("Confirm the change")
        if p.get("create_box"):
            if t.container_id or t.location_id:
                raise Problem("Tag already assigned", 409)
            b = p["create_box"]
            code = text(b.get("code", t.code), 24).upper()
            import re

            if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,23}", code):
                raise Problem("Invalid box code")
            box = Container(code=code, name=text(b.get("name", ""), 160))
            apply_box(box, b)
            box.photo = photo(b.get("photo", ""))
            box.save()
            event(r, "container", box, "create", {})
            t.container = box
            t.location = None
        elif action == "replace":
            old = find_tag(p["replace_code"])
            revision(old, {"revision": p.get("replace_revision")})
            if (
                old.pk == t.pk
                or t.container_id
                or t.location_id
                or not (old.container_id or old.location_id)
            ):
                raise Problem("Choose an unused replacement and an assigned old tag")
            t.container = old.container
            t.location = old.location
            old_before = tdata(old)
            old.state = "retired"
            old.revision += 1
            old.save()
            audit(r, "tag", old, "replaced", old_before, tdata(old))
        else:
            if bool(p.get("container_id")) == bool(p.get("location_id")):
                raise Problem("Choose one box or location")
            t.container = (
                Container.objects.get(pk=p["container_id"])
                if p.get("container_id")
                else None
            )
            t.location = (
                Location.objects.get(pk=p["location_id"])
                if p.get("location_id")
                else None
            )
    elif action in ("retire", "lost", "reactivate"):
        if p.get("confirm") is not True:
            raise Problem("Confirm the change")
        t.state = {"retire": "retired", "lost": "lost", "reactivate": "active"}[action]
    elif action == "phone_verify":
        if p.get("readback") != tdata(t)["url"] or p.get("confirm") is not True:
            raise Problem(
                "Read the physical tag in the NFC app and paste its exact URL"
            )
        if t.encoding not in ("unwritten", "phone_pending", "phone_verified"):
            raise Problem("This tag is reserved to a station", 409)
        from django.utils import timezone

        t.encoding = "phone_verified"
        t.encoded_at = timezone.now()
    elif action == "phone_skip":
        if t.encoding not in ("unwritten", "phone_pending", "phone_skipped"):
            raise Problem("This tag is not pending phone preparation", 409)
        t.encoding = "phone_skipped"
    elif action == "phone_prepare":
        if t.encoding not in ("unwritten", "phone_pending", "phone_skipped"):
            raise Problem("This tag is already prepared or reserved", 409)
        t.encoding = "phone_pending"
    else:
        raise Problem("Unknown tag action")
    t.revision += 1
    t.save()
    audit(r, "tag", t, action, before, tdata(t))
    return {"tag": tdata(t)}


@api
def manifest(r):
    rows = []
    for c in Container.objects.order_by("code"):
        rows.append(
            {
                "code": c.code,
                "name": c.name,
                "location": whereabouts(c),
                "destination": c.destination,
                "state": c.packing_state,
                "priority": c.priority,
                "description": c.description,
                "contents": "; ".join(
                    i.title for i in c.item_set.all() if i.status != "removed"
                ),
                "tags": "; ".join(c.tag_set.values_list("code", flat=True)),
            }
        )
    if r.GET.get("format") == "csv":
        f = io.StringIO()
        w = csv.DictWriter(
            f,
            fieldnames=[
                "code",
                "name",
                "location",
                "destination",
                "state",
                "priority",
                "description",
                "contents",
                "tags",
            ],
        )
        w.writeheader()
        # Prevent spreadsheet formula execution when exporting user text.
        for row in rows:
            w.writerow(
                {
                    k: ("'" + v if isinstance(v, str) and v[:1] in "=+-@\t\r" else v)
                    for k, v in row.items()
                }
            )
        out = HttpResponse(f.getvalue(), content_type="text/csv")
        out["Content-Disposition"] = 'attachment; filename="stash-moving.csv"'
        return out
    return {"boxes": rows}
