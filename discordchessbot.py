import os
import discord
from discord.ext import commands
import chess
import chess.svg
import chess.engine
from PIL import Image, ImageDraw, ImageFont
from cairosvg import svg2png
import random

# Initialize bot with command prefix and intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or("/", "!", "."), intents=intents)

# Load environment variable for bot token
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

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
def generate_board_image():
    if mode == 'ai' and player_color is not None:
        board_svg = chess.svg.board(board=board, size=350, orientation=player_color)
    else:
        board_svg = chess.svg.board(board=board, size=350)

    svg2png(bytestring=board_svg.encode('utf-8'), write_to='chessboard.png')
    image = Image.open("chessboard.png")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    moves = list(board.move_stack)
    move_text = "\n".join([f"{i+1}. {str(m)}" for i, m in enumerate(moves)])
    draw.text((10, 360), move_text, font=font, fill="black")
    image.save("chessboard.png")

# Command to start the interaction by choosing the game mode
@bot.command(name='play')
async def start_interaction(ctx):
    # Create a view for the mode selection buttons
    mode_view = discord.ui.View()

    solo_button = discord.ui.Button(label="1v1/Solo", style=discord.ButtonStyle.primary)
    ai_button = discord.ui.Button(label="AI", style=discord.ButtonStyle.primary)
    mode_view.add_item(solo_button)
    mode_view.add_item(ai_button)

    async def on_mode_button_click(interaction: discord.Interaction):
        global mode, player_color, current_turn
        
        button_id = interaction.data['custom_id']  # Access the custom_id from the interaction data
        mode = 'solo' if button_id == '1v1/Solo' else 'ai'
        
        # Reset the board and assign a random color to the player
        board.reset()
        player_color = chess.WHITE if mode == 'solo' else random.choice([chess.WHITE, chess.BLACK])
        current_turn = chess.WHITE
        color_text = "white" if player_color == chess.WHITE else "black"
        
        # Generate and send the board image
        generate_board_image()
        await interaction.response.send_message(f"New chess game started in `{mode}` mode! You are `{color_text}`.", file=discord.File("chessboard.png"))

        if mode == 'ai':
            # Directly ask for difficulty if AI mode is selected
            await choose_difficulty(ctx)
        else:
            await ctx.send(f"It's your turn to move! Use `/move <move>` to make a move.")

    solo_button.custom_id = '1v1/Solo'
    ai_button.custom_id = 'AI'
    solo_button.callback = on_mode_button_click
    ai_button.callback = on_mode_button_click

    await ctx.send("Choose a game mode:", view=mode_view)

# Command to show a guide for using the bot
@bot.command(name='guide')
async def show_guide(ctx):
    guide_text = (
        "Here are the available commands:\n"
        "`/mode <solo|ai>` - Select the game mode.\n"
        "`/start` - Start a new chess game.\n"
        "`/move <e2e4>` - Make a move using UCI format.\n"
        "`/ai` - Let AI make a move (only in AI mode).\n"
        "`/hint` - Get a hint for the next best move.\n"
        "`/exit` - Exit the game.\n"
    )
    await ctx.send(guide_text)
    
