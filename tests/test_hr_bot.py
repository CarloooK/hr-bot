"""Tests for HR Bot API endpoints."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

# 先设好必要的环境变量，避免 config.py 报错
os.environ.setdefault("DEEPSEEK_API_KEY", "test-skip")
os.environ.setdefault("DINGTALK_APP_KEY", "test-skip")
os.environ.setdefault("DINGTALK_APP_SECRET", "test-skip")

from main import app

client = TestClient(app)


class TestHealth:
    """/health 端点验证"""

    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "hr-bot"
        assert "queue_size" in data


class TestStats:
    """/api/stats 端点验证"""

    def test_stats_returns_expected_fields(self):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "uptime_seconds" in data
        assert "total_messages" in data
        assert "queue_size" in data
        assert isinstance(data["uptime_seconds"], int)
        assert isinstance(data["total_messages"], int)
        assert data["total_messages"] >= 0


class TestVersion:
    """/api/version 端点验证"""

    def test_version_returns_version(self):
        resp = client.get("/api/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)


class TestConfig:
    """/api/config 端点验证"""

    def test_config_returns_config_values(self):
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "host" in data
        assert "port" in data
        assert "collection_name" in data
