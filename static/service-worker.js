// Very small service worker: caches static assets so the app shell (CSS, icons)
// loads instantly and still opens (with a friendly offline page) with no internet.
// It does NOT cache dynamic pages like /customers or /dashboard, since that data
// must always come from the server — this only speeds up and "app-ifies" the UI shell.

const CACHE_NAME = "softaccess-crm-shell-v4";
const OFFLINE_URL = "/offline";
const SHELL_ASSETS = [
  "/static/css/style.css",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/manifest.json",
];
const PRECACHE = [...SHELL_ASSETS, OFFLINE_URL];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE))
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

  // Page navigations: go to the network, and if offline show the offline page.
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }

  // Only handle GET requests for our own static shell assets.
  if (event.request.method !== "GET" || !SHELL_ASSETS.some((a) => url.pathname === a)) {
    return;
  }

  // CSS changes often (design fixes) — always try the network first so a new
  // deploy shows up immediately, and only use the cached copy if offline.
  // Icons/manifest rarely change, so those stay cache-first (instant load).
  const isStylesheet = url.pathname.endsWith(".css");

  if (isStylesheet) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
  } else {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
  }
});
