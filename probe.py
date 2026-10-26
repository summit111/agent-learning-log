"""探测 base_url 的真实身份：它到底是 API，还是一个网页？

用法：
    python probe.py                 # 用 .env 里的 LLM_BASE_URL
    python probe.py https://xxx/v1  # 临时指定

很多 404 的真相是：你填的是网站首页，不是 API 地址。
浏览器打开有 200，不代表它是接口 —— 网页也会返回 200。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def load_env(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

KEY = os.environ.get("LLM_API_KEY", "")
BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LLM_BASE_URL", "")).rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

if not BASE:
    sys.exit("没有 base_url。用法：python probe.py https://你的地址")

print("=" * 68)
print(f"探测目标 : {BASE}")
print(f"候选模型 : {MODEL}")
print("=" * 68)

parts = urlsplit(BASE)
origin = f"{parts.scheme}://{parts.netloc}"
bearer = {"Authorization": f"Bearer {KEY}"}


# ---------------------------------------------------------------- 0. 这是网页还是接口？
print("\n[0] 先看这个地址到底是什么")
try:
    r = requests.get(origin, timeout=15, allow_redirects=True)
    ctype = r.headers.get("content-type", "?").split(";")[0].strip()
    print(f"    {origin}")
    print(f"    状态码      : {r.status_code}")
    print(f"    Content-Type: {ctype}")
    print(f"    服务端      : {r.headers.get('server', '?')}")
    print(f"    最终地址    : {r.url}")

    if "html" in ctype.lower():
        head = " ".join(r.text.split())[:150]
        print(f"    开头内容    : {head}")
        print("\n    ⚠️ 这是**网页**，不是 API 接口。")
        print("       网页返回 200 只说明网站能打开，不代表这台机器提供 /chat/completions。")
        print("       你需要的是后台文档里的『API Base URL / Endpoint』，")
        print("       它通常长得像 https://api.xxx.com/v1 或 https://xxx.com/api/v1")
    elif "json" in ctype.lower():
        print(f"    开头内容    : {' '.join(r.text.split())[:150]}")
        print("\n    ✅ 返回 JSON，像是接口根路径。继续往下试具体端点。")
    else:
        print(f"    开头内容    : {' '.join(r.text.split())[:150]}")
except Exception as e:
    print(f"    连接失败: {type(e).__name__}: {e}")


# ---------------------------------------------------------------- 1. 路径矩阵
PREFIXES = ["", "/v1", "/api/v1", "/zen/v1", "/api", "/openai/v1"]
bases: list[str] = []
if BASE.endswith("/v1") or BASE.endswith("/v1/"):
    bases = [BASE]
else:
    for p in PREFIXES:
        cand = BASE + p
        if cand not in bases:
            bases.append(cand)

print("\n[1] 逐个试 GET /models")
model_hits: list[str] = []
for b in bases:
    url = f"{b}/models"
    try:
        r = requests.get(url, headers=bearer, timeout=15)
        flag = {200: "✅", 401: "🔑", 403: "🔑", 404: "❌"}.get(r.status_code, "·")
        print(f"    {flag} {r.status_code}  {url}")
        if r.status_code == 200:
            model_hits.append(b)
            try:
                data = r.json()
                items = data.get("data", data) if isinstance(data, dict) else data
                ids = [
                    (x.get("id") if isinstance(x, dict) else str(x))
                    for x in (items if isinstance(items, list) else [])
                ]
                if ids:
                    print(f"         可用模型：{', '.join(ids[:20])}")
            except Exception:
                pass
        elif r.status_code in (401, 403):
            print(f"         └─ 路径存在！但 key/权限有问题：{' '.join(r.text.split())[:100]}")
    except Exception as e:
        print(f"    ERR    {url}  ({type(e).__name__})")

print("\n[2] 逐个试 POST /chat/completions（OpenAI 格式）")
openai_hits: list[str] = []
body = {"model": MODEL, "messages": [{"role": "user", "content": "说：收到"}], "max_tokens": 16}
for b in bases:
    url = f"{b}/chat/completions"
    try:
        r = requests.post(url, headers=bearer, json=body, timeout=20)
        flag = {200: "✅", 401: "🔑", 403: "🔑", 404: "❌", 400: "⚠️"}.get(r.status_code, "·")
        print(f"    {flag} {r.status_code}  {url}")
        if r.status_code == 200:
            openai_hits.append(b)
            print(f"         └─ 通了！回答：{r.json().get('choices', [{}])[0].get('message', {}).get('content')!r}")
        elif r.status_code in (400, 401, 403, 422):
            print(f"         └─ {r.text.splitlines()[0][:140]}")
    except Exception as e:
        print(f"    ERR    {url}  ({type(e).__name__})")

# ---------------------------------------------------------------- 结论
print("\n" + "=" * 68)
if openai_hits:
    print("✅ 找到了。把这一行写进 .env：")
    print(f"     LLM_BASE_URL={openai_hits[0]}")
    print("   然后跑 python hello_llm.py")
elif model_hits:
    print("✅ 接口是通的，模型列表也能拿到：")
    print(f"     LLM_BASE_URL={model_hits[0]}")
    print("   但 /chat/completions 没通 —— 可能要用别的对话路径，或需要正确的 model 名。")
else:
    print("❌ 一条都没通。")
    print()
    print("    如果 [0] 显示 Content-Type 是 text/html：")
    print("       → 你填的是网站地址，不是 API 地址。这是最常见的错。")
    print("       → 回平台后台找『API』『开发者』『Base URL』，那一行才是你要的。")
    print()
    print("    如果 [0] 也是 404 或连不上：")
    print("       → 地址本身抄错了。别自己拼，整行复制。")
    print()
    print("    如果出现 🔑 401/403：")
    print("       → 路径对了，但 key 没用，或这个计划不给 API 权限。")
print("=" * 68)
