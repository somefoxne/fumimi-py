"""
Danbooru API client.
Handles all requests to the Danbooru REST API.
"""

import os
import aiohttp
import asyncio
from typing import Optional


class DanbooruClient:
    """Async HTTP client for the Danbooru API."""

    def __init__(
        self,
        base_url: str = None,
        username: str = None,
        api_key: str = None,
    ):
        self.base_url = (base_url or os.getenv("BOORU_URL", "https://danbooru.donmai.us")).rstrip("/")
        self.username = username or os.getenv("BOORU_USER", "")
        self.api_key = api_key or os.getenv("BOORU_API_KEY", "")
        self._session: Optional[aiohttp.ClientSession] = None

    def _auth(self) -> dict:
        """Return basic auth params if credentials are set."""
        if self.username and self.api_key:
            return {"login": self.username, "api_key": self.api_key}
        return {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": "fumimi-discord-python/1.0"}
            )
        return self._session

    async def get(self, path: str, params: dict = None) -> dict | list:
        """Make a GET request to the Danbooru API."""
        session = await self._get_session()
        url = f"{self.base_url}/{path}.json"
        query = {**(params or {}), **self._auth()}
        async with session.get(url, params=query) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Posts ──────────────────────────────────────────────────────────────

    async def get_posts(self, tags: str = "", limit: int = 6, page: int = 1) -> list:
        return await self.get("posts", {
            "tags": tags,
            "limit": limit,
            "page": page,
        })

    async def get_post(self, post_id: int) -> dict:
        return await self.get(f"posts/{post_id}")

    async def get_post_count(self, tags: str = "") -> int:
        data = await self.get("counts/posts", {"tags": tags})
        return data.get("counts", {}).get("posts", 0)

    # ── Tags ───────────────────────────────────────────────────────────────

    async def get_tag(self, name: str) -> dict | None:
        results = await self.get("tags", {
            "search[name]": name,
            "limit": 1,
        })
        return results[0] if results else None

    async def get_tags(self, query: str, limit: int = 10, order: str = "count") -> list:
        return await self.get("tags", {
            "search[name_matches]": f"*{query}*",
            "search[order]": order,
            "search[hide_empty]": "no",
            "limit": limit,
        })

    async def get_related_tags(self, tag: str, category: str = None) -> dict:
        params = {"query": tag}
        if category:
            params["category"] = category
        return await self.get("related_tag", params)

    # ── Wiki ───────────────────────────────────────────────────────────────

    async def get_wiki(self, title: str) -> dict | None:
        results = await self.get("wiki_pages", {
            "search[title]": title,
            "limit": 1,
        })
        return results[0] if results else None

    # ── Artists ────────────────────────────────────────────────────────────

    async def get_artist(self, name: str) -> dict | None:
        results = await self.get("artists", {
            "search[name]": name,
            "limit": 1,
        })
        return results[0] if results else None

    # ── Comments ───────────────────────────────────────────────────────────

    async def get_comments(self, post_id: int = None, limit: int = 5) -> list:
        params = {"group_by": "comment", "limit": limit}
        if post_id:
            params["search[post_id]"] = post_id
        return await self.get("comments", params)

    # ── Forum ──────────────────────────────────────────────────────────────

    async def get_forum_topics(self, query: str = "", limit: int = 5) -> list:
        params = {"limit": limit}
        if query:
            params["search[title_matches]"] = f"*{query}*"
        return await self.get("forum_topics", params)

    async def get_forum_post(self, post_id: int) -> dict:
        return await self.get(f"forum_posts/{post_id}")

    # ── Stats / Counts ─────────────────────────────────────────────────────

    async def get_top_uploaders(self, period: str = "1d", limit: int = 10) -> list:
        """Get top uploaders from post_report endpoint (if available)."""
        try:
            return await self.get("reports/posts", {
                "search[period]": period,
                "limit": limit,
            })
        except Exception:
            return []
