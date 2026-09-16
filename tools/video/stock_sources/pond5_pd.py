"""Pond5 Public Domain stock source adapter.

Wraps Pond5's public domain collection behind the unified `StockSource`
protocol. The collection focuses on
historical and archival material: WWI/WWII, early cinema, space
launches, historical speeches, Olympic footage.

Returned collection labels are not legal clearance. Confirm the individual
source record, applicable attribution, and other media rights before publishing.

This adapter uses API access configured with POND5_API_KEY. Public website
browsability is not evidence that API access is available; no website scraper
fallback is implemented. Confirm asset rights before commercial delivery.

What Pond5 Public Domain is good for
-------------------------------------
- Historical / archival documentary footage (WWI, WWII, Cold War)
- Early cinema (Méliès, Edison, Lumière)
- Vintage newsreels and propaganda films
- Space race and early NASA footage
- Historical speeches (JFK, Churchill, MLK)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import Candidate, SearchFilters

_SEARCH_URL = "https://www.pond5.com/api/v2/search"
_LICENSE = "Public domain collection (Pond5 source classification; verify item rights)"

# Pond5 public domain items are tagged with specific collection IDs
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".wmv", ".webm", ".mpg", ".mpeg"}


class Pond5PublicDomainSource:
    """Pond5 Public Domain adapter. Satisfies `StockSource`."""

    name = "pond5_pd"
    display_name = "Pond5 Public Domain"
    provider = "pond5"
    priority = 38
    install_instructions = (
        "Provide POND5_API_KEY through the trusted launch environment and "
        "confirm API access. No public-website scraper fallback is implemented."
    )
    supports = {"video": True, "image": True}

    def is_available(self) -> bool:
        return bool(os.environ.get("POND5_API_KEY", "").strip())

    def search(self, query: str, filters: SearchFilters) -> list[Candidate]:
        import requests

        if not self.is_available():
            raise ValueError(self.install_instructions)
        kind = (filters.kind or "video").lower()

        # Pond5 public search endpoint
        params: dict[str, Any] = {
            "kw": query,
            "page": max(1, filters.page),
            "ps": max(1, min(filters.per_page, 50)),
            "free": 1,  # Only free/public domain items
        }

        if kind == "video":
            params["mt"] = "footage"
        elif kind == "image":
            params["mt"] = "photos"

        headers: dict[str, str] = {
            "User-Agent": "OpenMontage/1.0 (stock source adapter)",
        }
        api_key = os.environ.get("POND5_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        r = requests.get(
            _SEARCH_URL,
            headers=headers,
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()

        results = data.get("results", []) or data.get("items", []) or []
        return self._parse_results(results, kind, filters)

    def _parse_results(
        self, results: list[dict], kind: str, filters: SearchFilters
    ) -> list[Candidate]:
        out: list[Candidate] = []
        for item in results:
            item_id = str(item.get("id", "") or "")
            if not item_id:
                continue

            title = item.get("t", "") or item.get("title", "") or ""
            description = item.get("desc", "") or item.get("description", "") or ""
            keywords = item.get("kw", "") or item.get("keywords", "") or ""
            if isinstance(keywords, list):
                keywords = " ".join(keywords)
            source_tags = f"{title} {description} {keywords}".strip()

            duration = float(item.get("dur", 0) or item.get("duration", 0) or 0)
            if kind == "video":
                if filters.min_duration and duration and duration < filters.min_duration:
                    continue
                if filters.max_duration and duration and duration > filters.max_duration:
                    continue

            # Preview/download URL
            preview_url = (
                item.get("v", "")
                or item.get("preview_url", "")
                or item.get("icon_url", "")
                or ""
            )
            thumb_url = item.get("ic", "") or item.get("thumbnail_url", "") or ""

            if not preview_url:
                continue

            width = int(item.get("w", 0) or item.get("width", 0) or 0)
            height = int(item.get("h", 0) or item.get("height", 0) or 0)

            candidate_kind = "video" if kind != "image" else "image"
            source_url = f"https://www.pond5.com/stock-footage/{item_id}"

            out.append(
                Candidate(
                    source=self.name,
                    source_id=item_id,
                    source_url=source_url,
                    download_url=preview_url,
                    kind=candidate_kind,
                    width=width,
                    height=height,
                    duration=duration,
                    creator=item.get("an", "") or item.get("artist_name", "") or "Pond5 Public Domain",
                    license=_LICENSE,
                    source_tags=source_tags,
                    thumbnail_url=thumb_url,
                    extra={
                        "fps": item.get("fps"),
                        "codec": item.get("codec"),
                    },
                )
            )
        return out

    def download(self, candidate: Candidate, out_path: Path) -> Path:
        import requests

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with requests.get(
            candidate.download_url, stream=True, timeout=180
        ) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
        return out_path
