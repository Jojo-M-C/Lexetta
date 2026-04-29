
## Startup

```
docker compose up -d              # start Postgres
source .venv/bin/activate         # activate venv
uvicorn app.main:app --reload     # run app
```

## Schema Changes

```
# 1. Edit app/models.py
# 2. Generate migration
alembic revision --autogenerate -m "what changed"
# 3. READ the file in alembic/versions/ before applying
# 4. Apply
alembic upgrade head
```

## Add test data

```
alembic revision -m "seed something"
```
Open the new file in alembic/versions/ and replace upgrade() and downgrade().

## Postgres

```
# Open psql shell
docker compose exec db psql -U lexetta -d lexetta
```

## Reset database

```
docker compose down -v
docker compose up -d
alembic upgrade head
```

