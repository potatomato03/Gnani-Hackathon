from chunking import MAX_CHARS, clean, split_text


def test_short_text_is_one_chunk():
    assert split_text('Telmisartan is indicated for hypertension.') == ['Telmisartan is indicated for hypertension.']


def test_long_text_splits_at_sentence_ends_within_the_limit():
    sentence = 'This sentence is about forty-five characters. '
    parts = split_text(sentence * 100)
    assert len(parts) > 1
    assert all(len(p) <= MAX_CHARS for p in parts)
    assert all(p.endswith('characters.') for p in parts)
    assert ' '.join(parts) == clean(sentence * 100)


def test_one_overlong_sentence_is_cut_at_words():
    parts = split_text('word ' * 1000)
    assert all(len(p) <= MAX_CHARS for p in parts) and all(not p.startswith(' ') for p in parts)
    assert sum(len(p.split()) for p in parts) == 1000


def test_clean_drops_label_heading_numbers_and_bullets():
    assert clean('1 INDICATIONS AND USAGE Telmisartan tablets are indicated') == 'Telmisartan tablets are indicated'
    assert clean('5.2 Fetal Toxicity  •  Discontinue   when pregnancy is detected') == 'Fetal Toxicity Discontinue when pregnancy is detected'
