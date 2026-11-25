"""CAP-003: explicit 20-field coverage of reaudited, scoped caption candidates.

Not a RubricAssessment, human review or validated label. No visual inference,
negative CTA inference, arbitrary length bins or invented subjective scores.
"""
from collections import Counter
from statistics import median
from .domain import RUBRIC_FIELD_NAMES

VERSION = "bd-caption-rubric-coverage.v1"
STATES = ("metadata_observed", "lexical_candidate", "measurement_only", "not_assessed")
REQUIREMENTS = {
    "tipo_post":"metadata",
    "duracao_faixa":"authorized duration metadata and defined bins",
    "formato_video":"authorized video or multimodal evidence",
    "hook_primeiros_3s":"authorized temporal video evidence",
    "tipo_hook":"authorized opening segment and semantic evidence",
    "forca_hook_0a10":"authorized opening segment and calibrated scoring",
    "tema_principal":"caption lexical candidate or validated semantic evidence",
    "tem_rosto":"authorized image or video",
    "criador_e_empreendedor_real":"independent external proof",
    "prova_social":"reliable caption or authorized multimodal evidence",
    "texto_na_tela":"authorized image or video",
    "legenda_tamanho":"caption character measurement; rubric bins not defined",
    "ritmo_cortes_0a10":"authorized temporal video and calibrated scoring",
    "tom":"reliable semantic evidence",
    "usa_linguagem_regional":"reliable linguistic evidence",
    "clareza_mensagem_0a10":"calibrated semantic scoring",
    "tem_cta":"caption lexical candidate; absence is not negative",
    "tipo_cta":"caption lexical candidate or validated semantic evidence",
    "oferta_ou_beneficio_explicito":"reliable semantic evidence",
    "elementos_top5":"validated multimodal evidence and scoring",
}


def _states(row):
    if row["format"] not in ("reels","carrossel") or type(row["caption_chars"]) is not int or row["caption_chars"]<=0:
        raise ValueError("BD_EXPLORATORY_RUBRIC_INPUT_INVALID")
    states=dict.fromkeys(RUBRIC_FIELD_NAMES,"not_assessed")
    states["tipo_post"]="metadata_observed"
    states["legenda_tamanho"]="measurement_only"
    if row["topic"] is not None:
        states["tema_principal"]="lexical_candidate"
    if row["cta"] is not None:
        states["tem_cta"]=states["tipo_cta"]="lexical_candidate"
    return states


def _cohort(rows):
    counts={field:Counter() for field in RUBRIC_FIELD_NAMES}
    for row in rows:
        for field,state in _states(row).items():
            counts[field][state]+=1
    n=len(rows)
    def distribution(key):
        return dict(sorted(Counter(r[key] for r in rows if r[key] is not None).items()))
    return {"posts":n,"profiles":len({r["username"] for r in rows}),
            "fields":[{"field":field,"counts":{state:counts[field][state] for state in STATES},
                       "required_evidence":REQUIREMENTS[field]} for field in RUBRIC_FIELD_NAMES],
            "metadata_observed_cells":sum(c["metadata_observed"] for c in counts.values()),
            "lexical_candidate_cells":sum(c["lexical_candidate"] for c in counts.values()),
            "measurement_only_cells":sum(c["measurement_only"] for c in counts.values()),
            "not_assessed_cells":sum(c["not_assessed"] for c in counts.values()),
            "total_rubric_cells":n*len(RUBRIC_FIELD_NAMES),
            "caption_character_count":{"min":min((r["caption_chars"] for r in rows),default=None),
                "median":median([r["caption_chars"] for r in rows]) if n else None,
                "max":max((r["caption_chars"] for r in rows),default=None)},
            "candidate_topic_counts":distribution("topic"),"candidate_cta_counts":distribution("cta")}


def rubric_coverage(rows):
    if set(REQUIREMENTS)!=set(RUBRIC_FIELD_NAMES) or len({r["content_id"] for r in rows})!=len(rows):
        raise ValueError("BD_EXPLORATORY_RUBRIC_INPUT_INVALID")
    cohorts={"technical_all":rows,
             "semantic_exploratory":[r for r in rows if r["tier"] in ("grounded_positive","semantic_consensus_only")]}
    return {"policy_version":VERSION,"field_count":len(RUBRIC_FIELD_NAMES),
            "cohorts":{name:_cohort(group) for name,group in cohorts.items()},
            "candidate_labels_validated":False,"rubric_assessments_written":0,
            "human_reviews":0,"scientific_admissions":0,"media_modalities_assessed":False}
