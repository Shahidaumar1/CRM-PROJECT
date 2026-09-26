// Very small service worker: caches static assets so the app shell (CSS, icons)
// loads instantly and still opens (with a friendly offline page) with no internet.
// It does NOT cache dynamic pages like /customers or /dashboard, since that data
// must always come from the server — this only speeds up and "app-ifies" the UI shell.

const CACHE_NAME = "softaccess-crm-shell-v1";
const SHELL_ASSETS = [
  "/static/css/style.css",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Only handle GET requests for our own static shell assets.
  if (event.request.method !== "GET" || !SHELL_ASSETS.some((a) => url.pathname === a)) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
