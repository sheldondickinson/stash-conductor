import base64
import hashlib
import io
import json
import re
import secrets
import uuid
from datetime import timedelta
from difflib import SequenceMatcher
from functools import wraps

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.http import FileResponse, HttpResponse, JsonResponse
from django.http.response import HttpResponseBase
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import ApiToken, Container, Event, Item, Pairing, Receipt

Image.MAX_IMAGE_PIXELS = 40000000


class Problem(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


def api(fn):
    @csrf_exempt
    @wraps(fn)
    def wrap(request, *args, **kwargs):
        try:
            token = request.headers.get("Authorization", "")
            if token:
                if not token.startswith("Bearer "):
                    raise Problem("Authentication required", 401)
                t = (
                    ApiToken.objects.select_related("user")
                    .filter(
                        digest=hashlib.sha256(token[7:].encode()).hexdigest(),
                        expires__gt=timezone.now(),
                        user__is_active=True,
                    )
                    .first()
                )
                if not t:
                    raise Problem("Authentication required", 401)
                if request.method not in ("GET", "HEAD") and not t.write:
                    raise Problem("Read-only credential", 403)
                request.user = t.user
            elif not request.user.is_authenticated or not request.user.is_active:
                raise Problem("Authentication required", 401)
            elif CsrfViewMiddleware(lambda r: None).process_view(
                request, lambda r: None, (), {}
            ):
                raise Problem("Refresh this page before saving (CSRF)", 403)
            expected_user = request.headers.get("X-Stash-User")
            if expected_user and expected_user != str(request.user.pk):
                raise Problem(
                    "Account changed. Reopen Stash before sending drafts.", 403
                )
            if request.method not in ("GET", "HEAD"):
                if request.content_type != "application/json":
                    raise Problem("JSON required")
                body = request.body
                request.payload = json.loads(body or b"{}")
                if not isinstance(request.payload, dict):
                    raise Problem("Object required")
                key = request.headers.get("Idempotency-Key", "")
                if not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", key):
                    raise Problem("A unique Idempotency-Key is required")
                digest = hashlib.sha256(
                    request.path.encode() + b"\0" + body
                ).hexdigest()
                with transaction.atomic():
                    old = Receipt.objects.filter(actor=request.user, key=key).first()
                    if old:
                        if old.digest != digest:
                            raise Problem(
                                "Request key reused with different content", 409
                            )
                        return JsonResponse(old.response)
                    result = fn(request, *args, **kwargs)
                    Receipt.objects.create(
                        actor=request.user, key=key, digest=digest, response=result
                    )
                return JsonResponse(result)
            result = fn(request, *args, **kwargs)
            return (
                result if isinstance(result, HttpResponseBase) else JsonResponse(result)
            )
        except Problem as e:
            return JsonResponse({"error": e.message}, status=e.status)
        except (ObjectDoesNotExist, ValidationError):
            return JsonResponse(
                {"error": "Record not found or invalid identifier"}, status=404
            )
        except (IntegrityError, OperationalError):
            return JsonResponse(
                {
                    "error": "That code already exists, or a concurrent update occurred. Refresh and retry."
                },
                status=409,
            )
        except (
            ValueError,
            TypeError,
            KeyError,
            UnidentifiedImageError,
            Image.DecompressionBombError,
        ):
            return JsonResponse({"error": "Invalid request or image"}, status=400)

    return wrap


def owner(r):
    if not r.user.is_staff:
        raise Problem("Owner access required", 403)


def text(v, n):
    if not isinstance(v, str) or len(v) > n:
        raise Problem("Text is too long or invalid")
    return v.strip()


def photo(value):
    if not value:
        return ""
    if not isinstance(value, str) or len(value) > 28 * 1024 * 1024:
        raise Problem("Photo too large (20 MB limit)")
    raw = base64.b64decode(value.split(",", 1)[-1], validate=True)
    if len(raw) > 20 * 1024 * 1024:
        raise Problem("Photo too large (20 MB limit)")
    im = Image.open(io.BytesIO(raw))
    if im.width * im.height > 40000000:
        raise Problem("Photo exceeds 40 megapixels")
    im.verify()
    im = Image.open(io.BytesIO(raw))
    if im.format not in ("JPEG", "PNG", "WEBP", "HEIF", "HEIC"):
        raise Problem("Use JPEG, PNG or WebP photos")
    digest = hashlib.sha256(raw).hexdigest()
    ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "HEIF": "heic", "HEIC": "heic"}[
        im.format
    ]
    name = digest + "." + ext
    target = settings.MEDIA_ROOT / name
    if not target.exists():
        try:
            with target.open("xb") as f:
                f.write(raw)
        except FileExistsError:
            pass
    thumb = settings.MEDIA_ROOT / (digest + ".thumb.jpg")
    if not thumb.exists():
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((1000, 1000))
        tmp = thumb.with_suffix("." + uuid.uuid4().hex + ".tmp")
        im.save(tmp, "JPEG", quality=85)
        tmp.replace(thumb)
    return name


