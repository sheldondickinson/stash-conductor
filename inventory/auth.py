import hashlib
from datetime import timedelta

from authlib.integrations.django_client import OAuth
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Identity, LoginAttempt

oauth = OAuth()
if settings.AUTH_MODE == "oidc":
    oauth.register(
        "identity",
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        server_metadata_url=settings.OIDC_ISSUER.rstrip("/")
        + "/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid profile email groups",
            "code_challenge_method": "S256",
        },
        claims_options={"iss": {"essential": True, "value": settings.OIDC_ISSUER}},
    )


def safe_next(value):
    return (
        value
        if isinstance(value, str)
        and value.startswith("/")
        and not value.startswith("//")
        and "\\" not in value
        and not any(ord(c) < 32 for c in value)
        else "/"
    )


def signin(request):
    next_url = safe_next(request.GET.get("next", request.POST.get("next", "/")))
    if request.user.is_authenticated:
        return redirect(next_url)
    if settings.AUTH_MODE == "oidc":
        request.session["return_to"] = next_url
        return oauth.identity.authorize_redirect(
            request, settings.ORIGIN + "/auth/callback"
        )
    error = ""
    if request.method == "POST":
        key = hashlib.sha256(
            (request.POST.get("username", "").casefold()).encode()
        ).hexdigest()
        attempt, _ = LoginAttempt.objects.get_or_create(key=key)
        if attempt.count >= 8 and attempt.updated > timezone.now() - timedelta(
            minutes=15
        ):
            error = "Too many attempts. Wait 15 minutes before trying again."
        else:
            user = authenticate(
                request,
                username=request.POST.get("username", ""),
                password=request.POST.get("password", ""),
            )
            if user:
                attempt.delete()
                login(request, user)
                return redirect(next_url)
            attempt.count = (
                attempt.count + 1
                if attempt.updated > timezone.now() - timedelta(minutes=15)
                else 1
            )
            attempt.save()
            error = "Sign-in failed."
    return render(request, "login.html", {"error": error, "next": next_url})


def resolve_identity(info):
    if info.get("iss") != settings.OIDC_ISSUER or not info.get("sub"):
        raise ValueError("Invalid identity")
    groups = info.get("groups", [])
    if not isinstance(groups, list):
        raise ValueError("Invalid groups")
    owner = settings.OIDC_OWNER_GROUP in groups
    if not owner and settings.OIDC_MEMBER_GROUP not in groups:
        raise PermissionError("Access denied")
    with transaction.atomic():
        identity = (
            Identity.objects.filter(issuer=info["iss"], subject=info["sub"])
            .select_related("user")
            .first()
        )
        if identity:
            user = identity.user
        else:
            # Never link on email, display name or mutable username.
            name = (
                "oidc-"
                + hashlib.sha256(
                    (info["iss"] + "\0" + info["sub"]).encode()
                ).hexdigest()[:40]
            )
            user = User.objects.create_user(name, password=None)
            Identity.objects.create(user=user, issuer=info["iss"], subject=info["sub"])
        if not user.is_active:
            raise PermissionError("Disabled account")
        user.first_name = str(
            info.get("name") or info.get("preferred_username") or "Member"
        )[:150]
        user.is_staff = owner
        user.is_superuser = False
        user.save()
    return user


def callback(request):
    if settings.AUTH_MODE != "oidc":
        return HttpResponse(status=404)
    try:
        token = oauth.identity.authorize_access_token(request)
        info = token[
            "userinfo"
        ]  # Authlib verifies signature, issuer, audience, expiry and nonce.
        user = resolve_identity(info)
        dest = safe_next(request.session.pop("return_to", "/"))
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect(dest)
    except Exception:
        # Do not log codes, tokens or exception payloads.
        return HttpResponse(
            "Sign-in could not be completed. Access may not be granted, or the login expired. Start again.",
            status=403,
        )


@require_POST
def signout(request):
    logout(request)
    return redirect("/auth/login")
