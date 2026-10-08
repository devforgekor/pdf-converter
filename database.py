"""
데이터베이스 설정

참조 소스:
- FastAPI + SQLAlchemy 공식 문서: https://fastapi.tiangolo.com/tutorial/sql-databases/
- SQLAlchemy ORM 패턴: declarative_base, sessionmaker, get_db 의존성 주입
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./instance/app.db")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}  # SQLite 전용
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
