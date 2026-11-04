import secrets
import uuid

from django.contrib.auth.models import User
from django.db import models


class Identity(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    issuer = models.CharField(max_length=300)
    subject = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["issuer", "subject"], name="unique_oidc_identity"
            )
        ]


class Container(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=160, blank=True)
    location = models.CharField(max_length=300, blank=True)
    photo = models.CharField(max_length=100, blank=True)
    revision = models.PositiveIntegerField(default=1)
    physical_location = models.ForeignKey(
        "Location", null=True, blank=True, on_delete=models.PROTECT
    )
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    destination = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    packing_state = models.CharField(max_length=24, default="empty")
    fragile = models.BooleanField(default=False)
    heavy = models.BooleanField(default=False)
    priority = models.BooleanField(default=False)
    category = models.CharField(max_length=160, blank=True)
    keywords = models.CharField(max_length=500, blank=True)
    storage_notes = models.TextField(blank=True)
    review_date = models.DateField(null=True, blank=True)


class Location(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=24, unique=True)
    name = models.CharField(max_length=160)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)


class BoxSequence(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    next_number = models.PositiveBigIntegerField(default=1)


class BoxCode(models.Model):
    # Permanent reservations also survive any future archival/deletion workflow.
    code = models.CharField(primary_key=True, max_length=24)


class BoxBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField(unique=True)
    request_digest = models.CharField(max_length=64)
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    name = models.CharField(max_length=160, blank=True)
    defaults = models.JSONField(default=dict)
    created = models.DateTimeField(auto_now_add=True)


class BoxBatchMember(models.Model):
    batch = models.ForeignKey(
        BoxBatch, on_delete=models.PROTECT, related_name="members"
    )
    box = models.ForeignKey(Container, on_delete=models.PROTECT)
    position = models.PositiveIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "box"], name="box_batch_membership"
            ),
            models.UniqueConstraint(
                fields=["batch", "position"], name="box_batch_position"
            ),
        ]


def tag_token():
    return secrets.token_urlsafe(16)


def tag_code():
    return "T" + secrets.token_hex(4).upper()


class TagBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    created = models.DateTimeField(auto_now_add=True)


class Tag(models.Model):
    token = models.CharField(
        primary_key=True, max_length=22, default=tag_token, editable=False
    )
    code = models.CharField(max_length=12, unique=True, default=tag_code)
    batch = models.ForeignKey(TagBatch, on_delete=models.PROTECT)
    container = models.ForeignKey(
        Container, null=True, blank=True, on_delete=models.PROTECT
    )
    location = models.ForeignKey(
        Location, null=True, blank=True, on_delete=models.PROTECT
    )
    state = models.CharField(max_length=16, default="active")
    encoding = models.CharField(max_length=24, default="unwritten")
    encoded_at = models.DateTimeField(null=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~(
                    models.Q(container__isnull=False) & models.Q(location__isnull=False)
                ),
                name="tag_one_target",
            )
        ]


class Station(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    secret_hash = models.CharField(max_length=64)
    revoked = models.BooleanField(default=False)
    batch = models.ForeignKey(TagBatch, null=True, on_delete=models.PROTECT)
    armed_until = models.DateTimeField(null=True)
    armed_by = models.ForeignKey(User, null=True, on_delete=models.PROTECT)
    print_after = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True)
    last_result = models.CharField(max_length=300, blank=True)
    # One explicit overwrite authorisation for one inspected UID, never a broad switch.
    overwrite_uid = models.CharField(max_length=32, blank=True)
    revision = models.PositiveIntegerField(default=1)


class EncodingReservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    station = models.ForeignKey(Station, on_delete=models.PROTECT)
    tag = models.OneToOneField(Tag, on_delete=models.PROTECT)
    uid = models.CharField(max_length=32, unique=True)
    state = models.CharField(max_length=16, default="reserved")
    created = models.DateTimeField(auto_now_add=True)
    verified = models.DateTimeField(null=True)


class Printer(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    name = models.CharField(max_length=100, default="Brother PT-P750W")
    tape_mm = models.PositiveSmallIntegerField(default=24)
    finishing = models.CharField(max_length=24, default="single-full")
    revision = models.PositiveIntegerField(default=1)
    last_check = models.DateTimeField(null=True)
    status = models.JSONField(default=dict)


class PrintJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    source_key = models.CharField(max_length=100, unique=True)
    labels = models.JSONField()
    tape_mm = models.PositiveSmallIntegerField()
    finishing = models.CharField(max_length=24)
    state = models.CharField(max_length=24, default="queued")
    detail = models.CharField(max_length=500, blank=True)
    result = models.JSONField(default=dict)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)


class Item(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=240)
    original = models.TextField(blank=True)
    aliases = models.TextField(blank=True)
    container = models.ForeignKey(Container, null=True, on_delete=models.PROTECT)
    last_container = models.ForeignKey(
        Container, null=True, on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(max_length=24, default="stored")
    quantity = models.PositiveIntegerField(null=True)
    unit = models.CharField(max_length=40, default="batch")
    photo = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict)
    suggestions = models.JSONField(default=list)
    revision = models.PositiveIntegerField(default=1)
    confirmed = models.DateTimeField(auto_now_add=True)
    created = models.DateTimeField(auto_now_add=True)


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.CharField(max_length=40)
    entity_id = models.CharField(max_length=40)
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created = models.DateTimeField(auto_now_add=True)


class Receipt(models.Model):
    key = models.CharField(max_length=100)
    actor = models.ForeignKey(User, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64)
    response = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["actor", "key"], name="unique_request")
        ]


class Pairing(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    installation = models.CharField(max_length=100)
    secret_hash = models.CharField(max_length=64)
    label = models.CharField(max_length=100)
    revoked = models.BooleanField(default=False)
    destination = models.CharField(max_length=24, blank=True)
    expires = models.DateTimeField(null=True)


class ApiToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=100)
    write = models.BooleanField(default=False)
    expires = models.DateTimeField()


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    updated = models.DateTimeField(auto_now=True)
