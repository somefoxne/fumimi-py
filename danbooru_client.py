"""
Danbooru API Client
===================
Kết hợp cấu trúc của cr-bot và fumimi-discord.
Sử dụng file settings.py để quản lý cấu hình.
"""

import logging
import aiohttp
from typing import Any, Optional
import settings

log = logging.getLogger("fumimi.danbooru")

HTTP_ERRORS: dict[int, str] = {
    400: "Tham số không hợp lệ (Bad Request).",
    401: "Xác thực thất bại. Kiểm tra thông tin đăng nhập.",
    403: "Không có quyền truy cập (Forbidden).",
    404: "Không tìm thấy (Not Found).",
    410: "Vượt quá giới hạn phân trang.",
    420: "Bản ghi không thể lưu (Invalid Record).",
    422: "Tài nguyên bị khóa (Locked).",
    423: "Tài nguyên đã tồn tại (Already Exists).",
    424: "Tham số không hợp lệ (Invalid Parameters).",
    429: "Vượt rate limit – thử lại sau.",
    500: "Lỗi server nội bộ.",
    502: "Server quá tải – thử lại sau.",
    503: "Server không khả dụng (downbooru?).",
}

class DanbooruError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")

class DanbooruClient:
    def __init__(self):
        self.base_url = settings.get_active_booru_url().rstrip("/")
        self.username = settings.get_active_login()
        self.api_key = settings.get_active_apikey()
        self.user_agent = settings.USERAGENT
        self._session: Optional[aiohttp.ClientSession] = None

    def _make_auth(self) -> Optional[aiohttp.BasicAuth]:
        if self.username and self.api_key:
            return aiohttp.BasicAuth(self.username, self.api_key)
        return None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": self.user_agent},
                auth=self._make_auth(),
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get(self, path: str, params: dict = None) -> Any:
        session = await self._get_session()
        url = f"{self.base_url}/{path}.json"
        query = {k: v for k, v in (params or {}).items() if v is not None}

        log.debug("GET %s params=%s", url, query)
        async with session.get(url, params=query) as resp:
            if resp.status == 200:
                return await resp.json()
            friendly = HTTP_ERRORS.get(resp.status, f"Lỗi HTTP {resp.status}")
            try:
                body = await resp.json()
                if isinstance(body, dict):
                    friendly = body.get("message") or body.get("reason") or friendly
            except Exception:
                pass
            raise DanbooruError(resp.status, friendly)

    POST_FIELDS = "id,uploader,created_at,score,fav_count,tag_string,rating,media_asset,source,file_url,large_file_url"

    async def get_posts(self, tags: str = "", limit: int = 6, page: int | str = 1, only: str = None) -> list[dict]:
        fields = only or self.POST_FIELDS
        return await self.get("posts", {"tags": tags or None, "limit": limit, "page": page, "only": fields})

    async def get_post(self, post_id: int) -> dict:
        return await self.get(f"posts/{post_id}", {"only": self.POST_FIELDS})

    async def get_random_post(self, tags: str = "") -> dict:
        return await self.get("posts/random", {"tags": tags or None, "only": self.POST_FIELDS})

    async def get_post_count(self, tags: str = "") -> Optional[int]:
        data = await self.get("counts/posts", {"tags": tags or None})
        return data.get("counts", {}).get("posts")

    async def get_tag(self, name: str) -> dict | None:
        results = await self.get("tags", {"search[name]": name, "search[hide_empty]": "no", "only": "id,name,post_count,category,is_deprecated,antecedent_alias,wiki_page", "limit": 1})
        return results[0] if results else None

    async def search_tags(self, pattern: str, order: str = "count", category: int = None, limit: int = 10) -> list[dict]:
        return await self.get("tags", {"search[name_matches]": pattern, "search[order]": order, "search[category]": category, "search[hide_empty]": "no", "only": "id,name,post_count,category", "limit": limit})

    async def get_related_tags(self, query: str, category: str = None) -> dict:
        return await self.get("related_tag", {"query": query, "category": category})

    async def get_wiki(self, title: str) -> dict | None:
        results = await self.get("wiki_pages", {"search[title]": title, "only": "id,title,body,tag", "limit": 1})
        return results[0] if results else None

    async def get_artist(self, name: str) -> dict | None:
        results = await self.get("artists", {"search[name]": name, "only": "id,name,is_banned,other_names,urls", "limit": 1})
        return results[0] if results else None

    async def get_comments(self, post_id: int = None, limit: int = 5, order: str = "id_desc") -> list[dict]:
        return await self.get("comments", {"group_by": "comment", "search[post_id]": post_id, "search[order]": order, "only": "id,body,created_at,creator,score", "limit": limit})

    async def get_forum_topics(self, query: str = "", limit: int = 5, order: str = "updated_at_desc") -> list[dict]:
        params = {"search[order]": order, "only": "id,title,response_count,is_sticky,is_locked,category_id", "limit": limit}
        if query: params["search[title_matches]"] = f"*{query}*"
        return await self.get("forum_topics", params)

    async def get_forum_post(self, post_id: int) -> dict:
        return await self.get(f"forum_posts/{post_id}", {"only": "id,body,created_at,creator,topic"})

    async def get_popular_posts(self, date: str = None, scale: str = "day", limit: int = 4) -> list[dict]:
        return await self.get("explore/posts/popular", {"date": date, "scale": scale, "limit": limit, "only": self.POST_FIELDS})

    async def autocomplete_tags(self, query: str, limit: int = 10) -> list[dict]:
        return await self.get("autocomplete", {"search[query]": query, "search[type]": "tag_query", "limit": limit})

    async def get_bulk_update_requests(self, limit: int = 5, status: str = "pending") -> list[dict]:
        return await self.get("bulk_update_requests", {"search[status]": status, "only": "id,script,user,forum_topic,created_at,status", "limit": limit})

    async def get_top_uploaders(self, tags: str = "", limit: int = 10, from_date: str = "2005-05-24") -> list[dict]:
        """Lấy danh sách Top Uploaders từ Danbooru reports API."""
        params = {
            "search[group]": "uploader",
            "search[group_limit]": limit,
            "search[from]": from_date,
        }
        if tags:
            params["search[tags]"] = tags
        return await self.get("reports/posts", params)
