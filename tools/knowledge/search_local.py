"""Search the embedded chunks on this machine, to check retrieval before anything is uploaded.

    python tools/knowledge/search_local.py "what is telmisartan used for" "paracetamol overdose"
"""
import json
import sys

import numpy

from embed_chunks import CHUNK_FILES, DATA_DIR, MODEL, load_embeddings, load_model


def top_matches(query_vector, vectors, k=5):
    """Indexes of the k nearest vectors by cosine similarity (the vectors are normalised)."""
    scores = vectors @ query_vector
    best = numpy.argsort(-scores)[:k]
    return [(int(i), float(scores[i])) for i in best]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ids, vectors, meta = load_embeddings(DATA_DIR / 'knowledge/embeddings' / MODEL.split('/')[-1])
    chunks = {}
    for name in CHUNK_FILES:
        with (DATA_DIR / 'knowledge/chunks' / name).open(encoding='utf-8') as handle:
            for line in handle:
                chunk = json.loads(line)
                chunks[chunk['id']] = chunk
    model = load_model()
    for question, query_vector in zip(sys.argv[1:], model.query_embed(sys.argv[1:])):
        print(f'\n## {question}')
        for index, score in top_matches(query_vector, vectors):
            chunk = chunks[ids[index]]
            print(f"{score:.3f}  {chunk['source']:13}  {chunk['title'][:40]:40}  {chunk['section'][:22]:22}  {chunk['text'][len(chunk['title']):][:90]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
