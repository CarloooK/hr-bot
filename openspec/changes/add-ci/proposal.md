# Proposal: Add CI Pipeline with Tests

**Status**: Draft

## Motivation
当前项目没有自动化测试和持续集成。当多个 Agent 在不同 PC 上协作时，需要一个自动化的验证层确保：
1. 每个 Agent 推送的代码不会破坏已有功能
2. 任何人都能通过 CI badge 直观了解项目健康状态

## Scope
### In Scope
- 本地测试（pytest）验证 4 个 API 端点
- GitHub Actions CI 自动运行测试
- 测试覆盖 /health, /api/stats, /api/version, /api/config

### Out of Scope
- 钉钉消息处理的集成测试（需要真实的 DingTalk Stream）
- ChromaDB 查询测试（需要数据库）
- 性能或负载测试

## User-Facing Changes
无。开发者可以在 GitHub 仓库的 Actions 标签页看到 CI 运行结果。
