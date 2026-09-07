# Test environment

A throwaway Nautobot for working on this app, pinned to the same version as the
EEN test cluster (**3.0.11 / Python 3.12**).

Everything goes through the `./dev` script at the repository root. You need
Docker Desktop running; nothing else.

```
./dev up        start Nautobot + postgres + redis, wait until it answers
./dev seed      load demo parts, stock and history
./dev smoke     end-to-end REST API check
./dev test      run the app's test suite
./dev down      stop, keeping the database
./dev wipe      stop and delete the database (asks first)
```

`./dev up` prints the URL and credentials when it is ready:

| | |
|---|---|
| URL | <http://localhost:8081/> |
| Login | `admin` / `admin` |
| API token | `0123456789abcdef0123456789abcdef01234567` |
| App | <http://localhost:8081/plugins/spare-parts/> |
| API | <http://localhost:8081/api/plugins/spare-parts/> |

## How the app gets into the container

The repository is mounted at `/source` and `PYTHONPATH=/source`, so the running
Nautobot imports the app straight off your working copy. There is no build step
and no editable install: **edit a file, `./dev restart`, reload the page**.

Templates are picked up without even a restart.

## Everyday tasks

```
./dev logs                 follow the Nautobot log
./dev restart              pick up Python changes
./dev makemigrations       after changing models.py
./dev migrate              apply them
./dev nbshell              Django ORM shell
./dev dbshell              psql
./dev manage <subcommand>  any nautobot-server subcommand
./dev check                nautobot-server check
./dev lint                 black --check + flake8
```

## Testing another Nautobot version

Change `NAUTOBOT_VERSION` / `PYTHON_VER` in `dev.env`, then `./dev wipe && ./dev up`.
Only the pinned version is verified — see `../COMPATIBILITY.md`.

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | The four containers |
| `dev.env` | Version pins and throwaway credentials |
| `nautobot_config.py` | Nautobot settings, with the app enabled |
| `seed_demo_data.py` | Demo data, safe to run repeatedly |
| `api_smoke_test.py` | HTTP-only end-to-end API check |

The credentials in `dev.env` are deliberately committed. They only ever reach a
container listening on localhost — do not reuse them anywhere else.

`development/.probe.py` and `.intro.py` are gitignored scratch files; write
whatever you like there and run it with
`./dev manage shell --interface python < development/.probe.py`.
