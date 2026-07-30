# WeFlow local service-boundary mode

`docker-compose.yml` is a local-development topology only. Every exposed port is bound to
`127.0.0.1`; the PostgreSQL and MinIO values are literal non-secret placeholders and must
not be copied to a deployed environment.

Run it only after Docker is available:

```text
python scripts/dev.py compose up
python scripts/dev.py up --mode service-boundary
```

Offline mode remains the required baseline and does not need Docker, a model credential, or
network access after dependencies are installed.
