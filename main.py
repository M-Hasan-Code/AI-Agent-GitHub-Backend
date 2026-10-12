from DB.models import DATABASE_URL
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from contextlib import asynccontextmanager
from fastapi import FastAPI
from DB.models import Base, engine
from auth.github_login import router as github_router
from routers.repos import router as repos
from routers.chunk_repo import router as chunkrepo
from routers.rag import build_graph, router as rag_router

CHECKPOINT_DB_URL = (
    DATABASE_URL
    .replace("postgresql+asyncpg://", "postgresql://")
    .replace("ssl=require", "sslmode=require")
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncPostgresSaver.from_conn_string(CHECKPOINT_DB_URL) as checkpointer:
        await checkpointer.setup()
        app.state.graph = build_graph(checkpointer)

        yield

    await engine.dispose()

app = FastAPI(lifespan=lifespan)

app.include_router(github_router)
app.include_router(repos)
app.include_router(chunkrepo)
app.include_router(rag_router)