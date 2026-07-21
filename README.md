# FluidRead

A web-based reading assistant that helps non-native English speakers read English texts.

Readers upload a document (`.txt`, `.pdf`, `.epub`); words that are likely to be difficult
_for that particular reader_ are highlighted, and hovering one shows a context-aware
translation to the selected target language. Every interaction is logged as labelled training data for a personalised
lexical-complexity model.

This is a Bachelor's thesis project by Johanna Christoph @ Informatics TU Wien.

---

## Table of contents

- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [Difficulty prediction](#difficulty-prediction)
- [Data collected for research](#data-collected-for-research)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Database and migrations](#database-and-migrations)
- [The CEFR word list](#the-cefr-word-list)
- [Running a user study](#running-a-user-study)
- [Deployment](#deployment)
- [Repository layout](#repository-layout)
- [Limitations and future work](#limitations-and-future-work)

---

## What it does

1. **Onboarding** — a new participant picks a translation language and a self-assessed CEFR
   reading level (A1–C2).
2. **Calibration** — a one-time exercise rating 18 words for perceived difficulty (1–5).
   This is both explicit ground truth and the cold-start signal for the personalised model.
3. **Reading** — the reader opens a document. Words predicted to be difficult are highlighted;
   hovering one fetches the translation to the target language in the sentence's context.
4. **Vocabulary** — looked-up words are collected into flashcards with their sentence context,
   exportable as a tab-separated file for Anki.

Supported formats: **`.txt`**, **`.pdf`**, **`.epub`**.

## How it works

The model decides what to highlight, the reader's response to those highlights becomes labelled data, and that data
conditions the next prediction for that same reader.

```
calibration ──► upload ──► parse ──► pages + paragraphs ──► reader
                                                               │
                                                               ▼
  ┌────────────────────── personalisation loop ───────────────────────┐
  │                                                                   │
  │  LCP model ──► highlights ──► hover ──► translate ──► vocabulary  │
  │      ▲                          │                                 │
  │      │                          ▼                                 │
  │      │                   read_words +                             │
  │      │                   highlighted_words                        │
  │      │                          │                                 │
  │      └─── per-reader history ◄──┘                                 │
  │          (18 calibration ratings + recent behaviour)              │
  │                                                                   │
  └───────────────────────────────────────────────────────────────────┘
```

**Calibration seeds the loop.** Before any reading happens, the 18 onboarding ratings give the
model something to condition on, so the very first page is already personalised rather than
cold.

The model scores each rare word in its sentence context, and the
reader sees highlights. Hovering one fetches a translation and adds the word to their
vocabulary. That hover is a **positive** signal; a highlighted word left alone on a page the
reader demonstrably read is a **negative** one. Both land in `read_words` /
`highlighted_words`, and those rows — together with the calibration ratings — are assembled
into the per-reader history that accompanies the next prediction request. Highlighting
therefore adapts to the individual rather than to a fixed level.

The loop is closed **per request, not per training run**: the model weights are fixed, and
personalisation happens by conditioning on the history passed in with each call. Retraining on
the collected data is future work.

**Two content models, chosen per format.**

- **`.txt` and `.epub` → structured HTML.** On upload the backend extracts text and structure
  into `pages` / `paragraphs` rows. The frontend renders clickable word spans, and the whole
  interaction pipeline keys off `paragraph_id`.
- **`.pdf` → client-side rendering.** PDFs are drawn by PDF.js onto a canvas, with per-word
  bounding boxes fetched on demand for highlight overlays. Extracting reliable structure from
  arbitrary PDFs is lossy, so PDFs deliberately have no page/paragraph rows; lookups send the
  page text instead of a `paragraph_id`.

EPUB reuses the txt content pipeline (so highlighting, lookup and vocabulary work unchanged)
and adds `chapters` and `epub_images`.

## Difficulty prediction

**1. CEFR baseline.** This was added to make this thesis independent from Simois Weber's partner thesis which focussed on the LCP model.
A word is difficult if its CEFR level is **at or above** the reader's
level. Words are lemmatised with spaCy before lookup, so _exploring_ matches _explore_.

**2. Personalised LCP model (default).** A lexical-complexity-prediction model conditioned on
the individual reader's history, served on a GPU container via [Modal](https://modal.com)
(`app/lib/lcp_modal.py`). We chose to use Modal to make a remote user study possible with minimal costs.

**Translation** uses OpenAI `gpt-4o-mini`, prompted with the surrounding _sentence_ rather
than the bare word so that senses are disambiguated in context. Translations are prefetched
per page and cached on `highlighted_words.translation_target`. A translator failure never
fails a lookup — the interaction is still logged, with a null translation.

## Data collected for research

The point of the system is the labelled data it produces.

| Table                   | One row means                                     | Why it matters                                                               |
| ----------------------- | ------------------------------------------------- |------------------------------------------------------------------------------|
| `read_words`            | a word was on a page the reader demonstrably read | Trustworthy positives **and** negatives                                      |
| `highlighted_words`     | the system highlighted this word                  | Lets predictions be scored against behaviour |
| `calibration_responses` | an explicit 1–5 difficulty rating                 | Initial calibration for the LCP model                                        |
Two deliberate choices here:

- **Research data survives document deletion.** Deleting a document cascades to its
  pages/paragraphs but only nulls the foreign keys on interaction rows, which keep their
  context snapshot. Vocabulary entries are untouched.

## Tech stack

**Backend** — Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL 16

**Frontend** — Vite, React 18, TypeScript

**Infrastructure** — Docker Compose, Caddy (TLS + static frontend), DigitalOcean droplet,
Modal (GPU inference).

## Getting started

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker Desktop
- An OpenAI API key (for translations)
- A Modal account (only if you want ML-based highlighting; the CEFR path works without it)

### First-time setup

```bash
# 1. Environment
cp .env.example .env          # then fill in OPENAI_API_KEY

# 2. Python dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# 3. Database (Postgres in Docker) + schema
docker compose up -d
alembic upgrade head          # creates tables, seeds test users and calibration items

# 4. CEFR word list
python -m scripts.import_cefr data/cefr_words.csv

# 5. Frontend
cd frontend && npm install
```

### Running

Two terminals (Postgres stays in the background):

```bash
# Terminal 1 — backend at http://localhost:8000  (API docs at /docs)
source .venv/bin/activate
uvicorn app.main:app --reload

# Terminal 2 — frontend at http://localhost:5173
cd frontend && npm run dev
```

Open http://localhost:5173. The login page lists six seeded test users, `learner_a1`
through `learner_c2`.

> **Authentication is intentionally mock.** Logging in stores a user id in `localStorage`,
> sent as an `X-User-Id` header. This is a supervised-study prototype, not a public service;
> in deployment the whole site sits behind HTTP basic auth. Do not expose it otherwise.

## Configuration

All settings are read from `.env` (see `.env.example` for the annotated version).

| Variable                                                   | Required            | Purpose                                                                      |
| ---------------------------------------------------------- | ------------------- | ---------------------------------------------------------------------------- |
| `DATABASE_URL`                                             | yes                 | Postgres connection string                                                   |
| `UPLOAD_DIR`                                               | no                  | Where uploaded files are stored (default `./uploads`)                        |
| `OPENAI_API_KEY`                                           | for translation     | OpenAI key for `gpt-4o-mini`                                                 |
| `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`                    | for ML highlighting | Modal auth. Locally `modal setup` suffices; **in Docker these are required** |
| `LCP_MODEL_DIR` / `LCP_MODEL_TOKEN` / `LCP_MODEL_REVISION` | for model deploys   | Read by `modal_deploy.py` only                                               |

## Database and migrations

The schema is managed entirely by Alembic.

```bash
# After editing app/models.py
alembic revision --autogenerate -m "what changed"
#   → READ the generated file in alembic/versions/ before applying
alembic upgrade head
alembic downgrade -1

# psql shell
docker compose exec db psql -U lexetta -d lexetta

# Full reset (destructive)
docker compose down -v && docker compose up -d && alembic upgrade head
```

Data migrations seed the six test users and the 18 calibration items, so a fresh database is
immediately usable.

## The CEFR word list

`data/cefr_words.csv` backs the CEFR baseline. Its ~9,900 rows are lemmatised on import, so
inflected forms resolve to the same entry and the stored table holds 8,313 distinct lemmas.

```bash
python -m scripts.import_cefr data/cefr_words.csv
```

Distribution after import:

| Level | Words |
| ----- | ----- |
| A1    | 1037  |
| A2    | 1179  |
| B1    | 2012  |
| B2    | 2327  |
| C1    | 885   |
| C2    | 873   |

Note the labelling convention: this dataset places fairly common words (_incredible_,
_monument_) at B1, which is why the baseline uses an **at-or-above** rule.

## Running a user study

Six level-matched texts live in `study_texts/` (`A1.txt` … `C2.txt`). When a participant
completes onboarding, `POST /study/assign` gives them their **own copy** of the text matching
the level they entered, so per-reader state (reading position, highlights, lookups) stays
cleanly separated.

## Deployment

Production runs on a DigitalOcean droplet: Docker Compose with Postgres, the FastAPI backend,
and Caddy terminating TLS and serving the built frontend from disk. 

## Repository layout

```
app/
  main.py               FastAPI app and all endpoints
  models.py             SQLAlchemy models
  database.py           engine, SessionLocal, Base, get_db
  config.py             pydantic-settings configuration
  parsers/              txt / epub parsing and pagination
  lib/
    difficulty.py       CEFR rule + ML path, frequency gate, history assembly
    lcp_modal.py        Modal GPU app serving the LCP model
    lemmatize.py        spaCy lemmatisation
    sentences.py        sentence segmentation for translation context
    translator.py       translator interface
    translators/        OpenAI implementation + factory
alembic/versions/       schema and data migrations
scripts/import_cefr.py  one-off CEFR word list import
study_texts/            level-matched texts for the user study
frontend/src/
  pages/                Login, Onboarding, Calibration, Library, Vocabulary, Profile
  pages/readers/        Reader dispatch + Txt / Pdf / Epub readers
  components/           Token, WordTooltip, dialogs, shared controls
  lib/tokenize.ts       shared tokenizer
```

## Limitations and future work

- **Mock authentication.** Sufficient for a supervised study behind basic auth; not suitable
  for public deployment.
- **No automated test suite.** Verification has been manual and end-to-end.
- **Cold starts.** The Modal container can take several seconds to spin up when idle, which is
  visible as first-page latency unless a container is kept warm.
