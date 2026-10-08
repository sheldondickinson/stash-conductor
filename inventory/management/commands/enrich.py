"""Explicit optional enrichment job; disabled unless a trusted endpoint is configured."""

import base64
import os

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventory.models import Item


class Command(BaseCommand):
    help = "Send one explicitly selected photo to a configured trusted AI endpoint; suggestions only."

    def add_arguments(self, p):
        p.add_argument("item_id")

    def handle(self, *args, **opts):
        endpoint = os.environ.get("AI_ENDPOINT")
        token = os.environ.get("AI_TOKEN")
        if not endpoint or not token:
            raise CommandError(
                "AI disabled. Set AI_ENDPOINT and AI_TOKEN in private configuration."
            )
        if not endpoint.startswith("https://"):
            raise CommandError("HTTPS endpoint required")
        i = Item.objects.get(pk=opts["item_id"])
        if not i.photo:
            raise CommandError("This record has no photo")
        s = requests.Session()
        s.trust_env = False
        r = s.post(
            endpoint,
            headers={"Authorization": "Bearer " + token},
            json={
                "image_base64": base64.b64encode(
                    (settings.MEDIA_ROOT / i.photo).read_bytes()
                ).decode(),
                "original_phrase": i.original,
                "instruction": "Suggest a title, aliases and visible markings. State uncertainty. Never infer quantities or electrical ratings without evidence.",
            },
            timeout=45,
            allow_redirects=False,
        )
        if r.status_code != 200:
            raise CommandError("Provider failed; response suppressed")
        if len(r.content) > 32000:
            raise CommandError("Suggestion too large")
        result = r.json()
        with transaction.atomic():
            i = Item.objects.get(pk=i.pk)
            i.suggestions = [
                *i.suggestions,
                {
                    "provider": endpoint.split("/")[2],
                    "unconfirmed": True,
                    "suggestion": result,
                },
            ]
            i.revision += 1
            i.save()
        self.stdout.write(
            "Unconfirmed suggestion saved; inventory identity, count and location unchanged."
        )
