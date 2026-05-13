FROM python:3.12-slim AS base

WORKDIR /app

RUN pip install --no-cache-dir poetry==2.4.1

COPY pyproject.toml poetry.lock poetry.toml ./
RUN poetry install --no-interaction --no-ansi --only main

COPY . .

ENTRYPOINT ["poetry", "run", "python", "main.py"]
CMD ["TSLA"]
