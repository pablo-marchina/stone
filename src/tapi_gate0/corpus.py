"""Auditable, read-only corpus coverage over explicitly registered source accounts.

A profile registry is a sampling frame, NOT legal authorization or an OAuth grant.
No provider APIs are called, nor are credentials inspected or returned.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Table, Column, String, ForeignKeyConstraint, select, insert
from sqlalchemy.exc import IntegrityError

from .connectors import Platform, ConnectorError
from .domain import ContentItem, MetricsCreate
from .identity import IdentityFailure
from .ingestion import source_grants, ingestion_records
from .sa_store import metadata, content_items, metrics_snapshots
from .storage import now_utc

corpus_profiles = Table('corpus_profiles', metadata,
    Column('tenant_id', String(128), primary_key=True),
    Column('platform', String(32), primary_key=True),
    Column('source_account_id', String(128), primary_key=True),
    Column('sector', String(24), nullable=False),
    Column('sampling_stratum', String(80), nullable=False),
    Column('evidence_reference', String(512), nullable=False),
    Column('registered_at', String(40), nullable=False),
    ForeignKeyConstraint(['tenant_id','platform','source_account_id'],
                         ['ingestion_source_grants.tenant_id',
                          'ingestion_source_grants.platform',
                          'ingestion_source_grants.source_account_id']))

class CorpusProfileCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    platform: Platform
    source_account_id: str = Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9_-]+$')
    sector: Literal['commerce','food','services','beauty','other']
    sampling_stratum: str = Field(min_length=1,max_length=80,pattern=r'^[a-z0-9][a-z0-9_-]*$')
    evidence_reference: str = Field(min_length=12,max_length=512)


def register_profile(engine, tenant: str, payload: CorpusProfileCreate):
    """Record curation intent only after an administrative source grant exists."""
    with engine.begin() as db:
        grant = db.execute(select(source_grants.c.source_account_id).where(
            source_grants.c.tenant_id == tenant,
            source_grants.c.platform == payload.platform.value,
            source_grants.c.source_account_id == payload.source_account_id)).first()
        if not grant:
            raise ConnectorError('SOURCE_GRANT_REQUIRED_FOR_CORPUS',403)
        try:
            db.execute(insert(corpus_profiles).values(
                tenant_id=tenant,platform=payload.platform.value,
                source_account_id=payload.source_account_id,sector=payload.sector,
                sampling_stratum=payload.sampling_stratum,
                evidence_reference=payload.evidence_reference,
                registered_at=now_utc().isoformat()))
        except IntegrityError as exc:
            raise ConnectorError('CORPUS_PROFILE_ALREADY_REGISTERED',409) from exc
    return {'platform': payload.platform.value, 'source_account_id': payload.source_account_id,
            'registered': True, 'access_verified': False,
            'note': 'Sampling registration is not OAuth or permission verification.'}


def corpus_data_card(engine, tenant: str, *, as_of: datetime | None = None,
                     min_age_days: int = 14) -> dict:
    """Report eligible *Instagram* posts; keep YouTube separate as complementary data."""
    as_of = as_of or now_utc()
    if as_of.tzinfo is None:
        raise ValueError('as_of must be timezone-aware')
    as_of = as_of.astimezone(timezone.utc)
    if min_age_days < 14 or min_age_days > 3650:
        raise ValueError('min_age_days must be between 14 and 3650')
    with engine.connect() as db:
        profiles = db.execute(select(corpus_profiles).where(
            corpus_profiles.c.tenant_id == tenant)).mappings().all()
        grants = db.execute(select(source_grants).where(
            source_grants.c.tenant_id == tenant)).mappings().all()
        records = db.execute(select(ingestion_records).where(
            ingestion_records.c.tenant_id == tenant)).mappings().all()
        content = db.execute(select(content_items.c.id, content_items.c.payload).where(
            content_items.c.tenant_id == tenant)).all()
        metrics = db.execute(select(metrics_snapshots.c.content_id,metrics_snapshots.c.payload).where(
            metrics_snapshots.c.tenant_id == tenant)).all()

    registry = {(x['platform'],x['source_account_id']):x for x in profiles}
    grant_map = {(x['platform'],x['source_account_id']):x for x in grants}
    posts = {x[0]: ContentItem.model_validate_json(x[1]) for x in content}
    latest = {}
    for cid, blob in metrics:
        m = MetricsCreate.model_validate_json(blob)
        if m.observed_at > as_of:
            continue
        prev = latest.get(cid)
        if prev is None or (m.observed_at,m.snapshot_id) > (prev.observed_at,prev.snapshot_id):
            latest[cid] = m

    counts = dict(eligible_instagram_posts=0, eligible_instagram_profiles=0,
                  eligible_youtube_supplementary_posts=0, excluded_unregistered=0,
                  excluded_grant_or_technical=0, excluded_too_recent=0,
                  excluded_without_metrics=0, excluded_nonpositive_denominator=0)
    sectors = {sector: 0 for sector in ('commerce','food','services','beauty','other')}
    strata = {}
    for profile in profiles:
        if profile['platform'] == Platform.INSTAGRAM.value:
            entry = strata.setdefault(profile['sampling_stratum'],
                                      {'registered_profiles':0, 'eligible_profiles':0, 'eligible_posts':0})
            entry['registered_profiles'] += 1
    qualifying_instagram_accounts = set()
    for rec in records:
        key = (rec['platform'],rec['source_account_id'])
        profile = registry.get(key)
        if not profile:
            counts['excluded_unregistered'] += 1
            continue
        grant = grant_map.get(key)
        if (not grant or not grant['enabled'] or
            datetime.fromisoformat(grant['expires_at']) <= as_of or
            not grant['technical_verified_at']):
            counts['excluded_grant_or_technical'] += 1
            continue
        post = posts.get(rec['content_id'])
        if post is None or post.is_synthetic:
            counts['excluded_unregistered'] += 1
            continue
        if (as_of - post.published_at).total_seconds() < min_age_days * 86400:
            counts['excluded_too_recent'] += 1
            continue
        m = latest.get(rec['content_id'])
        if m is None:
            counts['excluded_without_metrics'] += 1
            continue
        if m.follower_count <= 0:
            counts['excluded_nonpositive_denominator'] += 1
            continue
        if rec['platform'] == Platform.INSTAGRAM.value:
            counts['eligible_instagram_posts'] += 1
            sectors[profile['sector']] += 1
            strata[profile['sampling_stratum']]['eligible_posts'] += 1
            qualifying_instagram_accounts.add(key)
        else:
            counts['eligible_youtube_supplementary_posts'] += 1

    counts['eligible_instagram_profiles'] = len(qualifying_instagram_accounts)
    for key in qualifying_instagram_accounts:
        strata[registry[key]['sampling_stratum']]['eligible_profiles'] += 1
    active_grants = sum(bool((g:=grant_map.get((p['platform'],p['source_account_id'])))
        and g['enabled'] and datetime.fromisoformat(g['expires_at']) > as_of) for p in profiles)
    technically_checked = sum(bool((g:=grant_map.get((p['platform'],p['source_account_id'])))
        and g['enabled'] and datetime.fromisoformat(g['expires_at']) > as_of
        and g['technical_verified_at']) for p in profiles)
    good_posts = counts['eligible_instagram_posts']
    good_profiles = counts['eligible_instagram_profiles']
    return {
        'as_of': as_of.isoformat(),
        'target': {'minimum_profiles': 30, 'minimum_posts': 2000,
                   'maximum_posts': 5000, 'minimum_post_age_days': min_age_days,
                   'primary_platform': 'instagram'},
        'sampling_frame': {'registered_profiles': len(profiles),
                           'with_current_administrative_grant': active_grants,
                           'with_prior_technical_verification': technically_checked},
        'observed': counts,
        'instagram_posts_by_operator_sector': sectors,
        'instagram_sampling_strata': strata,
        'deficit': {'profiles': max(0, 30-good_profiles),
                    'posts': max(0, 2000-good_posts)},
        'target_reached': good_profiles>=30 and 2000<=good_posts<=5000,
        'caveats': [
            'Registry entries and administrative grants do not independently prove legal rights.',
            'Technical verification records a prior API response, not guaranteed current token access.',
            'Instagram follower counts may reflect observation time, not publication time.',
            'YouTube Shorts are complementary and excluded from the primary Instagram target.',
            'This is observational corpus coverage, not a causal engagement claim.',
        ],
        'external_requests_performed': 0,
    }


def router_for_corpus(identity, engine):
    router = APIRouter(prefix='/v1/corpus',tags=['Authorized corpus audit'])

    def principal(request: Request):
        scheme, _, token = request.headers.get('authorization','').partition(' ')
        if scheme.lower() != 'bearer' or not token or ' ' in token:
            raise IdentityFailure()
        return identity.resolve(token)

    @router.post('/profiles',status_code=201)
    def create_profile(payload:CorpusProfileCreate, p=Depends(principal)):
        if p.role != 'admin':
            raise IdentityFailure('FORBIDDEN',403)
        return register_profile(engine,p.tenant_id,payload)

    @router.get('/data-card')
    def get_data_card(min_age_days:int=14,p=Depends(principal)):
        if p.role not in {'admin','researcher','service'}:
            raise IdentityFailure('FORBIDDEN',403)
        if not 14<=min_age_days<=3650:
            raise ConnectorError('INVALID_MIN_AGE_DAYS',422)
        return corpus_data_card(engine,p.tenant_id,min_age_days=min_age_days)

    return router
