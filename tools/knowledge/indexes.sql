-- Built after a bulk load, which is much faster than keeping them up to date row by row.
create index if not exists knowledge_chunks_embedding_idx on public.knowledge_chunks
  using hnsw (embedding extensions.halfvec_cosine_ops);
create index if not exists knowledge_chunks_fts_idx on public.knowledge_chunks using gin (fts);
create index if not exists knowledge_chunks_ingredients_idx on public.knowledge_chunks using gin (ingredients);
create index if not exists knowledge_chunks_label_idx on public.knowledge_chunks (label_id);
create index if not exists indian_products_name_idx on public.indian_products (lower(name));
create index if not exists indian_products_ingredients_idx on public.indian_products using gin (ingredients);
truncate public.knowledge_words;
insert into public.knowledge_words select word, ndoc from ts_stat('select fts from public.knowledge_chunks');
analyze public.knowledge_chunks;
analyze public.indian_products;
