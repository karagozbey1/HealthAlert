from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

# Asenkron veritabanı oturumu sağlayan FastAPI dependency.
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# Tüm tabloları yoksa oluşturur.
async def init_db() -> None:
    import models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