def cdata(c):
    return {
        "id": str(c.id),
        "code": c.code,
        "name": c.name,
        "location": c.location,
        "photo": c.photo,
        "revision": c.revision,
        **{
            f: getattr(c, f)
            for f in (
                "destination",
                "description",
                "packing_state",
                "fragile",
                "heavy",
                "priority",
                "category",
                "keywords",
                "storage_notes",
            )
        },
        "review_date": c.review_date.isoformat() if c.review_date else None,
        "physical_location_id": str(c.physical_location_id)
        if c.physical_location_id
        else None,
        "parent_id": str(c.parent_id) if c.parent_id else None,
        "tag_codes": list(
            c.tag_set.filter(state="active").values_list("code", flat=True)
        ),
        "effective_location": __import__(
            "inventory.moving", fromlist=["whereabouts"]
        ).whereabouts(c),
    }


def idata(i):
    return {
        "id": str(i.id),
        "title": i.title,
        "original": i.original,
        "aliases": i.aliases,
        "container_id": str(i.container_id) if i.container_id else None,
        "last_container_id": str(i.last_container_id) if i.last_container_id else None,
        "status": i.status,
        "quantity": i.quantity,
        "unit": i.unit,
        "photo": i.photo,
        "metadata": i.metadata,
        "suggestions": i.suggestions,
        "revision": i.revision,
        "confirmed": i.confirmed.isoformat(),
        "created": i.created.isoformat(),
    }


def event(r, entity, obj, action, before):
    after = cdata(obj) if entity == "container" else idata(obj)
    e = Event.objects.create(
        entity=entity,
        entity_id=str(obj.pk),
        actor=r.user,
        action=action,
        before=before,
        after=after,
    )
    return {"record": after, "event": str(e.id)}


def revision(obj, p):
    if p.get("revision") != obj.revision:
        raise Problem("This record changed elsewhere. Refresh before editing.", 409)


def container(value):
    return Container.objects.get(id=value) if value else None


@api
def me(r):
    return {
        "id": r.user.pk,
        "name": r.user.first_name or r.user.username,
        "owner": r.user.is_staff,
        "namespace": "household:" + str(r.user.pk),
        "csrf": get_token(r),
        "auth_mode": settings.AUTH_MODE,
        "conductor_url": settings.CONDUCTOR_URL,
    }


@api
def containers(r):
    if r.method == "GET":
        return {"containers": [cdata(c) for c in Container.objects.order_by("code")]}
    if r.method != "POST":
        raise Problem("Method not allowed", 405)
    p = r.payload
    count = p.get("count", 1)
    if type(count) is not int or not 1 <= count <= 50:
        raise Problem("Batch size must be 1–50")
    code = text(p.get("code", ""), 24).upper()
    if code and not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,23}", code):
        raise Problem("Use a short code with letters, numbers, _ or -")
    if count > 1 and code and not re.search(r"\d+$", code):
        raise Problem("Batch start code must end in a number")
    from .box_allocation import create_box
    from .box_names import NameAllocator

    out = []
    allocator = NameAllocator([text(p.get("name", ""), 160)])
    for n in range(count):
        name = code
        if n and code:
            m = re.search(r"(\d+)$", code)
            name = code[: m.start()] + str(int(m[0]) + n).zfill(len(m[0]))
        c = create_box(
            {**p, "code": name, "photo": p.get("photo", "") if n == 0 else ""},
            allocator,
        )
        out.append(event(r, "container", c, "create", {}))
    return {"created": out}


