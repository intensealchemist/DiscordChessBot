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
 
# Initialize bot with command prefix and intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or("/", "!", "."),
                   intents=intents)

# Load environment variable for bot token
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

stockfish = Stockfish("/usr/games/stockfish")


@bot.event
async def on_command_error(ctx, error):
    # Log the error for debugging purposes
    print(f"Error occurred: {error}")

    # Handle specific errors
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(
            "Oops! That command doesn't exist. Please use a valid command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "A required argument is missing. Please check the command and try again."
        )
    else:
        await ctx.send(f"An unexpected error occurred: {error}")


# Global variables to track game state
board = chess.Board()
mode = None
player_color = None
difficulty = 'normal'  # Default difficulty
current_turn = chess.WHITE

# Mapping difficulty levels to Stockfish options
difficulty_map = {
    'peaceful': 1,
    'easy': 2,
    'normal': 5,
    'hard': 10,
    'hardcore': 20,
}

# Function to generate and save the board image with move history
def generate_board_image(board, perspective='white'):
    # Constants
    square_size = 35
    board_size = 8 * square_size
    label_margin = 20
    total_size = board_size + 2 * label_margin

    # Create a blank chessboard image with extra space for labels
    board_image = Image.new("RGBA", (total_size, total_size),
                            (255, 255, 255, 0))
    draw = ImageDraw.Draw(board_image)
    colors = [(255, 255, 255), (128, 128, 128)]  # white, gray

    # Draw the chessboard squares
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

    # Draw rank (numbers) and file (letters) labels with background
    font = ImageFont.load_default()
    text_color = (255, 255, 255)  # white text
    bg_color = (0, 0, 0)  # black background

    for i in range(8):
        # Rank numbers (left and right)
        rank_label = str(8 - i) if perspective == 'white' else str(i + 1)

        # Draw background for rank labels
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

        # File letters (top and bottom)
        file_label = chr(ord('a') +
                         i) if perspective == 'white' else chr(ord('h') - i)

        # Draw background for file labels
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

        # Draw file labels
        draw.text((label_margin + i * square_size + square_size // 4, 5),
                  file_label,
                  fill=text_color,
                  font=font)
        draw.text((label_margin + i * square_size + square_size // 4,
                   total_size - 15),
                  file_label,
                  fill=text_color,
                  font=font)

    # Load and resize piece images
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

    # Paste pieces on the board according to the perspective
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            piece_symbol = piece.symbol()

            # Calculate the correct position for the piece
            if perspective == 'white':
                pos = (label_margin + file * square_size,
                       label_margin + (7 - rank) * square_size)
            else:  # If perspective is black, reverse the position
                pos = (label_margin + (7 - file) * square_size,
                       label_margin + rank * square_size)

            board_image.paste(piece_images[piece_symbol], pos,
                              piece_images[piece_symbol])

    # Save the image
    board_image.save("chessboard.png")


# A dictionary to hold the game state for each pair of players
games = {}
class Leaderboard:
    def __init__(self):
        self.scores = {}

    def update_score(self, player: discord.User, result: str):
        if player not in self.scores:
            self.scores[player] = {"wins": 0, "losses": 0, "draws": 0}
        if result == "win":
            self.scores[player]["wins"] += 1
        elif result == "loss":
            self.scores[player]["losses"] += 1
        elif result == "draw":
            self.scores[player]["draws"] += 1

    def display_leaderboard(self):
        sorted_scores = sorted(self.scores.items(), key=lambda item: item[1]["wins"], reverse=True)
        leaderboard_str = "🏆 **Leaderboard** 🏆\n"
        for player, stats in sorted_scores:
            leaderboard_str += f"{player.mention}: {stats['wins']} Wins, {stats['losses']} Losses, {stats['draws']} Draws\n"
        return leaderboard_str

# Create an instance of the Leaderboard class
leaderboard = Leaderboard()

# Command to display the leaderboard
@bot.command(name='leaderboard',aliases=['lb','l'])
async def show_leaderboard(ctx):
    leaderboard_message = leaderboard.display_leaderboard()
    if leaderboard_message:
        await ctx.send(leaderboard_message)
    else:
        await ctx.send("No scores recorded yet!")

# Example of updating the leaderboard when a game concludes
@bot.command(name='endgame')
async def end_game(ctx, result: str):
    # Example: assuming the command is used like !endgame win
    leaderboard.update_score(ctx.author, result)
    await ctx.send(f"{ctx.author.mention}'s score has been updated with a {result}!")


# Check for win condition, etc.
@bot.command()
async def resign(ctx):
    game = games.pop(ctx.author.id, None)

    if not game:
        await ctx.send("You're not in a game!")
        return

    opponent = bot.get_user(game['opponent'])
    games.pop(opponent.id, None)

    await ctx.send(
        f"{ctx.author.mention} has resigned. {opponent.mention} wins!")

# Command to start the interaction by choosing the game mode
@bot.command(name='play', aliases=['start', 'p'])
async def start_interaction(ctx):
    # Create a view for the mode selection buttons
    mode_view = discord.ui.View()

    solo_button = discord.ui.Button(label="Solo",
                                    style=discord.ButtonStyle.primary)
    ai_button = discord.ui.Button(label="AI",
                                  style=discord.ButtonStyle.primary)
    pvp_button = discord.ui.Button(label="1v1",
                                   style=discord.ButtonStyle.primary)
    mode_view.add_item(solo_button)
    mode_view.add_item(ai_button)
    mode_view.add_item(pvp_button)

    async def on_mode_button_click(interaction: discord.Interaction):
        global mode, player_color, current_turn

        button_id = interaction.data['custom_id']
        if button_id == 'Solo':
            mode = 'solo'
            await start_solo_game(ctx)
        elif button_id == 'AI':
            mode = 'ai'
            await start_ai_game(ctx)
        elif button_id == '1v1':
            mode = '1v1'
            await ctx.send(
                f"{ctx.author.mention} has selected 1v1 mode! Use `/challenge @opponent` to challenge another player."
            )

    solo_button.custom_id = 'Solo'
    ai_button.custom_id = 'AI'
    pvp_button.custom_id = '1v1'
    solo_button.callback = on_mode_button_click
    ai_button.callback = on_mode_button_click
    pvp_button.callback = on_mode_button_click

    await ctx.send("Choose a game mode:", view=mode_view)


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

    # Initialize game state for the two players
    games[ctx.author.id] = {
        'opponent': opponent.id,
        'board': chess.Board(),
        'turn': ctx.author.id
    }
    games[opponent.id] = games[ctx.author.id]  # Point to the same game state

    challenge_message = await ctx.send(
        f"{ctx.author.mention} has challenged {opponent.mention} to a 1v1 chess match! React with ✅ to accept."
    )

    # Add reaction for acceptance
    await challenge_message.add_reaction('✅')

    def check(reaction, user):
        return user == opponent and str(
            reaction.emoji
        ) == '✅' and reaction.message.id == challenge_message.id

    try:
        # Wait for the opponent's reaction for 10 seconds
        await bot.wait_for('reaction_add', timeout=10.0, check=check)
    except asyncio.TimeoutError:
        # If time expires without reaction
        await ctx.send(
            f"{opponent.mention} did not respond in time. Challenge expired.")
        games.pop(ctx.author.id, None)
        games.pop(opponent.id, None)
    else:
        # If opponent accepted
        await ctx.send(
            f"{opponent.mention} accepted the challenge! {ctx.author.mention}, it's your turn to move! Use `/move <move>` to make a move."
        )


# Command to show a guide for using the bot
@bot.command(name='guide')
async def show_guide(ctx):
    guide_text = ("Here are the available commands:\n"
                  "`/mode <solo|ai>` - Select the game mode.\n"
                  "`/start` - Start a new chess game.\n"
                  "`/move <e2e4>` - Make a move using UCI format.\n"
                  "`/ai` - Let AI make a move (only in AI mode).\n"
                  "`/hint` - Get a hint for the next best move.\n"
                  "`/exit` - Exit the game.\n"
                  "`/challenge` - challenge another player for a 1v1 game.\n")
    await ctx.send(guide_text)


# Function to handle difficulty selection and start the AI game
async def choose_difficulty(ctx):
    global difficulty

    # Create a view for the difficulty buttons
    difficulty_view = discord.ui.View()

    # Add buttons for each difficulty level
    for level in difficulty_map.keys():
        button = discord.ui.Button(label=level.capitalize(),
                                   style=discord.ButtonStyle.primary)
        button.custom_id = level
        difficulty_view.add_item(button)

    # Add a random difficulty button
    random_button = discord.ui.Button(label="Random",
                                      style=discord.ButtonStyle.secondary)
    random_button.custom_id = 'random'
    difficulty_view.add_item(random_button)

    async def on_difficulty_button_click(interaction: discord.Interaction):
        global difficulty, current_turn

        button_id = interaction.data[
            'custom_id']  # Access the custom_id from the interaction data
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


# Command to make a move
@bot.command(name='move', aliases=['mv','m'])
async def make_move(ctx, move: str):
    global board, mode, current_turn, player_color

    if mode is None:
        await ctx.send("Please select a mode using `/play`.")
        return

    # Check if it's the player's turn in duo/1v1 mode
    if mode == 'duo':
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

    # Regular single-player or AI mode
    elif current_turn != player_color:
        await ctx.send(
            "It's not your turn yet. Please wait for the other player to move."
        )
        return

    try:
        move_obj = chess.Move.from_uci(move)
        if move_obj in board.legal_moves:
            board.push(move_obj)

            # Switch turns and update the perspective
            current_turn = chess.BLACK if current_turn == chess.WHITE else chess.WHITE
            perspective = 'white' if player_color == chess.WHITE else 'black'
            generate_board_image(board, perspective=perspective)

            await ctx.send(f"Move `{move}` accepted.",
                           file=discord.File("chessboard.png"))

            # Check if the game is over (checkmate, stalemate, etc.)
            if board.is_checkmate():
                await ctx.send("Checkmate! Game over.")
                if mode == 'duo':
                    # End the game in duo mode
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
                if mode == 'duo':
                    # End the game in duo mode
                    game = games.pop(ctx.author.id, None)
                    if game:
                        opponent = bot.get_user(game['opponent'])
                        games.pop(opponent.id, None)
                return

            # Handle AI move in AI mode
            if mode == 'ai' and current_turn != player_color and not board.is_game_over(
            ):
                await ai_move(ctx)
            elif mode == 'duo':
                # Update the game state for both players in duo/1v1 mode
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


# Command to let AI make a move
@bot.command(name='ai', aliases=['a'])
async def ai_move(ctx):
    global board, current_turn, player_color

    if board.is_game_over():
        await ctx.send("Game over!")
        return
    try:
        # Set the current position on the board for Stockfish
        stockfish.set_fen_position(board.fen())

        # Get the best move from Stockfish
        best_move = stockfish.get_best_move()
        board.push_uci(best_move)

        # Switch turns and update the perspective based on the player's color
        current_turn = chess.BLACK if current_turn == chess.WHITE else chess.WHITE
        perspective = 'white' if player_color == chess.WHITE else 'black'
        generate_board_image(board, perspective=perspective)

        # Send the move and updated board image
        await ctx.send(f"Stockfish plays `{best_move}`.",
                       file=discord.File("chessboard.png"))

        # Check if the game is over after the AI's move
        if board.is_game_over():
            await ctx.send("Game over!")
        else:
            # If it's the player's turn, prompt them to make a move
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
        await start_interaction(ctx)  # Reuse the function to start a new game
        await interaction.response.send_message("Starting a new game...",
                                                ephemeral=True)

    restart_button.callback = on_restart_button_click
    await ctx.send("You can start a new game using the button below:",
                   view=restart_view)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
bot.run(TOKEN)
