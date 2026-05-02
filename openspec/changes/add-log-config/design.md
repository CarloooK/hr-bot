# Design: Add Log Rotation Config via Environment Variable

## Approach
1. 在 config.py 中添加两个环境变量配置项（带默认值）
2. 在 main.py 中从 config 导入并替换 hardcoded 值

## Architecture
```
环境变量                         config.py                      main.py
LOG_MAX_BYTES=20971520  ──▶  LOG_MAX_BYTES = int(...)  ──▶  RotatingFileHandler(maxBytes=...)
LOG_BACKUP_COUNT=10     ──▶  LOG_BACKUP_COUNT = int(...) ──▶  RotatingFileHandler(backupCount=...)
```

## Files to Change
- `config.py` — 添加两个新配置项
- `main.py` — 替换 hardcoded 值

## Risks & Trade-offs
- 如果 os.getenv 的值不是合法整数，int() 会抛 ValueError。可以通过 try/except 保底或信任用户配置。