@api
def container_detail(r, pk):
    c = Container.objects.get(pk=pk)
    if r.method == "GET":
        return cdata(c)
    if r.method != "POST":
        raise Problem("Method not allowed", 405)
    p = r.payload
    revision(c, p)
    before = cdata(c)
    for f in ("name", "location"):
        if f in p:
            setattr(c, f, text(p[f], 300 if f == "location" else 160))
    if p.get("photo"):
        c.photo = photo(p["photo"])
    from .moving import apply_box

    apply_box(c, p)
    c.revision += 1
    c.save()
    return event(r, "container", c, "edit", before)


@api
def items(r):
    if r.method == "GET":
        query = r.GET.get("q", "").casefold().strip()[:300]
        rows = Item.objects.order_by("-created")
        rows = (
            rows.filter(status="removed")
            if r.GET.get("status") == "removed"
            else rows.exclude(status="removed")
        )
        if r.GET.get("container"):
            rows = rows.filter(container_id=r.GET["container"])
        result = []
        for i in rows:
            hay = " ".join(
                [
                    i.title,
                    i.original,
                    i.aliases,
                    json.dumps(i.metadata),
                    json.dumps(cdata(i.container)) if i.container else "",
                ]
            ).casefold()
            terms = query.split()
            if not terms or all(
                t in hay
                or any(SequenceMatcher(None, t, w).ratio() >= 0.8 for w in hay.split())
                for t in terms
            ):
                result.append(idata(i))
        return {"items": result}
    if r.method != "POST":
        raise Problem("Method not allowed", 405)
    p = r.payload
    title = text(p.get("title", ""), 240)
    pic = photo(p.get("photo", ""))
    if not title and not pic:
        raise Problem("Add a photo or a rough description")
    c = container(p.get("container_id"))
    if not c:
        raise Problem("Select a container")
    q = p.get("quantity")
    if q is not None and (type(q) is not int or q < 1):
        raise Problem("Quantity must be a positive count or unknown")
    i = Item.objects.create(
        title=title or "Unidentified item",
        original=title,
        container=c,
        last_container=c,
        photo=pic,
        quantity=q,
        unit=text(p.get("unit", "batch"), 40),
    )
    return event(r, "item", i, "capture", {})


@api
def item_detail(r, pk):
    i = Item.objects.get(pk=pk)
    if r.method == "GET":
        events = (
            Event.objects.filter(entity="item", entity_id=str(pk))
            .select_related("actor")
            .order_by("-created")
        )
        return {
            "item": idata(i),
            "history": [
                {
                    "id": str(e.id),
                    "action": e.action,
                    "actor": e.actor.first_name or e.actor.username,
                    "at": e.created.isoformat(),
                    "before": e.before,
                    "after": e.after,
                }
                for e in events
            ],
        }
    if r.method != "POST":
        raise Problem("Method not allowed", 405)
    return change(r, i, r.payload)


def change(r, i, p):
    revision(i, p)
    before = idata(i)
    action = p.get("action", "edit")
    if action in ("move", "return"):
        c = container(p.get("container_id") or i.last_container_id)
        if not c:
            raise Problem("Choose a return container")
        i.container = c
        i.last_container = c
        i.status = "stored"
        i.confirmed = timezone.now()
    elif action in ("take", "used", "missing", "unknown", "remove"):
        if i.container_id:
            i.last_container_id = i.container_id
        i.status = {
            "take": "in_use",
            "used": "used_up",
            "missing": "missing",
            "unknown": "unknown",
            "remove": "removed",
        }[action]
        if action in ("take", "used", "unknown"):
            i.container = None
        if action == "take" and p.get("destination"):
            i.metadata = {**i.metadata, "in_use_at": text(p["destination"], 300)}
    elif action == "split":
        q = p.get("quantity")
        c = container(p.get("container_id"))
        if i.quantity is None or type(q) is not int or not 0 < q < i.quantity or not c:
            raise Problem(
                "Split requires a counted quantity smaller than the total and a destination"
            )
        if i.metadata.get("serial") or i.metadata.get("mac"):
            raise Problem("A serialised device cannot be split")
        i.quantity -= q
        clone = Item.objects.create(
            title=i.title,
            original=i.original,
            aliases=i.aliases,
            container=c,
            last_container=c,
            status="stored",
            quantity=q,
            unit=i.unit,
            photo=i.photo,
            metadata={**i.metadata, "split_from": str(i.id)},
        )
        event(r, "item", clone, "split_child", {})
    elif action == "edit":
        for f in ("title", "aliases", "unit"):
            if f in p:
                setattr(i, f, text(p[f], 2000 if f == "aliases" else 240))
        if not i.title:
            raise Problem("Title cannot be empty")
        if "quantity" in p:
            if p["quantity"] is not None and (
                type(p["quantity"]) is not int or p["quantity"] < 1
            ):
                raise Problem("Count must be positive or unknown")
            i.quantity = p["quantity"]
        if "metadata" in p:
            if (
                not isinstance(p["metadata"], dict)
                or len(json.dumps(p["metadata"])) > 16000
            ):
                raise Problem("Metadata must be an object under 16 KB")
            i.metadata = p["metadata"]
        if p.get("photo"):
            i.photo = photo(p["photo"])
    else:
        raise Problem("Unknown action")
    i.revision += 1
    i.save()
    result = event(r, "item", i, action, before)
    if action == "split":
        result["split_item"] = str(clone.id)
    return result


