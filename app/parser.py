import re
from typing import List, Dict, Any

ALIAS_MAP = {
    "bp":"bench press","bench":"bench press","bench press":"bench press",
    "ohp":"overhead press","press":"overhead press",
    "dl":"deadlift","deadlift":"deadlift",
    "squat":"squat","squats":"squat",
    "row":"barbell row","run":"run","walk":"walk","cycle":"cycle","bike":"cycle",
}

def normalize_unit(u: str) -> str:
    u = (u or "").lower().strip()
    if u in ("kg","kgs"): return "kg"
    if u in ("lb","lbs"): return "lb"
    return "kg"

def lb_to_kg(lb: float) -> float:
    return round(lb * 0.45359237, 2)

def canonical_ex(n: str) -> str:
    n = (n or "").lower().strip()
    return ALIAS_MAP.get(n, n)

WEIGHT = r"(?P<wt>\d+(?:\.\d+)?)\s*(?P<wunit>kg|kgs|lb|lbs)?"
REPS = r"(?P<reps>\d+)"
SETS = r"(?P<sets>\d+)"
TIME = r"(?P<time>\d{1,2}:\d{2})"
DIST = r"(?P<dist>\d+(?:\.\d+)?)\s*(?P<dunit>km|k|m)"

PATTERNS = [
    re.compile(rf"^(?P<ex>.+?)\s+{SETS}x{REPS}\s*@\s*{WEIGHT}$"),
    re.compile(rf"^(?P<ex>.+?)\s+{WEIGHT}\s*x\s*{REPS}$"),
    re.compile(rf"^(?P<ex>.+?)\s+{WEIGHT}\s+(?P<list>(?:\d+\s*,\s*)*\d+)$"),
    re.compile(rf"^(?P<ex>.+?)\s+(?P<wt2>\d+(?:\.\d+)?)x(?P<reps2>\d+)x(?P<sets2>\d+)$"),
    re.compile(rf"^(?P<ex2>run|walk|cycle)\s+{DIST}(?:\s+{TIME})?$"),
]

def parse_time_to_sec(t: str):
    if not t: return None
    mm, ss = t.split(":")
    return int(mm)*60 + int(ss)

def parse_workout(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    parts = [p.strip() for p in re.split(r"[,\|;]\s*", text.strip()) if p.strip()]
    for seg in parts:
        seg_l = seg.lower()
        matched = False
        for pat in PATTERNS:
            m = pat.match(seg_l)
            if not m: continue
            matched = True
            gd = m.groupdict()

            if "ex" in gd:  # strength
                ex = canonical_ex(gd["ex"])
                if gd.get("sets") and gd.get("reps"):
                    w = float(gd["wt"]); unit = normalize_unit(gd.get("wunit"))
                    kg = w if unit=="kg" else lb_to_kg(w)
                    for _ in range(int(gd["sets"])):
                        rows.append({"exercise": ex, "reps": int(gd["reps"]), "weight_kg": kg})
                elif gd.get("list"):
                    w = float(gd["wt"]); unit = normalize_unit(gd.get("wunit"))
                    kg = w if unit=="kg" else lb_to_kg(w)
                    for r in [int(x.strip()) for x in gd["list"].split(",")]:
                        rows.append({"exercise": ex, "reps": r, "weight_kg": kg})
                else:
                    w = float(gd["wt"]); unit = normalize_unit(gd.get("wunit"))
                    kg = w if unit=="kg" else lb_to_kg(w)
                    rows.append({"exercise": ex, "reps": int(gd["reps"]), "weight_kg": kg})

            elif gd.get("wt2"):  # weight x reps x sets
                ex = canonical_ex(m.group(1))
                kg = float(gd["wt2"])
                for _ in range(int(gd["sets2"])):
                    rows.append({"exercise": ex, "reps": int(gd["reps2"]), "weight_kg": kg})

            elif gd.get("ex2"):  # cardio
                ex = canonical_ex(gd["ex2"])
                dist = float(gd["dist"]); dunit = gd["dunit"]
                dist_km = dist/1000.0 if dunit=="m" else dist
                dur = parse_time_to_sec(gd.get("time"))
                rows.append({"exercise": ex, "distance_km": round(dist_km,3), "duration_sec": dur})
            break

        if not matched:  # fallback note
            rows.append({"exercise": canonical_ex(seg)})

    return rows
