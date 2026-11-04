FROM golang:1.27.3-bookworm AS printer-build
WORKDIR /bridge
COPY integrations/ptouch/go.mod integrations/ptouch/go.sum ./
RUN go mod download
COPY integrations/ptouch/main.go ./
RUN CGO_ENABLED=0 go build -trimpath -o /stash-print-bridge .

FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STASH_DATA=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 -m stash
COPY . .
COPY --from=printer-build /stash-print-bridge /usr/local/bin/stash-print-bridge
RUN SECRET_KEY=build-only-not-a-runtime-secret python manage.py collectstatic --noinput && mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
EXPOSE 8000
CMD ["sh","-c","python manage.py migrate --noinput && exec gunicorn stash.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 2 --timeout 60 --limit-request-line 8190 --access-logfile /dev/null --no-control-socket"]
