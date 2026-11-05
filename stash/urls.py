from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import path
from django.views.decorators.csrf import ensure_csrf_cookie

from inventory import api, auth, box_batches, moving, printing, stations


@ensure_csrf_cookie
def app(request, **kwargs):
    if not request.user.is_authenticated:
        return redirect(
            "/auth/login?"
            + __import__("urllib.parse", fromlist=["urlencode"]).urlencode(
                {"next": request.get_full_path()}
            )
        )
    return render(request, "app.html")


def sw(request):
    r = FileResponse(
        (settings.BASE_DIR / "static/sw.js").open("rb"),
        content_type="application/javascript",
    )
    r["Service-Worker-Allowed"] = "/"
    return r


urlpatterns = [
    path("health", lambda r: JsonResponse({"status": "ok", "version": "0.3.2"})),
    path("auth/login", auth.signin),
    path("auth/callback", auth.callback),
    path("auth/logout", auth.signout),
    path("sw.js", sw),
    path("api/me", api.me),
    path("api/containers", api.containers),
    path("api/containers/<uuid:pk>", api.container_detail),
    path("api/box-preview", box_batches.preview),
    path("api/box-batches", box_batches.batches),
    path("api/box-batches/<uuid:pk>", box_batches.batches),
    path("api/box-batches/<uuid:pk>/labels.pdf", box_batches.labels),
    path("api/box-labels.pdf", box_batches.labels),
    path("api/name-unnamed-boxes", box_batches.name_unnamed),
    path("api/items", api.items),
    path("api/items/<uuid:pk>", api.item_detail),
    path("api/bulk", api.bulk),
    path("api/undo/<uuid:pk>", api.undo),
    path("api/media/<str:name>", api.media),
    path("api/label/<str:code>", api.label),
    path("api/export", api.export),
    path("api/pairings", api.pairings),
    path("api/handoff/<uuid:pk>", api.handoff),
    path("api/consume", api.consume),
    path("api/users", api.users),
    path("api/tokens", api.tokens),
    path("api/locations", moving.locations),
    path("api/locations/<uuid:pk>", moving.locations),
    path("api/moves", moving.moves),
    path("api/activity", moving.activity),
    path("api/batches", moving.batches),
    path("api/tags", moving.tags),
    path("api/tags/<str:token>", moving.tags),
    path("api/moving-manifest", moving.manifest),
    path("api/printer", printing.printer),
    path("api/print-jobs", printing.jobs),
    path("api/print-jobs/<uuid:pk>", printing.jobs),
    path("api/label-preview", printing.preview),
    path("api/stations", stations.stations),
    path("api/stations/<uuid:pk>", stations.stations),
    path("api/station/<uuid:pk>/exchange", stations.exchange),
    path("api/station/<uuid:pk>/firmware", stations.firmware),
    path("t/<str:token>", app),
    path("l/<str:code>", app),
    path("packing", app),
    path("", app),
    path("c/<str:code>", app),
    path("i/<uuid:pk>", app),
]
