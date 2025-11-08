import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

print("DB URL:", repr(SQLALCHEMY_DATABASE_URL))

# Optimize connection pooling for better performance
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=10,  # Number of connections to keep open
    max_overflow=20,  # Additional connections that can be created on demand
    pool_pre_ping=True,  # Verify connections before using them
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=False,  # Set to True for SQL query logging (useful for debugging)
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
