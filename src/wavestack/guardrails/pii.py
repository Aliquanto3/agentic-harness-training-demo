"""Personal-data guardrail (CAP-5): Microsoft Presidio, `fr_core_news_sm` (spaCy) for names
and places, plus a few French patterns Presidio has no built-in for.

shortcut: `presidio-fr` is not a published package (the Hub lists only a community add-on of
patterns, not a maintained pip install) — the orchestrator authorized the simplest working
substitute. These four patterns are added as ordinary `PatternRecognizer`s instead:
NIR (social security number), SIRET/SIREN, a tax number and a licence plate. Presidio's own
built-ins already cover EMAIL_ADDRESS and IBAN_CODE; PHONE_NUMBER gets an FR-region recognizer
with French context words on top of the built-in one.
"""

from __future__ import annotations

from wavestack.guardrails.contract import Classification, Entity

THRESHOLD = 0.4  # brownfield.md: 0.73 precision measured at Presidio's own default threshold
LABELS = {
    "EMAIL_ADDRESS": "E-MAIL",
    "PHONE_NUMBER": "TÉLÉPHONE",
    "IBAN_CODE": "IBAN",
    "PERSON": "NOM",
    "LOCATION": "LIEU",
    "ORGANIZATION": "ORGANISATION",
    "NIR_FR": "NIR",
    "SIRET_FR": "SIRET",
    "TAX_ID_FR": "NUMÉRO FISCAL",
    "PLATE_FR": "PLAQUE",
}

# French patterns Presidio has no built-in for (story 4, "presidio-fr" substitute).
_FR_PATTERNS = (
    # NIR: 1 (sexe) + 2 (année) + 2 (mois) + 2 (département, 2A/2B compris) + 3 + 3 + 2 (clé).
    (
        "NIR_FR",
        r"\b[12]\s?\d{2}\s?(0[1-9]|1[0-2])\s?(\d{2}|2[AB])\s?\d{3}\s?\d{3}\s?\d{2}\b",
        0.6,
        None,
    ),
    # SIREN/SIRET and the tax number are bare digit runs: under THRESHOLD alone, detected only
    # with a context word nearby (Presidio adds 0.35), so "commande 123456789" stays untouched.
    ("SIRET_FR", r"\b\d{3}\s?\d{3}\s?\d{3}(\s?\d{5})?\b", 0.3, ["siret", "siren"]),
    (
        "TAX_ID_FR",
        r"\b[0-3]\d\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b",
        0.3,
        ["fiscal", "spi", "impôt", "impôts", "impots"],
    ),
    ("PLATE_FR", r"\b[A-Z]{2}-\d{3}-[A-Z]{2}\b", 0.6, None),
)
_PHONE_CONTEXT = ["téléphone", "tél", "portable", "mobile", "joignable", "appeler", "numéro"]


def _build_analyzer():
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import PhoneRecognizer

    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "fr", "model_name": "fr_core_news_sm"}],
        }
    )
    analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["fr"])
    for entity, regex, score, context in _FR_PATTERNS:
        recognizer = PatternRecognizer(
            supported_entity=entity,
            patterns=[Pattern(name=entity, regex=regex, score=score)],
            context=context,
            supported_language="fr",
        )
        analyzer.registry.add_recognizer(recognizer)
    # The built-in phone recognizer has no FR region and English context words only.
    analyzer.registry.add_recognizer(
        PhoneRecognizer(supported_language="fr", supported_regions=("FR",), context=_PHONE_CONTEXT)
    )
    return analyzer


class PiiGuardrail:
    """Lazy: `fr_core_news_sm` and Presidio's engines load on the first `classify`."""

    def __init__(self) -> None:
        self._analyzer = None
        self._anonymizer = None

    @property
    def loaded(self) -> bool:
        return self._analyzer is not None

    def ensure_loaded(self) -> None:
        if self.loaded:
            return
        from presidio_anonymizer import AnonymizerEngine

        self._analyzer = _build_analyzer()
        self._anonymizer = AnonymizerEngine()

    def classify(self, text: str) -> Classification:
        self.ensure_loaded()
        results = [
            r for r in self._analyzer.analyze(text=text, language="fr") if r.score >= THRESHOLD
        ]
        entities = tuple(
            Entity(
                label=LABELS.get(r.entity_type, r.entity_type),
                start=r.start,
                end=r.end,
                score=r.score,
            )
            for r in results
        )
        top = max((r.score for r in results), default=0.0)
        return Classification(
            detected=bool(results), score=top, threshold=THRESHOLD, entities=entities
        )

    def mask(self, text: str, entities: tuple[Entity, ...]) -> str:
        if not entities:
            return text
        from presidio_anonymizer import OperatorConfig
        from presidio_anonymizer.entities import RecognizerResult

        self.ensure_loaded()
        reverse = {v: k for k, v in LABELS.items()}
        results = [
            RecognizerResult(
                entity_type=reverse.get(e.label, e.label), start=e.start, end=e.end, score=e.score
            )
            for e in entities
        ]
        operators = {
            reverse.get(e.label, e.label): OperatorConfig("replace", {"new_value": f"[{e.label}]"})
            for e in entities
        }
        return self._anonymizer.anonymize(
            text=text, analyzer_results=results, operators=operators
        ).text

    def unload(self) -> None:
        self._analyzer = None
        self._anonymizer = None
