# Discord Chess Bot

![Python Version](https://img.shields.io/badge/Python-3.11-blue)
![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/status-active-success)

Play chess directly in Discord: Solo practice, vs Stockfish AI, PvP 1v1, and single-elimination tournaments with persistent ELO ratings and game history.

## Highlights

- Board images generated with PIL; piece sprites included in repo.
- Stockfish AI with difficulty presets: peaceful, easy, normal, hard, hardcore.
- Persistent storage (SQLite): players, ratings, W/L/D, games (PGN), tournaments, matches.
- ELO leaderboard with player rank and W/L/D.
- Tournament system: create, join, start, bracket view, automatic progression, and tiebreaks on draws.
- Hint command to get the engine’s suggested move.
- Configurable paths via environment variables.

## Getting Started

1) Clone and enter the project

```bash
git clone https://github.com/intensealchemist/DiscordChessBot.git
cd DiscordChessBot
```

2) Python environment and dependencies

```bash
python -m venv .venv
# Windows PowerShell
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3) Environment variables

Set via your shell or a process manager. Required/optional variables:

- DISCORD_BOT_TOKEN: Your bot token.
- STOCKFISH_PATH: Optional path to Stockfish binary (defaults to "stockfish" in PATH).
- CHESSBOT_DB: Optional path to SQLite DB (defaults to "chessbot.db").

Windows PowerShell example:

```powershell
$env:DISCORD_BOT_TOKEN = "YOUR_TOKEN_HERE"
$env:STOCKFISH_PATH = "C:\\path\\to\\stockfish.exe" 
$env:CHESSBOT_DB = "C:\\path\\to\\chessbot.db"            # optional
```

4) Run the bot

```bash
python discordchessbot.py
```

## Configuration

Environment variables used by the bot:

| Variable | Required | Default | Description |
|---|---|---|---|
| DISCORD_BOT_TOKEN | Yes | — | Discord bot token for authentication. |
| STOCKFISH_PATH | No | stockfish | Path to the Stockfish binary or command on PATH. |
| CHESSBOT_DB | No | chessbot.db | SQLite database file path for persistence. |

## Commands Overview

- !start_ai — start an AI game (aliases: !play_ai, !ai_game)
- !p — quick alias to start an AI game
- !solo — start a Solo practice game (you play White)
- !challenge @user — start a 1v1 match
- !move e2e4 — make a move (UCI format). Aliases: !mv, !m
- !ai — make AI move (if it’s AI’s turn). Alias: !a
- !hint — get the engine’s suggested move
- !resign — resign the current game
- !exit — exit and clear the current game session. Aliases: !quit, !q
- !leaderboard — top 10 by ELO and your global rank. Aliases: !lb, !l
- !tournament_create <name> — create a tournament
- !tournament_join <id> — join a tournament
- !tournament_start <id> — start the tournament (Round 1)
- !tournament_bracket <id> — display the current bracket

Note: These are message-prefix commands (prefixes: `/`, `!`, `.`). For example, you can type `!start_ai` or `.p`. They are not “slash” application commands.

### Quick Commands Table

| Command | Description |
|---|---|
| !start_ai | Start an AI game (aliases: !play_ai, !ai_game) |
| !p | Quick alias to start an AI game |
| !solo | Start a Solo practice game |
| !challenge @user | Start a 1v1 match with a user |
| !move e2e4 | Make a UCI move (aliases: !mv, !m) |
| !ai | Engine plays if it is AI's turn (alias: !a) |
| !hint | Show engine's suggested move |
| !resign | Resign your current game |
| !exit | Exit and clear current game session (aliases: !quit, !q) |
| !leaderboard | Top 10 by ELO + your rank (aliases: !lb, !l) |
| !tournament_create <name> | Create a tournament |
| !tournament_join <id> | Join a tournament |
| !tournament_start <id> | Start the tournament (Round 1) |
| !tournament_bracket <id> | Display the current bracket |

## Usage examples

- Start AI game quickly
  ```text
  !p
  ```
- Start AI game (explicit)
  ```text
  !start_ai
  ```
- Move in current game
  ```text
  !move e2e4
  ```
- Ask engine to move (when it’s its turn)
  ```text
  !ai
  ```

## Persistence and ELO

- `players`: user_id, rating (default 1200), wins, losses, draws.
- `games`: white_id, black_id, result, PGN, created_at.
- `tournaments`, `tournament_players`, `tournament_matches` (with `is_tiebreak`).
- ELO updates occur after 1v1 and tournament games.

## Piece Assets and Board Rendering

Board images are saved as `chessboard.png` and posted to Discord.
Coordinates are drawn around the board.

Piece PNGs are organized under `assets/pieces/`:

```
assets/
  pieces/
    white/
      white-king.png
      white-queen.png
      white-rook.png
      white-bishop.png
      white-knight.png
      white-pawn.png
    black/
      black-king.png
      black-queen.png
      black-rook.png
      black-bishop.png
      black-knight.png
      black-pawn.png
