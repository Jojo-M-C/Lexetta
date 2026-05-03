# TODOs

- view vocabulary list
- delete document
- support md and pdf files
- implement zoom for reading viewer
- enable ML in settings

# Simois Setup Helper

## Stack

- **Backend**: FastAPI, SQLAlchemy, Alembic, PostgreSQL (in Docker)
- **Frontend**: React + TypeScript (Vite), React Router, Tailwind CSS

## Prerequisites

- **Python 3.12+**
- **Node.js 18+**
- **Docker Desktop**

## First-time setup

Clone the repo and `cd` into it, then:

### 1. Backend

```bash
# Create the .env file
cp .env.example .env

# Start Postgres in Docker
docker compose up -d

# Apply database migrations (creates tables and seeds test users)
alembic upgrade head
```

### 2. Frontend

```bash
cd frontend
npm install
```

## Running the app

You need three things running: Postgres, the backend, the frontend. Two terminals (Postgres runs in the background).

**Terminal 1 — Backend:**

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

Backend serves at http://localhost:8000. API docs at http://localhost:8000/docs.

**Terminal 2 — Frontend:**

```bash
cd frontend
npm run dev
```

Frontend serves at http://localhost:5173.

You should see the login page with six test users (`learner_a1` through `learner_c2`).

## Notes

- Test users are seeded automatically by Alembic (`learner_a1` through `learner_c2`, with reading levels A1–C2).
- Uploaded files are stored in `./uploads/` (also gitignored).


# Jojo Notes
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