@api
def bulk(r):
    if r.method != "POST":
        raise Problem("Method not allowed", 405)
    p = r.payload
    if p.get("action") not in ("take", "return", "move", "missing", "unknown", "used"):
        raise Problem("Invalid bulk action")
    entries = p.get("items", [])
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise Problem("Select 1–100 records")
    if len({x["id"] for x in entries}) != len(entries):
        raise Problem("Duplicate selection")
    return {
        "results": [
            change(r, Item.objects.get(pk=x["id"]), {**p, "revision": x["revision"]})
            for x in entries
        ]
    }


@api
def undo(r, pk):
    if r.method != "POST":
        raise Problem("Method not allowed", 405)
    e = Event.objects.get(pk=pk)
    if e.action in ("split", "split_child"):
        raise Problem(
            "Split creates two records. Correct the counts and locations explicitly."
        )
    if e.entity not in ("container", "item"):
        raise Problem("Use an explicit correction for this change")
    model = Container if e.entity == "container" else Item
    obj = model.objects.get(pk=e.entity_id)
    if obj.revision != e.after["revision"]:
        raise Problem("Later changes exist; use a correction instead.", 409)
    before = cdata(obj) if e.entity == "container" else idata(obj)
    if not e.before:
        if e.entity == "container":
            raise Problem(
                "Container creation is retained to protect labels and history"
            )
        obj.status = "removed"
    else:
        for f, v in e.before.items():
            if f not in (
                "id",
                "revision",
                "created",
                "suggestions",
                "effective_location",
                "tag_codes",
            ):
                setattr(obj, f, v)
    obj.revision += 1
    obj.save()
    obj.refresh_from_db()
    return event(r, e.entity, obj, "undo", before)


@api
def media(r, name):
    if not re.fullmatch(r"[a-f0-9]{64}\.(jpg|png|webp|heic|thumb.jpg)", name):
        raise Problem("Not found", 404)
    p = settings.MEDIA_ROOT / name
    if not p.is_file():
        raise Problem("Not found", 404)
    return FileResponse(
        p.open("rb"),
        content_type="image/jpeg"
        if name.endswith(".jpg")
        else "image/" + name.rsplit(".", 1)[-1],
    )


@api
def label(r, code):
    c = Container.objects.get(code=code)
    from .paper_labels import box_label
    from .printing import png

    return HttpResponse(png(box_label(c), 24), content_type="image/png")


@api
def export(r):
    owner(r)
    return {
        "version": 3,
        "box_batches": list(
            __import__(
                "inventory.models", fromlist=["BoxBatch"]
            ).BoxBatch.objects.values("id", "name", "defaults", "created")
        ),
        "box_batch_members": list(
            __import__(
                "inventory.models", fromlist=["BoxBatchMember"]
            ).BoxBatchMember.objects.values("batch_id", "box_id", "position")
        ),
        "box_codes": list(
            __import__(
                "inventory.models", fromlist=["BoxCode"]
            ).BoxCode.objects.values_list("code", flat=True)
        ),
        "box_sequence": list(
            __import__(
                "inventory.models", fromlist=["BoxSequence"]
            ).BoxSequence.objects.values()
        ),
        "locations": [
            __import__("inventory.moving", fromlist=["ldata"]).ldata(x)
            for x in __import__(
                "inventory.models", fromlist=["Location"]
            ).Location.objects.all()
        ],
        "tags": [
            __import__("inventory.moving", fromlist=["tdata"]).tdata(x)
            for x in __import__("inventory.models", fromlist=["Tag"]).Tag.objects.all()
        ],
        "batches": list(
            __import__(
                "inventory.models", fromlist=["TagBatch"]
            ).TagBatch.objects.values()
        ),
        "containers": [cdata(c) for c in Container.objects.all()],
        "items": [idata(i) for i in Item.objects.all()],
        "events": list(
            Event.objects.values(
                "id",
                "entity",
                "entity_id",
                "actor_id",
                "action",
                "before",
                "after",
                "created",
            )
        ),
    }


