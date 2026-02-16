# Browser Insight MCP API 文档

## MCP Tools

### `capture_current_page`

| 属性 | 说明 |
|------|------|
| 功能 | 触发一次完整的全量抓取、归档、分析流程 |
| 类型 | Tool |

**参数:**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `storage_path` | `str` | 是 | 文件存储的绝对路径，所有抓取的 JS 文件将归档到此目录下（按域名/日期组织） |
| `force_refresh` | `bool` | 否 (默认 `false`) | 是否忽略哈希缓存，强制重新解析所有文件 |

**返回:** 简报字符串，包含新增文件数、Source Map 还原数、索引代码块数、实际存储路径。

**示例返回:**
```
✅ 抓取完成，新增 5 个 JS 文件，还原了 3 个 Source Map，共索引 150 个代码块，存储路径: /Users/mac/projects/storage/example.com/2026-02-16。
```

---

### `search_local_codebase`

| 属性 | 说明 |
|------|------|
| 功能 | RAG 检索本地已索引的浏览器 JS 代码库 |
| 类型 | Tool |

**参数:**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `query` | `str` | 是 | 自然语言搜索问题 |
| `domain_filter` | `str` | 否 | 限制搜索的域名，例如 `example.com` |
| `limit` | `int` | 否 (默认 `10`) | 返回结果数量上限 |

**返回:** Markdown 格式的代码块列表，标注来源为 Source Map 还原 或 混淆代码。

---

## MCP Resources

### `insight://archived-sites`

| 属性 | 说明 |
|------|------|
| 功能 | 列出本地已归档的所有域名和抓取记录 |
| 类型 | Resource |

**返回:** 域名列表，包含文件数和最近抓取时间。
