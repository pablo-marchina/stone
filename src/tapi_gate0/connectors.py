"""Small, fixed-host official API adapters; no scraping, media download or paid APIs.

All calls use fixed endpoints, TLS, short timeouts and injected transport for tests.
Credentials are loaded from environment only at execution and never persisted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import os
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import Origin, MediaType, require_utc_date


class ConnectorError(Exception):
    def __init__(self, code: str, status: int = 422, *, provider_diagnostic: dict | None = None):
        self.code, self.status = code, status
        self.provider_diagnostic = provider_diagnostic or {}
        super().__init__(code)


class Platform(str, Enum):
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"


class NormalizedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Platform
    source_account_id: str = Field(min_length=1, max_length=128)
    source_item_id: str = Field(min_length=1, max_length=128)
    creator_handle: str = Field(min_length=1, max_length=256)
    media_type: MediaType
    source_url: str
    published_at: datetime
    caption: str | None = Field(default=None, max_length=10000)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    follower_count: int | None = Field(default=None, ge=0)
    denominator_quality: str = "unknown"
    views: int | None = Field(default=None, ge=0)
    metadata_only: bool = True

    @model_validator(mode="after")
    def validate_source(self):
        require_utc_date(self.published_at)
        if self.platform == Platform.INSTAGRAM and not self.source_url.startswith("https://www.instagram.com/"):
            raise ValueError("Instagram item must have canonical Instagram HTTPS URL")
        if self.platform == Platform.YOUTUBE and not self.source_url.startswith("https://www.youtube.com/"):
            raise ValueError("YouTube item must have canonical YouTube HTTPS URL")
        return self


def _integer(value):
    if value is None:
        return None
    # Reject malformed/missing statistics rather than silently inventing zeros.
    if isinstance(value, bool) or not str(value).isdigit():
        raise ConnectorError("INVALID_PROVIDER_STATISTIC")
    return int(value)


def _date(value):
    if not isinstance(value, str):
        raise ConnectorError("MISSING_PROVIDER_TIMESTAMP")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require_utc_date(result)
        return result
    except ValueError as exc:
        raise ConnectorError("INVALID_PROVIDER_TIMESTAMP") from exc


def _meta_error_diagnostic(response: httpx.Response) -> dict:
    """Allowlist numeric Graph error fields; never retain messages or raw payloads."""
    result = {"http_status": response.status_code}
    if len(response.content) > 1_000_000:
        return result
    try:
        body = response.json()
    except (ValueError, RecursionError):
        return result
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        for field in ("code", "error_subcode"):
            value = error.get(field)
            if type(value) is int and 0 <= value <= 2_147_483_647:
                result[field] = value
    return result


class OfficialHttp:
    """Never accepts caller-specified hosts, redirects or generic fetch URLs."""
    def __init__(self, client: httpx.Client | None = None, *,
                 instagram_version: str = "v23.0"):
        # Explicit allowlist: no caller-controlled paths, hosts or versions.
        if instagram_version not in {"v23.0", "v26.0"}:
            raise ValueError("UNSUPPORTED_META_GRAPH_VERSION")
        self.instagram_version = instagram_version
        self.client = client or httpx.Client(timeout=httpx.Timeout(8), follow_redirects=False)
        self._owned = client is None

    def close(self):
        if self._owned:
            self.client.close()

    def get(self, platform: Platform, path: str, params: dict, token: str) -> dict:
        if not token or len(token) < 10:
            raise ConnectorError("CREDENTIAL_MISSING", 403)
        base = {Platform.INSTAGRAM: f"https://graph.facebook.com/{self.instagram_version}/",
                Platform.YOUTUBE: "https://www.googleapis.com/youtube/v3/"}[platform]
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path) or path.startswith("/") or ".." in path:
            raise ConnectorError("UNSAFE_PROVIDER_PATH", 403)
        # Only fixed provider paths may be reached; caller never supplies a URL.
        if platform == Platform.INSTAGRAM and not re.fullmatch(r"[A-Za-z0-9_-]+(?:/media)?", path):
            raise ConnectorError("UNSAFE_PROVIDER_PATH", 403)
        if platform == Platform.YOUTUBE and path not in {"channels", "videos"}:
            raise ConnectorError("UNSAFE_PROVIDER_PATH", 403)
        try:
            response = self.client.get(base + path, params=params,
                                       headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
            if response.is_redirect:
                raise ConnectorError("PROVIDER_REDIRECT_DENIED", 403)
            if response.status_code >= 400:
                diagnostic = _meta_error_diagnostic(response) if platform == Platform.INSTAGRAM else {}
                if response.status_code in (401, 403):
                    raise ConnectorError("PROVIDER_PERMISSION_DENIED", 403, provider_diagnostic=diagnostic)
                if response.status_code == 429:
                    raise ConnectorError("PROVIDER_RATE_LIMITED", 429, provider_diagnostic=diagnostic)
                raise ConnectorError("PROVIDER_REQUEST_FAILED", 502, provider_diagnostic=diagnostic)
            if len(response.content) > 1_000_000:
                raise ConnectorError("PROVIDER_RESPONSE_INVALID",502)
            data = response.json()
            if not isinstance(data, dict):
                raise ConnectorError("PROVIDER_RESPONSE_INVALID", 502)
            return data
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError("PROVIDER_UNAVAILABLE", 502) from exc


class InstagramOfficial:
    platform = Platform.INSTAGRAM
    def __init__(self, http: OfficialHttp): self.http = http

    def verify(self, account_id: str, token: str) -> dict:
        # Works only for eligible professional accounts available to token.
        result = self.http.get(self.platform, account_id,
                               {"fields": "id,username,followers_count"}, token)
        if str(result.get("id")) != account_id or not result.get("username"):
            raise ConnectorError("PROVIDER_ACCOUNT_MISMATCH", 403)
        return {"id": account_id, "username": result["username"],
                "followers_count": _integer(result.get("followers_count"))}

    def fetch(self, account_id: str, token: str, verified: dict, limit: int,
              item_ids: list[str] | None = None) -> list[NormalizedItem]:
        # Backwards-compatible single-page interface for existing callers.
        items, _ = self.fetch_page(account_id, token, verified, limit, item_ids=item_ids)
        return items

    def fetch_page(self, account_id: str, token: str, verified: dict, limit: int,
                   *, after: str | None = None,
                   item_ids: list[str] | None = None) -> tuple[list[NormalizedItem], str | None]:
        """One bounded official page. Never follow a provider-supplied 'next' URL.

        Only the opaque cursor is used, as a query parameter on the fixed host.
        Pages that contain ineligible formats can still have a next cursor.
        """
        if item_ids:
            raise ConnectorError("INSTAGRAM_LIST_MODE_ONLY")
        if not 1 <= limit <= 10:
            raise ConnectorError("INVALID_PAGE_LIMIT")
        if after is not None and not re.fullmatch(r"[A-Za-z0-9_+/=-]{1,512}", after):
            raise ConnectorError("INVALID_PAGINATION_CURSOR", 422)
        params = {
            "fields": "id,media_type,media_product_type,caption,timestamp,permalink,like_count,comments_count",
            "limit": limit,
        }
        if after is not None:
            params["after"] = after
        payload = self.http.get(self.platform, f"{account_id}/media", params, token)
        if not isinstance(payload.get("data"), list):
            raise ConnectorError("PROVIDER_RESPONSE_INVALID", 502)
        out = []
        for x in payload["data"][:limit]:
            if not isinstance(x, dict):
                continue
            mid = str(x.get("id", ""))
            if not re.fullmatch(r"[0-9_]+", mid):
                continue
            kind = x.get("media_type")
            product = x.get("media_product_type")
            if kind == "CAROUSEL_ALBUM":
                form = MediaType.CAROUSEL
            elif product == "REELS":
                form = MediaType.REELS
            elif kind == "IMAGE":
                form = MediaType.IMAGE
            else:
                continue
            url = x.get("permalink")
            if not isinstance(url, str) or not url.startswith("https://www.instagram.com/"):
                continue
            out.append(NormalizedItem(
                platform=self.platform, source_account_id=account_id,
                source_item_id=mid, creator_handle=verified["username"], media_type=form,
                source_url=url, published_at=_date(x.get("timestamp")),
                caption=(x.get("caption") or "")[:10000] or None,
                likes=_integer(x.get("like_count")), comments=_integer(x.get("comments_count")),
                follower_count=verified["followers_count"],
                denominator_quality="observed_current_only", metadata_only=True,
            ))
        paging = payload.get("paging") or {}
        if not isinstance(paging, dict):
            raise ConnectorError("PROVIDER_RESPONSE_INVALID", 502)
        cursors = paging.get("cursors") or {}
        if not isinstance(cursors, dict):
            raise ConnectorError("PROVIDER_RESPONSE_INVALID", 502)
        next_cursor = cursors.get("after") if paging.get("next") else None
        if next_cursor is not None:
            if not isinstance(next_cursor, str) or not re.fullmatch(
                r"[A-Za-z0-9_+/=-]{1,512}", next_cursor
            ):
                raise ConnectorError("INVALID_PROVIDER_CURSOR", 502)
            if next_cursor == after:
                raise ConnectorError("PAGINATION_CURSOR_STALLED", 502)
        return out, next_cursor


class YouTubeOfficial:
    platform = Platform.YOUTUBE
    def __init__(self,http:OfficialHttp):self.http=http

    def verify(self,account_id:str,token:str)->dict:
        data=self.http.get(self.platform,"channels",{"part":"snippet,statistics","id":account_id},token)
        items=data.get("items",[])
        if len(items)!=1 or str(items[0].get("id"))!=account_id:
            raise ConnectorError("PROVIDER_ACCOUNT_MISMATCH",403)
        x=items[0];stats=x.get("statistics") or {}
        hidden=stats.get("hiddenSubscriberCount",False)
        return {"id":account_id,"username":str(x.get("snippet",{}).get("title") or account_id),
                "followers_count":None if hidden else _integer(stats.get("subscriberCount"))}

    def fetch(self,account_id:str,token:str,verified:dict,limit:int,
              item_ids:list[str] | None=None)->list[NormalizedItem]:
        if not item_ids:raise ConnectorError("YOUTUBE_EXPLICIT_VIDEO_IDS_REQUIRED")
        if len(item_ids)>min(limit,50) or any(not re.fullmatch(r"[A-Za-z0-9_-]{11}",i) for i in item_ids):
            raise ConnectorError("INVALID_YOUTUBE_VIDEO_IDS")
        data=self.http.get(self.platform,"videos",{"part":"snippet,statistics,contentDetails",
                                                    "id":",".join(item_ids)},token)
        if not isinstance(data.get("items"),list):raise ConnectorError("PROVIDER_RESPONSE_INVALID",502)
        out=[]
        for x in data["items"]:
            if x.get("id") not in item_ids:continue
            sn=x.get("snippet") or {};stats=x.get("statistics") or {}
            if sn.get("channelId")!=account_id:raise ConnectorError("PROVIDER_ACCOUNT_MISMATCH",403)
            # Shorts membership cannot be inferred reliably from duration alone.
            out.append(NormalizedItem(platform=self.platform,source_account_id=account_id,
                source_item_id=x["id"],creator_handle=verified["username"],media_type=MediaType.SHORTS,
                source_url=f'https://www.youtube.com/shorts/{x["id"]}',published_at=_date(sn.get("publishedAt")),
                caption=(sn.get("title","")+"\n"+sn.get("description", "")).strip()[:10000] or None,
                likes=_integer(stats.get("likeCount")),comments=_integer(stats.get("commentCount")),
                follower_count=verified["followers_count"],denominator_quality="youtube_rounded_estimate",
                views=_integer(stats.get("viewCount")),metadata_only=True))
        return out


def credential_for(platform:Platform)->str:
    variable={Platform.INSTAGRAM:"TAPI_INSTAGRAM_ACCESS_TOKEN",
              Platform.YOUTUBE:"TAPI_YOUTUBE_ACCESS_TOKEN"}[platform]
    token=os.getenv(variable, "")
    if not token:raise ConnectorError("CREDENTIAL_MISSING",403)
    return token
