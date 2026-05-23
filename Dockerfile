FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    OPENAI_API_KEY=sk-RmbHvJkkj6UK08Ah5wexMiINiLmJSKzc5OaDEiMjweepG3Ri \
    OPENAI_BASE_URL=https://api.silra.cn/v1 \
    MODEL=deepseek-chat \
    DEBATE_ROUNDS=3

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY prompts.py server.py ./
COPY static ./static

EXPOSE 8080

# Zeabur 会注入 PORT；未注入时默认 8080
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
