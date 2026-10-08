// Only public, versioned shell resources. Never cache private pages, API, photos or auth.
const CACHE = "stash-shell-v1";
const FILES = [
  "/static/app.css",
  "/static/app.js",
  "/static/vendor/jsQR.js",
  "/static/brand/icon-192.png",
  "/static/offline.html",
];
self.addEventListener("install", (e) =>
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILES))),
);
self.addEventListener("activate", (e) =>
  e.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  ),
);
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (u.origin !== self.location.origin) return;
  if (FILES.includes(u.pathname)) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }
  if (e.request.mode === "navigate" && !u.pathname.startsWith("/auth/"))
    e.respondWith(
      fetch(e.request).catch(() => caches.match("/static/offline.html")),
    );
});
