FROM python:3.13.7-slim-trixie
RUN apt-get update && apt-get install git ffmpeg -y
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY main.py pyproject.toml uv.lock ./
RUN uv sync
CMD ["uv","run","python","main.py"]