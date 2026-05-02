# HR Bot — 运维操作指南

> 钉钉智能 HR 助手：基于 RAG（ChromaDB + DeepSeek Chat）的员工问答机器人

---

## 快速参考

| 操作 | 命令 |
|------|------|
| 查看状态 | `hr-bot-status` |
| 查看最新日志 | `hr-bot-log` |
| 实时日志 | `hr-bot-tail` |
| 重启服务 | `hr-bot-restart` |
| 查看告警摘要 | `hr-bot-alert` |
| 重建文档索引 | `hr-bot-reindex` |

---

## 一、架构概览

```
┌─────────────┐     DingTalk Stream      ┌──────────────────────┐
│  钉钉 (HR群)  │◄────────────────────────►│  hr-bot (FastAPI)     │
│  @机器人提问  │                          │  localhost:8000       │
└─────────────┘                           │                      │
                                          │  ┌────────────────┐  │
                                          │  │ rag_engine.py  │──┼────► DeepSeek API
                                          │  │ (检索 + LLM)   │  │      (deepseek-chat)
                                          │  └───────┬────────┘  │
                                          │          │           │
                                          │  ┌───────▼────────┐  │
                                          │  │ ChromaDB       │  │
                                          │  │ (向量数据库)    │  │
                                          │  └────────────────┘  │
                                          └──────────────────────┘
```

### 文件结构

| 路径 | 说明 |
|------|------|
| `main.py` | FastAPI 入口 + DingTalk Stream 连接 |
| `config.py` | 配置（凭据、TOP_K 等） |
| `rag_engine.py` | RAG 引擎（检索 + LLM 调用） |
| `embedding_fn.py` | ONNX MiniLM 向量化 |
| `ingest.py` | 文档导入 & 分块索引 |
| `topic_registry.py` | 截图型 PDF 主题匹配 |
| `scripts/healthcheck.sh` | 健康检查脚本（每5分钟） |
| `scripts/logwatch.sh` | 日志异常监控脚本（每15分钟） |
| `scripts/alert-history.sh` | 告警摘要查看脚本 |
| `docs/` | 原始 HR 文档（PDF/DOCX） |
| `db/chroma.sqlite3` | 向量数据库 |
| `logs/server.log` | 运行日志（轮转：10MB × 5个） |
| `logs/healthcheck.log` | 健康检查日志 |
| `logs/alert.log` | 告警日志 |
| `.env` | API 密钥配置 |

---

## 二、安装 & 首次部署

### 前置要求

- Python 3.10+
- 钉钉企业内部应用（已配置机器人 Stream Mode）
- DeepSeek API Key

### 部署步骤

```bash
# 1. 克隆/上传项目
cd /home/admin/hr-bot

# 2. 创建虚拟环境 & 安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. 配置凭据
cp .env.example .env
# 编辑 .env，填入：
#   DEEPSEEK_API_KEY=sk-xxx
#   DINGTALK_APP_KEY=xxx
#   DINGTALK_APP_SECRET=xxx

# 4. 导入 HR 文档到 docs/ 目录
#   支持格式：.pdf（可搜索文字）, .docx, .txt

# 5. 构建向量索引
source venv/bin/activate
python ingest.py

# 6. 启动服务
systemctl --user daemon-reload
systemctl --user enable --now hr-bot.service

# 7. 验证
curl http://localhost:8000/health
# → {"status":"ok","service":"hr-bot","queue_size":0}
```

---

## 三、日常运维

### 3.1 查看服务状态

```bash
# 服务运行状态
systemctl --user status hr-bot.service

# 健康检查日志
tail -f /home/admin/hr-bot/logs/healthcheck.log

# 最近告警
bash /home/admin/hr-bot/scripts/alert-history.sh
```

### 3.2 查看日志

```bash
# 应用日志（最近50条）
journalctl --user -u hr-bot.service -n 50 --no-pager -o cat

# 实时日志
journalctl --user -u hr-bot.service -f -o cat

# 系统日志文件（轮转）
tail -f /home/admin/hr-bot/logs/server.log
```

### 3.3 重启服务

```bash
systemctl --user restart hr-bot.service
```

启动后约 2-3 秒即可响应。可通过 `curl http://localhost:8000/health` 确认。

### 3.4 添加/更新文档

```bash
# 1. 将新文档放到 docs/ 目录（支持 .pdf/.docx/.txt）
# 2. 重新构建索引
cd /home/admin/hr-bot && source venv/bin/activate && python ingest.py
# 3. 重启服务加载新索引
systemctl --user restart hr-bot.service
```

> ⚠️ 文档更新后必须 `python ingest.py` + 重启，旧索引不会自动刷新。

---

## 四、系统服务架构

### 系统服务 (systemd --user)

| 服务/定时器 | 用途 | 频率 |
|------------|------|------|
| `hr-bot.service` | 主服务进程 | 持续运行 |
| `hr-bot-healthcheck.service` | 健康检查 | 每 5 分钟 |
| `hr-bot-healthcheck.timer` | 健康检查触发 | 每 5 分钟 |
| `hr-bot-logwatch.service` | 日志异常检测 | 每 15 分钟 |
| `hr-bot-logwatch.timer` | 日志检测触发 | 每 15 分钟 |
| `hr-bot-cleanup.service` | 旧日志清理 | 每日 |
| `hr-bot-cleanup.timer` | 清理触发 | 每日 |

### 自动恢复机制

