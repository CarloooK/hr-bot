# Proposal: Chat History API

**Status**: Draft

## Motivation
当前 HR Bot 的消息处理是无状态的 — 钉钉消息进来，AI 回复后就没有了。用户（HR 人员）无法回溯某个员工的对话历史。需要一个 API 来查询历史对话，方便后续的审计、人工复核和数据分析。

## Scope
### In Scope
- 新增 REST API 端点 `GET /api/chat/history?user_id=xxx&limit=20`
- 返回按时间倒序的对话记录列表
- 每条记录包含：role, content, timestamp
- 支持按用户 ID 筛选
- 支持分页（limit + offset）

### Out of Scope
- 聊天记录的搜索/全文检索（后续迭代）
- Web 管理界面的对话查看页面
- 消息编辑或删除
- 对话导出

## User-Facing Changes
新增一个 API 端点，调用方（管理后台、审计工具）可以通过 HTTP 请求获取任意员工的对话历史。

## Open Questions
- 对话记录的存储是否需要新建表，还是直接用 ChromaDB 的已有记录？
- 历史数据需要保留多久？
