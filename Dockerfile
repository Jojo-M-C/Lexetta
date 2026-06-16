FROM python:3.12-slim

WORKDIR /app

# Install Python deps first (cached unless requirements.txt changes), then the
# spaCy English model — easy to forget, breaks lemmatization/sentences if missing.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && python -m spacy download en_core_web_sm

COPY . .

# Apply migrations (seeds the 6 test users + calibration items) on every start,
# then run the app. No --reload in production.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]