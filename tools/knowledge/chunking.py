"""Shared text cleaning and splitting for the medicine knowledge chunks."""
import json
import re

# About 400 tokens: room for the chunk's heading inside a 512-token embedding window.
MAX_CHARS = 1500
SENTENCE_END = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9(•])')
# Label sections open with their own number and capitalised name: "1 INDICATIONS AND USAGE".
LABEL_HEADING = re.compile(r'^\d+(?:\.\d+)*\s+[A-Z][A-Z ,&/-]+(?=\s+[A-Z][a-z])\s*')


def clean(text):
    text = LABEL_HEADING.sub('', ' '.join(text.split()))
    text = re.sub(r'^\d+(?:\.\d+)+\s+', '', text)
    return ' '.join(text.replace('•', ' ').split())


def split_text(text, limit=MAX_CHARS):
    """Whole sentences up to the limit; a sentence longer than the limit is cut between words."""
    pieces = []
    for sentence in SENTENCE_END.split(clean(text)):
        while len(sentence) > limit:
            cut = sentence.rfind(' ', 0, limit + 1)
            cut = cut if cut > 0 else limit
            pieces.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        if sentence:
            pieces.append(sentence)
    chunks, current = [], ''
    for piece in pieces:
        if current and len(current) + 1 + len(piece) > limit:
            chunks.append(current)
            current = piece
        else:
            current = current + ' ' + piece if current else piece
    if current:
        chunks.append(current)
    return chunks


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open('w', encoding='utf-8', newline='\n') as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
            count += 1
    return count
