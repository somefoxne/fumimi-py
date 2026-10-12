"""
Danbooru API Client
===================
Kết hợp cấu trúc của cr-bot và fumimi-discord.
Sử dụng file settings.py để quản lý cấu hình.
"""

import asyncio
import fnmatch
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

    @staticmethod
    def _matches_query(tag_string: str, query_tokens: list[str]) -> bool:
        """Kiểm tra một bài viết có khớp toàn bộ cú pháp truy vấn của Danbooru hay không."""
        if not tag_string:
            return False
        post_tags = set(tag_string.split())
        or_tokens = []

        for token in query_tokens:
            if token.startswith("~"):
                or_tokens.append(token[1:])
            elif token.startswith("-"):
                neg = token[1:]
                if "*" in neg:
                    if any(fnmatch.fnmatch(t, neg) for t in post_tags):
                        return False
                else:
                    if neg in post_tags:
                        return False
            else:
                pos = token
                if "*" in pos:
                    if not any(fnmatch.fnmatch(t, pos) for t in post_tags):
                        return False
                else:
                    if pos not in post_tags:
                        return False

        if or_tokens:
            has_or = False
            for or_token in or_tokens:
                if "*" in or_token:
                    if any(fnmatch.fnmatch(t, or_token) for t in post_tags):
                        has_or = True
                        break
                else:
                    if or_token in post_tags:
                        has_or = True
                        break
            if not has_or:
                return False

        return True

    async def _fetch_stratified_samples(self, tags: str = None, total_samples: int = 1000) -> list[dict]:
        """Lấy 1,000 bài mẫu phân tầng qua các mốc lịch sử với trường only=id,tag_string."""
        per_batch = 200
        num_batches = max(total_samples // per_batch, 1)

        # Mốc 1: bài mới nhất
        first_batch = await self.get("posts", {"tags": tags or None, "limit": per_batch, "only": "id,tag_string"})
        if not first_batch or not isinstance(first_batch, list):
            return []
        if len(first_batch) < per_batch:
            return first_batch

        max_id = first_batch[0].get("id")
        if not max_id or max_id <= 0:
            return first_batch

        tasks = []
        milestones = [0.8, 0.6, 0.4, 0.2][:num_batches - 1]
        for frac in milestones:
            target_id = int(max_id * frac)
            tasks.append(
                self.get("posts", {"tags": tags or None, "limit": per_batch, "page": f"b{target_id}", "only": "id,tag_string"})
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_posts = list(first_batch)
        for res in results:
            if isinstance(res, list) and res:
                all_posts.extend(res)

        return all_posts

    async def _estimate_pure_or(self, tokens: list[str]) -> Optional[int]:
        """Ước tính cho các truy vấn thuần OR (~tag1 ~tag2 ...) bằng nguyên lý Bao hàm - Loại trừ."""
        tag_names = [t[1:] for t in tokens if not any(c in t for c in "*:")]
        if not tag_names or len(tag_names) != len(tokens):
            return None

        # Lấy post_count chuẩn xác của từng tag từ cơ sở dữ liệu Danbooru
        tag_infos = await asyncio.gather(*[self.get_tag(t) for t in tag_names], return_exceptions=True)
        counts = {}
        for i, info in enumerate(tag_infos):
            if isinstance(info, dict) and info.get("post_count") is not None:
                counts[tag_names[i]] = info["post_count"]
            else:
                return None

        sum_counts = sum(counts.values())
        if len(tag_names) == 1:
            return sum_counts

        # Đo độ trùng lặp (overlap) giữa các tag bằng mẫu 200 bài từ mỗi tag
        sample_tasks = [
            self.get("posts", {"tags": t, "limit": 200, "only": "id,tag_string"})
            for t in tag_names
        ]
        sample_results = await asyncio.gather(*sample_tasks, return_exceptions=True)

        overlap_ratios = []
        for i, res in enumerate(sample_results):
            if isinstance(res, list) and res:
                other_tags = set(tag_names) - {tag_names[i]}
                overlap_count = sum(1 for p in res if any(ot in set(p.get("tag_string", "").split()) for ot in other_tags))
                overlap_ratios.append(overlap_count / len(res))

        if overlap_ratios:
            avg_overlap = sum(overlap_ratios) / len(overlap_ratios)
            est_total = sum_counts * (1.0 - (avg_overlap * (len(tag_names) - 1) / len(tag_names)))
            max_single = max(counts.values())
            return max(int(est_total), max_single)

        return sum_counts

    async def estimate_post_count(self, tags: str = "") -> Optional[int]:
        """Ước tính số lượng post xấp xỉ bằng phương pháp Monte Carlo / Stratified Sampling với cỡ mẫu 1,000 bài thực tế."""
        try:
            tokens = (tags or "").strip().split()
            if not tokens:
                return await self.get_post_count("")

            # 1. Truy vấn thuần OR (~tag1 ~tag2 ...)
            if all(t.startswith("~") for t in tokens) and len(tokens) <= 6:
                est_or = await self._estimate_pure_or(tokens)
                if est_or is not None:
                    return est_or

            # 2. Tìm Base Tag dương (không phủ định, không OR, không wildcard, không metatag)
            base_tag = None
            base_count = None
            pos_tokens = [t for t in tokens if not t.startswith(("-", "~")) and not any(c in t for c in "*:")]

            if pos_tokens:
                tag_infos = await asyncio.gather(*[self.get_tag(t) for t in pos_tokens], return_exceptions=True)
                valid_candidates = []
                for i, info in enumerate(tag_infos):
                    if isinstance(info, dict) and info.get("post_count"):
                        valid_candidates.append((pos_tokens[i], info["post_count"]))

                if valid_candidates:
                    valid_candidates.sort(key=lambda x: x[1])
                    base_tag, base_count = valid_candidates[0]

            sample_universe = base_tag if base_tag else None
            total_universe_count = base_count if base_count else None

            if not total_universe_count:
                total_universe_count = await self.get_post_count("")
                if not total_universe_count:
                    total_universe_count = 8_600_000

            # 3. Lấy mẫu 1,000 bài thực tế từ universe (5 mốc x 200 bài)
            posts_sample = await self._fetch_stratified_samples(sample_universe, total_samples=1000)
            if not posts_sample:
                return None

            # 4. Lọc trực tiếp từng bài theo toàn bộ điều kiện query
            matching_count = sum(1 for p in posts_sample if self._matches_query(p.get("tag_string", ""), tokens))

            sample_ratio = matching_count / len(posts_sample)
            estimated = int(total_universe_count * sample_ratio)

            if base_count:
                estimated = min(estimated, base_count)

            return max(estimated, matching_count)
        except Exception as e:
            log.warning("Lỗi khi ước tính post count cho tags '%s': %s", tags, e)
            return None

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
