import os, ssl, asyncpg
from typing import Optional
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()

async def create_pool() -> Optional[asyncpg.Pool]:
    print("Creating DB pool with URL:", DATABASE_URL)
    if not DATABASE_URL:
        return None
    parsed = urlparse(DATABASE_URL)
    host = parsed.hostname or ""
    is_local = host in ("localhost", "127.0.0.1")
    sslctx = None if is_local else ssl.create_default_context()
    return await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5, ssl=sslctx)
