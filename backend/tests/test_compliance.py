from app.modules.compliance import apply_replacement, check_criteria, check_text, has_blocking

BAD = """Assistante commerciale
Nous cherchons une femme uniquement, de moins de 35 ans, bonne présentation, habitant à Villeurbanne.
Anglais langue maternelle apprécié. Jeune diplômé accepté. CV avec photo obligatoire. Indiquez vos prétentions salariales."""


def rules(text):
    return {a["rule"]: a for a in check_text(text)}


def test_blocking_mentions():
    r = rules(BAD)
    assert r["sex_required"]["level"] == "block"
    assert r["age_limit"]["level"] == "block"
    assert has_blocking(check_text(BAD))


def test_warnings_with_reformulation():
    r = rules(BAD)
    for rule in ("appearance", "residence", "mother_tongue", "young", "photo", "salary_history", "gendered_title",
                 "salary_missing"):
        assert rule in r, rule
    assert r["appearance"]["replacement"] == "tenue adaptée à l'accueil de la clientèle"


def test_family_situation_is_blocking():
    alerts = check_text("Vendeur (H/F)\nSalaire 1 900 € brut. Idéalement célibataire et sans enfants.")
    assert [a["level"] for a in alerts if a["rule"] == "family"] == ["block", "block"]


def test_experience_years_are_not_age():
    text = "Comptable (H/F)\n5 ans d'expérience minimum. Salaire : 2 500 € brut par mois."
    assert check_text(text) == []


def test_apply_replacement_one_gesture():
    alert = rules(BAD)["mother_tongue"]
    fixed = apply_replacement(BAD, alert)
    assert "langue maternelle" not in fixed and "niveau C1" in fixed
    alert = rules(BAD)["gendered_title"]
    assert apply_replacement(BAD, alert).splitlines()[0].endswith("(H/F)")


def test_salary_present_no_warning():
    assert "salary_missing" not in rules("Vendeur (H/F)\nRémunération : 1 900 € brut / mois.")


def test_discriminatory_criteria_refused():
    refused = check_criteria([{"id": "c1", "label": "Habiter à proximité du magasin"},
                              {"id": "c2", "label": "Permis B"}, {"id": "c3", "label": "Sans enfants"}])
    assert {r["criterion_id"] for r in refused} == {"c1", "c3"}


def test_sanitize_fixes_silently_what_can_be_fixed():
    from app.modules.compliance import remove_mention, sanitize

    fixed, issues = sanitize("Vendeuse\nBonne présentation exigée. Rémunération : 1 900 € brut / mois.")
    assert issues == []
    assert fixed.splitlines()[0] == "Vendeuse (H/F)" and "Tenue adaptée" in fixed
    fixed, issues = sanitize("Vendeur (H/F)\nCandidats de moins de 30 ans. Salaire 1 900 € brut.")
    assert [(i["rule"], i["match"]) for i in issues] == [("age_limit", "moins de 30 ans")]
    cleaned = remove_mention(fixed, issues[0]["match"])
    assert sanitize(cleaned)[1] == [] and "30 ans" not in cleaned