- **服务崩溃** → `Restart=always`，10 秒后自动重启
- **5 分钟内崩溃超 5 次** → 停止重试（防止死循环）
- **健康检查连续 3 次失败** → 自动重启服务
- **服务器重启** → `WantedBy=default.target` + linger 确保开机自启

---

## 五、监控告警说明

### 5.1 健康检查 (`healthcheck.sh`)

每 5 分钟请求 `GET /health`。如果连续 3 次失败（约 15 分钟无响应）：
1. 写入 `alert.log`
2. 自动重启服务
3. 重启后再次检查，如果仍未恢复则写入人工介入告警

### 5.2 日志异常监控 (`logwatch.sh`)

每 15 分钟扫描 `server.log` 新增行，发现以下关键词写入告警：
- `ERROR` / `CRITICAL` / `Traceback` / `Exception` / `调用失败`

### 5.3 查看告警历史

```bash
# 最近 24 小时
bash /home/admin/hr-bot/scripts/alert-history.sh

# 最近 1 小时
bash /home/admin/hr-bot/scripts/alert-history.sh 1

# 最近 7 天
bash /home/admin/hr-bot/scripts/alert-history.sh 168
```

---

## 六、调优指南

### 回答质量

| 参数 | 位置 | 说明 | 推荐值 |
|------|------|------|--------|
| `TOP_K` | `config.py` | 检索返回的 chunk 数量 | 12-15 |
| `CHUNK_SIZE` | `config.py` | 文档分块大小（字符数） | 500 |
| `temperature` | `rag_engine.py` | LLM 输出随机性 | 0.3（固定） |
| `_CACHE_TTL` | `rag_engine.py` | 答案缓存时间（秒） | 300 |

### 查询扩展

编辑 `rag_engine.py` 中的 `_QUERY_EXPANSIONS` 字典。例如：

```python
"福利": "福利 饭贴 精微币 补贴 薪资 年假 奖金 五险一金 社保 公积金 补充医疗"
```

### 话题增强

编辑 `rag_engine.py` 中的 `_BOOST_PAGES` 字典。指定对特定问题自动注入特定页的内容。

---

## 七、成本估算

### API 费用 (DeepSeek Chat / V4 Flash)

| 用量 | 日均查询 | 月费 | 年费 |
|------|---------|------|------|
| 小团队 (~50人) | 15 次 | ¥1.2 | ¥14 |
| 中型 (~200人) | 60 次 | ¥4.8 | ¥58 |
| 大型 (~500人) | 200 次 | ¥16 | ¥192 |

> 实际成本更低：5 分钟 TTL 缓存命中复用，常见问题不重复计费。

### 云服务器（参考价）

| 配置 | 月费 |
|------|------|
| 2C4G 轻量云 | ¥50-70 |
| 2C4G ECS | ¥80-120 |

### 存储

- ChromaDB 向量库：约 3MB（当前 215 chunks）
- 日志：每日约 50-200KB

---

## 八、常见问题

### Q: 服务启动后没有响应

```bash
# 检查进程
systemctl --user status hr-bot.service

# 检查日志
journalctl --user -u hr-bot.service -n 30 --no-pager

# 检查 .env 配置
cat /home/admin/hr-bot/.env | grep -v PASSWORD
```

### Q: DeepSeek API 调用失败

1. 检查 API Key 是否有效：`curl https://api.deepseek.com/v1/models -H "Authorization: Bearer $DEEPSEEK_API_KEY"`
2. 检查账户余额：登录 [DeepSeek Platform](https://platform.deepseek.com)
3. 查看 `logs/server.log` 中的 `ERROR` 行

### Q: 钉钉收不到回复

1. 检查钉钉凭据是否正确（AppKey / AppSecret）
2. 确认钉钉机器人已发布并配置了 Stream Mode
3. 检查 `logs/server.log` 中是否有 `>>> 消息` 日志行（有则说明收到消息）
4. 重启服务：`systemctl --user restart hr-bot.service`

### Q: 怎么让机器人响应群聊？

在钉钉群中 @机器人并提问。当前配置仅响应 @消息（群聊需 @，单聊无需）。

---

## 九、紧急故障处理

### 服务完全不可用

```bash
# 1. 尝试重启
systemctl --user restart hr-bot.service
sleep 3
curl http://localhost:8000/health

# 2. 如果仍不可用，前台调试启动
cd /home/admin/hr-bot && source venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000
# 观察控制台输出的错误

# 3. 检查磁盘 / 内存
df -h /   # 磁盘是否满
free -h   # 内存是否够
```

### 恢复备份

```bash
# ChromaDB 向量库
cp /home/admin/hr-bot/db/chroma.sqlite3 /backup/hr-bot/chroma.sqlite3

# 恢复
cp /backup/hr-bot/chroma.sqlite3 /home/admin/hr-bot/db/chroma.sqlite3
systemctl --user restart hr-bot.service
```

---

## 十、部署到新服务器 Checklist

- [ ] Python 3.10+ 环境就绪
- [ ] `git clone` 或上传项目文件
- [ ] `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- [ ] `.env` 配置完成（DeepSeek API Key + 钉钉凭据）
- [ ] `python ingest.py` 构建索引
- [ ] `mkdir -p ~/.config/systemd/user/ && cp hr-bot.service 到该目录`
- [ ] `systemctl --user daemon-reload && systemctl --user enable --now hr-bot.service`
- [ ] `loginctl enable-linger $USER`（确保开机自启）
- [ ] `curl http://localhost:8000/health` 返回 `ok`
- [ ] 钉钉群 @机器人 测试问答
