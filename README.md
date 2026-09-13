# Chess AI Coach ♟️🤖

An intelligent, terminal-based chess analysis companion. It retrieves recent matches directly from Lichess, calculates key tactical turning points via a local **Stockfish** engine, and translates raw engine evaluations into natural, conversational coaching using **Gemini 3.6 Flash**.

---

## Architecture Overview

```text
       +------------------+
       |   Lichess API    |  ---> Fetch recent player PGN / game records
       +--------+---------+
                |
                v
       +------------------+
       | Stockfish Engine |  ---> Deep positional evaluations & blunder detection
       +--------+---------+
                |
                v
       +------------------+
       | Gemini 3.6 Flash |  ---> Natural language coaching & tactical diagnostics
       +--------+---------+
                |
                v
       +------------------+
       | Rich Terminal UI |  ---> Formatted panels, evaluations, and board state
       +------------------+

## Project Structure
```text

    chess/
    ├── .gitignore          # Excludes environments, caches, and local profiles
    ├── README.md           # Documentation and setup instructions
    ├── requirements.txt    # Production Python dependencies
    ├── chess_coach.py      # Core CLI loop, engine bridge, and LLM orchestration
    └── chess_ui.py         # Terminal UI formatting and board rendering (Rich)

## Setup and Installattion
```text

    sudo apt update && sudo apt install stockfish
    git clone git@github.com:Allanprince001/chess-ai-coach.git
    cd chess-ai-coach

    python3 -m venv chess_venv
    source chess_venv/bin/activate
    pip install --upgrade pip
    pip install -r req.txt

    export GEMINI_API_KEY="your_actual_gemini_api_key_here"

    python3 chess_coach.py <lichess_username>
