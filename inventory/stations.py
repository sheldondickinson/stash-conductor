"""Revocable encoder identities have access only to allocation and readback reports."""

import hashlib
import json
import re
import secrets
from datetime import timedelta
from functools import wraps

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .api import Problem, api, owner, revision, text
from .models import EncodingReservation, Event, Station, Tag, TagBatch
from .moving import tdata
from .printing import definition, enqueue


def sdata(s):
    return {
        "id": str(s.id),
        "name": s.name,
        "revoked": s.revoked,
        "batch_id": str(s.batch_id) if s.batch_id else None,
        "armed": bool(
            s.armed_until and s.armed_until > timezone.now() and not s.revoked
        ),
        "armed_until": s.armed_until.isoformat() if s.armed_until else None,
        "last_seen": s.last_seen.isoformat() if s.last_seen else None,
        "last_result": s.last_result,
        "print_after": s.print_after,
        "revision": s.revision,
        "reservations": [
            {"id": str(v.id), "code": v.tag.code, "uid": v.uid, "state": v.state}
            for v in s.encodingreservation_set.select_related("tag").order_by(
                "-created"
            )[:20]
        ],
    }


@api
def stations(r, pk=None):
    if r.method == "GET":
        return {"stations": [sdata(s) for s in Station.objects.all()]}
    if r.method != "POST":
        raise Problem("POST required", 405)
    p = r.payload
    if not pk:
        owner(r)
        secret = secrets.token_urlsafe(32)
        s = Station.objects.create(
            name=text(p.get("name", "Tag station"), 100),
            secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
        )
        return {"station": sdata(s), "credential": secret}
    s = Station.objects.get(pk=pk)
    revision(s, p)
    action = p.get("action")
    if action == "revoke":
        owner(r)
        s.revoked = True
        s.armed_until = None
    elif action == "arm":
        if s.revoked:
            raise Problem("Station credential is revoked", 409)
        s.batch = TagBatch.objects.get(pk=p["batch_id"])
        s.armed_by = r.user
        s.armed_until = timezone.now() + timedelta(minutes=5)
        s.print_after = p.get("print_after") is True
        s.overwrite_uid = ""
    elif action == "disarm":
        s.armed_until = None
        s.overwrite_uid = ""
    elif action == "overwrite":
        if p.get("confirm") is not True or not re.fullmatch(
            r"[0-9A-F]{14}", p.get("uid", "")
        ):
            raise Problem("Inspect the tag and explicitly confirm its seven byte UID")
        if not s.armed_until or s.armed_until < timezone.now():
            raise Problem("Arm this station first")
        s.overwrite_uid = p["uid"]
    elif action == "resume":
        v = EncodingReservation.objects.get(
            pk=p["reservation_id"], station=s, state="skipped"
        )
        if (
            v.tag.state != "active"
            or EncodingReservation.objects.filter(station=s, state="reserved").exists()
        ):
            raise Problem(
                "Resolve the active reservation before resuming an active tag", 409
            )
        v.state = "reserved"
        v.save()
        v.tag.encoding = "reserved"
        v.tag.save(update_fields=["encoding"])
    elif action == "skip":
        v = EncodingReservation.objects.get(pk=p["reservation_id"], station=s)
        if v.state == "verified":
            raise Problem("Already verified")
        v.state = "skipped"
        v.save()
        v.tag.encoding = "skipped"
        v.tag.save(update_fields=["encoding"])
        # Reserved URLs are never recycled. A partially written tag keeps its identity.
    else:
        raise Problem("Unknown station action")
    s.revision += 1
    s.save()
    return sdata(s)


def station_api(fn):
    @csrf_exempt
    @wraps(fn)
    def wrap(r, pk):
        if r.method != "POST":
            return JsonResponse({"error": "POST required"}, status=405)
        try:
            if len(r.body) > 4096:
                raise Problem("Request too large", 413)
            token = r.headers.get("Authorization", "")
            if not token.startswith("Bearer "):
                raise Problem("Station authentication required", 401)
            with transaction.atomic():
                s = Station.objects.get(pk=pk, revoked=False)
                if not secrets.compare_digest(
                    s.secret_hash, hashlib.sha256(token[7:].encode()).hexdigest()
                ):
                    raise Problem("Station authentication required", 401)
                p = json.loads(r.body)
                if not isinstance(p, dict):
                    raise Problem("Object required")
                s.last_seen = timezone.now()
                result = fn(s, p)
                s.save()
            return JsonResponse(result)
        except OperationalError:
            return JsonResponse(
                {"error": "Concurrent operation. Retry the same reservation."},
                status=409,
            )
        except Problem as e:
            return JsonResponse({"error": e.message}, status=e.status)
        except (
            ValueError,
            KeyError,
            TypeError,
            ValidationError,
            IntegrityError,
            ObjectDoesNotExist,
        ):
            return JsonResponse({"error": "Invalid station request"}, status=400)

    return wrap


