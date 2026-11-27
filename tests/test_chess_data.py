import pandas as pd

from chess_data import (
    extract_moves_count, extract_move_times_from_pgn, localize_games,
    parse_chesscom_game, parse_lichess_game,
)

PGN = """[Event "Live Chess"]
[Date "2024.01.05"]
[White "me"]
[Black "you"]

1. e4 {[%clk 0:02:59.9]} 1... e5 {[%clk 0:02:58.1]} 2. Qh5 {[%clk 0:02:55.3]} 2... Nc6 {[%clk 0:02:50.7]} 3. Bc4 {[%clk 0:02:50]} 3... Nf6 {[%clk 0:02:45.2]} 4. Qxf7# {[%clk 0:02:48.4]} 1-0
"""


def test_moves_count_ignores_clock_and_date():
    assert extract_moves_count(PGN) == 4


def test_moves_count_lichess_style_and_empty():
    assert extract_moves_count("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6") == 3
    assert extract_moves_count("") == 0


def test_move_times_white():
    assert extract_move_times_from_pgn(PGN, True) == [4.6, 5.3, 1.6]


def _cc_game(rules="chess", white_result="win", black_result="checkmated"):
    return {
        "end_time": 1704470400, "rules": rules, "time_class": "blitz", "pgn": PGN,
        "url": "https://www.chess.com/game/live/1",
        "white": {"username": "Me", "result": white_result, "rating": 1500},
        "black": {"username": "you", "result": black_result, "rating": 1480},
    }


def test_chesscom_parse_and_variant_skip():
    row = parse_chesscom_game(_cc_game(), "me", "me (C)")
    assert row["Wynik"] == "Wygrane" and row["Ruchy"] == 4 and row["Kolor"] == "Białe"
    assert parse_chesscom_game(_cc_game(rules="chess960"), "me", "me (C)") is None
    draw = parse_chesscom_game(_cc_game(white_result="repetition", black_result="repetition"), "me", "x")
    assert draw["Wynik"] == "Remisy"


def _li_game(status="mate", winner="white"):
    g = {"id": "abc", "status": status, "variant": "standard", "speed": "blitz",
         "createdAt": 1704470000000, "lastMoveAt": 1704470400000, "moves": "e4 e5 Qh5 Nc6 Bc4 Nf6 Qxf7#",
         "players": {"white": {"user": {"name": "Me"}, "rating": 1600},
                     "black": {"user": {"name": "you"}, "rating": 1590}}}
    if winner:
        g["winner"] = winner
    return g


def test_lichess_parse_aborted_skipped_and_end_time():
    row = parse_lichess_game(_li_game(), "me", "me (L)")
    assert row["Wynik"] == "Wygrane" and row["Ruchy"] == 4 and row["EndTs"] == 1704470400
    assert parse_lichess_game(_li_game(status="aborted", winner=None), "me", "x") is None


def test_localize_uses_user_timezone_not_utc():
    df = pd.DataFrame({"EndTs": [1704470400]})  # 2024-01-05 16:00 UTC
    out = localize_games(df, "Europe/Warsaw")
    assert out["Godzina"].iloc[0] == 17
    assert out["Dzień"].iloc[0] == "Pt"
