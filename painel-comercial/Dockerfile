FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
RUN pip install --no-cache-dir -e . \
 && useradd --create-home painel
USER painel

EXPOSE 8000
# Aplica migrations pendentes e sobe a API + painel + MCP.
CMD ["sh", "-c", "painel migrar && painel servir --host 0.0.0.0 --porta 8000"]
