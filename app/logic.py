from typing import List, Dict, Any, Optional
import asyncpg

async def get_or_create_user(con: asyncpg.Connection, phone_hash: str) -> str:
    row = await con.fetchrow("select id from users where phone_hash=$1", phone_hash)
    if row: return row["id"]
    row = await con.fetchrow("insert into users(phone_hash) values($1) returning id", phone_hash)
    return row["id"]

async def get_unit(con: asyncpg.Connection, user_id: str) -> str:
    row = await con.fetchrow("select unit_pref from users where id=$1", user_id)
    return (row and row["unit_pref"]) or "kg"

async def set_unit(con: asyncpg.Connection, user_id: str, unit: str):
    await con.execute("update users set unit_pref=$1 where id=$2", unit, user_id)

async def insert_entry(con: asyncpg.Connection, user_id: str, raw_text: str) -> str:
    row = await con.fetchrow("insert into entries(user_id, raw_text) values($1,$2) returning id", user_id, raw_text)
    return row["id"]

async def delete_last_entry(con: asyncpg.Connection, user_id: str) -> bool:
    row = await con.fetchrow("select id from entries where user_id=$1 order by ts desc limit 1", user_id)
    if not row: return False
    await con.execute("delete from entries where id=$1", row["id"])
    return True

async def insert_sets(con: asyncpg.Connection, entry_id: str, sets_rows: List[Dict[str, Any]]):
    for i, s in enumerate(sets_rows):
        await con.execute(
            "insert into sets(entry_id, exercise, set_index, reps, weight_kg, distance_km, duration_sec) values($1,$2,$3,$4,$5,$6,$7)",
            entry_id, s["exercise"], i+1, s.get("reps"), s.get("weight_kg"), s.get("distance_km"), s.get("duration_sec")
        )
