from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

SILICONFLOW_API_URL = "https://api.siliconflow.cn/v1/embeddings"
MAX_BATCH_SIZE = 32
# bge-m3 最大 8192 tokens，代码 token 密度高（约 1 token ≈ 2-3 字符），保守截断
MAX_TEXT_CHARS = 4000


class EmbeddingService:
    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        batch_size: int = 32,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
    ):
        self._model_name = model_name
        self._batch_size = min(batch_size, MAX_BATCH_SIZE)
        self._api_key = api_key or os.environ.get("SILICONFLOW_API_KEY", "")
        self._api_url = api_url or SILICONFLOW_API_URL

        if not self._api_key:
            raise ValueError(
                "未配置硅基流动 API Key。请设置环境变量 SILICONFLOW_API_KEY "
                "或在配置文件 embedding.api_key 中填写。"
            )

    async def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        truncated = []
        for t in texts:
            t = t.strip()
            if not t:
                t = " "
            if len(t) > MAX_TEXT_CHARS:
                t = t[:MAX_TEXT_CHARS]
            truncated.append(t)
        payload = {
            "model": self._model_name,
            "input": truncated,
            "encoding_format": "float",
        }

        async with aiohttp.ClientSession() as session:
            for attempt in range(3):
                async with session.post(
                    self._api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 429:
                        wait = 2**attempt + 1
                        logger.warning("API 限流 (429)，等待 %ds 后重试", wait)
                        await asyncio.sleep(wait)
                        continue
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(
                            f"硅基流动 Embedding API 错误 (HTTP {resp.status}): {body}"
                        )
                    result = await resp.json()
                    break
            else:
                raise RuntimeError("硅基流动 Embedding API 限流，重试 3 次仍失败")

        data = result.get("data", [])
        data.sort(key=lambda x: x["index"])
        return [item["embedding"] for item in data]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        zero_vector: list[float] = [0.0] * 1024

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            try:
                embeddings = await self._request_embeddings(batch)
                all_embeddings.extend(embeddings)
            except RuntimeError as e:
                if "413" not in str(e):
                    raise
                logger.warning(
                    "批次 %d 超 token 限制，降级为逐条处理", i // self._batch_size + 1
                )
                for j, text in enumerate(batch):
                    try:
                        emb = await self._request_embeddings([text])
                        all_embeddings.extend(emb)
                    except RuntimeError:
                        logger.warning(
                            "跳过超长文本 (index=%d, len=%d)", i + j, len(text)
                        )
                        all_embeddings.append(zero_vector)

        return all_embeddings

    async def embed_query(self, query: str) -> list[float]:
        results = await self._request_embeddings([query])
        return results[0]
