create extension if not exists "pgcrypto";

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  name text default 'Kaung',
  level integer default 1,
  xp integer default 0,
  streak integer default 0,
  preferred_theme text default 'kali',
  language text default 'en',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  content text default '',
  tags text[] default '{}',
  pinned boolean default false,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  subject text default '',
  priority text default 'Medium',
  due_date date,
  done boolean default false,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.study_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  minutes integer not null default 25,
  kind text default 'focus',
  session_date date default current_date,
  created_at timestamptz default now()
);

create table if not exists public.flashcards (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  question text not null,
  answer text not null,
  known boolean default false,
  next_review_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists public.quizzes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  topic text not null,
  score integer default 0,
  total_questions integer default 10,
  weak_topic text default '',
  suggested_review text default '',
  created_at timestamptz default now()
);

create table if not exists public.resources (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  category text not null,
  description text default '',
  difficulty text default 'Beginner',
  estimated_minutes integer default 30,
  created_at timestamptz default now()
);

create table if not exists public.ai_chats (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  mode text default 'Explain Mode',
  prompt text not null,
  response text default '',
  created_at timestamptz default now()
);

alter table public.profiles enable row level security;
alter table public.notes enable row level security;
alter table public.tasks enable row level security;
alter table public.study_sessions enable row level security;
alter table public.flashcards enable row level security;
alter table public.quizzes enable row level security;
alter table public.resources enable row level security;
alter table public.ai_chats enable row level security;

drop policy if exists "profiles own rows" on public.profiles;
drop policy if exists "notes own rows" on public.notes;
drop policy if exists "tasks own rows" on public.tasks;
drop policy if exists "sessions own rows" on public.study_sessions;
drop policy if exists "flashcards own rows" on public.flashcards;
drop policy if exists "quizzes own rows" on public.quizzes;
drop policy if exists "ai chats own rows" on public.ai_chats;
drop policy if exists "resources readable" on public.resources;

create policy "profiles own rows" on public.profiles for all using (auth.uid() = id) with check (auth.uid() = id);
create policy "notes own rows" on public.notes for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "tasks own rows" on public.tasks for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "sessions own rows" on public.study_sessions for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "flashcards own rows" on public.flashcards for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "quizzes own rows" on public.quizzes for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "ai chats own rows" on public.ai_chats for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "resources readable" on public.resources for select using (true);

do $$
begin
  alter table public.resources add constraint resources_title_key unique (title);
exception when duplicate_object then null;
end $$;

insert into public.resources (title, category, description, difficulty, estimated_minutes)
values
  ('Programming', 'Programming', 'Python loops, data structures, and project practice', 'Beginner', 45),
  ('Cyber Security', 'Cyber Security', 'Networking, firewall rules, and Linux hardening', 'Intermediate', 60),
  ('AI', 'AI', 'Prompting, model basics, and study automation', 'Beginner', 35),
  ('English / IELTS', 'English / IELTS', 'Writing practice and vocabulary review', 'Intermediate', 50),
  ('Linux', 'Linux', 'Commands, permissions, services, and logs', 'Beginner', 40),
  ('Web Development', 'Web Development', 'HTML, CSS, JavaScript, deploy workflow', 'Beginner', 70),
  ('University Assignments', 'University Assignments', 'Research, outlines, citations, and presentation prep', 'All levels', 30)
on conflict (title) do update set
  category = excluded.category,
  description = excluded.description,
  difficulty = excluded.difficulty,
  estimated_minutes = excluded.estimated_minutes;

do $$
begin
  alter publication supabase_realtime add table public.notes;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.tasks;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.study_sessions;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.flashcards;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.quizzes;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.ai_chats;
exception when duplicate_object then null;
end $$;
