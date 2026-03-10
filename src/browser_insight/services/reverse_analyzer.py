from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .index_manager import IndexManager


@dataclass(frozen=True)
class ReverseTemplate:
    name: str
    description: str
    patterns: tuple[str, ...]
    hook_keywords: tuple[str, ...]
    header_keywords: tuple[str, ...]
    recommended_queries: tuple[str, ...]


FUNCTION_TARGET_PATTERNS = (
    re.compile(
        r"\b(window\.[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*){0,2})\s*=\s*(?:async\s*)?function\b"
    ),
    re.compile(
        r"\b(window\.[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*){0,2})\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"
    ),
    re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\("),
    re.compile(
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>)"
    ),
    re.compile(
        r"\b([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*){1,3})\s*=\s*(?:async\s*)?function\b"
    ),
)

HEADER_NAME_PATTERN = re.compile(
    r"(?i)(?:['\"])(x-(?:sign|signature|token|timestamp|nonce)|authorization|cookie)(?:['\"])"
)

REVERSE_TEMPLATES: dict[str, ReverseTemplate] = {
    "sign": ReverseTemplate(
        name="sign",
        description="定位签名生成、摘要拼接、时间戳和 nonce 参与的请求校验逻辑。",
        patterns=(
            r"(?i)\b(sign|signature|getSign|makeSign|calcSign|signRequest|genSign)\b",
            r"(?i)\b(md5|sha1|sha256|hmac|HmacSHA|HmacMD5)\b",
            r"(?i)\b(timestamp|nonce|secret|appKey|salt)\b",
        ),
        hook_keywords=("sign", "signature", "nonce", "timestamp", "secret"),
        header_keywords=("x-sign", "x-signature", "x-timestamp", "x-nonce"),
        recommended_queries=(
            "登录请求 sign 生成逻辑",
            "时间戳 nonce 签名函数",
            "摘要拼接 secret 位置",
        ),
    ),
    "token": ReverseTemplate(
        name="token",
        description="定位 token 获取、刷新、缓存和鉴权注入逻辑。",
        patterns=(
            r"(?i)\b(token|accessToken|refreshToken|authToken|bearer)\b",
            r"(?i)\b(localStorage|sessionStorage|cookie|Authorization)\b",
            r"(?i)\b(setItem|getItem|setRequestHeader)\b",
        ),
        hook_keywords=("token", "auth", "bearer", "refresh", "cookie"),
        header_keywords=("authorization", "cookie", "x-token"),
        recommended_queries=(
            "token 注入请求头",
            "access token refresh 流程",
            "cookie token 本地缓存",
        ),
    ),
    "encrypt": ReverseTemplate(
        name="encrypt",
        description="定位密码、参数、载荷加密与编码逻辑。",
        patterns=(
            r"(?i)\b(encrypt|decrypt|encode|decode|cipher|plaintext|publicKey)\b",
            r"(?i)\b(CryptoJS|AES|DES|RSA|JSEncrypt|Base64|btoa|atob)\b",
            r"(?i)\b(password|passwd|pwd)\b",
        ),
        hook_keywords=("encrypt", "decrypt", "encode", "cipher", "password"),
        header_keywords=("x-sign", "x-token"),
        recommended_queries=(
            "密码加密入口",
            "publicKey RSA encrypt",
            "请求参数 encode/decode 逻辑",
        ),
    ),
    "headers": ReverseTemplate(
        name="headers",
        description="定位请求头组装、请求配置和拦截器逻辑。",
        patterns=(
            r"(?i)\b(headers|setRequestHeader|Authorization|Cookie)\b",
            r"(?i)\b(axios|fetch|XMLHttpRequest|interceptor|request\.use)\b",
            r"(?i)\b(x-sign|x-signature|x-token|x-timestamp|x-nonce)\b",
        ),
        hook_keywords=("header", "request", "interceptor", "axios", "fetch"),
        header_keywords=(
            "authorization",
            "cookie",
            "x-sign",
            "x-signature",
            "x-token",
            "x-timestamp",
            "x-nonce",
        ),
        recommended_queries=(
            "axios 请求头拦截器",
            "fetch headers 组装",
            "x-sign x-token 注入位置",
        ),
    ),
}


