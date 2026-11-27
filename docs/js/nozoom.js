// Wyłącza przybliżanie strony (szczypanie, podwójne stuknięcie) poza wykresami, gdzie przybliżanie jest przydatne.
const inChart = (t) => t instanceof Element && !!t.closest(".chart, .js-plotly-plot");

export function disablePageZoom() {
  const opt = { passive: false };
  // iOS Safari: gest szczypania.
  for (const ev of ["gesturestart", "gesturechange", "gestureend"]) {
    document.addEventListener(ev, (e) => { if (!inChart(e.target)) e.preventDefault(); }, opt);
  }
  // Android i reszta: dwa palce na raz.
  document.addEventListener("touchmove", (e) => { if (e.touches.length > 1 && !inChart(e.target)) e.preventDefault(); }, opt);
  // Podwójne stuknięcie wyłącza CSS (touch-action: manipulation), bez blokowania szybkich kliknięć.
}
