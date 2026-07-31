-- 가계부 웹앱 : transactions 테이블
create extension if not exists "pgcrypto";

create table if not exists public.transactions (
  id uuid primary key default gen_random_uuid(),
  date date not null,
  month text not null, -- 예: "2026-03"
  type text not null check (type in ('income', 'expense', 'savings')),
  category text not null,
  description text default '',
  amount integer not null check (amount >= 0),
  created_at timestamptz not null default now()
);

create index if not exists transactions_month_idx on public.transactions (month);
create index if not exists transactions_type_idx on public.transactions (type);
create index if not exists transactions_date_idx on public.transactions (date);

alter table public.transactions enable row level security;

-- 개인용 단일 사용자 앱을 가정한 공개 정책입니다.
-- 여러 사용자를 지원하려면 user_id 컬럼을 추가하고 auth.uid() 기준으로 정책을 제한하세요.
create policy "Allow anon select" on public.transactions
  for select using (true);

create policy "Allow anon insert" on public.transactions
  for insert with check (true);

create policy "Allow anon delete" on public.transactions
  for delete using (true);
