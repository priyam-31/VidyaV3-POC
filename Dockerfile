FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    python3-dev \
    ffmpeg \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir google-generativeai
COPY . .

CMD ["streamlit", "run", "app.py", "--server.port=10000", "--server.address=0.0.0.0"]