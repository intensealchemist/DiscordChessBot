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
