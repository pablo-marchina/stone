"""Constrained, read-only Instagram Business Discovery feasibility probe.

The viewer is the authenticated Instagram professional account. The target is
an explicitly selected *different* professional account. No media downloaded,
no automatic discovery, no database writes, and no paging URL is followed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from .connectors import ConnectorError, OfficialHttp, Platform, _integer, _date
from .domain import MediaType

USERNAME = re.compile(r"[A-Za-z0-9_.]{1,30}\Z")
IG_ID = re.compile(r"[0-9]{5,32}\Z")
CURSOR = re.compile(r"[A-Za-z0-9_+/=-]{1,512}\Z")


class BusinessDiscoveryProbe:
    def __init__(self, http: OfficialHttp):
        self.http = http

    @staticmethod
    def _fields(target: str, limit: int, after: str | None) -> str:
        # Caller cannot supply Graph field expressions or arbitrary paths.
        media_args = f"media.limit({limit})"
        if after is not None:
            media_args += f".after({after})"
        return (f"business_discovery.username({target})"
                "{id,username,followers_count,media_count,"
                f"{media_args}"
                "{id,media_type,media_product_type,permalink,timestamp,like_count,comments_count}}")

    def check(self, viewer_id: str, target: str, token: str, *,
              limit: int = 3, max_pages: int = 1,
              now: datetime | None = None) -> dict:
        if not IG_ID.fullmatch(viewer_id):
            raise ConnectorError("INVALID_VIEWER_IG_ID", 422)
        if not USERNAME.fullmatch(target) or target.startswith(".") or target.endswith("."):
            raise ConnectorError("INVALID_TARGET_USERNAME", 422)
        if not 1 <= limit <= 10 or not 1 <= max_pages <= 3:
            raise ConnectorError("INVALID_PROBE_LIMIT", 422)
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ConnectorError("INVALID_AS_OF_TIME", 422)
        now = now.astimezone(timezone.utc)
        threshold = now - timedelta(days=14)
        after = None
        visited = set()
        seen_media = set()
        count = dict(returned=0, reels=0, carousels=0, static_images=0,
                     other_formats=0, too_recent=0, invalid_metadata=0,
                     missing_metrics=0, invalid_denominator=0,
                     eligible_14d=0, duplicates=0)
        profile = None
        pages = 0
        pagination_status = "NOT_CHECKED"
        for _ in range(max_pages):
            payload = self.http.get(Platform.INSTAGRAM, viewer_id,
                {"fields": self._fields(target, limit, after)}, token)
            discovery = payload.get("business_discovery")
            if not isinstance(discovery, dict):
                raise ConnectorError("BUSINESS_DISCOVERY_NOT_AVAILABLE", 403)
            actual = discovery.get("username")
            if not isinstance(actual, str) or actual.casefold() != target.casefold():
                raise ConnectorError("DISCOVERED_ACCOUNT_MISMATCH", 403)
            identifier = str(discovery.get("id", ""))
            if not IG_ID.fullmatch(identifier):
                raise ConnectorError("INVALID_DISCOVERED_ACCOUNT", 502)
            followers = _integer(discovery.get("followers_count"))
            published_total = _integer(discovery.get("media_count"))
            if profile is None:
                profile = {"id": identifier, "username": actual,
                           "followers_observed_now": followers,
                           "reported_media_count": published_total}
            elif identifier != profile["id"]:
                raise ConnectorError("DISCOVERY_PROFILE_CHANGED_DURING_PAGINATION", 502)
            media = discovery.get("media")
            if not isinstance(media, dict) or not isinstance(media.get("data"), list):
                raise ConnectorError("DISCOVERY_MEDIA_UNAVAILABLE", 502)
            pages += 1
            for entry in media["data"][:limit]:
                count["returned"] += 1
                if not isinstance(entry, dict):
                    count["invalid_metadata"] += 1
                    continue
                media_id = str(entry.get("id", ""))
                if not IG_ID.fullmatch(media_id):
                    count["invalid_metadata"] += 1
                    continue
                if media_id in seen_media:
                    count["duplicates"] += 1
                    continue
                seen_media.add(media_id)
                if entry.get("media_type") == "CAROUSEL_ALBUM":
                    kind = MediaType.CAROUSEL
                    count["carousels"] += 1
                elif entry.get("media_product_type") == "REELS":
                    kind = MediaType.REELS
                    count["reels"] += 1
                elif entry.get("media_type") == "IMAGE":
                    kind = MediaType.IMAGE
                    count["static_images"] += 1
                else:
                    count["other_formats"] += 1
                    continue
                if kind not in {MediaType.REELS, MediaType.CAROUSEL}:
                    continue
                permalink = entry.get("permalink")
                if not isinstance(permalink, str) or not permalink.startswith(
                        "https://www.instagram.com/"):
                    count["invalid_metadata"] += 1
                    continue
                try:
                    date = _date(entry.get("timestamp"))
                except ConnectorError:
                    count["invalid_metadata"] += 1
                    continue
                if date > threshold:
                    count["too_recent"] += 1
                    continue
                try:
                    likes = _integer(entry.get("like_count"))
                    comments = _integer(entry.get("comments_count"))
                except ConnectorError:
                    count["invalid_metadata"] += 1
                    continue
                if likes is None or comments is None:
                    count["missing_metrics"] += 1
                    continue
                if followers is None or followers <= 0:
                    count["invalid_denominator"] += 1
                    continue
                count["eligible_14d"] += 1
            paging = media.get("paging") or {}
            if not isinstance(paging, dict):
                raise ConnectorError("INVALID_DISCOVERY_PAGING", 502)
            cursors = paging.get("cursors") or {}
            if not isinstance(cursors, dict):
                raise ConnectorError("INVALID_DISCOVERY_PAGING", 502)
            # Nested Business Discovery media commonly exposes only
            # paging.cursors.after, without a paging.next URL. A full page
            # without either cursor is *not* proof of exhaustion.
            cursor = cursors.get("after")
            if cursor is not None and (
                not isinstance(cursor, str) or not CURSOR.fullmatch(cursor)
            ):
                raise ConnectorError("INVALID_DISCOVERY_CURSOR", 502)
            has_next = bool(paging.get("next"))
            if has_next and cursor is None:
                raise ConnectorError("DISCOVERY_PAGING_CURSOR_MISSING", 502)
            page_is_full = len(media["data"]) >= limit
            next_cursor = cursor if cursor is not None and (
                has_next or page_is_full
            ) else None
            if next_cursor is not None:
                if next_cursor in visited or next_cursor == after:
                    raise ConnectorError("DISCOVERY_CURSOR_STALLED", 502)
                visited.add(next_cursor)
                pagination_status = "CURSOR_AVAILABLE"
            elif page_is_full:
                pagination_status = "UNVERIFIED_FULL_PAGE_NO_CURSOR"
            else:
                pagination_status = "PARTIAL_PAGE_NO_CURSOR"
            after = next_cursor
            if after is None:
                break
        return {
            "status": "DISCOVERY_SAMPLE_READ",
            "source": "instagram_business_discovery",
            "viewer_ig_id": viewer_id,
            "target": profile,
            "sample": count,
            "pages_examined": pages,
            "another_page_possible": after is not None,
            "pagination_status": pagination_status,
            "exhaustion_confirmed": False,
            "sample_only": True,
            "persisted_posts": 0,
            "rights_grant_recorded": False,
            "limitations": [
                "Only an explicitly selected professional profile was queried.",
                "Follower count observed now is not follower count at publication.",
                "This read is not evidence of third-party reuse rights.",
                "No media files were downloaded or written to a database.",
            ],
        }
