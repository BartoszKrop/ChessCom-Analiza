# ChessStats

Statystyki partii z Chess.com i Lichess: ranking, skuteczność wg godzin/dni/długości partii, tempo ruchów, serie, wnioski (sesje, siła rywala, rywale, podsumowanie miesiąca), drzewko debiutów, porównanie graczy i H2H.

## Strona (`docs/`)

Statyczna strona (HTML + JS + Plotly), dane pobierane prosto z przeglądarki z publicznych API.
Zakończone miesiące Chess.com i partie Lichess zapisują się w IndexedDB, więc kolejne wejścia pobierają tylko nowe partie.

- Włączenie: **Settings → Pages → Deploy from a branch → `main` / `/docs`**.
- Link z nickiem od razu uruchamia analizę: `.../?user=NICK&platform=Chess.com` (albo `Lichess`).
- Lokalnie: `python3 -m http.server -d docs` i otwórz http://localhost:8000.
- Testy: `node --test tests/js/*.test.mjs`.

## Biblioteki w `docs/vendor/`

- [Stockfish.js](https://github.com/nmrugg/stockfish.js) 18 lite single-threaded (GPLv3, `vendor/stockfish/Copying.txt`): analiza partii w przeglądarce.
- Bierki cburnett (Colin M.L. Burnett, CC BY-SA 3.0) w `css/pieces.css`, z pakietu @lichess-org/chessground.
- [chess.js](https://github.com/jhlywa/chess.js) 1.4.0 (BSD-2, `vendor/chess.js.LICENSE`): odtwarzanie ruchów z PGN.
