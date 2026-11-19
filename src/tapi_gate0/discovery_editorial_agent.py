"""Local agent preview over reaudited exploratory rows, not scientific recommendations.

No raw captions, external calls, independent validation, publishing or Studio writes.
"""
from collections import defaultdict
from hashlib import sha256
from random import Random
from statistics import mean
from fractions import Fraction

from .discovery_editorial_descriptive import er, analyze_editorial

VERSION = "bd-editorial-agent-preview.v1"
COHORTS = ("technical_all", "semantic_exploratory")
SCOPES = ("observables_global", "observables_within_profile")
FIELDS = ("format", "topic", "cta")
BOOTSTRAP_REPLICATES = 1000
MIN_MATCHED_PROFILES = 3
MIN_TOP_CASES = 3
MIN_TOP_PROFILES = 2
MIN_TOP_OBSERVED = 5


def _cohort(rows, name):
    return rows if name == COHORTS[0] else [
        r for r in rows if r["tier"] in ("grounded_positive", "semantic_consensus_only")]


def cluster_contrast(rows, top_ids, field, value):
    """Resample matched profile differences, fixed ranking membership.

    This is a sensitivity distribution of an equal-profile-weighted observed
    contrast, not a CI for a population effect or a re-ranked cluster bootstrap.
    """
    groups = defaultdict(lambda: [[], []])
    for r in rows:
        if r[field] is not None:
            groups[r["username"]][0 if r["content_id"] in top_ids else 1].append(r[field] == value)
    differences = [Fraction(sum(a), len(a))-Fraction(sum(b), len(b))
                   for _, (a,b) in sorted(groups.items()) if a and b]
    n = len(differences)
    result = {"matched_profiles":n, "replicates":0, "mean_difference_pp":None,
              "resampling_interval_pp":None, "fixed_membership":True,
              "population_inference":False}
    if n:
        result["mean_difference_pp"] = round(float(mean(differences))*100,6)
    if n >= MIN_MATCHED_PROFILES:
        rng = Random(20261114)
        # Work in floats only after exact profile proportions have been computed.
        values = [float(d) for d in differences]
        simulated = sorted(mean(rng.choices(values, k=n))*100 for _ in range(BOOTSTRAP_REPLICATES))
        result.update(replicates=BOOTSTRAP_REPLICATES,
                      resampling_interval_pp=[round(simulated[24],6),round(simulated[974],6)])
    return result



def describe_finding_limits(views, sensitivity):
    """Describe evidence limits without changing selection or granting approval.

    Fractions use all ranked posts as denominator: missing lexical labels
    remain unknown, never negative. Four views overlap and are not replications.
    Bootstrap ranges are conditional sensitivity, not confidence intervals.
    """
    expected = {(cohort, scope) for cohort in COHORTS for scope in SCOPES}
    if set(views) != expected or set(sensitivity) != set(COHORTS):
        raise ValueError("BD_AGENT_EVIDENCE_PARTITION_MISMATCH")
    coverage = {}
    for cohort, scope in sorted(expected):
        view = views[(cohort, scope)]
        top, rest = view["top_total"], view["rest_total"]
        top_observed, rest_observed = view["top_observed"], view["rest_observed"]
        if (top <= 0 or rest <= 0
                or not 0 <= top_observed <= top
                or not 0 <= rest_observed <= rest):
            raise ValueError("BD_AGENT_EVIDENCE_COVERAGE_INVALID")
        coverage[cohort + "." + scope] = {
            "top_observed": top_observed,
            "top_total": top,
            "top_coverage_fraction": round(top_observed / top, 6),
            "rest_observed": rest_observed,
            "rest_total": rest,
            "rest_coverage_fraction": round(rest_observed / rest, 6),
            "unknown_is_not_negative": True,
        }
    intervals = {}
    for cohort in COHORTS:
        measure = sensitivity[cohort]
        bounds = measure["resampling_interval_pp"]
        if bounds is not None and (len(bounds) != 2 or bounds[0] > bounds[1]):
            raise ValueError("BD_AGENT_SENSITIVITY_INTERVAL_INVALID")
        intervals[cohort] = {
            "matched_profiles": measure["matched_profiles"],
            "resampling_interval_available": bounds is not None,
            "interval_includes_zero": (
                bounds[0] <= 0 <= bounds[1] if bounds is not None else None
            ),
            "interval_is_population_confidence_interval": False,
        }
    return {
        "observables_provenance": "caption_lexical_not_grounded_rubric",
        "four_views_are_independent_replications": False,
        "coverage": coverage,
        "sensitivity": intervals,
        "scientific_or_causal_claim_supported": False,
        "editorial_recommendation_approved": False,
    }


def _references(rows, rankings, field, value):
    # Prefer semantic cohort and both ranks; then diverse creators, max five.
    sem = rankings[COHORTS[1]]
    global_ids = set(sem.get("global_top", []))
    within_ids = set(sem.get("within_profile_top", []))
    candidates = [r for r in rows if r[field] == value and
                  r["content_id"] in (global_ids | within_ids)]
    candidates.sort(key=lambda r:(-(r["content_id"] in global_ids and r["content_id"] in within_ids),
                                   -er(r),r["content_id"]))
    chosen, profiles = [], set()
    for r in candidates:
        if r["username"] in profiles:
            continue
        profiles.add(r["username"])
        chosen.append({"content_id":r["content_id"],"snapshot_id":r["snapshot_id"],
                       "username":r["username"],"tier":r["tier"],
                       "er_fraction":str(er(r)),"caption_sha256":r["caption_sha256"],
                       "in_global_top":r["content_id"] in global_ids,
                       "in_within_profile_top":r["content_id"] in within_ids,
                       "observed_field":field,"observed_value":value})
        if len(chosen) == 5:
            break
    return chosen