# Function to handle difficulty selection and start the AI game
async def choose_difficulty(ctx):
    global difficulty

    # Create a view for the difficulty buttons
    difficulty_view = discord.ui.View()

    # Add buttons for each difficulty level
    for level in difficulty_map.keys():
        button = discord.ui.Button(label=level.capitalize(), style=discord.ButtonStyle.primary)
        button.custom_id = level
        difficulty_view.add_item(button)

    # Add a random difficulty button
    random_button = discord.ui.Button(label="Random", style=discord.ButtonStyle.secondary)
    random_button.custom_id = 'random'
    difficulty_view.add_item(random_button)

    async def on_difficulty_button_click(interaction: discord.Interaction):
        global difficulty, current_turn

        button_id = interaction.data['custom_id']  # Access the custom_id from the interaction data
        difficulty = button_id if button_id != 'random' else random.choice(list(difficulty_map.keys()))
        await interaction.response.send_message(f"Difficulty set to `{difficulty}`.", ephemeral=True)

        if mode == 'ai' and player_color == chess.BLACK:
            if current_turn == player_color:
                await ctx.send(f"It's your turn to move! Use `/move <move>` to make a move.")
            else:
                await ai_move(ctx)
        else:
            if current_turn == player_color:
                await ctx.send(f"It's your turn to move! Use `/move <move>` to make a move.")
            else:
                await ctx.send(f"Waiting for the opponent's move.")

    for item in difficulty_view.children:
        item.callback = on_difficulty_button_click

    await ctx.send("Please choose the AI difficulty level:", view=difficulty_view)

# Command to make a move
@bot.command(name='move', aliases=['mv'])
async def make_move(ctx, move: str):
    global board, mode, current_turn, player_color
    if mode is None:
        await ctx.send("Please select a mode using `/play`.")
        return
    
    if current_turn != (player_color if mode == 'ai' else chess.WHITE):
        await ctx.send("It's not your turn yet. Please wait for the other player to move.")
        return

    try:
        move_obj = chess.Move.from_uci(move)
        if move_obj in board.legal_moves:
            board.push(move_obj)
            generate_board_image()
            await ctx.send(f"Move `{move}` accepted.", file=discord.File("chessboard.png"))
            current_turn = chess.BLACK if current_turn == chess.WHITE else chess.WHITE
            if mode == 'ai' and current_turn == chess.BLACK and not board.is_game_over():
                await ai_move(ctx)
            else:
                await ctx.send(f"It's your turn to move! Use `/move <move>` to make a move.")

        else:
            await ctx.send("Invalid move. The move is not legal. Try again.")
    except ValueError:
        await ctx.send("Invalid move format. Use UCI format like `e2e4`.")

# Command to let AI make a move
@bot.command(name='ai', aliases=['a'])
async def ai_move(ctx):
    global board, current_turn
    if board.is_game_over():
        await ctx.send("Game over!")
        return
    try:
        engine = chess.engine.SimpleEngine.popen_uci("/usr/games/stockfish")
    except FileNotFoundError:
        await ctx.send("Stockfish engine not found. Please install it using `sudo apt-get install stockfish`.")
        return

    try:
        result = engine.play(board, chess.engine.Limit(time=difficulty_map[difficulty]))
        board.push(result.move)
        generate_board_image()
        await ctx.send(f"Stockfish plays `{result.move}`.", file=discord.File("chessboard.png"))
        current_turn = chess.WHITE
    except Exception as e:
        await ctx.send(f"Error with AI move: {e}")
    finally:
        engine.quit()

# Command to provide a hint for the next move
@bot.command(name='hint', aliases=['h'])
async def provide_hint(ctx):
    global board
    if board.is_game_over():
        await ctx.send("Game over!")
        return
    try:
        engine = chess.engine.SimpleEngine.popen_uci("/usr/games/stockfish")
    except FileNotFoundError:
        await ctx.send("Stockfish engine not found. Please install it using `sudo apt-get install stockfish`.")
        return

    try:
        result = engine.play(board, chess.engine.Limit(time=difficulty_map[difficulty]))
        hint_move = result.move
        await ctx.send(f"Hint: The best move is `{hint_move}`.")
    except Exception as e:
        await ctx.send(f"Error with hint: {e}")
    finally:
        engine.quit()

# Command to exit the game
@bot.command(name='exit', aliases=['quit', 'q'])
async def exit_game(ctx):
    await ctx.send("Exiting the game. Bye!")
    await bot.logout()

# Run the bot
if TOKEN is None:
    print("Error: DISCORD_BOT_TOKEN environment variable not set.")
else:
    bot.run(TOKEN)
