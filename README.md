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
