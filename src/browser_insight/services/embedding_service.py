from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

SILICONFLOW_API_URL = "https://api.siliconflow.cn/v1/embeddings"
MAX_BATCH_SIZE = 32


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
        payload = {
            "model": self._model_name,
            "input": texts,
            "encoding_format": "float",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self._api_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"硅基流动 Embedding API 错误 (HTTP {resp.status}): {body}"
                    )
                result = await resp.json()

        data = result.get("data", [])
        data.sort(key=lambda x: x["index"])
        return [item["embedding"] for item in data]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            embeddings = await self._request_embeddings(batch)
            all_embeddings.extend(embeddings)
            logger.debug(
                "向量化批次 %d/%d 完成 (%d 条)",
                i // self._batch_size + 1,
                (len(texts) - 1) // self._batch_size + 1,
                len(batch),
            )

        return all_embeddings

    async def embed_query(self, query: str) -> list[float]:
        results = await self._request_embeddings([query])
        return results[0]
