from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

app = FastAPI(title="Lexetta")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected"}


def get_current_user(
    x_user_id: int = Header(...),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, x_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@app.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return current_user