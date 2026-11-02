"""Embed the knowledge chunks with bge-base-en-v1.5 on this machine (fastembed, ONNX).

    python tools/knowledge/embed_chunks.py
    ../.venv-embed/Scripts/python tools/knowledge/embed_chunks.py --gpu

The CPU takes about 3.5 hours; the GPU takes minutes, from the separate
`.venv-embed` environment (onnxruntime-gpu with CUDA 13), which keeps CUDA 13
away from Whisper's CUDA 12 environment.

Reads ../DATA/knowledge/chunks/*.jsonl and writes the vectors, their chunk ids and
a record of the model to ../DATA/knowledge/embeddings/<model>/. The model is kept
in ../models/fastembed. Questions must be embedded with the same model's query
mode (`query_embed`), which adds bge's search prefix.
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get('DATA_DIR', REPO_ROOT.parent / 'DATA'))
MODEL_DIR = REPO_ROOT.parent / 'models' / 'fastembed'
MODEL = 'BAAI/bge-base-en-v1.5'
CHUNK_FILES = ('openfda_label.jsonl', 'nlem_2022.jsonl', 'jan_aushadhi.jsonl')


def embed_files(paths, embed, batch_size=16):
    """Chunk ids in file order, and one vector per chunk from embed(texts).

    Texts are embedded shortest first, so each small batch pads little; the vectors
    are put back in file order. On the CPU this cut the time by about a third.
    """
    ids, texts = [], []
    for path in paths:
        with Path(path).open(encoding='utf-8') as handle:
            for line in handle:
                chunk = json.loads(line)
                ids.append(chunk['id'])
                texts.append(chunk['text'])
    seen = set()
    duplicates = sorted({i for i in ids if i in seen or seen.add(i)})
    if duplicates:
        raise ValueError('duplicate chunk ids: ' + ', '.join(duplicates[:5]))
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    vectors = [None] * len(texts)
    started = time.time()
    for start in range(0, len(order), batch_size):
        batch = order[start:start + batch_size]
        for index, vector in zip(batch, embed([texts[i] for i in batch])):
            vectors[index] = vector
        done = start + len(batch)
        if done % (batch_size * 64) == 0 or done == len(order):
            print(f'{done} of {len(order)} in {time.time() - started:.0f}s', flush=True)
    return ids, numpy.vstack(vectors).astype(numpy.float32)


def save_embeddings(out_dir, ids, vectors, meta):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    numpy.save(out_dir / 'vectors.npy', vectors)
    (out_dir / 'ids.txt').write_text('\n'.join(ids) + '\n', encoding='utf-8')
    record = {**meta, 'count': len(ids), 'dim': int(vectors.shape[1])}
    (out_dir / 'meta.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')


def load_embeddings(out_dir):
    out_dir = Path(out_dir)
    # One id per line: Jan Aushadhi ids hold spaces ("jan_aushadhi:Central Nervous System (CNS):2").
    ids = (out_dir / 'ids.txt').read_text(encoding='utf-8').splitlines()
    meta = json.loads((out_dir / 'meta.json').read_text(encoding='utf-8'))
    return ids, numpy.load(out_dir / 'vectors.npy'), meta


def load_model(gpu=False):
    from fastembed import TextEmbedding
    if not gpu:
        return TextEmbedding(MODEL, cache_dir=str(MODEL_DIR))
    import onnxruntime
    onnxruntime.preload_dlls()
    model = TextEmbedding(MODEL, cache_dir=str(MODEL_DIR), providers=['CUDAExecutionProvider'])
    # onnxruntime falls back to the CPU silently when a CUDA library is missing (runbook C-56).
    if 'CUDAExecutionProvider' not in model.model.model.get_providers():
        raise RuntimeError('the GPU was asked for but onnxruntime fell back to the CPU')
    return model


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    import fastembed
    gpu = '--gpu' in sys.argv[1:]
    model = load_model(gpu)
    paths = [DATA_DIR / 'knowledge/chunks' / name for name in CHUNK_FILES]
    ids, vectors = embed_files(paths, lambda texts: model.passage_embed(texts, batch_size=len(texts)),
                               batch_size=64 if gpu else 16)
    out_dir = DATA_DIR / 'knowledge/embeddings' / MODEL.split('/')[-1]
    save_embeddings(out_dir, ids, vectors, {'model': MODEL, 'fastembed': fastembed.__version__,
                                            'device': 'gpu' if gpu else 'cpu', 'mode': 'passage',
                                            'normalised': True, 'files': list(CHUNK_FILES)})
    print(f'{len(ids)} vectors of {vectors.shape[1]} dimensions in {out_dir}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
