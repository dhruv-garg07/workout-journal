import os, logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from dotenv import load_dotenv
import asyncpg

from .db import create_pool, DATABASE_URL
from .mcp import handle_mcp

load_dotenv()
log = logging.getLogger("uvicorn.error")

HASH_SALT = (os.getenv("HASH_SALT") or "").strip()
TOKENS_RAW = (os.getenv("BEARER_TOKENS") or "devtoken:919876543210").strip()
BEARER_TOKENS = dict(item.split(":") for item in TOKENS_RAW.split(",")) if TOKENS_RAW else {}

app = FastAPI()
pool: Optional[asyncpg.Pool] = None

def _env_ok():
    errs = []
    if not DATABASE_URL: errs.append("DATABASE_URL missing")
    if not HASH_SALT: errs.append("HASH_SALT missing")
    if errs: raise RuntimeError(" | ".join(errs))

@app.on_event("startup")
async def _startup():
    global pool
    _env_ok()
    try:
        pool = await create_pool()
        log.info("✅ DB pool created")
    except Exception as e:
        log.exception("❌ Failed to create DB pool")
        pool = None

@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"

@app.get("/diag")
async def diag():
    info = {
        "env": {
            "DATABASE_URL_present": bool(DATABASE_URL),
            "HASH_SALT_present": bool(HASH_SALT),
            "BEARER_TOKENS_present": bool(BEARER_TOKENS),
        },
        "db": {"pool_ready": pool is not None}
    }
    if pool is not None:
        try:
            async with pool.acquire() as con:
                v = await con.fetchval("select 1;")
            info["db"]["ping"] = v
        except Exception as e:
            info["db"]["ping_error"] = f"{e.__class__.__name__}: {e}"
    return JSONResponse(info)

@app.post("/mcp")
async def mcp(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    # Let validate run without DB to connect Puch even during DB issues
    if body.get("tool") == "validate":
        return await handle_mcp(body=body, pool=None, bearer_tokens=BEARER_TOKENS)

    if pool is None:
        raise HTTPException(500, "DB not connected")

    return await handle_mcp(body=body, pool=pool, bearer_tokens=BEARER_TOKENS)
