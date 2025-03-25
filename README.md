# Discord Chess Bot

![Python](https://img.shields.io/badge/Python-99.8%25-blue)
![Shell](https://img.shields.io/badge/Shell-0.2%25-blue)

A Discord bot that allows users to play chess directly in Discord channels. This bot is written in Python and utilizes the Discord API.

## Features

- Play chess games with other users Or With Bots in Discord.
- Supports standard chess rules and moves.
- Command-based interaction within Discord channels.
- Real-time updates of the chess board.
- Save and load games.

## Installation

To get the bot up and running, follow these steps:

1. Clone the repository:
    ```bash
    git clone https://github.com/intensealchemist/DiscordChessBot.git
    cd DiscordChessBot
    ```

2. Create a virtual environment and activate it:
    ```bash
    python3 -m venv env
    source env/bin/activate  # On Windows use `env\Scripts\activate`
    ```

3. Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

4. Set up your Discord bot:
    - Create a new bot on the [Discord Developer Portal](https://discord.com/developers/applications).
    - Copy the bot token.
    - Create a `.env` file in the project root and add your bot token:
        ```env
        DISCORD_TOKEN=your-bot-token-here
        ```

5. Run the bot:
    ```bash
    python bot.py
    ```

## Usage

Once the bot is running, you can invite it to your Discord server and use the following commands:

- `!startgame @user`: Start a new chess game with another user.
- `!move e2 e4`: Make a move in the current game.
- `!board`: Display the current board state.
- `!savegame`: Save the current game.
- `!loadgame`: Load a previously saved game.
- `!endgame`: End the current game.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request if you have any improvements or bug fixes.

1. Fork the repository.
2. Create a new branch (`git checkout -b feature/my-feature`).
3. Commit your changes (`git commit -m 'Add my feature'`).
4. Push to the branch (`git push origin feature/my-feature`).
5. Open a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Python Chess Library](https://python-chess.readthedocs.io/en/latest/): Used for handling chess game logic.
- [Discord.py](https://discordpy.readthedocs.io/en/stable/): Used for interacting with the Discord API.
