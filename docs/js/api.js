// Pobieranie partii prosto z przeglądarki (oba API obsługują CORS).
// Zakończone miesiące Chess.com trzymamy w IndexedDB, bo się nie zmieniają:
// drugie wejście na profil pobiera tylko bieżący miesiąc.

import { parseChesscomGame, parseLichessGame, MODES } from "./parse.js";

export class PlayerNotFound extends Error {}
export class ApiError extends Error {}

const CHESSCOM_WORKERS = 3; // Chess.com prosi o zapytania sekwencyjne; 3 równolegle to bezpieczny kompromis
const CACHE_VERSION = 1; // zmień, gdy zmieni się format sparsowanych partii

// ---------------------------------------------------------------- IndexedDB
let dbPromise = null;
function db() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve) => {
      try {
        const req = indexedDB.open("chess-stats", CACHE_VERSION);
        req.onupgradeneeded = () => {
          const d = req.result;
          for (const name of [...d.objectStoreNames]) d.deleteObjectStore(name);
          d.createObjectStore("months");
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => resolve(null);
      } catch {
        resolve(null); // np. tryb prywatny: działamy bez cache
      }
    });
  }
  return dbPromise;
}

async function cacheGet(key) {
  const d = await db();
  if (!d) return undefined;
  return new Promise((resolve) => {
    const req = d.transaction("months").objectStore("months").get(key);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => resolve(undefined);
  });
}

async function cacheSet(key, value) {
  const d = await db();
  if (!d) return;
  try {
    d.transaction("months", "readwrite").objectStore("months").put(value, key);
  } catch { /* brak miejsca itp. – trudno */ }
}

// ---------------------------------------------------------------- HTTP
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function get(url, init = {}) {
  for (let attempt = 0; attempt < 3; attempt++) {
    let res;
    try {
      res = await fetch(url, init);
    } catch (e) {
      if (attempt === 2) throw new ApiError("Brak połączenia z API. Sprawdź internet i spróbuj ponownie.");
      await sleep(1000 * (attempt + 1));
      continue;
    }
    if (res.status === 429) {
      if (attempt === 2) throw new ApiError("Przekroczono limit zapytań API (429). Spróbuj za minutę.");
      await sleep(Math.min(Number(res.headers.get("Retry-After")) * 1000 || 5000 * (attempt + 1), 60000));
      continue;
    }
    return res;
  }
  throw new ApiError("Nie udało się pobrać danych.");
}

// ---------------------------------------------------------------- Chess.com
async function chesscomMonth(url, user) {
  const res = await get(url);
  if (!res.ok) throw new ApiError(`Chess.com zwrócił błąd ${res.status} dla archiwum ${url.split("/").slice(-2).join("/")}.`);
  const data = await res.json();
  const account = `${user} (C)`;
  return (data.games || []).map((g) => parseChesscomGame(g, user, account)).filter(Boolean);
}

async function fetchChesscom(user, onProgress, force) {
  const base = `https://api.chess.com/pub/player/${encodeURIComponent(user.toLowerCase())}`;
  const p = await get(base);
  if (p.status === 404 || p.status === 410) throw new PlayerNotFound(user);
  if (!p.ok) throw new ApiError(`Chess.com zwrócił błąd ${p.status}.`);
  const profile = await p.json();
  const a = await get(`${base}/games/archives`);
  if (!a.ok) throw new ApiError(`Chess.com zwrócił błąd ${a.status} (lista archiwów).`);
  const archives = (await a.json()).archives || [];

  const now = new Date();
  const current = `/${now.getUTCFullYear()}/${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
  const months = new Array(archives.length);
  let next = 0, done = 0;

  async function worker() {
    while (next < archives.length) {
      const i = next++;
      const url = archives[i];
      const finished = !url.endsWith(current) && i !== archives.length - 1;
      const key = `${url}|${user.toLowerCase()}`;
      let rows = finished && !force ? await cacheGet(key) : undefined;
      if (!rows) {
        rows = await chesscomMonth(url, user);
        if (finished) cacheSet(key, rows);
      }
      months[i] = rows;
      onProgress?.(++done, archives.length, `Chess.com: archiwum ${done}/${archives.length}`);
    }
  }
  await Promise.all(Array.from({ length: CHESSCOM_WORKERS }, worker));
  return { profile: { avatar: profile.avatar || "", name: profile.username || user }, games: months.flat() };
}

// ---------------------------------------------------------------- Lichess
async function fetchLichess(user, onProgress) {
  const p = await get(`https://lichess.org/api/user/${encodeURIComponent(user)}`);
  if (p.status === 404) throw new PlayerNotFound(user);
  if (!p.ok) throw new ApiError(`Lichess zwrócił błąd ${p.status}.`);
  const profile = await p.json();
  if (profile.disabled || profile.closed) throw new PlayerNotFound(user);
  const expected = ["bullet", "blitz", "rapid"].reduce((s, k) => s + (profile.perfs?.[k]?.games || 0), 0);

  // Tylko standardowe szachy w trybach, które pokazuje aplikacja: mniej danych = szybciej.
  const url = `https://lichess.org/api/games/user/${encodeURIComponent(user)}?opening=true&clocks=true&perfType=bullet,blitz,rapid`;
  const res = await get(url, { headers: { Accept: "application/x-ndjson" } });
  if (!res.ok) throw new ApiError(`Lichess zwrócił błąd ${res.status} (eksport partii).`);

  const account = `${user} (L)`;
  const games = [];
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "", seen = 0;
  const handle = (line) => {
    if (!line.trim()) return;
    seen++;
    try {
      const row = parseLichessGame(JSON.parse(line), user, account);
      if (row) games.push(row);
    } catch { /* pomijamy uszkodzoną linię */ }
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop();
    lines.forEach(handle);
    onProgress?.(seen, Math.max(expected, seen), `Lichess: ${seen} partii`);
  }
  handle(buf);
  return { profile: { avatar: profile.profile?.avatar || "", name: profile.username || user }, games };
}

// ---------------------------------------------------------------- API publiczne
export async function fetchPlayer(user, platform, onProgress, { force = false } = {}) {
  user = user.trim();
  const out = platform === "Lichess" ? await fetchLichess(user, onProgress) : await fetchChesscom(user, onProgress, force);
  out.games = out.games.filter((g) => MODES.includes(g.mode)).sort((a, b) => a.endTs - b.endTs);
  return out;
}

export async function importToLichess(pgn) {
  try {
    const res = await fetch("https://lichess.org/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body: new URLSearchParams({ pgn }),
    });
    if (!res.ok) return null;
    return (await res.json()).url || null;
  } catch {
    return null;
  }
}
