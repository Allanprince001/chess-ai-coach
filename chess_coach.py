import io
import os
import sys
import chess
import chess.engine
import chess.pgn
import chess.syzygy
import requests
import berserk
from google import genai
from google.genai import types

# ---------------------------------------------------------
# Configuration Paths (Adjust to your system binaries/paths)
# ---------------------------------------------------------
STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH", "/usr/games/stockfish")
SYZYGY_PATH = os.environ.get("SYZYGY_PATH", None)  # e.g., "/path/to/syzygy/3-4-5"


# ---------------------------------------------------------
# Tool Functions exposed to Gemini (Function Calling)
# ---------------------------------------------------------

def evaluate_position_or_move(fen: str, move_san_or_uci: str = "") -> dict:
    """
    Evaluates a chess position given a FEN string. If a move is provided,
    it makes the move first and evaluates the resulting board using Stockfish.
    Returns centipawn evaluation, best move, and tactical refutation.
    """
    try:
        board = chess.Board(fen)
        if move_san_or_uci:
            try:
                move = board.parse_san(move_san_or_uci)
            except ValueError:
                move = chess.Move.from_uci(move_san_or_uci)
            board.push(move)

        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        info = engine.analyse(board, chess.engine.Limit(depth=16))
        engine.quit()

        score = info["score"].white().score(mate_score=10000)
        pv_moves = [board.san(m) for m in info.get("pv", [])[:4]]

        return {
            "fen_after": board.fen(),
            "eval_white_cp": score,
            "engine_best_line": " ".join(pv_moves),
            "is_game_over": board.is_game_over()
        }
    except Exception as e:
        return {"error": str(e)}


def query_opening_explorer(fen: str) -> dict:
    """
    Queries the Lichess Masters Opening Database for a given FEN position.
    Returns the opening name, popular grandmaster moves, and win/draw statistics.
    """
    try:
        url = "https://explorer.lichess.ovh/masters"
        params = {"fen": fen, "moves": 5}
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code != 200:
            return {"error": f"Lichess Explorer returned status code {resp.status_code}"}
        
        data = resp.json()
        opening = data.get("opening", {})
        moves = [
            {
                "san": m["san"],
                "white_wins": m["white"],
                "draws": m["draws"],
                "black_wins": m["black"]
            }
            for m in data.get("moves", [])
        ]
        return {
            "eco": opening.get("eco", "N/A"),
            "name": opening.get("name", "Unknown Line"),
            "candidate_moves": moves
        }
    except Exception as e:
        return {"error": str(e)}


