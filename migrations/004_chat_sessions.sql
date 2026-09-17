-- ============================================================================
-- FinGuru — Persistent chat sessions for the AI CA Advisor (ChatGPT-style).
-- Groups the existing `ai_conversations` audit rows into named conversations a
-- user can load, rename, and delete. Requires migrations/001 (ai_conversations).
--
-- WHAT IT ADDS
--   * public.chat_sessions          — one row per saved conversation:
--        id, user_id, title, created_at, updated_at
--   * ai_conversations.session_id   — nullable FK to chat_sessions(id) with
--        ON DELETE CASCADE: deleting a session removes its messages.
--        Existing rows keep NULL (fully backward compatible — old audit rows
--        are simply not linked to any session).
--
-- HOW TO RUN: Supabase Dashboard → SQL Editor → paste & *Run*.
-- Idempotent: safe to re-run (guards with IF NOT EXISTS / DO-loop pattern).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. CHAT SESSIONS — one row per saved conversation
-- ----------------------------------------------------------------------------
create table if not exists public.chat_sessions (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null references auth.users(id) on delete cascade,
    title      text not null default 'New chat',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- FK from the existing audit table: nullable, cascade-deletes with the session.
alter table public.ai_conversations
    add column if not exists session_id uuid
        references public.chat_sessions(id) on delete cascade;

-- ----------------------------------------------------------------------------
-- 2. ROW LEVEL SECURITY — owner-scoped, same policies as migrations/001
-- ----------------------------------------------------------------------------
alter table public.chat_sessions enable row level security;

-- Policy creation is not idempotent in plain SQL, so guard each one with a
-- DO-loop that skips when the policy already exists (mirrors 001's intent).
do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'chat_sessions'
          and policyname = 'Users can view own rows'
    ) then
        execute format('create policy "Users can view own rows" on public.chat_sessions for select using (auth.uid() = user_id)');
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'chat_sessions'
          and policyname = 'Users can insert own rows'
    ) then
        execute format('create policy "Users can insert own rows" on public.chat_sessions for insert with check (auth.uid() = user_id)');
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'chat_sessions'
          and policyname = 'Users can update own rows'
    ) then
        execute format('create policy "Users can update own rows" on public.chat_sessions for update using (auth.uid() = user_id)');
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'chat_sessions'
          and policyname = 'Users can delete own rows'
    ) then
        execute format('create policy "Users can delete own rows" on public.chat_sessions for delete using (auth.uid() = user_id)');
    end if;
end $$;

-- ----------------------------------------------------------------------------
-- 3. Indexes for common lookups
-- ----------------------------------------------------------------------------
create index if not exists idx_chat_sessions_user
    on public.chat_sessions(user_id, updated_at desc);
create index if not exists idx_ai_convs_session
    on public.ai_conversations(session_id);