DRAFTS = (
    ("Venda mais com um preço que faça sentido", "Liste os custos de cada produto, considere suas despesas e compare a margem antes de definir o preço.", "Salve para revisar sua precificação."),
    ("Seu cliente saiu sem comprar. E agora?", "Anote as dúvidas mais frequentes, explique o benefício do produto e facilite o próximo contato.", "Conte qual dúvida você mais recebe."),
    ("Organize os pedidos sem perder vendas", "Registre pedido, valor, prazo e pagamento em uma lista única. Revise as pendências no fim do dia.", "Salve este checklist."),
    ("Mais vendas nem sempre significam mais lucro", "Compare receita, custos e margem. Separe os gastos do negócio e revise os produtos que mais contribuem para o resultado.", "Compartilhe com quem empreende."),
    ("Faça o cliente lembrar do seu negócio", "Prepare um atendimento claro, combine o prazo e faça um acompanhamento respeitoso depois da entrega.", "Comente uma prática que funciona na sua loja."),
)


def build_agent_preview(rows, *, tenant, as_of, manifest_sha256):
    """Only call with rows revalidated against live local scope and snapshots."""
    from .agent_evidence_b2 import CreativeSpecHandoff
    editorial = analyze_editorial(rows)
    rankings = editorial["private_rankings"]
    comparisons = defaultdict(dict)
    for name in COHORTS:
        summary = editorial["cohorts"][name]
        for scope in SCOPES:
            for field in FIELDS:
                dist = summary.get(scope, {}).get(field)
                if dist is None:
                    continue
                for item in dist["comparisons"]:
                    comparisons[field,item["value"]][name,scope] = {
                        **item, "top_observed":dist["top"]["observed"],
                        "rest_observed":dist["rest"]["observed"],
                        "top_total":dist["top"]["posts"],"rest_total":dist["rest"]["posts"]}
    findings, refs_by_id, creatives = [], {}, []
    for (field,value), views in sorted(comparisons.items()):
        if len(views) != 4 or not all(
            v["difference_percentage_points"] is not None and v["difference_percentage_points"] > 0
            and v["top_count"] >= MIN_TOP_CASES and v["top_profiles"] >= MIN_TOP_PROFILES
            and v["top_observed"] >= MIN_TOP_OBSERVED for v in views.values()):
            continue
        refs = _references(rows, rankings, field, value)
        if len(refs) < MIN_TOP_PROFILES:
            continue
        for r in refs:
            refs_by_id.setdefault(r["content_id"], {k:v for k,v in r.items()
                                                     if k not in ("observed_field","observed_value")})
        sensitivity = {}
        for name in COHORTS:
            group = _cohort(rows,name)
            supported_ids = set(rankings[name].get("percentiles",{}))
            sensitivity[name] = cluster_contrast(
                [r for r in group if r["content_id"] in supported_ids],
                set(rankings[name].get("within_profile_top",[])), field, value)
        finding = {"kind":"exploratory_editorial_hypothesis","field":field,"value":value,
                   "four_view_concordance":True,
                   "views":{name+"."+scope:v for (name,scope),v in views.items()},
                   "cluster_sensitivity":sensitivity,
                   "evidence_limits":describe_finding_limits(views, sensitivity),
                   "reference_content_ids":[r["content_id"] for r in refs],
                   "claim":"Sinal descritivo para investigação editorial; não implica causalidade nem audiência MPE validada."}
        findings.append(finding)
        # Only sales-topic drafts use this authored template library. Other
        # observations may be inspected, never automatically turned into advice.
        if (field,value) == ("topic","vendas"):
            for index,(headline,body,cta) in enumerate(DRAFTS,1):
                rid = finding["reference_content_ids"]
                key = sha256((tenant+"|"+manifest_sha256+"|"+str(index)+"|"+",".join(rid)).encode()).hexdigest()[:24]
                spec = CreativeSpecHandoff(spec_id="exploratory."+key,tenant_id=tenant,
                    objective="Testar uma hipótese editorial de educação em vendas para pequenos negócios.",
                    headline=headline,body=body,cta=cta,platform_intent="instagram_carousel",
                    reference_content_ids=rid)
                creatives.append({"creative_spec":spec.model_dump(mode="json"),
                                  "status":"draft_hypothesis_not_approved",
                                  "format_and_cta_are_design_choices":True,
                                  "hypothesis_field":field,"hypothesis_value":value})
    return {"schema_version":VERSION,"as_of":as_of,"manifest_sha256":manifest_sha256,
            "modes":{"analisar":"descriptive_findings","recomendar":"inspect_or_test_hypotheses",
                     "gerar_criativo":"authored_template_drafts_only"},
            "findings":findings,"reference_posts":list(refs_by_id.values()),"creatives":creatives,
            "confidence_flag":"EXPLORATORY_NOT_INDEPENDENTLY_VALIDATED",
            "explanation":"Hipóteses de quatro recortes sobrepostos, não replicações independentes. Referências locais rastreáveis; rascunhos não autorizam publicação.",
            "action":"inspect_or_test_hypotheses" if findings else "collect_more_evidence",
            "scientific_admissions":0,"scientifically_validated":False,"publication_approved":False,
            "studio_mutated":False,"causal_claims":False,
            "selection_policy":{"min_top_count":MIN_TOP_CASES,"min_top_profiles":MIN_TOP_PROFILES,
                                "min_top_observed":MIN_TOP_OBSERVED,"positive_in_all_four_views":True}}
