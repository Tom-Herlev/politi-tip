/* Service worker for Politi Tip.
   App-skallen caches, data.json hentes altid fra nettet først. */
const SHELL_CACHE = "polititip-shell-v1";
const DATA_CACHE = "polititip-data-v1";

const SHELL_ASSETS = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-192-maskable.png",
  "./icons/icon-512-maskable.png",
  "./icons/apple-touch-icon.png",
  "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
  "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== SHELL_CACHE && key !== DATA_CACHE)
          .map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

function isDataRequest(request) {
  try {
    const url = new URL(request.url);
    return url.pathname.endsWith("/data.json") || url.pathname.endsWith("data.json");
  } catch (_) {
    return false;
  }
}

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  if (isDataRequest(event.request)) {
    event.respondWith(networkFirst(event.request, DATA_CACHE));
    return;
  }

  const url = new URL(event.request.url);
  const isShell = event.request.mode === "navigate" || SHELL_ASSETS.some((asset) => {
    if (asset.startsWith("http")) return event.request.url.startsWith(asset.split("?")[0]);
    return url.pathname.endsWith(asset.replace("./", "/")) || (asset === "./" && url.pathname.endsWith("/"));
  });

  if (isShell || url.origin === self.location.origin) {
    event.respondWith(cacheFirst(event.request, SHELL_CACHE));
  }
});

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request, { cache: "no-store" });
    if (response && response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw err;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request, { ignoreSearch: true });
  if (cached) return cached;
  const response = await fetch(request);
  if (response && response.ok) {
    cache.put(request, response.clone());
  }
  return response;
}
