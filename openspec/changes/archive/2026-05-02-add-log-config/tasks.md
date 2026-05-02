# Tasks: Add Log Rotation Config via Environment Variable

- [x] 1. 在 config.py 中添加 `LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "10485760"))` 和 `LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))` 
- [x] 2. 在 main.py 中将 `maxBytes=10 * 1024 * 1024` 替换为 `maxBytes=LOG_MAX_BYTES`
- [x] 3. 在 main.py 中将 `backupCount=5` 替换为 `backupCount=LOG_BACKUP_COUNT`
- [x] 4. 运行 `python -c "from main import app; print('import OK')"` 验证语法无误
