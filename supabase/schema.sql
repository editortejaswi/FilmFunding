-- FilmFund Radar — Supabase schema v1
-- Run in: Supabase Dashboard → SQL Editor → New query → paste → Run.
-- Safe to re-run (idempotent). Auth (users, passwords, reset) is handled by
-- Supabase Auth itself (auth.users) — these tables only add per-user app state.

-- ── profiles: one row per user, auto-created on signup ──────────────────────
create table if not exists public.profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  email      text,
  regions    text[] default '{}',      -- country filters this user cares about
  digest_opt boolean default true,     -- wants the periodic email digest?
  created_at timestamptz default now()
);
alter table public.profiles enable row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles
  for select using (auth.uid() = id);
drop policy if exists profiles_insert_own on public.profiles;
create policy profiles_insert_own on public.profiles
  for insert with check (auth.uid() = id);
drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles
  for update using (auth.uid() = id);

-- auto-create a profile whenever a new auth user signs up
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end; $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ── saved: opportunities a user bookmarked (opp_id matches opportunities.json) ─
create table if not exists public.saved (
  user_id  uuid references auth.users(id) on delete cascade,
  opp_id   text not null,
  saved_at timestamptz default now(),
  primary key (user_id, opp_id)
);
alter table public.saved enable row level security;

drop policy if exists saved_own on public.saved;
create policy saved_own on public.saved
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
