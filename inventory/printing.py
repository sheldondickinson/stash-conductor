"""PT-P750W label rendering and durable, conservative print queue."""

import base64
import io
import json
import subprocess
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import qrcode
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from .api import Problem, api, owner, revision, text
from .models import Container, Printer, PrintJob, Tag
from .moving import tdata

HEIGHTS = {18: 112, 24: 128}
CUTS = ("single-full", "single-half", "batch-half")


def definition(ref, title=False):
    if ref == "test":
        return {
            "code": "TEST",
            "title": "Stash test label",
            "url": settings.ORIGIN + "/",
        }
    kind, code = ref.split(":", 1)
    if kind == "tag":
        t = Tag.objects.get(token=code)
        if t.state != "active":
            raise Problem("Retired or lost tags cannot be printed")
        return {
            "code": t.code,
            "title": t.container.name if t.container else "",
            "box_code": t.container.code if t.container else "",
            "url": tdata(t)["url"],
        }
    if kind == "box":
        c = Container.objects.get(pk=code)
        from .paper_labels import box_label

        return box_label(c)
    raise Problem("Choose a box or tag")


def label_image(label, tape=24):
    if tape not in HEIGHTS:
        raise Problem("QR labels require 18 or 24 mm TZe tape")
    h = HEIGHTS[tape]
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=4
    )
    qr.add_data(label["url"])
    qr.make(fit=True)
    modules = len(qr.get_matrix())
    scale = h // modules
    if scale < 2:
        raise Problem("This URL is too long for a readable QR on this tape")
    qr.box_size = scale
    pic = qr.make_image(fill_color="black", back_color="white").convert("1")
    width = (
        round(80 * 180 / 25.4) - 28
    )  # 80 mm finished target, excluding two 2 mm feeds
    im = Image.new("1", (width, h), 1)
    im.paste(pic, (0, (h - pic.height) // 2))
    draw = ImageDraw.Draw(im)
    fontpath = settings.BASE_DIR / "static/vendor/label-font.ttf"

    def font(size):
        return (
            ImageFont.truetype(str(fontpath), size)
            if fontpath.exists()
            else ImageFont.load_default(size=size)
        )

    x = pic.width + 8
    size = 36
    while size > 12 and draw.textlength(label["code"], font=font(size)) > width - x - 4:
        size -= 1
    draw.text((x, 9), label["code"], font=font(size), fill=0)
    title = " ".join(label.get("title", "").split())
    title_size = 28
    while (
        title_size > 16
        and draw.textlength(title, font=font(title_size)) > width - x - 4
    ):
        title_size -= 1
    if draw.textlength(title, font=font(title_size)) > width - x - 4:
        while (
            title
            and draw.textlength(title + "…", font=font(title_size)) > width - x - 4
        ):
            title = title[:-1]
        title += "…"
    if title:
        draw.text((x, 55), title, font=font(title_size), fill=0)
    footer = label.get("box_code", "")
    footer = footer + " · Stash" if footer else "Stash Conductor"
    draw.text((x, h - 20), footer, font=font(13), fill=0)
    return im


def png(label, tape):
    f = io.BytesIO()
    label_image(label, tape).save(f, "PNG", dpi=(180, 180))
    return f.getvalue()


@contextmanager
def printer_lock():
    import fcntl

    with (settings.DATA_DIR / "printer.lock").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Problem("Printer is busy. Try again shortly.", 409)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def bridge(request):
    executable = settings.PRINT_BRIDGE
    if not executable or not Path(executable).is_file():
        return {"state": "failed", "detail": "Print bridge is not installed"}
    if request["action"] != "prepare" and not Path(settings.PRINTER_CONFIG).is_file():
        return {
            "state": "failed",
            "detail": "Brother connection has not been configured. Ask the owner to connect the PT-P750W.",
        }
    try:
        result = subprocess.run(
            [executable, settings.PRINTER_CONFIG],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=100,
            check=False,
        )
        result = json.loads(result.stdout)
        if result.get("state") not in (
            "observed",
            "prepared",
            "completed",
            "sent_unconfirmed",
            "outcome_unknown",
            "failed",
        ):
            raise ValueError()
        return result
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return {
            "state": "outcome_unknown" if request["action"] == "print" else "failed",
            "detail": "Print service did not return a reliable result. No automatic retry.",
        }


def pdata(p):
    return {
        "name": p.name,
        "tape_mm": p.tape_mm,
        "finishing": p.finishing,
        "revision": p.revision,
        "configured": Path(settings.PRINTER_CONFIG).is_file(),
        "status": p.status,
        "last_check": p.last_check.isoformat() if p.last_check else None,
        "print_height_mm": round(HEIGHTS[p.tape_mm] * 25.4 / 180, 2),
        "dpi": 180,
    }


@api
def printer(r):
    p, _ = Printer.objects.get_or_create(pk=1)
    if r.method == "GET":
        return pdata(p)
    if r.method != "POST":
        raise Problem("POST required", 405)
    data = r.payload
    if data.get("action") == "check":
        with printer_lock():
            p.status = bridge({"action": "status"})
        p.last_check = timezone.now()
        p.save(update_fields=["status", "last_check"])
        return pdata(p)
    owner(r)
    revision(p, data)
    if data.get("tape_mm") not in HEIGHTS or data.get("finishing") not in CUTS:
        raise Problem("Use 18 or 24 mm TZe tape and a supported cut option")
    p.tape_mm = data["tape_mm"]
    p.finishing = data["finishing"]
    p.revision += 1
    p.save()
    return pdata(p)


def jdata(j):
    return {
        "id": str(j.id),
        "labels": j.labels,
        "tape_mm": j.tape_mm,
        "finishing": j.finishing,
        "state": j.state,
        "detail": j.detail,
        "result": j.result,
        "created": j.created.isoformat(),
    }


def enqueue(actor, labels, key, tape=None, finishing=None):
    existing = PrintJob.objects.filter(source_key=key).first()
    if existing:
        return existing
    p, _ = Printer.objects.get_or_create(pk=1)
    tape = tape or p.tape_mm
    finishing = finishing or p.finishing
    if len(labels) > 50 or not labels:
        raise Problem("Choose 1 to 50 labels")
    if PrintJob.objects.filter(state__in=["queued", "sending", "held"]).count() >= 100:
        raise Problem("Print queue is full")
    for x in labels:
        label_image(x, tape)
    return PrintJob.objects.create(
        actor=actor, source_key=key, labels=labels, tape_mm=tape, finishing=finishing
    )


@api
def jobs(r, pk=None):
    if r.method == "GET":
        return {"jobs": [jdata(j) for j in PrintJob.objects.order_by("-created")[:100]]}
    if r.method != "POST":
        raise Problem("POST required", 405)
    p = r.payload
    if pk:
        j = PrintJob.objects.get(pk=pk)
        action = p.get("action")
        if action == "cancel":
            if j.state not in ("queued", "held"):
                raise Problem("Only labels not yet sending can be cancelled", 409)
            j.state = "cancelled"
            j.detail = "Cancelled before sending"
            j.save()
            return jdata(j)
        if action == "resume":
            if j.state != "held":
                raise Problem("This job is not held", 409)
            j.state = "queued"
            j.created = timezone.now()
            j.save()
            return jdata(j)
        if action == "confirm":
            if j.state not in ("sent_unconfirmed", "outcome_unknown"):
                raise Problem("This job does not need confirmation", 409)
            if p.get("confirm") is not True:
                raise Problem("Confirm that you inspected all physical labels")
            j.state = "completed"
            j.detail = "Physical output confirmed by " + (
                r.user.first_name or r.user.username
            )
            j.save()
            return jdata(j)
        if action == "reprint":
            if p.get("confirm") is not True:
                raise Problem("Inspect the printer first, then confirm another copy")
            return jdata(
                enqueue(
                    r.user,
                    j.labels,
                    "reprint:" + r.headers["Idempotency-Key"],
                    j.tape_mm,
                    j.finishing,
                )
            )
        raise Problem("Unknown print action")
    copies = p.get("copies", 1)
    refs = p.get("refs", [])
    if (
        type(copies) is not int
        or not 1 <= copies <= 20
        or not isinstance(refs, list)
        or not refs
        or len(refs) * copies > 50
    ):
        raise Problem("Choose at most 50 labels and 1 to 20 copies")
    labels = [
        definition(text(ref, 100), p.get("include_title") is True)
        for ref in refs
        for _ in range(copies)
    ]
    return jdata(
        enqueue(
            r.user,
            labels,
            "user:" + str(r.user.pk) + ":" + r.headers["Idempotency-Key"],
        )
    )


@api
def preview(r):
    p, _ = Printer.objects.get_or_create(pk=1)
    data = definition(r.GET.get("ref", "test"), r.GET.get("title") == "1")
    raw = png(data, p.tape_mm)
    if r.GET.get("format") == "svg":
        im = label_image(data, p.tape_mm)
        width = im.width * 25.4 / 180
        height = im.height * 25.4 / 180
        content = f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width + 4}mm" height="{p.tape_mm}mm" viewBox="0 0 {width + 4} {p.tape_mm}"><rect width="100%" height="100%" fill="white"/><image x="2" y="{(p.tape_mm - height) / 2}" width="{width}" height="{height}" xlink:href="data:image/png;base64,{base64.b64encode(raw).decode()}"/></svg>'
        out = HttpResponse(content, content_type="image/svg+xml")
        out["Content-Disposition"] = 'attachment; filename="stash-label.svg"'
        return out
    out = HttpResponse(raw, content_type="image/png")
    if r.GET.get("download"):
        out["Content-Disposition"] = 'attachment; filename="stash-label.png"'
    return out


def work_once():
    # The process lock spans claim, physical send and result persistence, including status checks.
    with printer_lock():
        with transaction.atomic():
            # A previous worker died after claim: never resend automatically.
            PrintJob.objects.filter(state="sending").update(
                state="outcome_unknown",
                detail="Worker stopped while sending. Inspect physical output before reprinting.",
            )
            PrintJob.objects.filter(
                state="queued", created__lt=timezone.now() - timedelta(hours=1)
            ).update(
                state="held",
                detail="Held after more than one hour. Resume deliberately.",
            )
            j = PrintJob.objects.filter(state="queued").order_by("created").first()
            if not j:
                return False
            j.state = "sending"
            j.detail = "Sending to Brother"
            j.save()
        images = [base64.b64encode(png(x, j.tape_mm)).decode() for x in j.labels]
        result = bridge(
            {
                "action": "print",
                "images": images,
                "tape_mm": j.tape_mm,
                "finishing": j.finishing,
            }
        )
        with transaction.atomic():
            j.state = result["state"]
            j.detail = result.get("detail", "")[:500]
            j.result = result.get("result", {})
            j.save()
        return True
