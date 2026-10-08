import getpass

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or recover a local account interactively; no SMTP or password arguments."

    def add_arguments(self, p):
        p.add_argument("username")
        p.add_argument("--owner", action="store_true")
        p.add_argument("--disable", action="store_true")

    def handle(self, *args, **opts):
        if settings.AUTH_MODE != "local":
            raise CommandError("Local accounts are disabled in OIDC mode.")
        u = User.objects.filter(username=opts["username"]).first()
        if opts["disable"]:
            if not u:
                raise CommandError("No such account")
            u.is_active = False
            u.save()
            return
        password = getpass.getpass("New password: ")
        if password != getpass.getpass("Repeat password: "):
            raise CommandError("Passwords differ")
        validate_password(password, u)
        if u is None:
            u = User(username=opts["username"])
        u.set_password(password)
        u.is_staff = opts["owner"]
        u.is_active = True
        u.save()
        self.stdout.write(
            "Local account saved. Share credentials securely; nothing has been sent."
        )
