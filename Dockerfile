FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    jinja2 \
    python-multipart \
    langchain \
    langchain-openai \
    python-dotenv \
    redis \
    chromadb

EXPOSE 8000

CMD ["uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000"]