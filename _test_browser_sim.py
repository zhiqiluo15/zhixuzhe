"""完整模拟浏览器 fetch 行为，定位 /setup 报"网络错误"的根因"""
import http.client
import json

HOST = "127.0.0.1"
PORT = 8080

def request(method, path, headers=None, body=None):
    conn = http.client.HTTPConnection(HOST, PORT, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read().decode(errors="replace")
    out = (resp.status, dict(resp.getheaders()), data)
    conn.close()
    return out

print("=== 场景 A：同源浏览器（页面在 127.0.0.1:8080）===\n")

# A1: 首次打开页面 GET / → 拿 Set-Cookie
st, hd, _ = request("GET", "/", {"User-Agent": "Mozilla/5.0 Chrome/125.0.0.0"})
set_cookie = hd.get("Set-Cookie", "")
print(f"A1 GET /        → {st}, Set-Cookie: {set_cookie[:50]}...")
cookie = set_cookie.split(";")[0]

# A2: 浏览器 POST /setup（同源，带 cookie + Origin）— JSON 请求
body = json.dumps({"key": "sk-real-test-12345"})
st, hd, data = request("POST", "/setup",
    {"Content-Type": "application/json", "Origin": "http://127.0.0.1:8080", "Cookie": cookie},
    body)
print(f"A2 POST /setup  → {st}, ACAO={hd.get('Access-Control-Allow-Origin')}")
print(f"   body: {data[:120]}")

# A3: 页面刷新后 cookie 保留，再次 POST
st, hd, data = request("POST", "/setup",
    {"Content-Type": "application/json", "Origin": "http://127.0.0.1:8080", "Cookie": cookie},
    json.dumps({"key": "sk-real-test-12345"}))
print(f"A3 POST /setup  → {st}, body: {data[:120]}")

print("\n=== 场景 B：localhost 访问（常见！）===\n")
# B1: 浏览器从 localhost:8080 打开页面
st, hd, _ = request("GET", "/", {"Host": "localhost:8080", "User-Agent": "Mozilla/5.0"})
set_cookie2 = hd.get("Set-Cookie", "")
print(f"B1 GET /        → {st}, Set-Cookie: {set_cookie2[:50]}...")
cookie2 = set_cookie2.split(";")[0]

# B2: POST /setup，Origin 是 localhost:8080
body = json.dumps({"key": "sk-real-test-12345"})
st, hd, data = request("POST", "/setup",
    {"Content-Type": "application/json", "Origin": "http://localhost:8080", "Cookie": cookie2},
    body)
print(f"B2 POST /setup  → {st}, ACAO={hd.get('Access-Control-Allow-Origin')}")
print(f"   body: {data[:120]}")

print("\n=== 场景 C：OPTIONS 预检（浏览器对 JSON POST 的预检）===\n")
st, hd, data = request("OPTIONS", "/setup",
    {"Origin": "http://127.0.0.1:8080", "Access-Control-Request-Method": "POST",
     "Access-Control-Request-Headers": "content-type"})
print(f"C1 OPTIONS      → {st}, ACAO={hd.get('Access-Control-Allow-Origin')}, "
      f"Allow-Headers={hd.get('Access-Control-Allow-Headers')}")

print("\n=== 场景 D：无 cookie 的 POST（浏览器禁用 cookie / 隐私模式）===\n")
st, hd, data = request("POST", "/setup",
    {"Content-Type": "application/json", "Origin": "http://127.0.0.1:8080"},
    json.dumps({"key": "sk-real-test-12345"}))
print(f"D1 POST /setup  → {st}, body: {data[:120]}")
