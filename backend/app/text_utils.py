"""Outils de texte partagés : normalisation, mots-clés, recherche d'extraits."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

STOPWORDS = set(
    """a au aux avec ce ces cette d de des du elle en et etre il ils je la le les leur lui ma mais me
    meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton
    tu un une vos votre vous y l s n c j m t si dans est sont avoir ans an annee annees experience
    minimum moins plus bonne bon bonnes bons tres etc niveau capacite capable savoir sens maitrise
    connaissance connaissances poste h f souhaite souhaitee indispensable obligatoire""".split()
)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str) -> str:
    s = strip_accents(s.lower())
    s = s.replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


def keywords(s: str) -> list[str]:
    words = re.findall(r"[a-z0-9+#]+", norm(s))
    return [w for w in words if w not in STOPWORDS and (len(w) > 2 or w.isdigit() or w in {"c", "b"})]


def stem(w: str) -> str:
    return w[:5] if len(w) > 5 else w


def keyword_hits(needles: list[str], haystack: str) -> int:
    hay = {stem(w) for w in keywords(haystack)}
    return sum(1 for n in {stem(x) for x in needles} if n in hay)


def lines_of(text: str) -> list[str]:
    return [ln.strip(" \t•-–*·") for ln in text.splitlines() if ln.strip(" \t•-–*·")]


def sentences_of(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


def find_excerpt(excerpt: str, source: str, threshold: float = 0.9) -> str | None:
    """Retrouve un extrait dans le texte source.

    Renvoie le passage exact du source (pour l'affichage) ou None si introuvable.
    Tolère casse, accents, espaces et ponctuation légère ; sinon similarité ≥ seuil
    sur une fenêtre glissante. C'est le garde-fou contre les inventions du modèle.
    """
    if not excerpt or not source:
        return None
    ex = norm(excerpt).strip(" .,;:")
    if len(ex) < 4:
        return None
    # Index de correspondance caractère normalisé -> position d'origine.
    norm_chars: list[str] = []
    positions: list[int] = []
    prev_space = False
    for i, ch in enumerate(source):
        n = strip_accents(ch.lower()).replace("’", "'")
        for c in n:
            if c.isspace():
                if prev_space:
                    continue
                c, prev_space = " ", True
            else:
                prev_space = False
            norm_chars.append(c)
            positions.append(i)
    hay = "".join(norm_chars)
    idx = hay.find(ex)
    if idx >= 0:
        start, end = positions[idx], positions[idx + len(ex) - 1] + 1
        return source[start:end]
    # Similarité approximative (guillemets, tirets, coquille d'OCR).
    L = len(ex)
    best, best_pos = 0.0, -1
    step = max(1, L // 8)
    for pos in range(0, max(1, len(hay) - L + 1), step):
        r = SequenceMatcher(None, ex, hay[pos : pos + L], autojunk=False).ratio()
        if r > best:
            best, best_pos = r, pos
    if best >= threshold and best_pos >= 0:
        # Affinage autour de la meilleure position.
        for pos in range(max(0, best_pos - step), min(len(hay) - L, best_pos + step) + 1):
            r = SequenceMatcher(None, ex, hay[pos : pos + L], autojunk=False).ratio()
            if r >= best:
                best, best_pos = r, pos
        start = positions[best_pos]
        end = positions[min(len(positions) - 1, best_pos + L - 1)] + 1
        return source[start:end]
    return None
