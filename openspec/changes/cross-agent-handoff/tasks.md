# Tasks: System Stats API

- [x] 1. 在 main.py 的模块级别添加 `_start_time = time.time()` 和 `_msg_counter = 0` — 实际代码已修改
- [x] 2. 在 Handler.process() 成功处理消息后调用 `_increment_msg_counter()` 递增计数器 — 实际代码已修改
- [x] 3. 在 main.py 添加 `GET /api/stats` 端点 — 实际代码已添加
- [x] 4. 运行 `python -c "from main import app; print('import OK')"` 验证语法无误 — **PASS**
- [ ] 5. 用 curl 请求 `/api/stats` 检查返回格式符合预期（需要服务运行中）
