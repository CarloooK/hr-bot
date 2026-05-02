# Design: System Stats API

## Approach
扩展 main.py 文件，在现有基础上增加：
1. 在 `Handler.process()` 中为每一条成功处理的消息递增计数器
2. 新增 `GET /api/stats` 端点返回数据
3. 项目启动时记录 start_time

## Architecture
```
Handler.process() → 消息处理成功 → msg_counter += 1
                                     ↓
GET /api/stats → { start_time, uptime_seconds, total_messages, queue_size }
```

## Files to Change
- `main.py` — 加 start_time 全局变量、msg_counter 全局变量、/api/stats 端点
- 在 Handler 的消息处理成功路径上递增计数器

## Risks & Trade-offs
- 内存计数器在进程重启后归零 —— 对于这个轻量级需求可以接受。后续需要持久化时再改 Redis。
