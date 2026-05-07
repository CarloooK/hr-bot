# Design: Add CI Pipeline with Tests

## Approach
1. 用 FastAPI TestClient 对现有 API 端点写无状态测试
2. GitHub Actions 在 push 和 PR 时自动拉取代码、安装依赖、运行 pytest

## Architecture
```
Agent push → GitHub → Actions runner → checkout → pip install → pytest → pass/fail badge
                                                                   ↓
                                                      所有 Agent 能看到结果
```

## Files to Change
- `tests/test_hr_bot.py` — 4 个测试类，覆盖所有 API 端点
- `pytest.ini` — pytest 配置（testpaths, python_files）
- `.github/workflows/ci.yml` — GitHub Actions 工作流
- `requirements.txt` — 添加 pytest 依赖

## Risks & Trade-offs
- CI 环境没有 .env 文件，测试需要 mock 或设置 dummy 环境变量（已经通过 os.environ.setdefault 处理）
- ROS 系统环境可能污染 pytest entry points（已在 CI 中通过 Python 代码过滤 sys.path 解决）
