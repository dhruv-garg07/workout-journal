from typing import Dict, Any, Optional, List
from fastapi import HTTPException
import asyncpg, hashlib, os
from .parser import parse_workout, normalize_unit
from .logic import get_or_create_user, get_unit, set_unit, insert_entry, delete_last_entry, insert_sets

HASH_SALT = (os.getenv("HASH_SALT") or "").strip()

def phone_hash(phone: str) -> str:
    return hashlib.sha256((HASH_SALT + "|" + phone).encode()).hexdigest()

def kg_to_user(kg: float, unit: str) -> float:
    return round(kg if unit=="kg" else kg/0.45359237, 2)

async def handle_mcp(*, body: Dict[str, Any], pool: Optional[asyncpg.Pool],
                     bearer_tokens: Dict[str, str]) -> Dict[str, Any]:
    tool = body.get("tool")
    args = body.get("args", {})

    if tool == "validate":
        token = args.get("token","")
        phone = bearer_tokens.get(token)
        if not phone:
            raise HTTPException(401, "Invalid bearer token")
        return {"phone": phone}

    # resolve phone from token (dev flow) or direct phone (if provided by Puch)
    phone = args.get("phone")
    if not phone and args.get("token") in bearer_tokens:
        phone = bearer_tokens[args["token"]]
    if not phone:
        raise HTTPException(400, "Missing phone")

    if pool is None:
        raise HTTPException(500, "DB not connected")

    ph = phone_hash(phone)

    async with pool.acquire() as con:
        user_id = await get_or_create_user(con, ph)

        if tool == "set_unit":
            unit = normalize_unit(args.get("unit","kg"))
            await set_unit(con, user_id, unit)
            return {"message": f"✅ Unit set to {unit}"}

        if tool == "log_workout":
            text = (args.get("text") or "").strip()
            if not text:
                raise HTTPException(400, "text required")
            entry_id = await insert_entry(con, user_id, text)
            rows = parse_workout(text)
            await insert_sets(con, entry_id, rows)

            unit = await get_unit(con, user_id)
            tonnage = sum((r.get("weight_kg") or 0) * (r.get("reps") or 0) for r in rows)
            # compact, WhatsApp-friendly message
            by_ex = {}
            for r in rows:
                ex = r["exercise"]; by_ex.setdefault(ex, []).append(r)
            lines: List[str] = []
            for ex, rs in by_ex.items():
                weights = {r.get("weight_kg") for r in rs if r.get("weight_kg") is not None}
                repss = [r.get("reps") for r in rs if r.get("reps") is not None]
                if len(weights)==1 and len(set(repss))==1 and weights and repss:
                    w = list(weights)[0]; reps = repss[0]
                    lines.append(f"✅ {ex.title()} — {len(rs)}×{reps} @ {kg_to_user(w, unit)} {unit}")
                else:
                    for r in rs:
                        frag = []
                        if r.get("reps") is not None: frag.append(f"{r['reps']} reps")
                        if r.get("weight_kg") is not None: frag.append(f"@ {kg_to_user(r['weight_kg'], unit)} {unit}")
                        lines.append(f"✅ {ex.title()} — " + (" ".join(frag) if frag else "logged"))
            if tonnage>0:
                lines.append(f"📦 Tonnage: {kg_to_user(tonnage, unit):g} {unit}·reps")
            return {"message": "\n".join(lines)}

        if tool == "summary":
            rng = (args.get("range") or "week").lower()
            unit = await get_unit(con, user_id)
            if rng == "today":
                ton = await con.fetchval("""
                    select coalesce(sum(s.weight_kg*s.reps),0)
                    from sets s join entries e on e.id=s.entry_id
                    where e.user_id=$1 and e.ts::date = now()::date
                """, user_id) or 0
                ses = await con.fetchval("select count(*) from entries where user_id=$1 and ts::date = now()::date", user_id) or 0
                return {"message": f"📅 Today — Sessions: {int(ses)} | Tonnage: {kg_to_user(float(ton), unit):g} {unit}·reps"}
            elif rng == "month":
                ton = await con.fetchval("""
                    select coalesce(sum(s.weight_kg*s.reps),0)
                    from sets s join entries e on e.id=s.entry_id
                    where e.user_id=$1 and date_trunc('month', e.ts)=date_trunc('month', now())
                """, user_id) or 0
                ses = await con.fetchval("""
                    select count(*) from entries
                    where user_id=$1 and date_trunc('month', ts)=date_trunc('month', now())
                """, user_id) or 0
                return {"message": f"📅 Month — Sessions: {int(ses)} | Tonnage: {kg_to_user(float(ton), unit):g} {unit}·reps"}
            else:
                ton = await con.fetchval("""
                    select coalesce(sum(s.weight_kg*s.reps),0)
                    from sets s join entries e on e.id=s.entry_id
                    where e.user_id=$1 and e.ts >= now() - interval '7 days'
                """, user_id) or 0
                ses = await con.fetchval("""
                    select count(*) from entries
                    where user_id=$1 and ts >= now() - interval '7 days'
                """, user_id) or 0
                top = await con.fetchrow("""
                    select s.exercise, max(s.weight_kg) as w
                    from sets s join entries e on e.id=s.entry_id
                    where e.user_id=$1 and e.ts >= now() - interval '7 days' and s.weight_kg is not null
                    group by s.exercise order by w desc limit 1
                """, user_id)
                top_lift = f"{top['exercise']} {kg_to_user(float(top['w']), unit)} {unit}" if top else "—"
                return {"message": f"📅 Week — Sessions: {int(ses)} | Tonnage: {kg_to_user(float(ton), unit):g} {unit}·reps | Top: {top_lift}"}

        if tool == "last":
            ex = args.get("exercise")
            unit = await get_unit(con, user_id)
            if ex:
                rows = await con.fetch("""
                    select s.exercise, s.reps, s.weight_kg, e.ts
                    from sets s join entries e on e.id=s.entry_id
                    where e.user_id=$1 and lower(s.exercise)=lower($2)
                    order by e.ts desc, s.set_index asc limit 30
                """, user_id, ex)
            else:
                rows = await con.fetch("""
                    select s.exercise, s.reps, s.weight_kg, e.ts
                    from sets s join entries e on e.id=s.entry_id
                    where e.user_id=$1
                    order by e.ts desc, s.set_index asc limit 30
                """, user_id)
            if not rows: return {"message":"No previous sessions found."}
            ts0 = rows[0]["ts"]
            same = [r for r in rows if r["ts"]==ts0]
            lines = []
            by_ex = {}
            for r in same: by_ex.setdefault(r["exercise"], []).append(r)
            for exn, rs in by_ex.items():
                ws = {float(r["weight_kg"]) for r in rs if r["weight_kg"] is not None}
                reps = [r["reps"] for r in rs if r["reps"] is not None]
                if len(ws)==1 and len(set(reps))==1 and reps:
                    w = list(ws)[0]
                    lines.append(f"🕘 {exn.title()} — {len(rs)}×{reps[0]} @ {kg_to_user(w, unit)} {unit}")
                else:
                    for r in rs:
                        frag=[]
                        if r["reps"] is not None: frag.append(f"{r['reps']} reps")
                        if r["weight_kg"] is not None: frag.append(f"@ {kg_to_user(float(r['weight_kg']), unit)} {unit}")
                        lines.append(f"🕘 {exn.title()} — " + (" ".join(frag) if frag else "logged"))
            return {"message":"\n".join(lines)}

        if tool == "undo":
            ok = await delete_last_entry(con, user_id)
            return {"message": "↩️ Last entry removed." if ok else "Nothing to undo."}

        raise HTTPException(400, "Unknown tool")
