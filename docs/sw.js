// Service worker:
// 1) dodaje nagłówki COOP/COEP, żeby strona była „cross-origin isolated”: bez tego przeglądarka nie da silnikowi
//    szachowemu wielu wątków (SharedArrayBuffer), a GitHub Pages nie pozwala ustawiać nagłówków;
// 2) zawsze najpierw sieć (nowa wersja strony od razu widoczna), pliki z cache tylko gdy nie ma internetu;
// 3) Plotly z CDN trzyma w cache (duży plik, rzadko się zmienia).
// Zapytań do API Chess.com i Lichess nie dotyka.
const CACHE = "chessstats-v22";
const CDN_CACHE = "chessstats-cdn-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil((async () => {
  for (const k of await caches.keys()) if (k !== CACHE && k !== CDN_CACHE) await caches.delete(k);
  await self.clients.claim();
})()));

function isolate(res) {
  if (res.status === 0 || res.type === "opaque") return res;
  const headers = new Headers(res.headers);
  headers.set("Cross-Origin-Opener-Policy", "same-origin");
  headers.set("Cross-Origin-Embedder-Policy", "credentialless");
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (url.origin !== location.origin) {
    // Plotly z jsdelivr: najpierw cache (plik jest przypięty do wersji w adresie).
    if (url.hostname === "cdn.jsdelivr.net" && /plotly/.test(url.pathname)) {
      e.respondWith(caches.open(CDN_CACHE).then(async (c) => {
        const hit = await c.match(req);
        if (hit) return hit;
        const res = await fetch(req);
        if (res.ok || res.type === "opaque") c.put(req, res.clone()).catch(() => {});
        return res;
      }));
    }
    return;
  }

  // only-if-cached bez trybu same-origin psuje fetch w niektórych przeglądarkach.
  if (req.cache === "only-if-cached" && req.mode !== "same-origin") return;
  e.respondWith(
    fetch(req.url, { cache: "no-cache", credentials: "same-origin" })
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return isolate(res);
      })
      .catch(async () => {
        const hit = await caches.match(req);
        return hit ? isolate(hit) : Response.error();
      })
  );
});
