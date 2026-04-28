from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# tmdash server database configuration
DATABASE_URL = "postgresql+psycopg://shooca:shooca222@10.5.185.21:5432/shooca_db"

#An engine is SQLAlchemy’s "gateway" to the database
#Responsible for opening TCP connections, managing a connection pool, sending SQL to Postgres, receiving results
#An engine is not a connection. It’s a manager of connections
engine = create_engine(DATABASE_URL, future=True)

#A Session: represents a short-lived “conversation” with the database, tracks ORM objects, knows what to INSERT / UPDATE / DELETE, issues SQL only when told to
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