def probe_endgame_tablebase(fen: str) -> dict:
    """
    Probes Syzygy tablebases (or the online tablebase fallback) for perfect
    endgame play when 7 or fewer pieces remain on the board.
    Returns theoretical outcome (Win, Draw, Loss) and Distance to Zero (DTZ).
    """
    board = chess.Board(fen)
    piece_count = len(board.piece_map())
    if piece_count > 7:
        return {"info": f"Position has {piece_count} pieces. Tablebases only support <= 7 pieces."}

    # 1. Local probing if path is set
    if SYZYGY_PATH and os.path.isdir(SYZYGY_PATH):
        try:
            with chess.syzygy.open_tablebase(SYZYGY_PATH) as tablebase:
                wdl = tablebase.get_wdl(board)
                dtz = tablebase.get_dtz(board)
                results = {-2: "Loss", -1: "Blessed Loss", 0: "Draw", 1: "Cursed Win", 2: "Win"}
                return {"outcome": results.get(wdl, "Unknown"), "dtz": dtz, "source": "local_syzygy"}
        except Exception:
            pass  # Fallback to online probing

    # 2. Lichess Tablebase Online API Fallback
    try:
        url = "http://tablebase.lichess.ovh/standard"
        resp = requests.get(url, params={"fen": fen}, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            category = data.get("category", "Unknown")  # 'win', 'draw', 'loss'
            best_move = data.get("moves", [{}])[0].get("san", "None") if data.get("moves") else "None"
            return {"theoretical_outcome": category, "optimal_move": best_move, "source": "lichess_tablebase"}
    except Exception as e:
        return {"error": str(e)}

    return {"error": "Unable to query tablebases."}


# ---------------------------------------------------------
# Lichess Ingestion & Parsing
# ---------------------------------------------------------

def fetch_player_games(username: str, max_games: int = 3) -> list[str]:
    """Fetches games directly via Lichess HTTP API with proper headers to prevent connection resets."""
    url = f"https://lichess.org/api/games/user/{username}"
    headers = {
        "User-Agent": f"ChessCoachApp/1.0 ({username})",
        "Accept": "application/x-chess-pgn"
    }
    
    token = os.environ.get("LICHESS_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    params = {
        "max": max_games,
        "clocks": "true",
        "evals": "false",
        "opening": "true"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 404:
            print(f"[!] User '{username}' not found on Lichess.")
            return []
        if response.status_code != 200:
            print(f"[!] Lichess returned HTTP {response.status_code}: {response.text[:100]}")
            return []
            
        raw_text = response.text.strip()
        if not raw_text:
            return []
            
        # Split concatenated PGNs by the starting bracket
        games = []
        for chunk in raw_text.split("\n\n\n"):
            if chunk.strip():
                games.append(chunk.strip())
        return games

    except requests.exceptions.RequestException as e:
        print(f"[!] Network error reaching Lichess: {e}")
        return []

def pre_analyze_game(pgn_str: str, target_user: str, depth: int = 12):
    """Parses PGN and pre-computes Stockfish centipawn shifts for fast context injection."""
    game = chess.pgn.read_game(io.StringIO(pgn_str))
    if not game:
        return None, "Empty PGN"

    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    board = game.board()
    eval_log = []

    for idx, move in enumerate(game.mainline_moves()):
        san_move = board.san(move)
        board.push(move)

        info = engine.analyse(board, chess.engine.Limit(depth=depth))
        score = info["score"].white().score(mate_score=10000)

        move_num = (idx // 2) + 1
        turn = "White" if idx % 2 == 0 else "Black"
        eval_log.append(f"{move_num}.{turn} ({san_move}) -> White Eval: {score} cp | FEN: {board.fen()}")

    engine.quit()
    return game.headers, "\n".join(eval_log)


# ---------------------------------------------------------
# Interactive Coaching Loop
# ---------------------------------------------------------

def run_coach(username: str):
    print(f"[*] Fetching games from Lichess for: {username}...")
    games = fetch_player_games(username, max_games=1)
    if not games:
        print(f"[!] No public games found for {username}.")
        return

    print("[*] Running Stockfish deterministic pre-pass...")
    headers, eval_stream = pre_analyze_game(games[0], username)

    system_instruction = f"""
    You are an elite, candid, and supportive Grandmaster coach chatting with {username}.
    
    The user's core opening interests are:
    - As White: Scotch Game (1. e4 e5 2. Nf3 Nc6 3. d4), Closed Sicilian against 1... c5, Panov Attack against Caro-Kann (leads to IQP setups), and Queen's Gambit setups with IQP.
    - As Black: Modern Scandinavian (1. e4 d5 2. exd5 Nf6).
    The user wants to cultivate blindfold board visualization and clean endgame precision.

    LATEST MATCH CONTEXT:
    White: {headers.get('White')} | Black: {headers.get('Black')} | Result: {headers.get('Result')}
    Event: {headers.get('Event')} | Time Control: {headers.get('TimeControl')}

    MOVE-BY-MOVE ENGINE RECORD:
    {eval_stream}

    TOOLS AT YOUR DISPOSAL:
    - evaluate_position_or_move: Test what-if moves and tactical variations using local Stockfish.
    - query_opening_explorer: Check master stats, opening names, and book moves.
    - probe_endgame_tablebase: Query perfect Syzygy theoretical play when pieces <= 7.

    COACHING RULES:
    1. Ground all tactical claims in tool output. Never hallucinate moves or evaluations.
    2. When explaining errors, explain the underlying structural reason (e.g., lost an outpost, surrendered center, pawn chain weakness) rather than merely reciting engine centipawn scores.
    3. Keep answers punchy and conversational. Avoid walls of text.
    """

    client = genai.Client()

    # Pass the functions directly to client.chats.create
    # The Google Gen AI SDK handles tool execution and response synthesis automatically
    chat = client.chats.create(
        model="gemini-3.6-flash",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.3,
            tools=[evaluate_position_or_move, query_opening_explorer, probe_endgame_tablebase]
        )
    )

    print("\n========================= CHESS COACH ONLINE =========================")
    initial_res = chat.send_message(
        "Give me a crisp 3-bullet breakdown of my latest game: the opening accuracy, "
        "the critical tactical turning point, and my endgame/conversion precision."
    )
    print(f"\nCOACH>\n{initial_res.text}\n")
    print("----------------------------------------------------------------------")
    print("Ask questions about moves, test hypothetical lines, drill openings, or type 'exit'.\n")

    while True:
        try:
            user_msg = input(f"{username}> ").strip()
            if not user_msg:
                continue
            if user_msg.lower() in ["exit", "quit", "q"]:
                print("Keep your pieces active and control the center. Goodbye!")
                break

            response = chat.send_message(user_msg)
            print(f"\nCOACH>\n{response.text}\n")

        except KeyboardInterrupt:
            print("\nSession ended.")
            break


if __name__ == "__main__":
    player = sys.argv[1] if len(sys.argv) > 1 else "MagnusCarlsen"
    run_coach(player)
