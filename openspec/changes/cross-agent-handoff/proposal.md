# Proposal: System Stats API

**Status**: Draft

## Motivation
当前没有渠道了解 HR Bot 的运行状态。运维需要知道：服务运行了多久、处理了多少消息、队列里是否有积压。

## Scope
### In Scope
- 新增 `GET /api/stats` 端点
- 返回内容：uptime_seconds, total_messages_processed, queue_size
- total_messages_processed 通过一个内存计数器追踪
- 不需要数据库或持久化存储

### Out of Scope
- 历史趋势图（后续交给监控系统如 Prometheus）
- 钉钉通知告警
- 权限校验（对内端点，和 /health 一样不鉴权）

## User-Facing Changes
新增一个 API 端点，curl 或管理工具可以查询。

## Open Questions
无。
