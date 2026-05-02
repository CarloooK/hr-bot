# Proposal: Add Log Rotation Config via Environment Variable

**Status**: Draft

## Motivation
当前日志轮转的 `maxBytes` 和 `backupCount` 是 hardcoded 在 main.py 中的。运维环境不同可能需要不同的轮转配置（开发环境日志小，生产环境日志多）。通过环境变量配置更灵活。

## Scope
### In Scope
- config.py 中添加 `LOG_MAX_BYTES` 和 `LOG_BACKUP_COUNT` 两个配置项
- main.py 中使用这两个配置项替换硬编码值

### Out of Scope
- 日志级别或格式的可配置化
- 日志文件的路径配置

## User-Facing Changes
无。运行时行为不变（默认值与当前相同）。
