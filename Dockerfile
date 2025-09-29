#FROM python:3.13.7-slim-trixie
FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04
RUN apt-get update && apt-get install git ffmpeg g++ -y
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY main.py pyproject.toml uv.lock ./
RUN uv sync
EXPOSE 8080
CMD ["uv","run","python","main.py"]