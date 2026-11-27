// Drobne dopracowania: animowane liczby, przejście zakładek, gest przełączania zakładek, przycisk „do góry".
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// Liczby w kafelkach narastają od zera (tylko zwykłe liczby, np. "3282", "48%", "114.3 h").
export function countUp(root) {
  if (reduced()) return;
  root.querySelectorAll(".metric .value").forEach((el) => {
    const m = el.textContent.trim().match(/^(-?\d+(?:[.,]\d+)?)(\s?(?:%|h))?$/);
    if (!m) return;
    const end = parseFloat(m[1].replace(",", "."));
    if (!Number.isFinite(end) || Math.abs(end) < 5) return;
    const dec = (m[1].split(/[.,]/)[1] || "").length, sep = m[1].includes(",") ? "," : ".", unit = m[2] || "";
    const t0 = performance.now(), dur = 550;
    const step = (now) => {
      const k = Math.min(1, (now - t0) / dur), e = 1 - (1 - k) ** 3;
      el.textContent = (end * e).toFixed(dec).replace(".", sep) + unit;
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

// Płynne wejście zawartości zakładki (kolejne elementy z lekkim opóźnieniem).
export function enter(el) {
  if (reduced()) return;
  el.classList.remove("tab-enter");
  void el.offsetWidth; // restart animacji
  el.classList.add("tab-enter");
}

// Przesunięcie palcem w bok zmienia zakładkę (nie na wykresach, planszy, tabelach i polach formularzy).
export function initSwipeTabs() {
  const area = document.getElementById("tab-content");
  let x0 = null, y0 = 0, t0 = 0;
  const blocked = (t) => t instanceof Element && !!t.closest(".chart, .js-plotly-plot, .board, .sf-panel, .table-wrap, input, select, textarea, .game-list .sf-main");
  area.addEventListener("touchstart", (e) => {
    if (e.touches.length !== 1 || blocked(e.target)) { x0 = null; return; }
    x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; t0 = Date.now();
  }, { passive: true });
  area.addEventListener("touchend", (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
    x0 = null;
    if (Math.abs(dx) < 80 || Math.abs(dy) > 45 || Date.now() - t0 > 600) return;
    const btns = [...document.querySelectorAll("#tabs button[data-tab]")].filter((b) => b.dataset.tab !== "__rival");
    const i = btns.findIndex((b) => b.classList.contains("on"));
    const next = btns[i + (dx < 0 ? 1 : -1)];
    if (next) next.click();
  }, { passive: true });
}

export function initToTop() {
  const b = document.createElement("button");
  b.id = "to-top";
  b.type = "button";
  b.setAttribute("aria-label", "Do góry");
  b.innerHTML = `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 15 6-6 6 6"/></svg>`;
  b.addEventListener("click", () => scrollTo({ top: 0, behavior: reduced() ? "auto" : "smooth" }));
  document.body.appendChild(b);
  let on = false;
  addEventListener("scroll", () => {
    const show = scrollY > 700;
    if (show !== on) { on = show; b.classList.toggle("show", show); }
  }, { passive: true });
}
