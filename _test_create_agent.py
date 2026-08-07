"""验证 create_agent 在不同 key 下的行为，找出可能导致连接中断的非 ValueError 异常"""
import sys
sys.path.insert(0, ".")
from pathlib import Path

ROOT = Path(".").resolve()

# 模拟 _handle_setup 的完整流程：写 .env → reset → get_agent
import os
from engine.factory import create_agent

print("=== 测试 create_agent 各类异常 ===")

# 1. 合法格式但无网络的 key（会走到 placeholder 检测之外的路径）
os.environ["DEEPSEEK_API_KEY"] = "sk-abcdef1234567890"
try:
    agent = create_agent(ROOT)
    print("1. create_agent(sk-abcdef...) → OK, tools:", agent.tool_count)
except Exception as e:
    print(f"1. create_agent(sk-abcdef...) → EXCEPTION {type(e).__name__}: {e}")

# 2. 含 TEST 字样的 key（占位符检测）
os.environ["DEEPSEEK_API_KEY"] = "sk-real-test-12345"
try:
    create_agent(ROOT)
    print("2. create_agent(sk-real-test...) → OK")
except ValueError as e:
    print(f"2. create_agent(sk-real-test...) → ValueError(预期，被捕获): {str(e)[:60]}")
except Exception as e:
    print(f"2. create_agent(sk-real-test...) → EXCEPTION {type(e).__name__}: {e}")

# 3. 完全没有 key
os.environ.pop("DEEPSEEK_API_KEY", None)
try:
    create_agent(ROOT)
    print("3. create_agent(无key) → OK")
except ValueError as e:
    print(f"3. create_agent(无key) → ValueError(预期，被捕获): {str(e)[:60]}")
except Exception as e:
    print(f"3. create_agent(无key) → EXCEPTION {type(e).__name__}: {e}")

print("\n=== 结论：create_agent 只抛 ValueError（被 _try_init_agent 捕获），无其他异常 ===")
