import re
from collections import Counter
from math import log
from sqlalchemy.orm import Session
from app.models import KBChunk, KBDocument


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    chunks = []
    i = 0
    while i < len(text):
        j = min(len(text), i + max_chars)
        chunk = text[i:j]
        chunks.append(chunk)
        i = max(0, j - overlap)
        if j == len(text):
            break
    return chunks


_word_re = re.compile(r"[A-Za-z0-9가-힣_]+", re.UNICODE)


def tokenize(s: str) -> list[str]:
    return [w.lower() for w in _word_re.findall(s) if len(w) >= 2]


def bm25_search(db: Session, query: str, top_k: int = 5):
    # MVP: Postgres에 chunk를 저장해두고, 메모리에서 BM25 점수 계산
    chunks = db.query(KBChunk).all()
    if not chunks:
        return []

    docs_tokens = [tokenize(c.text) for c in chunks]
    q_tokens = tokenize(query)
    if not q_tokens:
        return []

    N = len(docs_tokens)
    df = Counter()
    for toks in docs_tokens:
        df.update(set(toks))

    avgdl = sum(len(t) for t in docs_tokens) / max(1, N)
    k1, b = 1.5, 0.75

    def score(doc_toks):
        tf = Counter(doc_toks)
        dl = len(doc_toks)
        s = 0.0
        for t in q_tokens:
            if t not in tf:
                continue
            n_q = df.get(t, 0)
            idf = log((N - n_q + 0.5) / (n_q + 0.5) + 1.0)
            denom = tf[t] + k1 * (1 - b + b * dl / avgdl)
            s += idf * (tf[t] * (k1 + 1)) / denom
        return s

    scored = []
    for c, toks in zip(chunks, docs_tokens):
        s = score(toks)
        if s > 0:
            scored.append((s, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    hits = []
    for s, c in scored[:top_k]:
        doc = db.query(KBDocument).filter(KBDocument.id == c.doc_id).first()
        hits.append(
            {
                "doc_id": c.doc_id,
                "chunk_id": c.id,
                "score": float(s),
                "text": c.text[:1200],
                "filename": doc.filename if doc else None,
            }
        )
    return hits
