import json

import numpy

from embed_chunks import embed_files, load_embeddings, save_embeddings


def write(path, rows):
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')


def fake_embed(texts):
    for text in texts:
        yield numpy.array([len(text), 1.0], dtype=numpy.float32)


def test_vectors_stay_aligned_with_ids_across_files(tmp_path):
    write(tmp_path / 'a.jsonl', [{'id': 'a1', 'text': 'x'}, {'id': 'a2', 'text': 'xxx'}])
    write(tmp_path / 'b.jsonl', [{'id': 'b1', 'text': 'xx'}])
    ids, vectors = embed_files([tmp_path / 'a.jsonl', tmp_path / 'b.jsonl'], fake_embed, batch_size=2)
    assert ids == ['a1', 'a2', 'b1']
    assert vectors[:, 0].tolist() == [1, 3, 2]


def test_saved_embeddings_round_trip_with_their_model_record(tmp_path):
    vectors = numpy.ones((2, 3), dtype=numpy.float32)
    save_embeddings(tmp_path, ['a', 'jan_aushadhi:Central Nervous System (CNS):2'], vectors, {'model': 'test'})
    ids, loaded, meta = load_embeddings(tmp_path)
    assert ids == ['a', 'jan_aushadhi:Central Nervous System (CNS):2']
    assert loaded.shape == (2, 3) and meta['model'] == 'test' and meta['count'] == 2


def test_search_ranks_by_cosine_similarity():
    from search_local import top_matches
    vectors = numpy.array([[1, 0], [0.6, 0.8], [0, 1]], dtype=numpy.float32)
    assert [i for i, _ in top_matches(numpy.array([0, 1], dtype=numpy.float32), vectors, k=2)] == [2, 1]


def test_duplicate_ids_are_refused(tmp_path):
    write(tmp_path / 'a.jsonl', [{'id': 'a1', 'text': 'x'}, {'id': 'a1', 'text': 'y'}])
    try:
        embed_files([tmp_path / 'a.jsonl'], fake_embed)
    except ValueError as error:
        assert 'a1' in str(error)
    else:
        raise AssertionError('duplicate id accepted')