@api
def pairings(r):
    if r.method == "GET":
        return {
            "pairings": list(
                Pairing.objects.filter(user=r.user, revoked=False).values(
                    "id", "label", "installation"
                )
            )
        }
    if r.method != "POST":
        raise Problem("Method not allowed", 405)
    p = r.payload
    if p.get("revoke"):
        Pairing.objects.filter(pk=p["revoke"], user=r.user).update(
            revoked=True, destination=""
        )
        return {"revoked": True}
    secret = secrets.token_urlsafe(32)
    pair = Pairing.objects.create(
        user=r.user,
        installation=text(p["installation"], 100),
        label=text(p.get("label", "My phone"), 100),
        secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
    )
    return {
        "id": str(pair.id),
        "credential": secret,
        "endpoint": settings.ORIGIN + "/api/handoff/" + str(pair.id),
    }


@csrf_exempt
def handoff(r, pk):
    if r.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    token = r.headers.get("Authorization", "")
    if not token.startswith("Bearer "):
        return JsonResponse({"error": "Unauthorised"}, status=401)
    try:
        with transaction.atomic():
            p = Pairing.objects.select_related("user").get(
                pk=pk, revoked=False, user__is_active=True
            )
            if not secrets.compare_digest(
                p.secret_hash, hashlib.sha256(token[7:].encode()).hexdigest()
            ):
                raise ValueError()
            data = json.loads(r.body)
            c = Container.objects.get(code=data["code"].upper())
            p.destination = c.code
            p.expires = timezone.now() + timedelta(seconds=60)
            p.save()
        return JsonResponse({"pending": True, "expires_in": 60})
    except (ObjectDoesNotExist, ValueError, KeyError, TypeError, ValidationError):
        return JsonResponse({"error": "Invalid pairing or container"}, status=403)


@api
def consume(r):
    if r.method != "POST":
        raise Problem("Method not allowed", 405)
    pair = (
        Pairing.objects.filter(
            user=r.user,
            installation=r.payload["installation"],
            revoked=False,
            destination__gt="",
            expires__gt=timezone.now(),
        )
        .order_by("-expires")
        .first()
    )
    code = pair.destination if pair else None
    Pairing.objects.filter(user=r.user, installation=r.payload["installation"]).update(
        destination="", expires=None
    )
    return {"code": code}


@api
def users(r):
    owner(r)
    if r.method == "GET":
        return {
            "users": list(
                User.objects.values(
                    "id", "username", "first_name", "is_staff", "is_active"
                )
            )
        }
    if settings.AUTH_MODE != "local":
        raise Problem(
            "Manage membership in your identity provider. Existing sessions last at most one hour.",
            403,
        )
    from django.contrib.auth.password_validation import validate_password

    p = r.payload
    if p.get("disable"):
        u = User.objects.get(pk=p["disable"])
        if u.pk == r.user.pk:
            raise Problem("Cannot disable yourself")
        u.is_active = False
        u.save()
        return {"disabled": True}
    validate_password(p["password"])
    u = User.objects.create_user(
        text(p["username"], 100), password=p["password"], is_staff=bool(p.get("owner"))
    )
    return {"id": u.pk}


@api
def tokens(r):
    owner(r)
    if r.method == "GET":
        return {
            "tokens": list(
                ApiToken.objects.filter(user=r.user).values(
                    "id", "label", "write", "expires"
                )
            )
        }
    p = r.payload
    if p.get("revoke"):
        ApiToken.objects.filter(pk=p["revoke"], user=r.user).delete()
        return {"revoked": True}
    secret = secrets.token_urlsafe(32)
    ApiToken.objects.create(
        user=r.user,
        digest=hashlib.sha256(secret.encode()).hexdigest(),
        label=text(p.get("label", "Integration"), 100),
        write=bool(p.get("write")),
        expires=timezone.now() + timedelta(days=30),
    )
    return {"token": secret, "expires_in_days": 30}
