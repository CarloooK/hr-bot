# Tasks: System Stats API

- [ ] 1. 在 main.py 的模块级别添加 `_start_time = time.time()` 和 `_msg_counter = 0`
- [ ] 2. 在 Handler.process() 成功处理消息后（标记 STATUS_OK 前）调用 `increment_msg_counter()` 递增计数器
- [ ] 3. 在 main.py 添加 `GET /api/stats` 端点，返回 JSON: `{ "uptime_seconds": int(time.time() - _start_time), "total_messages": _msg_counter, "queue_size": len(_waiting_tasks) }`
- [ ] 4. 运行 `python -c "from main import app; print('import OK')"` 验证语法无误
- [ ] 5. 用 curl 请求 `/api/stats` 检查返回格式符合预期
