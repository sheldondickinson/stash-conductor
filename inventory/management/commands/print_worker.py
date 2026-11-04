import time

from django.core.management.base import BaseCommand

from inventory.api import Problem
from inventory.printing import work_once


class Command(BaseCommand):
    help = "Run the serial Stash printer worker. Never retries uncertain output."

    def add_arguments(self, p):
        p.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        while True:
            try:
                work_once()
            except Problem:
                pass
            if options["once"]:
                return
            time.sleep(2)
