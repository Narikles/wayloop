from app.modules.masking import MASK, mask_cv
from app.text_utils import find_excerpt

CV = """Camille Martin
14 rue Garibaldi, 69006 Lyon
06 12 34 56 78 · camille.martin@example.org
Née le 12/03/1994 · Mariée, 2 enfants · Nationalité : française
Âge : 32 ans
RQTH
Assistante ADV — 2019 - 2024 — 12 ans d'expérience dans le négoce
Permis B"""


def test_masks_personal_data():
    masked, counts = mask_cv(CV, ["Camille", "Martin"])
    for leaked in ("Camille", "Martin", "Garibaldi", "06 12", "@example", "12/03/1994", "Mariée", "enfants",
                   "française", "32 ans", "RQTH"):
        assert leaked not in masked, leaked
    for kept in ("Assistante ADV", "2019 - 2024", "12 ans d'expérience", "Permis B"):
        assert kept in masked, kept
    assert {"identite", "contact", "adresse", "age", "famille", "nationalite", "sante"} <= set(counts)
    assert MASK in masked


def test_find_excerpt_tolerates_case_accents_spaces():
    src = "Expérience\nAssistante  ADV — Matériaux Rhône SA\n2021 - aujourd'hui"
    assert find_excerpt("assistante adv — materiaux rhone sa", src) == "Assistante  ADV — Matériaux Rhône SA"


def test_find_excerpt_rejects_invention():
    src = "Vendeur en magasin 2020 - 2024. Encaissement, mise en rayon."
    assert find_excerpt("5 ans d'expérience en administration des ventes", src) is None
