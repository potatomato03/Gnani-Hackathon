"""Ask the knowledge in Supabase questions, through match_chunks (vector plus keyword search).

    python tools/knowledge/search_supabase.py "what is telmisartan used for"
    python tools/knowledge/search_supabase.py --brand "Dolo 650" "overdose"

With --brand, the brand is first looked up in indian_products and the search is
limited to chunks about that brand's ingredients.
"""
import sys

from embed_chunks import load_model
from upload_supabase import REPO_ROOT, read_env, vector_literal

SEARCH = ('select source, title, section, similarity, score, content from public.match_chunks('
          '%s::extensions.halfvec, %s, 6, ingredients => %s)')
BRAND = ("select name, composition, ingredients from public.indian_products "
         "where lower(name) like lower(%s) || '%%' order by length(name) limit 1")


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    import psycopg
    args = sys.argv[1:]
    brand = args.pop(1) if args and args[0] == '--brand' else None
    args = [a for a in args if a != '--brand']
    model = load_model()
    with psycopg.connect(read_env(REPO_ROOT / '.env')['SUPABASE_DB_URL'], connect_timeout=30) as conn:
        ingredients = None
        if brand:
            found = conn.execute(BRAND, (brand,)).fetchone()
            if not found:
                print(f'{brand}: not in indian_products')
                return 1
            name, composition, ingredients = found
            print(f'{brand} -> {name}: {composition} -> {ingredients}')
        for question, vector in zip(args, model.query_embed(args)):
            print(f'\n## {question}')
            rows = conn.execute(SEARCH, (vector_literal(vector), question, ingredients)).fetchall()
            for source, title, section, similarity, score, content in rows:
                sim = f'{similarity:.3f}' if similarity is not None else ' text'
                print(f'{sim}  {score:.4f}  {source:13}  {title[:38]:38}  {section[:20]:20}  {content[len(title):][:80]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