def reserved(v, s):
    return {
        "reservation_id": str(v.id),
        "uid": v.uid,
        "state": v.state,
        "tag": tdata(v.tag),
        "may_write": bool(
            s.armed_until
            and s.armed_until > timezone.now()
            and v.state == "reserved"
            and v.tag.state == "active"
            and s.armed_by
            and s.armed_by.is_active
        ),
        "overwrite": s.overwrite_uid == v.uid,
    }


@station_api
def exchange(s, p):
    action = p.get("action")
    if action == "health":
        return sdata(s)
    uid = p.get("uid", "")
    if not re.fullmatch("[0-9A-F]{14}", uid):
        raise Problem("Only seven byte NTAG UIDs are supported")
    if action == "inspect":
        s.last_result = text(p.get("detail", "Tag inspected"), 280) + " " + uid
        return {"write": False}
    if action == "reserve":
        old = EncodingReservation.objects.filter(uid=uid).first()
        if old:
            if old.station_id != s.id:
                raise Problem("Tag belongs to another station reservation", 409)
            return reserved(old, s)
        if (
            not s.armed_until
            or s.armed_until <= timezone.now()
            or not s.armed_by
            or not s.armed_by.is_active
        ):
            raise Problem("Station is disarmed", 409)
        if p.get("kind") not in ("NTAG213", "NTAG215", "NTAG216"):
            raise Problem("Unsupported tag type")
        if p.get("blank") is not True and s.overwrite_uid != uid:
            raise Problem("Nonblank tag requires explicit confirmation", 409)
        # Do not advance until previous reservation has verified or been explicitly skipped.
        if EncodingReservation.objects.filter(station=s, state="reserved").exists():
            raise Problem("Verify or skip the outstanding reservation first", 409)
        t = (
            Tag.objects.filter(
                batch=s.batch,
                state="active",
                encoding="unwritten",
                container__isnull=True,
                location__isnull=True,
            )
            .order_by("code")
            .first()
        )
        if not t:
            raise Problem("No unassigned unwritten tags remain in this batch", 409)
        t.encoding = "reserved"
        t.revision += 1
        t.save()
        v = EncodingReservation.objects.create(station=s, tag=t, uid=uid)
        s.last_result = "Reserved " + t.code
        return reserved(v, s)
    if action == "verify":
        v = EncodingReservation.objects.get(pk=p["reservation_id"], station=s, uid=uid)
        if p.get("readback") != tdata(v.tag)["url"]:
            raise Problem("Readback differs from the reserved URL", 409)
        if v.state == "skipped":
            raise Problem(
                "Reservation was skipped. Inspect and resolve it in Stash.", 409
            )
        if v.state != "verified":
            v.state = "verified"
            v.verified = timezone.now()
            v.save()
            t = v.tag
            t.encoding = "verified"
            t.encoded_at = v.verified
            t.revision += 1
            t.save()
            Event.objects.create(
                entity="tag",
                entity_id=t.token,
                actor=s.armed_by,
                action="station_verify",
                after={
                    "station_id": str(s.id),
                    "code": t.code,
                    "reservation_id": str(v.id),
                },
            )
        s.last_result = "Verified " + v.tag.code
        s.overwrite_uid = ""
        # Successful work extends only an active arm; a reset/offline acknowledgement never rearms.
        if s.armed_until and s.armed_until > timezone.now():
            s.armed_until = timezone.now() + timedelta(minutes=5)
        job = None
        if s.print_after:
            job = enqueue(
                s.armed_by, [definition("tag:" + v.tag.token)], "encoding:" + str(v.id)
            )
        return {
            "verified": True,
            "code": v.tag.code,
            "print_job_id": str(job.id) if job else None,
        }
    raise Problem("Unknown station operation")


@csrf_exempt
def firmware(r, pk):
    """A station can fetch only the operator staged binary, with its narrow identity."""
    from pathlib import Path

    from django.conf import settings
    from django.http import FileResponse

    if r.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    credential = r.headers.get("Authorization", "")
    s = Station.objects.filter(pk=pk, revoked=False).first()
    if (
        not s
        or not credential.startswith("Bearer ")
        or not secrets.compare_digest(
            s.secret_hash, hashlib.sha256(credential[7:].encode()).hexdigest()
        )
    ):
        return JsonResponse({"error": "Station authentication required"}, status=401)
    path = Path(settings.STATION_FIRMWARE)
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        return JsonResponse({"error": "No staged firmware"}, status=404)
    response = FileResponse(path.open("rb"), content_type="application/octet-stream")
    response["X-Firmware-SHA256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return response
