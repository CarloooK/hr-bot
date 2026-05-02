# Tasks: Chat History API

- [x] 1. 新建 `app/routers/chat_history.py` — 已创建文件，定义 `GET /api/chat/history` 端点，支持 `user_id`、`limit`（默认20）、`offset`（默认0）
- [x] 2. 新建 `app/services/chat_history_service.py` — 已创建文件，实现 `get_history()` 通过 ChromaDB metadata filter 查询
- [x] 3. 在 `app/main.py` 中注册 chat_history router — 已添加 `from app.routers.chat_history import chat_router` + `app.include_router(chat_router)`
- [x] 4. 鉴权 — 已添加 `app/core/security.py`，从环境变量 `CHAT_HISTORY_API_KEY` 读取，通过 `X-API-Key` header 校验
- [ ] 5. 运行 `pytest` 确保现有测试全部通过
- [ ] 6. 用 curl 手动验证：`curl -H "X-API-Key: $KEY" "http://localhost:8000/api/chat/history?user_id=test_user&limit=5"`
