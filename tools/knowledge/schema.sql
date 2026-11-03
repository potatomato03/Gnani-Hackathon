-- Medicine knowledge in Supabase (runbook D-100, D-102, D-103). Safe to rerun.
-- Needs pgvector in the extensions schema: create extension if not exists vector with schema extensions;

create table if not exists public.knowledge_chunks (
  id text primary key,
  source text not null check (source in ('openfda_label', 'nlem_2022', 'jan_aushadhi')),
  -- One label, NLEM medicine or Jan Aushadhi group; search keeps at most a few chunks of each.
  label_id text not null,
  title text not null,
  section text not null,
  part int not null,
  parts int not null,
  ingredients text[] not null default '{}',
  route text,
  classes text,
  content text not null,
  url text,
  date text,
  licence text,
  note text,
  embedding extensions.halfvec(768) not null,
  fts tsvector generated always as (to_tsvector('english', title || ' ' || section || ' ' || content)) stored
);

create table if not exists public.indian_products (
  id int primary key,
  name text not null,
  manufacturer text,
  pack text,
  composition text not null,
  -- Normalised keys, so a brand joins to its label chunks: 'Paracetamol' is stored as 'acetaminophen'.
  ingredients text[] not null,
  -- 0 to 1 from the list's own order, best-selling first within each letter (runbook C-66).
  popularity real
);
alter table public.indian_products add column if not exists popularity real;

-- How many chunks hold each word, filled after each load by indexes.sql. Postgres ranks text without
-- weighing how rare a word is, so keyword search weighs each word itself: "domperidone" counts for much,
-- "use" for little. A binary list of common words dropped "diabetes" too (runbook C-60).
drop table if exists public.knowledge_common_words;
create table if not exists public.knowledge_words (word text primary key, ndoc int not null);

-- No policy for the publishable key: only the backend (secret key or database role) reads these tables.
alter table public.knowledge_chunks enable row level security;
alter table public.indian_products enable row level security;
alter table public.knowledge_words enable row level security;

-- Vector and keyword results merged by reciprocal rank fusion, at most per_label chunks of one label.
-- The first version had no ingredients argument; left in place it would make calls ambiguous.
drop function if exists public.match_chunks(extensions.halfvec, text, int, text[], int, int);
create or replace function public.match_chunks(
  query_embedding extensions.halfvec(768),
  query_text text,
  match_count int default 8,
  sources text[] default null,
  per_label int default 2,
  candidates int default 80,
  -- Only chunks about any of these ingredient keys, e.g. a brand's ingredients from indian_products.
  ingredients text[] default null
)
returns table (id text, source text, title text, section text, content text, url text, similarity float, score float)
language plpgsql
set search_path = public, extensions
as $$
#variable_conflict use_column
begin
  -- pgvector's default search width (40) missed 3 of the 10 nearest chunks for "domperidone uses";
  -- 400 found all 10 (runbook C-60). Set per call: Supabase refuses hnsw settings in the definition itself.
  perform set_config('hnsw.ef_search', '400', true);
  perform set_config('hnsw.iterative_scan', 'relaxed_order', true);
  return query
  with vector_hits as (
    select c.id, 1 - (c.embedding <=> query_embedding) as similarity,
           row_number() over (order by c.embedding <=> query_embedding) as rank
    from knowledge_chunks c
    where (sources is null or c.source = any(sources))
      and (match_chunks.ingredients is null or c.ingredients && match_chunks.ingredients)
    order by c.embedding <=> query_embedding
    limit candidates
  ),
  -- Each of the question's words weighs log(chunks / chunks holding it); a chunk scores the sum of the
  -- weights of the words it holds. Any word may match, so "generic for diabetes" still finds
  -- "Anti-Diabetic". Words in a fifth of all chunks or more are skipped as too common to matter.
  total as (
    select count(*)::float as n from knowledge_chunks
  ),
  query_terms as (
    select distinct t.lexeme, ln(total.n / w.ndoc) as weight
    from unnest(to_tsvector('english', query_text)) t
    join knowledge_words w on w.word = t.lexeme, total
    where w.ndoc < total.n * 0.2
  ),
  -- Chunks holding the same words share a rank, so the vector ranking breaks the tie: hundreds of chunks
  -- hold only "telmisartan", and arbitrary ranks among them outweighed the best vector match (C-60).
  text_hits as (
    select c.id, dense_rank() over (order by sum(qt.weight) desc) as rank
    from query_terms qt
    join knowledge_chunks c on c.fts @@ to_tsquery('simple', quote_literal(qt.lexeme))
    where (sources is null or c.source = any(sources))
      and (match_chunks.ingredients is null or c.ingredients && match_chunks.ingredients)
    group by c.id
  ),
  -- Every vector candidate gets its keyword credit; a chunk found by keywords alone joins only from the
  -- strongest three keyword ranks.
  fused as (
    select coalesce(v.id, t.id) as id, v.similarity::float as similarity,
           (coalesce(1.0 / (60 + v.rank), 0) + coalesce(1.0 / (60 + t.rank), 0))::float as score
    from vector_hits v full outer join text_hits t on v.id = t.id
    where v.id is not null or t.rank <= 3
  ),
  capped as (
    select f.*, row_number() over (partition by c.label_id order by f.score desc) as nth
    from fused f join knowledge_chunks c on c.id = f.id
  )
  select c.id, c.source, c.title, c.section, c.content, c.url, capped.similarity, capped.score
  from capped join knowledge_chunks c on c.id = capped.id
  where capped.nth <= per_label
  order by capped.score desc
  limit match_count;
end
$$;

revoke execute on function public.match_chunks from public, anon, authenticated;
