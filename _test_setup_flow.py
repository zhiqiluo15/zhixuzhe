"""复现浏览器流程：GET / 拿 cookie → POST /setup 带 Origin+Cookie → 观察响应"""
import http.client
import json

HOST = "127.0.0.1"
PORT = 8080

# ── 步骤 1：模拟浏览器打开页面（GET /），拿 Set-Cookie ──
conn = http.client.HTTPConnection(HOST, PORT, timeout=5)
conn.request("GET", "/", headers={"User-Agent": "Mozilla/5.0 Chrome/125.0.0.0"})
resp = conn.getresponse()
resp.read()
set_cookie = resp.getheader("Set-Cookie")
print(f"1. GET /          → {resp.status}, Set-Cookie: {set_cookie}")
conn.close()

cookie = set_cookie.split(";")[0] if set_cookie else ""
print(f"   cookie = {cookie}\n")

# ── 步骤 2：模拟浏览器 fetch POST /setup（同源 http://127.0.0.1:8080）──
# 浏览器同源 POST 会带 Origin 头 + cookie（fetch 默认 same-origin 带 cookie）
conn = http.client.HTTPConnection(HOST, PORT, timeout=5)
body = json.dumps({"key": "sk-real-key-placeholder"})
conn.request("POST", "/setup",
    body=body,
    headers={
        "Content-Type": "application/json",
        "Origin": "http://127.0.0.1:8080",
        "Cookie": cookie,
        "Content-Length": str(len(body)),
    })
resp = conn.getresponse()
data = resp.read().decode()
print(f"2. POST /setup 同源 Origin+Cookie → {resp.status}")
print(f"   ACAO: {resp.getheader('Access-Control-Allow-Origin')}")
print(f"   body: {data}\n")
conn.close()

# ── 步骤 3：模拟 fetch POST /setup 但没有 cookie（浏览器缓存禁用时）──
conn = http.client.HTTPConnection(HOST, PORT, timeout=5)
body = json.dumps({"key": "sk-real-key-placeholder"})
conn.request("POST", "/setup",
    body=body,
    headers={
        "Content-Type": "application/json",
        "Origin": "http://127.0.0.1:8080",
        "Content-Length": str(len(body)),
    })
resp = conn.getresponse()
data = resp.read().decode()
print(f"3. POST /setup 有 Origin 无 Cookie → {resp.status}, body: {data}")
conn.close()
