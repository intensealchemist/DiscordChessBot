import os
import discord
from discord.ext import commands
import chess
import chess.svg
import chess.engine
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import random
import asyncio
from stockfish import Stockfish
from threading import Thread
import time
import threading
import sqlite3
import math
import datetime
import chess.pgn

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or("/", "!", "."),
                   intents=intents)

TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Configure Stockfish path via env; fallback to system PATH
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "stockfish")
stockfish = Stockfish(STOCKFISH_PATH)

############################
# Persistence and ELO Setup #
############################

DB_PATH = os.getenv("CHESSBOT_DB", "chessbot.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            rating REAL NOT NULL DEFAULT 1200.0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            draws INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            white_id INTEGER,
            black_id INTEGER,
            result TEXT,
            pgn TEXT,
            created_at TEXT
        )
        """
    )
    # Tournaments
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            name TEXT,
            status TEXT, -- created, ongoing, finished
            created_at TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tournament_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER,
            user_id INTEGER
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS tournament_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER,
            round INTEGER,
            white_id INTEGER,
            black_id INTEGER,
            winner_id INTEGER,
            status TEXT, -- pending, ongoing, done
            is_tiebreak INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    # Ensure schema has is_tiebreak column (for draw replays)
    try:
        c.execute("ALTER TABLE tournament_matches ADD COLUMN is_tiebreak INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        # Column likely exists already
        pass
    conn.commit()
    conn.close()

def get_or_create_player(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, rating, wins, losses, draws FROM players WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute(
            "INSERT INTO players(user_id, rating, wins, losses, draws, updated_at) VALUES (?, 1200, 0, 0, 0, ?)",
            (user_id, datetime.datetime.utcnow().isoformat()),
        )
        conn.commit()
        c.execute("SELECT user_id, rating, wins, losses, draws FROM players WHERE user_id=?", (user_id,))
        row = c.fetchone()
    conn.close()
    return row  # (user_id, rating, wins, losses, draws)

def update_player_stats(user_id: int, result: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if result == "win":
        c.execute("UPDATE players SET wins = wins + 1, updated_at=? WHERE user_id=?", (datetime.datetime.utcnow().isoformat(), user_id))
    elif result == "loss":
        c.execute("UPDATE players SET losses = losses + 1, updated_at=? WHERE user_id=?", (datetime.datetime.utcnow().isoformat(), user_id))
    elif result == "draw":
        c.execute("UPDATE players SET draws = draws + 1, updated_at=? WHERE user_id=?", (datetime.datetime.utcnow().isoformat(), user_id))
    conn.commit()
    conn.close()

def expected_score(r_a: float, r_b: float) -> float:
    return 1 / (1 + 10 ** ((r_b - r_a) / 400))

def update_elo(white_id: int, black_id: int, result: str, k: int = 32):
    # result: '1-0' white wins, '0-1' black wins, '1/2-1/2' draw
    w = get_or_create_player(white_id)
    b = get_or_create_player(black_id)
    r_w, r_b = float(w[1]), float(b[1])
    exp_w = expected_score(r_w, r_b)
    exp_b = expected_score(r_b, r_w)
    if result == '1-0':
        s_w, s_b = 1.0, 0.0
        update_player_stats(white_id, "win")
        update_player_stats(black_id, "loss")
    elif result == '0-1':
        s_w, s_b = 0.0, 1.0
        update_player_stats(white_id, "loss")
        update_player_stats(black_id, "win")
    else:
        s_w, s_b = 0.5, 0.5
        update_player_stats(white_id, "draw")
        update_player_stats(black_id, "draw")

    new_r_w = r_w + k * (s_w - exp_w)
    new_r_b = r_b + k * (s_b - exp_b)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute("UPDATE players SET rating=?, updated_at=? WHERE user_id=?", (new_r_w, now, white_id))
    c.execute("UPDATE players SET rating=?, updated_at=? WHERE user_id=?", (new_r_b, now, black_id))
    conn.commit()
    conn.close()

def record_game(white_id: int, black_id: int, result: str, game_board: chess.Board):
    # Export PGN
    game = chess.pgn.Game()
    game.headers["White"] = str(white_id)
    game.headers["Black"] = str(black_id)
    game.headers["Result"] = result
    node = game
    for mv in game_board.move_stack:
        node = node.add_variation(mv)
    pgn_str = str(game)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO games(white_id, black_id, result, pgn, created_at) VALUES (?, ?, ?, ?, ?)",
        (white_id, black_id, result, pgn_str, datetime.datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

@bot.event
async def on_command_error(ctx, error):
    print(f"Error occurred: {error}")

    if isinstance(error, commands.CommandNotFound):
        await ctx.send(
            "Oops! That command doesn't exist. Please use a valid command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "A required argument is missing. Please check the command and try again."
        )
    else:
        await ctx.send(f"An unexpected error occurred: {error}")

board = chess.Board()
mode = None
player_color = None
difficulty = 'normal'  
current_turn = chess.WHITE

difficulty_map = {
    'peaceful': 1,
    'easy': 2,
    'normal': 5,
    'hard': 10,
    'hardcore': 20,
}

def generate_board_image(board, perspective='white'):
    square_size = 35
    board_size = 8 * square_size
    label_margin = 20
    total_size = board_size + 2 * label_margin

    board_image = Image.new("RGBA", (total_size, total_size),
                            (255, 255, 255, 0))
    draw = ImageDraw.Draw(board_image)
    colors = [(255, 255, 255), (128, 128, 128)]  

    for rank in range(8):
        for file in range(8):
            color = colors[(rank + file) % 2]
            draw.rectangle([
                label_margin + file * square_size,
                label_margin + rank * square_size, label_margin +
                (file + 1) * square_size, label_margin +
                (rank + 1) * square_size
            ],
                           fill=color)

    font = ImageFont.load_default()
    text_color = (255, 255, 255) 
    bg_color = (0, 0, 0) 

    for i in range(8):
        rank_label = str(8 - i) if perspective == 'white' else str(i + 1)

        draw.rectangle([
            5, label_margin + i * square_size, label_margin - 5, label_margin +
            (i + 1) * square_size
        ],
                       fill=bg_color)
        draw.rectangle([
            total_size - 15, label_margin + i * square_size, total_size,
            label_margin + (i + 1) * square_size
        ],
                       fill=bg_color)

        # Draw rank labels
        draw.text((5, label_margin + i * square_size + square_size // 4),
                  rank_label,
                  fill=text_color,
                  font=font)
        draw.text((total_size - 15,
                   label_margin + i * square_size + square_size // 4),
                  rank_label,
                  fill=text_color,
                  font=font)
     
        file_label = chr(ord('a') +
                         i) if perspective == 'white' else chr(ord('h') - i)

        draw.rectangle([
            label_margin + i * square_size, 5, label_margin +
            (i + 1) * square_size, label_margin - 5
        ],
                       fill=bg_color)
        draw.rectangle([
            label_margin + i * square_size, total_size - 15, label_margin +
            (i + 1) * square_size, total_size
        ],
                       fill=bg_color)

        draw.text((label_margin + i * square_size + square_size // 4, 5),
                  file_label,
                  fill=text_color,
                  font=font)
        draw.text((label_margin + i * square_size + square_size // 4,
                   total_size - 15),
                  file_label,
                  fill=text_color,
                  font=font)

    piece_images = {
        'P': Image.open("white-pawn.png").resize((35, 35), Image.LANCZOS),
        'R': Image.open("white-rook.png").resize((35, 35), Image.LANCZOS),
        'N': Image.open("white-knight.png").resize((35, 35), Image.LANCZOS),
        'B': Image.open("white-bishop.png").resize((35, 35), Image.LANCZOS),
        'Q': Image.open("white-queen.png").resize((35, 35), Image.LANCZOS),
        'K': Image.open("white-king.png").resize((35, 35), Image.LANCZOS),
        'p': Image.open("black-pawn.png").resize((35, 35), Image.LANCZOS),
        'r': Image.open("black-rook.png").resize((35, 35), Image.LANCZOS),
        'n': Image.open("black-knight.png").resize((35, 35), Image.LANCZOS),
        'b': Image.open("black-bishop.png").resize((35, 35), Image.LANCZOS),
        'q': Image.open("black-queen.png").resize((35, 35), Image.LANCZOS),
        'k': Image.open("black-king.png").resize((35, 35), Image.LANCZOS)
    }

    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            piece_symbol = piece.symbol()
         
            if perspective == 'white':
                pos = (label_margin + file * square_size,
                       label_margin + (7 - rank) * square_size)
            else:
                pos = (label_margin + (7 - file) * square_size,
                       label_margin + rank * square_size)

            board_image.paste(piece_images[piece_symbol], pos,
                              piece_images[piece_symbol])

    board_image.save("chessboard.png")

games = {}
class Leaderboard:
    def __init__(self):
        self.scores = {}

    def update_score(self, player: discord.User, result: str):
        # Keep legacy in-memory stats for now; persistent ratings handled via DB
        if player not in self.scores:
            self.scores[player] = {"wins": 0, "losses": 0, "draws": 0}
        if result == "win":
            self.scores[player]["wins"] += 1
        elif result == "loss":
            self.scores[player]["losses"] += 1
        elif result == "draw":
            self.scores[player]["draws"] += 1

    def display_leaderboard(self, requester_id=None):
        # Show top 10 by rating from DB and append requester's global rank if provided
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, rating, wins, losses, draws FROM players ORDER BY rating DESC LIMIT 10")
        rows = c.fetchall()
        extra = ""
        if requester_id is not None:
            # Fetch requester rating
            c.execute("SELECT rating, wins, losses, draws FROM players WHERE user_id=?", (requester_id,))
            me = c.fetchone()
            if me:
                my_rating = float(me[0])
                # Global rank: 1 + count of players with strictly higher rating
                c.execute("SELECT COUNT(*) FROM players WHERE rating > ?", (my_rating,))
                higher = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM players")
                total = c.fetchone()[0]
                my_rank = higher + 1
                extra = f"\nYour rank: {my_rank}/{total} — {my_rating:.0f} ELO"
        conn.close()
        if not rows:
            return "No scores recorded yet!"
        leaderboard_str = "🏆 ELO Leaderboard 🏆\n"
        for idx, (uid, rating, wins, losses, draws) in enumerate(rows, start=1):
            leaderboard_str += f"{idx}. <@{uid}> — {rating:.0f} ELO | {wins}W-{losses}L-{draws}D\n"
        return leaderboard_str + extra

@bot.command(name='leaderboard',aliases=['lb','l'])
async def show_leaderboard(ctx):
    leaderboard = Leaderboard()
    leaderboard_message = leaderboard.display_leaderboard(ctx.author.id)
    await ctx.send(leaderboard_message)

@bot.command()
async def resign(ctx):
    game = games.pop(ctx.author.id, None)

    if not game:
        await ctx.send("You're not in a game!")
        return

    opponent = bot.get_user(game['opponent'])
    # ELO update only for 1v1 games
    if game.get('mode') == '1v1':
        white_id = game['white']
        black_id = game['black']
        if ctx.author.id == white_id:
            result = '0-1'
        else:
            result = '1-0'
        update_elo(white_id, black_id, result)
        record_game(white_id, black_id, result, game['board'])
    elif game.get('mode') == 'tournament':
        white_id = game['white']
        black_id = game['black']
        if ctx.author.id == white_id:
            result = '0-1'
            winner_id = black_id
        else:
            result = '1-0'
            winner_id = white_id
        update_elo(white_id, black_id, result)
        record_game(white_id, black_id, result, game['board'])
        _complete_tournament_match_and_advance(ctx, game['tournament_id'], game['match_id'], winner_id)
    games.pop(opponent.id, None)

    await ctx.send(
        f"{ctx.author.mention} has resigned. {opponent.mention} wins!")

async def start_solo_game(ctx):
    global player_color, current_turn
    board.reset()
    player_color = chess.WHITE
    current_turn = chess.WHITE

    generate_board_image(board, perspective='white')
    await ctx.send("New chess game started in `Solo` mode! You are `white`.",
                   file=discord.File("chessboard.png"))
    await ctx.send("It's your turn to move! Use `/move <move>` to make a move."
                   )

async def start_ai_game(ctx):
    global player_color, current_turn
    board.reset()
    player_color = random.choice([chess.WHITE, chess.BLACK])
    current_turn = chess.WHITE

    color_text = "white" if player_color == chess.WHITE else "black"
    generate_board_image(board, perspective=color_text)
    await ctx.send(
        f"New chess game started in `AI` mode! You are `{color_text}`.",
        file=discord.File("chessboard.png"))

    await choose_difficulty(ctx)
    if player_color == chess.BLACK:
        await ai_move(ctx)

@bot.command()
async def challenge(ctx, opponent: discord.Member):
    if ctx.author == opponent:
        await ctx.send("You can't challenge yourself!")
        return

    if ctx.author.id in games or opponent.id in games:
        await ctx.send("One of the players is already in a game!")
        return
    # Challenger is white by default
    games[ctx.author.id] = {
        'opponent': opponent.id,
        'board': chess.Board(),
        'turn': ctx.author.id,
        'mode': '1v1',
        'white': ctx.author.id,
        'black': opponent.id
    }
    games[opponent.id] = games[ctx.author.id] 

    challenge_message = await ctx.send(
        f"{ctx.author.mention} has challenged {opponent.mention} to a 1v1 chess match! React with ✅ to accept."
    )

    await challenge_message.add_reaction('✅')

    def check(reaction, user):
        return user == opponent and str(
            reaction.emoji
        ) == '✅' and reaction.message.id == challenge_message.id

    try:
        await bot.wait_for('reaction_add', timeout=10.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send(
            f"{opponent.mention} did not respond in time. Challenge expired.")
        games.pop(ctx.author.id, None)
        games.pop(opponent.id, None)
    else:
        await ctx.send(
            f"{opponent.mention} accepted the challenge! {ctx.author.mention}, it's your turn to move! Use `/move <move>` to make a move."
        )

async def choose_difficulty(ctx):
    global difficulty

    difficulty_view = discord.ui.View()

    for level in difficulty_map.keys():
        button = discord.ui.Button(label=level.capitalize(),
                                   style=discord.ButtonStyle.primary)
        button.custom_id = level
        difficulty_view.add_item(button)

    random_button = discord.ui.Button(label="Random",
                                      style=discord.ButtonStyle.secondary)
    random_button.custom_id = 'random'
    difficulty_view.add_item(random_button)

    async def on_difficulty_button_click(interaction: discord.Interaction):
        global difficulty, current_turn

        button_id = interaction.data[
            'custom_id'] 
        difficulty = button_id if button_id != 'random' else random.choice(
            list(difficulty_map.keys()))
        await interaction.response.send_message(
            f"Difficulty set to `{difficulty}`.", ephemeral=True)

        if mode == 'ai' and player_color == chess.BLACK:
            if current_turn == player_color:
                await ctx.send(
                    f"It's your turn to move! Use `/move <move>` to make a move."
                )
            else:
                await ai_move(ctx)
        else:
            if current_turn == player_color:
                await ctx.send(
                    f"It's your turn to move! Use `/move <move>` to make a move."
                )
            else:
                await ctx.send(f"Waiting for the opponent's move.")

    for item in difficulty_view.children:
        item.callback = on_difficulty_button_click

    await ctx.send("Please choose the AI difficulty level:",
                   view=difficulty_view)

@bot.command(name='move', aliases=['mv','m'])
async def make_move(ctx, move: str):
    global board, mode, current_turn, player_color

    # If user is in an active head-to-head game (1v1 or tournament), prioritize that
    if ctx.author.id in games:
        game = games.get(ctx.author.id)
        if not game:
            await ctx.send("You're not in a game!")
            return

        if game['turn'] != ctx.author.id:
            await ctx.send(
                "It's not your turn yet. Please wait for the other player to move."
            )
            return

        board = game['board']

    elif mode in ('solo', 'ai') and current_turn != player_color:
        await ctx.send(
            "It's not your turn yet. Please wait for the other player to move."
        )
        return
    elif mode not in ('solo', 'ai'):
        # Not in solo/ai and not in games -> no active game
        await ctx.send("You're not in a game. Use `/play` or `/challenge @user`.")
        return

    try:
        move_obj = chess.Move.from_uci(move)
        if move_obj in board.legal_moves:
            board.push(move_obj)

            current_turn = chess.BLACK if current_turn == chess.WHITE else chess.WHITE
            perspective = 'white' if player_color == chess.WHITE else 'black'
            generate_board_image(board, perspective=perspective)

            await ctx.send(f"Move `{move}` accepted.",
                           file=discord.File("chessboard.png"))
            if board.is_checkmate():
                await ctx.send("Checkmate! Game over.")
                if mode == '1v1':
                    # Determine result: after push, side to move is checkmated
                    white_id = game['white']
                    black_id = game['black']
                    loser_is_white = (current_turn == chess.WHITE)
                    result = '0-1' if loser_is_white else '1-0'
                    update_elo(white_id, black_id, result)
                    record_game(white_id, black_id, result, board)
                    game = games.pop(ctx.author.id, None)
                    if game:
                        opponent = bot.get_user(game['opponent'])
                        games.pop(opponent.id, None)
                elif mode == 'tournament':
                    white_id = game['white']
                    black_id = game['black']
                    loser_is_white = (current_turn == chess.WHITE)
                    result = '0-1' if loser_is_white else '1-0'
                    winner_id = black_id if loser_is_white else white_id
                    update_elo(white_id, black_id, result)
                    record_game(white_id, black_id, result, board)
                    _complete_tournament_match_and_advance(ctx, game['tournament_id'], game['match_id'], winner_id)
                    game = games.pop(ctx.author.id, None)
                    if game:
                        opponent = bot.get_user(game['opponent'])
                        games.pop(opponent.id, None)
                return
            elif board.is_stalemate() or board.is_insufficient_material(
            ) or board.is_seventyfive_moves() or board.is_fivefold_repetition(
            ):
                await ctx.send(
                    "Draw! The game is a stalemate or ended due to insufficient material."
                )
                if mode == '1v1':
                    white_id = game['white']
                    black_id = game['black']
                    update_elo(white_id, black_id, '1/2-1/2')
                    record_game(white_id, black_id, '1/2-1/2', board)
                    game = games.pop(ctx.author.id, None)
                    if game:
                        opponent = bot.get_user(game['opponent'])
                        games.pop(opponent.id, None)
                elif mode == 'tournament':
                    white_id = game['white']
                    black_id = game['black']
                    update_elo(white_id, black_id, '1/2-1/2')
                    record_game(white_id, black_id, '1/2-1/2', board)
                    # Check if this match was already a tiebreak
                    info = _get_match_info(game['match_id'])
                    t_id = game['tournament_id']
                    if info and not info['is_tiebreak']:
                        # Mark current match done (draw) and start a tiebreak with swapped colors
                        conn_tb = sqlite3.connect(DB_PATH)
                        c_tb = conn_tb.cursor()
                        c_tb.execute("UPDATE tournament_matches SET status='done' WHERE id=?", (game['match_id'],))
                        conn_tb.commit()
                        conn_tb.close()
                        await ctx.send("Starting a tiebreak game with swapped colors due to draw.")
                        _create_tiebreak_match_and_start(ctx, t_id, info['round'], black_id, white_id)
                    else:
                        # Tiebreak also drawn -> randomly advance
                        winner_id = random.choice([white_id, black_id])
                        await ctx.send(f"Tiebreak draw resolved randomly: <@{winner_id}> advances.")
                        _complete_tournament_match_and_advance(ctx, t_id, game['match_id'], winner_id)
                    # Clear active game states for both players
                    game = games.pop(ctx.author.id, None)
                    if game:
                        opponent = bot.get_user(game['opponent'])
                        games.pop(opponent.id, None)
                return

            if mode == 'ai' and current_turn != player_color and not board.is_game_over(
            ):
                await ai_move(ctx)
            elif mode == '1v1' or mode == 'tournament':
                opponent_id = game['opponent']
                games[opponent_id]['board'] = board
                games[opponent_id]['turn'] = current_turn
                games[ctx.author.id] = games[opponent_id]

                opponent = bot.get_user(opponent_id)
                await ctx.send(
                    f"Move `{move}` accepted. It's now {opponent.mention}'s turn."
                )

        else:
            await ctx.send("Invalid move. The move is not legal. Try again.")
    except ValueError:
        await ctx.send("Invalid move format. Use UCI format like `e2e4`.")

@bot.command(name='ai', aliases=['a'])
async def ai_move(ctx):
    global board, current_turn, player_color

    if board.is_game_over():
        await ctx.send("Game over!")
        return
    try:

        stockfish.set_fen_position(board.fen())
        best_move = stockfish.get_best_move()
        board.push_uci(best_move)
        current_turn = chess.BLACK if current_turn == chess.WHITE else chess.WHITE
        perspective = 'white' if player_color == chess.WHITE else 'black'
        generate_board_image(board, perspective=perspective)
        await ctx.send(f"Stockfish plays `{best_move}`.",
                       file=discord.File("chessboard.png"))

        if board.is_game_over():
            await ctx.send("Game over!")
        else:
            if current_turn == player_color:
                await ctx.send(
                    f"It's your turn to move! Use `/move <move>` to make a move."
                )
            else:
                # If it's still the AI's turn, recursively call ai_move
                await ai_move(ctx)
    except Exception as e:
        await ctx.send(f"Error with AI move: {e}")

# Command to provide a hint for the next move
@bot.command(name='hint', aliases=['h'])
async def provide_hint(ctx):
    global board
    if board.is_game_over():
        await ctx.send("Game over!")
        return
    try:
        stockfish.set_fen_position(board.fen())
        hint_move = stockfish.get_best_move()
        await ctx.send(f"Hint: The best move is `{hint_move}`.")
    except Exception as e:
        await ctx.send(f"Error with hint: {e}")

###########################
# Tournament Functionality #
###########################

def _get_tournament_players(t_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM tournament_players WHERE tournament_id=?", (t_id,))
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows

def _create_matches_for_round(t_id: int, round_no: int, players: list[int]):
    pairs = []
    shuffled = players[:]
    random.shuffle(shuffled)
    # If odd, give last a bye (auto-advance)
    bye = None
    if len(shuffled) % 2 == 1:
        bye = shuffled.pop()
    for i in range(0, len(shuffled), 2):
        pairs.append((shuffled[i], shuffled[i+1]))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for w, b in pairs:
        c.execute("INSERT INTO tournament_matches(tournament_id, round, white_id, black_id, winner_id, status) VALUES (?, ?, ?, ?, NULL, 'pending')",
                  (t_id, round_no, w, b))
    if bye is not None:
        # Create a dummy match with bye winner
        c.execute("INSERT INTO tournament_matches(tournament_id, round, white_id, black_id, winner_id, status) VALUES (?, ?, ?, ?, ?, 'done')",
                  (t_id, round_no, bye, None, bye))
    conn.commit()
    conn.close()

def _all_round_done(t_id: int, round_no: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM tournament_matches WHERE tournament_id=? AND round=? AND status!='done'", (t_id, round_no))
    remaining = c.fetchone()[0]
    conn.close()
    return remaining == 0

def _get_current_round(t_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT MAX(round) FROM tournament_matches WHERE tournament_id=?", (t_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else 0

def _winners_of_round(t_id: int, round_no: int) -> list[int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT winner_id FROM tournament_matches WHERE tournament_id=? AND round=? AND winner_id IS NOT NULL", (t_id, round_no))
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows

def _start_pending_matches_in_round(ctx, t_id: int, round_no: int):

    # Start all pending matches sequentially (players play matches when they use /move; we set up games state)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, white_id, black_id FROM tournament_matches WHERE tournament_id=? AND round=? AND status='pending'", (t_id, round_no))
    matches = c.fetchall()
    # Mark as ongoing
    for mid, w, b in matches:
        c.execute("UPDATE tournament_matches SET status='ongoing' WHERE id=?", (mid,))
        # Set up a game for both players
        local_board = chess.Board()
        games[w] = {'opponent': b, 'board': local_board, 'turn': w, 'mode': 'tournament', 'white': w, 'black': b, 'tournament_id': t_id, 'match_id': mid}
        games[b] = games[w]
    conn.commit()
    conn.close()
    if matches:
        lines = [f"Starting Round {round_no} matches:"]
        for mid, w, b in matches:
            lines.append(f"Match #{mid}: <@{w}> (White) vs <@{b}> (Black) — White to move. Use /move <uci>")
        asyncio.create_task(ctx.send("\n".join(lines)))

def _get_match_info(match_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT round, white_id, black_id, is_tiebreak, tournament_id FROM tournament_matches WHERE id=?", (match_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        'round': row[0],
        'white': row[1],
        'black': row[2],
        'is_tiebreak': int(row[3]) if row[3] is not None else 0,
        'tournament_id': row[4]
    }

def _create_tiebreak_match_and_start(ctx, t_id: int, round_no: int, white_id: int, black_id: int):
    # Create tiebreak match with immediate start (status ongoing) and set up games
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO tournament_matches(tournament_id, round, white_id, black_id, winner_id, status, is_tiebreak) VALUES (?, ?, ?, ?, NULL, 'ongoing', 1)",
        (t_id, round_no, white_id, black_id)
    )
    match_id = c.lastrowid
    conn.commit()
    conn.close()
    local_board = chess.Board()
    games[white_id] = {
        'opponent': black_id,
        'board': local_board,
        'turn': white_id,
        'mode': 'tournament',
        'white': white_id,
        'black': black_id,
        'tournament_id': t_id,
        'match_id': match_id
    }
    games[black_id] = games[white_id]
    asyncio.create_task(ctx.send(f"Tiebreak started: Match #{match_id} (TB) — <@{white_id}> (White) vs <@{black_id}> (Black). White to move."))

def _complete_tournament_match_and_advance(ctx, t_id: int, match_id: int, winner_id: int):
    # Mark match done and set winner
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE tournament_matches SET winner_id=?, status='done' WHERE id=?", (winner_id, match_id))
    conn.commit()
    # Determine current round
    c.execute("SELECT round FROM tournament_matches WHERE id=?", (match_id,))
    row = c.fetchone()
    round_no = row[0] if row else 1
    conn.close()
    # If all matches in round done, create next round or finish
    if _all_round_done(t_id, round_no):
        winners = _winners_of_round(t_id, round_no)
        if len(winners) <= 1:
            # Tournament finished
            asyncio.create_task(ctx.send(f"🏆 Tournament #{t_id} winner: <@{winners[0]}>!"))
            conn2 = sqlite3.connect(DB_PATH)
            c2 = conn2.cursor()
            c2.execute("UPDATE tournaments SET status='finished' WHERE id=?", (t_id,))
            conn2.commit()
            conn2.close()
        else:
            next_round = round_no + 1
            _create_matches_for_round(t_id, next_round, winners)
            asyncio.create_task(ctx.send(f"All matches in Round {round_no} completed. Creating Round {next_round}..."))
            _start_pending_matches_in_round(ctx, t_id, next_round)

def _bracket_text(t_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT round, id, white_id, black_id, winner_id, status, is_tiebreak FROM tournament_matches WHERE tournament_id=? ORDER BY round, id", (t_id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return "No matches yet."
    out = []
    cur_round = None
    for rnd, mid, w, b, win, st, tb in rows:
        if rnd != cur_round:
            cur_round = rnd
            out.append(f"Round {rnd}:")
        tag = " (TB)" if tb else ""
        vs = f"<@{w}> vs <@{b}>{tag}" if b is not None else f"<@{w}> gets a bye"
        if st == 'done':
            line = f"  Match #{mid}: {vs} — Winner: <@{win}>"
        else:
            line = f"  Match #{mid}: {vs} — {st.title()}"
        out.append(line)
    return "\n".join(out)

@bot.command(name='tournament_create')
async def tournament_create(ctx, *, name: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO tournaments(guild_id, name, status, created_at) VALUES (?, ?, 'created', ?)", (ctx.guild.id if ctx.guild else 0, name, datetime.datetime.utcnow().isoformat()))
    t_id = c.lastrowid
    conn.commit()
    conn.close()
    await ctx.send(f"Tournament created: #{t_id} — {name}. Players can join with `/tournament_join {t_id}`")

@bot.command(name='tournament_join')
async def tournament_join(ctx, tournament_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Ensure tournament exists and not started
    c.execute("SELECT status FROM tournaments WHERE id=?", (tournament_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        await ctx.send("Tournament not found.")
        return
    if row[0] != 'created':
        conn.close()
        await ctx.send("Tournament already started or finished.")
        return
    # Add player if not already added
    c.execute("SELECT 1 FROM tournament_players WHERE tournament_id=? AND user_id=?", (tournament_id, ctx.author.id))
    exists = c.fetchone()
    if not exists:
        c.execute("INSERT INTO tournament_players(tournament_id, user_id) VALUES (?, ?)", (tournament_id, ctx.author.id))
        conn.commit()
        await ctx.send(f"You have joined tournament #{tournament_id}.")
    else:
        await ctx.send("You are already registered in this tournament.")
    conn.close()

@bot.command(name='tournament_start')
async def tournament_start(ctx, tournament_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status FROM tournaments WHERE id=?", (tournament_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        await ctx.send("Tournament not found.")
        return
    if row[0] != 'created':
        conn.close()
        await ctx.send("Tournament already started or finished.")
        return
    # Get players (need at least 2)
    c.execute("SELECT user_id FROM tournament_players WHERE tournament_id=?", (tournament_id,))
    players = [r[0] for r in c.fetchall()]
    if len(players) < 2:
        conn.close()
        await ctx.send("Need at least 2 players to start.")
        return
    # Create round 1 matches
    _create_matches_for_round(tournament_id, 1, players)
    c.execute("UPDATE tournaments SET status='ongoing' WHERE id=?", (tournament_id,))
    conn.commit()
    conn.close()
    await ctx.send(f"Tournament #{tournament_id} started. Generating Round 1 matches...")
    _start_pending_matches_in_round(ctx, tournament_id, 1)

@bot.command(name='tournament_bracket')
async def tournament_bracket(ctx, tournament_id: int):
    txt = _bracket_text(tournament_id)
    await ctx.send(f"Bracket for Tournament #{tournament_id}:\n{txt}")

# Command to exit the game
@bot.command(name='exit', aliases=['quit', 'q'])
async def exit_game(ctx):
    # Check if the user is in a game and clear the game state
    if ctx.author.id in games:
        opponent_id = games[ctx.author.id]['opponent']
        games.pop(ctx.author.id, None)
        games.pop(opponent_id, None)

        await ctx.send("Game has been exited. All game state has been cleared."
                       )
    else:
        await ctx.send("You are not in a game.")

    # Provide options to restart or choose a new game
    restart_view = discord.ui.View()
    restart_button = discord.ui.Button(label="Start a New Game",
                                       style=discord.ButtonStyle.primary,
                                       custom_id="start_new_game")
    restart_view.add_item(restart_button)

    async def on_restart_button_click(interaction: discord.Interaction):
        await start_interaction(ctx)
        await interaction.response.send_message("Starting a new game...",
                                                ephemeral=True)

    restart_button.callback = on_restart_button_click
    await ctx.send("You can start a new game using the button below:",
                   view=restart_view)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    # Initialize persistence
    init_db()
bot.run(TOKEN)
