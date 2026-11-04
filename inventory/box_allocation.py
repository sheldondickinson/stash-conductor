"""One server allocation path for ordinary, scanned and bulk boxes."""

import re

from django.db import connection

from .models import BoxCode, BoxSequence, Container


def next_number():
    numbers = [
        int(c[1:])
        for c in Container.objects.values_list("code", flat=True)
        if re.fullmatch(r"B\d+", c)
    ]
    saved = (
        BoxSequence.objects.filter(pk=1).values_list("next_number", flat=True).first()
        or 1
    )
    return max(saved, max(numbers, default=0) + 1)


def reserve_code(explicit=""):
    from .api import Problem, text

    if not connection.in_atomic_block:
        raise RuntimeError("Box allocation requires a transaction")
    seq, _ = BoxSequence.objects.select_for_update().get_or_create(pk=1)
    seq.next_number = next_number()
    code = text(explicit, 24).upper() or f"B{seq.next_number:03d}"
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,23}", code):
        raise Problem("Use a short code with letters and numbers")
    if re.fullmatch(r"B\d+", code) and int(code[1:]) >= 10**18:
        raise Problem("That box number is too large")
    if (
        Container.objects.filter(code=code).exists()
        or BoxCode.objects.filter(pk=code).exists()
    ):
        raise Problem("That box code has already been used", 409)
    BoxCode.objects.create(code=code)
    if re.fullmatch(r"B\d+", code):
        seq.next_number = max(seq.next_number, int(code[1:]) + 1)
    seq.save()
    return code


def create_box(payload, allocator=None):
    from .api import photo, text
    from .box_names import NameAllocator
    from .moving import apply_box

    code = reserve_code(payload.get("code", ""))
    allocator = allocator or NameAllocator()
    name = text(payload.get("name", ""), 160) or allocator.allocate(
        text(payload.get("proposed_name", ""), 160)
    )
    box = Container(
        code=code, name=name, location=text(payload.get("location", ""), 300)
    )
    apply_box(box, payload)
    box.photo = photo(payload.get("photo", ""))
    box.save()
    return box
