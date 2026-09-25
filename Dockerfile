FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && addgroup --system litrip \
    && adduser --system --ingroup litrip litrip

USER litrip

EXPOSE 8899

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8899/', timeout=4)"

ENTRYPOINT ["lit-rip"]
CMD ["gui", "--host", "0.0.0.0", "--no-browser", "--port", "8899"]