```

The renderer in `discordchessbot.py` loads from these paths automatically.

## Screenshots

Here are some live screenshots from the bot running locally.

- AI game start and board render

  ![AI Game Start](assets/Screenshot%202025-08-17%20184027.png)

- Difficulty selection and actions

  ![Difficulty Selection](assets/Screenshot%202025-08-17%20184357.png)

- Move updates and board refresh

  ![Move Update](assets/Screenshot%202025-08-17%20184432.png)

- Additional UI/flow

  ![Flow](assets/Screenshot%202025-08-17%20185056.png)

## Deployment

This repo includes a `procfile` and `start.sh` for simple process hosting.
General tips:

- Ensure the Stockfish binary is available on the host filesystem or in PATH; set `STOCKFISH_PATH` if needed.
- Ensure `DISCORD_BOT_TOKEN` is configured in the host environment.
- The bot writes/read the SQLite file path given by `CHESSBOT_DB` (or `chessbot.db` by default).

### Docker

1) Create a file named `Dockerfile` with the following contents (or copy this snippet into your deployment tooling):

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps (optional: add stockfish here if you want it inside the image)
# RUN apt-get update && apt-get install -y stockfish && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Environment variables expected at runtime:
#   DISCORD_BOT_TOKEN, optional STOCKFISH_PATH, CHESSBOT_DB

CMD ["python", "discordchessbot.py"]
```

2) Build and run (Linux/macOS shells shown):

```bash
docker build -t discord-chess-bot .
docker run --rm \
  -e DISCORD_BOT_TOKEN=YOUR_TOKEN \
  -e STOCKFISH_PATH=stockfish \
  -v $(pwd)/data:/app/data \
  -e CHESSBOT_DB=/app/data/chessbot.db \
  discord-chess-bot
```

Notes:

- If you installed stockfish inside the image, you can omit `STOCKFISH_PATH`.
- Bind-mount a volume to persist the SQLite database.

### Managed Hosting (Heroku/Render/Railway)

This repo includes `procfile` and `start.sh`. Typical steps:

- Set environment variables (`DISCORD_BOT_TOKEN`, optional `STOCKFISH_PATH`, `CHESSBOT_DB`).
- Ensure the runtime provides Stockfish or bundle a path (some hosts allow installing a package or including a static binary).
- Use the provided start command to run `discordchessbot.py`.

## Troubleshooting

- Bot won’t start: verify `DISCORD_BOT_TOKEN` and intents (Message Content) enabled in the Discord Developer Portal.
- Stockfish errors: ensure binary exists and is executable; set `STOCKFISH_PATH` correctly.
- Images not posting: check the process has permission to write the working directory for `chessboard.png`.
- Leaderboard empty: play at least one rated 1v1/tournament game to create player records.
- Database schema: the bot auto-creates/updates tables on startup; delete/backup your DB if you want a clean slate.

## Contributing

PRs welcome! Please open an issue first for large features. Typical flow:

1. Fork
2. Branch (`git checkout -b feat/your-feature`)
3. Commit (`git commit -m "feat: your feature"`)
4. Push and open PR

## License

MIT — see [LICENSE](LICENSE)

## Acknowledgments

- [Python Chess Library](https://python-chess.readthedocs.io/en/latest/): Used for handling chess game logic.
- [Discord.py](https://discordpy.readthedocs.io/en/stable/): Used for interacting with the Discord API.
