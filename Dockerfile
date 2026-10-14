FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg p7zip-full libarchive-tools ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p DOWNLOADS

EXPOSE 7860

# if the bot process dies the container stops (so the host restarts it)
CMD ["sh", "-c", "python app.py & exec python bot.py"]
