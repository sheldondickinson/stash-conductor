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
