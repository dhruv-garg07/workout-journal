create extension if not exists pgcrypto;

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  phone_hash text not null unique,
  unit_pref text not null default 'kg',
  created_at timestamptz not null default now()
);

create table if not exists entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  ts timestamptz not null default now(),
  raw_text text not null,
  note text
);
create index if not exists idx_entries_user_ts on entries(user_id, ts desc);

create table if not exists sets (
  id uuid primary key default gen_random_uuid(),
  entry_id uuid not null references entries(id) on delete cascade,
  exercise text not null,
  set_index int not null,
  reps int,
  weight_kg numeric(6,2),
  distance_km numeric(6,2),
  duration_sec int
);
create index if not exists idx_sets_ex on sets(exercise);
create index if not exists idx_sets_entry on sets(entry_id);

create table if not exists exercise_aliases (
  alias text primary key,
  canonical text not null
);

insert into exercise_aliases(alias, canonical) values
('bp','bench press'),('bench','bench press'),('bench press','bench press'),
('ohp','overhead press'),('press','overhead press'),
('dl','deadlift'),('deadlift','deadlift'),
('squat','squat'),('squats','squat'),
('row','barbell row'),('run','run'),('walk','walk'),
('cycle','cycle'),('bike','cycle')
on conflict do nothing;
