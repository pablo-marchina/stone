"""Bounded Instagram Business Discovery evidence for approved MPE sources only.

Produces an offline, provenance-rich eligibility *candidate* report. It does
not insert data in the application's corpus DB or independently certify rights.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

from .business_discovery import BusinessDiscoveryProbe, CURSOR
from .connectors import ConnectorError, OfficialHttp, Platform, _date, _integer
from .domain import MediaType

IG_ID = re.compile(r"[0-9]{5,32}\Z")


def canonical_hash(value: dict) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def _instagram_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    return (parts.scheme == "https" and parts.netloc == "www.instagram.com"
            and parts.path.startswith(("/reel/", "/p/", "/tv/")))


class FirstEligibleSampler:
    def __init__(self, http: OfficialHttp):
        self.http = http

    def scan(self, viewer_id: str, token: str, source_approval: dict, *,
             limit: int = 10, max_pages: int = 3,
             as_of: datetime | None = None) -> dict:
        """Only called after SourceFrame's local proof/operation gates pass."""
        from .mpe_sources import BANNED_TECHNICAL_TEST_ACCOUNTS, REQUIRED_SCOPES
        if not IG_ID.fullmatch(viewer_id):
            raise ConnectorError("INVALID_VIEWER_IG_ID", 422)
        if not isinstance(token, str) or len(token) < 10:
            raise ConnectorError("CREDENTIAL_MISSING", 403)
        if not 1 <= limit <= 10 or not 1 <= max_pages <= 3:
            raise ConnectorError("INVALID_SAMPLE_LIMIT", 422)
        target = source_approval.get("username", "")
        if (not isinstance(target, str) or target.casefold() in BANNED_TECHNICAL_TEST_ACCOUNTS
            or not re.fullmatch(r"[A-Za-z0-9_.]{1,30}", target)):
            raise ConnectorError("INVALID_CURATED_SOURCE", 403)
        if (not source_approval.get("operator_evidence_verified") or
            not REQUIRED_SCOPES.issubset(source_approval.get("allowed_operations", []))):
            raise ConnectorError("CURATED_SOURCE_APPROVAL_REQUIRED", 403)
        as_of = as_of or datetime.now(timezone.utc)
        if as_of.tzinfo is None:
            raise ConnectorError("INVALID_AS_OF_TIME", 422)
        as_of = as_of.astimezone(timezone.utc)
        threshold = as_of - timedelta(days=14)
        counts = {name: 0 for name in (
            "returned", "reels", "carousels", "other_formats", "too_recent",
            "invalid_metadata", "missing_metrics", "invalid_denominator",
            "eligible_14d", "duplicates")}
        media_records = []
        seen = set()
        after = None
        cursors_seen = set()
        page_hashes = []
        profile = None
        pagination_status = "NOT_CHECKED"
        pages_examined = 0
        for _ in range(max_pages):
            payload = self.http.get(Platform.INSTAGRAM, viewer_id,
                {"fields": BusinessDiscoveryProbe._fields(target, limit, after)}, token)
            if str(payload.get("id")) != viewer_id:
                raise ConnectorError("VIEWER_ACCOUNT_MISMATCH", 403)
            discovered = payload.get("business_discovery")
            if (not isinstance(discovered, dict) or
                not isinstance(discovered.get("username"), str) or
                discovered["username"].casefold() != target.casefold()):
                raise ConnectorError("DISCOVERED_ACCOUNT_MISMATCH", 403)
            actual_id = str(discovered.get("id", ""))
            if not IG_ID.fullmatch(actual_id):
                raise ConnectorError("INVALID_DISCOVERED_ACCOUNT", 502)
            followers = _integer(discovered.get("followers_count"))
            media_count = _integer(discovered.get("media_count"))
            if profile is None:
                profile = {"instagram_user_id": actual_id, "username": target,
                           "followers_observed_at": as_of.isoformat(),
                           "followers_observed_now": followers,
                           "provider_total_media_count": media_count}
            elif profile["instagram_user_id"] != actual_id:
                raise ConnectorError("DISCOVERY_PROFILE_CHANGED_DURING_PAGINATION", 502)
            media = discovered.get("media")
            if not isinstance(media, dict) or not isinstance(media.get("data"), list):
                raise ConnectorError("DISCOVERY_MEDIA_UNAVAILABLE", 502)
            rows = media["data"][:limit]
            pages_examined += 1
            # Integrity digest of only the whitelisted metadata obtained from
            # the Graph response; not a signature from Meta.
            page_hashes.append(canonical_hash({"source": actual_id, "items": rows}))
            for raw in rows:
                counts["returned"] += 1
                if not isinstance(raw, dict) or not IG_ID.fullmatch(str(raw.get("id", ""))):
                    counts["invalid_metadata"] += 1
                    continue
                mid = str(raw["id"])
                if mid in seen:
                    counts["duplicates"] += 1
                    continue
                seen.add(mid)
                if raw.get("media_type") == "CAROUSEL_ALBUM":
                    kind = MediaType.CAROUSEL
                    counts["carousels"] += 1
                elif raw.get("media_product_type") == "REELS":
                    kind = MediaType.REELS
                    counts["reels"] += 1
                else:
                    counts["other_formats"] += 1
                    continue
                if not _instagram_url(raw.get("permalink")):
                    counts["invalid_metadata"] += 1
                    continue
                try:
                    date = _date(raw.get("timestamp")).astimezone(timezone.utc)
                    likes = _integer(raw.get("like_count"))
                    comments = _integer(raw.get("comments_count"))
                except (ConnectorError, ValueError):
                    counts["invalid_metadata"] += 1
                    continue
                if date > threshold:
                    counts["too_recent"] += 1
                    continue
                if likes is None or comments is None:
                    counts["missing_metrics"] += 1
                    continue
                if followers is None or followers <= 0:
                    counts["invalid_denominator"] += 1
                    continue
                record = {
                    "platform": "instagram",
                    "acquisition_method": "graph_business_discovery",
                    "graph_api_version": "v23.0",
                    "source_account_id": actual_id,
                    "creator_username": target,
                    "source_item_id": mid,
                    "source_url": raw["permalink"],
                    "media_type": kind.value,
                    "published_at": date.isoformat(),
                    "observed_at": as_of.isoformat(),
                    "followers_measured_at": as_of.isoformat(),
                    "likes": likes,
                    "comments": comments,
                    "follower_count": followers,
                    "denominator_quality": "observed_current_only",
                    "eligible_age_days": 14,
                }
                record["integrity_sha256"] = canonical_hash(record)
                media_records.append(record)
                counts["eligible_14d"] += 1
            paging = media.get("paging") or {}
            if not isinstance(paging, dict) or not isinstance(paging.get("cursors") or {}, dict):
                raise ConnectorError("INVALID_DISCOVERY_PAGING", 502)
            cursor = (paging.get("cursors") or {}).get("after")
            if cursor is not None and (not isinstance(cursor, str) or not CURSOR.fullmatch(cursor)):
                raise ConnectorError("INVALID_DISCOVERY_CURSOR", 502)
            if paging.get("next") and not cursor:
                raise ConnectorError("DISCOVERY_PAGING_CURSOR_MISSING", 502)
            # Cursor-only responses are common: do not claim the page is final.
            can_advance = bool(cursor and (paging.get("next") or len(media["data"]) >= limit))
            if can_advance:
                if cursor in cursors_seen or cursor == after:
                    raise ConnectorError("DISCOVERY_CURSOR_STALLED", 502)
                cursors_seen.add(cursor)
                pagination_status = "CURSOR_AVAILABLE"
                after = cursor
            else:
                pagination_status = ("UNVERIFIED_FULL_PAGE_NO_CURSOR" if len(media["data"]) >= limit
                                     else "PARTIAL_PAGE_NO_CURSOR")
                after = None
                break
        return {
            "schema_version": "mpe-eligible-evidence.v1",
            "status": "EVIDENCE_PILOT_READ",
            "source": profile,
            "curation": source_approval,
            "as_of": as_of.isoformat(),
            "selection_policy": {"min_age_days": 14, "formats": ["reels", "carrossel"],
                                 "requires_positive_observed_denominator": True},
            "counts": counts,
            "eligible_media": media_records,
            "pages_examined": pages_examined,
            "page_metadata_sha256": page_hashes,
            "another_page_possible": after is not None,
            "pagination_status": pagination_status,
            "exhaustion_confirmed": False,
            "corpus_posts_persisted": 0,
            "not_a_rights_grant": True,
            "caveats": [
                "Only operator-curated approved sources are queried; evidence requires independent review.",
                "Contemporaneous followers are not historical followers at publication.",
                "Metadata export is not enrollment in the corpus database.",
                "Small bounded sample is not evidence that the profile was exhaustively read.",
            ],
        }