class ReverseAnalyzer:
    def __init__(self, index: IndexManager):
        self._index = index

    def render_report(
        self, domain_filter: Optional[str] = None, focus: Optional[str] = None
    ) -> str:
        templates, focus_key = self._resolve_templates(focus)

        sections = []
        for template in templates:
            findings = self._collect_findings(template, domain_filter=domain_filter)
            if findings:
                sections.append(self._render_template_section(template, findings))

        if not sections:
            return (
                "未检测到可用的逆向专题线索。\n"
                "建议先执行 capture_current_page 建索引，再尝试 analyze_encryption、"
                "capture_network_requests 与 hook_function 联动分析。"
            )

        header = [
            "🧭 逆向专题分析",
            f"范围: `{domain_filter}`" if domain_filter else "范围: 全部域名",
            f"专题: `{focus_key}`" if focus_key else "专题: sign / token / encrypt / headers",
            "",
        ]
        header.append(
            "建议顺序: 先看线索文件，再 Hook 候选函数，最后抓网络请求验证参数与请求头。"
        )
        return "\n".join(header + [""] + sections)

    def collect_hook_candidates(
        self,
        domain_filter: Optional[str] = None,
        focus: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        templates, _ = self._resolve_templates(focus)
        candidate_map: dict[str, dict] = {}

        for template in templates:
            findings = self._collect_findings(template, domain_filter=domain_filter)
            for finding in findings:
                for target in finding.get("hook_targets", []):
                    current = candidate_map.get(target)
                    candidate_score = int(finding.get("score", 0))
                    candidate_payload = {
                        "target": target,
                        "focuses": [template.name],
                        "score": candidate_score,
                        "original_file": finding.get("original_file", ""),
                        "url": finding.get("url", ""),
                        "line_start": finding.get("line_start", 0),
                        "line_end": finding.get("line_end", 0),
                        "source_map_restored": finding.get("source_map_restored", False),
                        "headers": list(finding.get("headers", [])),
                    }
                    if current is None:
                        candidate_map[target] = candidate_payload
                        continue

                    if template.name not in current["focuses"]:
                        current["focuses"].append(template.name)
                    current["score"] = max(current["score"], candidate_score)
                    for header in finding.get("headers", []):
                        if header not in current["headers"]:
                            current["headers"].append(header)

        candidates = list(candidate_map.values())
        candidates.sort(
            key=lambda item: (
                int(item.get("score", 0)),
                bool(item.get("source_map_restored")),
                item.get("target", ""),
            ),
            reverse=True,
        )
        return candidates[:limit]

    def collect_template_context(
        self, focus: Optional[str] = None
    ) -> dict[str, dict[str, object]]:
        templates, _ = self._resolve_templates(focus)
        context: dict[str, dict[str, object]] = {}
        for template in templates:
            context[template.name] = {
                "description": template.description,
                "header_keywords": list(template.header_keywords),
                "hook_keywords": list(template.hook_keywords),
                "recommended_queries": list(template.recommended_queries),
            }
        return context

    def _resolve_templates(
        self, focus: Optional[str]
    ) -> tuple[list[ReverseTemplate], Optional[str]]:
        focus_key = (focus or "").strip().lower() or None
        if focus_key and focus_key not in REVERSE_TEMPLATES:
            supported = ", ".join(REVERSE_TEMPLATES.keys())
            raise ValueError(f"focus 仅支持: {supported}")

        templates = (
            [REVERSE_TEMPLATES[focus_key]]
            if focus_key
            else list(REVERSE_TEMPLATES.values())
        )
        return templates, focus_key

    def _collect_findings(
        self, template: ReverseTemplate, domain_filter: Optional[str]
    ) -> list[dict]:
        deduped: dict[tuple[str, int, str], dict] = {}

        for pattern in template.patterns:
            matches = self._index.search_chunks_by_text(
                pattern, domain=domain_filter, limit=30
            )
            for match in matches:
                text = str(match.get("text", ""))
                key = (
                    str(match.get("url", "")),
                    int(match.get("line_start", 0) or 0),
                    text[:200],
                )
                entry = deduped.get(key)
                if entry is None:
                    entry = {
                        **match,
                        "matched_patterns": set(),
                        "hook_targets": self._extract_hook_targets(
                            text, template.hook_keywords
                        ),
                        "headers": self._extract_header_names(text, template.header_keywords),
                    }
                    deduped[key] = entry
                entry["matched_patterns"].add(pattern)

        findings = list(deduped.values())
        for finding in findings:
            finding["score"] = self._score_finding(finding, template)

        findings.sort(key=lambda item: item["score"], reverse=True)
        return findings[:5]

    def _score_finding(self, finding: dict, template: ReverseTemplate) -> int:
        text = str(finding.get("text", "")).lower()
        score = 0
        score += 2 if finding.get("source_map_restored") else 0
        score += min(len(finding.get("matched_patterns", set())), 3)
        score += min(len(finding.get("hook_targets", [])), 2)
        score += min(len(finding.get("headers", [])), 2)
        score += sum(1 for keyword in template.hook_keywords if keyword in text)
        return score

    def _extract_hook_targets(
        self, text: str, keywords: tuple[str, ...]
    ) -> list[str]:
        targets: list[str] = []
        lowered_keywords = tuple(keyword.lower() for keyword in keywords)

        for pattern in FUNCTION_TARGET_PATTERNS:
            for raw_target in pattern.findall(text):
                target = raw_target if isinstance(raw_target, str) else raw_target[0]
                candidate = target.strip()
                if not candidate:
                    continue
                lowered = candidate.lower()
                if any(keyword in lowered for keyword in lowered_keywords):
                    if candidate not in targets:
                        targets.append(candidate)
                elif "." in candidate and any(
                    keyword in text.lower() for keyword in lowered_keywords
                ):
                    if candidate not in targets:
                        targets.append(candidate)

        return targets[:5]

    def _extract_header_names(
        self, text: str, expected_keywords: tuple[str, ...]
    ) -> list[str]:
        found = []
        lowered_expected = {item.lower() for item in expected_keywords}
        lowered_text = text.lower()
        for name in HEADER_NAME_PATTERN.findall(text):
            normalized = name.lower()
            if normalized in lowered_expected and normalized not in found:
                found.append(normalized)
        for expected in expected_keywords:
            normalized = expected.lower()
            if normalized in lowered_text and normalized not in found:
                found.append(normalized)
        return found[:6]

    def _render_template_section(
        self, template: ReverseTemplate, findings: list[dict]
    ) -> str:
        lines = [f"## {template.name}", template.description]

        suggested_targets = self._merge_unique(
            [target for finding in findings for target in finding.get("hook_targets", [])]
        )
        if suggested_targets:
            lines.append("")
            lines.append("可疑 Hook 入口:")
            for target in suggested_targets[:5]:
                lines.append(f"- `{target}`")

        suggested_headers = self._merge_unique(
            [name for finding in findings for name in finding.get("headers", [])]
        )
        if suggested_headers:
            lines.append("")
            lines.append("关键请求头:")
            for header in suggested_headers[:6]:
                lines.append(f"- `{header}`")

        lines.append("")
        lines.append("推荐搜索词:")
        for query in template.recommended_queries:
            lines.append(f"- `{query}`")

        lines.append("")
        lines.append("代码线索:")
        for idx, finding in enumerate(findings, 1):
            source_tag = "🔄 Source Map" if finding.get("source_map_restored") else "📦 混淆代码"
            snippet = str(finding.get("text", "")).strip()
            if len(snippet) > 400:
                snippet = snippet[:400] + "..."
            lines.append(
                f"### 线索 {idx} [{source_tag}]\n"
                f"- 文件: `{finding.get('original_file', '?')}`\n"
                f"- 来源: `{finding.get('url', '')}`\n"
                f"- 行号: {finding.get('line_start', '?')}-{finding.get('line_end', '?')}\n"
                f"```javascript\n{snippet}\n```"
            )

        return "\n".join(lines)

    @staticmethod
    def _merge_unique(items: list[str]) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                merged.append(item)
        return merged
