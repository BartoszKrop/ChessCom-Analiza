// Po 10 sekundach proponuje instalację strony jako aplikacji (Chrome/Android: systemowy monit, iPhone: instrukcja).
const KEY = "installDismissed";
const safe = { get: (k) => { try { return localStorage.getItem(k); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* brak */ } } };

export function isStandalone() {
  return matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
}
export function isIos() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

export function initInstallPrompt(delayMs = 10000) {
  if (isStandalone() || safe.get(KEY)) return;
  let deferred = null;
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; });
  window.addEventListener("appinstalled", () => { safe.set(KEY, "1"); document.getElementById("install-banner")?.remove(); });
  setTimeout(() => {
    if (isStandalone() || safe.get(KEY) || (!deferred && !isIos())) return;
    const bar = document.createElement("div");
    bar.id = "install-banner";
    bar.setAttribute("role", "dialog");
    bar.innerHTML = `<img src="icons/icon-192.png" alt="" width="40" height="40"><div class="ib-text"><b>Zainstaluj ChessStats</b><span>${deferred
      ? "Jako aplikacja korzysta się dużo wygodniej: pełny ekran bez paska przeglądarki u góry, więcej miejsca na wykresy i partie, ikona na ekranie głównym i start jednym stuknięciem."
      : "Jako aplikacja korzysta się dużo wygodniej: pełny ekran bez paska przeglądarki u góry i więcej miejsca. Stuknij „Udostępnij” w Safari, potem „Do ekranu początkowego”."}</span></div>${deferred ? `<button class="primary" id="ib-go">Zainstaluj</button>` : ""}<button class="link-btn" id="ib-x" aria-label="Zamknij">✕</button>`;
    document.body.appendChild(bar);
    bar.querySelector("#ib-x").addEventListener("click", () => { safe.set(KEY, "1"); bar.remove(); });
    bar.querySelector("#ib-go")?.addEventListener("click", async () => {
      deferred.prompt();
      await deferred.userChoice.catch(() => {});
      deferred = null; safe.set(KEY, "1"); bar.remove();
    });
  }, delayMs);
}
