# ChessStats

Statystyki partii z Chess.com i Lichess: ranking, skuteczność wg godzin/dni/długości partii, tempo ruchów, serie, debiuty, porównanie graczy i H2H.

## Wersja na GitHub Pages (`docs/`)

Statyczna strona (HTML + JS + Plotly), dane pobierane prosto z przeglądarki z publicznych API.
Zakończone miesiące Chess.com i partie Lichess zapisują się w IndexedDB, więc kolejne wejścia pobierają tylko nowe partie.

- Włączenie: **Settings → Pages → Deploy from a branch → `main` / `/docs`**.
- Link z nickiem od razu uruchamia analizę: `.../?user=NICK&platform=Chess.com` (albo `Lichess`).
- Lokalnie: `python3 -m http.server -d docs` i otwórz http://localhost:8000.
- Testy: `node --test tests/js/`.

## Wersja Streamlit (`app.py`)

`pip install -r requirements.txt && streamlit run app.py`
