# Design: Chat History API

## Approach
在现有 FastAPI 应用上新增一个 router，从 ChromaDB 查询对话历史并返回。不需要新建数据库 — ChromaDB 已在存储向量时保留了原始文本和元数据（user_id, timestamp），可以直接复用。

## Architecture
```
钉钉用户 → DingTalk Stream → Message Handler → [ChromaDB: metadata={user_id, role, timestamp}]
                                                      ↑
管理后台 / curl → GET /api/chat/history?user_id=X  查询
                        ↓
                  ChatHistoryRouter
                        ↓
                  ChatHistoryService.get_history(user_id, limit, offset)
                        ↓
                  ChromaDB query (metadata filter)
                        ↓
                  JSONResponse [{role, content, timestamp}]
```

## Files to Change
- `app/main.py` — 注册新的 chat_history router
- `app/routers/chat_history.py` — 新文件，API 路由定义
- `app/services/chat_history_service.py` — 新文件，业务逻辑
- `app/core/security.py` — 可能加简单鉴权（对内 API 用 token 校验）

## Risks & Trade-offs
- 风险：ChromaDB 的 metadata filter 性能 — 员工数不多（<1000人），每条消息都有 user_id 索引，O(n) 扫描可以接受
- 取舍：直接用 ChromaDB 查（简单）vs 新建 PostgreSQL 表（查询更高效但多一个数据源）— 当前选简单方案
