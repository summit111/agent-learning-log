"""探测你的 API 网关：base_url 和 model 到底该填什么。

背景：走第三方网关（中转站 / 聚合平台 / 厂商计划）时，
      model 名字由**网关**决定，不是厂商官网那个名字。
      唯一可靠的确认方式：问网关要模型列表。

用法：
    python check_api.py

它会做四件事：
    1. 打印你当前 .env 里填的内容（key 打码）
    2. 请求 <base_url>/models，列出所有可用模型 ID
    3. 帮你筛出名字里带 deepseek / flash 的
    4. 用你填的 model 发一次真实请求，验证到底通不通
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def load_env(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        sys.exit(f"找不到 {p.resolve()}，请先把 .env.example 复制成 .env")
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def mask(s: str) -> str:
    if not s:
        return "(空)"
    if len(s) <= 12:
        return s[:2] + "*" * (len(s) - 2)
    return f"{s[:6]}...{s[-4:]}   (长度 {len(s)})"


load_env()

KEY = os.environ.get("LLM_API_KEY", "")
BASE = os.environ.get("LLM_BASE_URL", "").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "")

print("=" * 62)
print("当前配置")
print("=" * 62)
print(f"  LLM_API_KEY  = {mask(KEY)}")
print(f"  LLM_BASE_URL = {BASE or '(空)'}")
print(f"  LLM_MODEL    = {MODEL or '(空)'}")

H = {"Authorization": f"Bearer {KEY}"}


def get_models() -> list[str]:
    """尝试几个常见的模型列表地址。"""
    candidates = [f"{BASE}/models"]
    if not BASE.endswith("/v1"):
        candidates.append(f"{BASE}/v1/models")

    for url in candidates:
        print(f"\n[探测] GET {url}")
        try:
            r = requests.get(url, headers=H, timeout=20)
        except Exception as e:
            print(f"       连接失败：{type(e).__name__}: {e}")
            continue

        print(f"       HTTP {r.status_code}")
        if r.status_code != 200:
            print(f"       响应：{r.text[:200]}")
            continue

        try:
            data = r.json()
        except ValueError:
            print(f"       返回的不是 JSON：{r.text[:200]}")
            continue

        items = data
        if isinstance(data, dict):
            items = data.get("data") or data.get("models") or []

        ids: list[str] = []
        if isinstance(items, list):
            for it in items:
                if isinstance(it, str):
                    ids.append(it)
                elif isinstance(it, dict):
                    mid = it.get("id") or it.get("name") or it.get("model")
                    if mid:
                        ids.append(str(mid))

        if ids:
            return ids

    return []


ids = get_models()

if not ids:
    print("""
[结论] 拿不到模型列表。

    可能的原因，按可能性排序：
      1. base_url 写错了（多了/少了 /v1，或根本不是这个网关的地址）
      2. key 无效或没有这个计划的权限（401 / 403）
      3. 这个网关不提供 /models 接口 —— 那就只能翻它的文档，手抄模型名
      4. 你需要的是 Anthropic 风格接口（/v1/messages），不是 OpenAI 风格

    下一步：确认 key 和地址都抄对了，再跑一次。
""")
    sys.exit(1)

print(f"\n[结果] 共 {len(ids)} 个可用模型：")
for mid in ids:
    print(f"       - {mid}")

hits = [i for i in ids if "deepseek" in i.lower()]
if hits:
    print("\n[筛选] 名字里带 deepseek 的：")
    for mid in hits:
        mark = ""
        if "flash" in mid.lower():
            mark = "   ← 带 flash，多半就是你想要的那个"
        print(f"       * {mid}{mark}")
    print("\n       把这一整串**原样**复制到 .env 的 LLM_MODEL，大小写和横线都不能改。")
else:
    print("\n[筛选] 没有名字带 deepseek 的模型。检查一下是不是这个订阅不包含它。")

# ---------------------------------------------------------------- 真实调用验证
print("\n" + "=" * 62)
print("真实调用验证")
print("=" * 62)

if not MODEL:
    sys.exit("LLM_MODEL 是空的，先填上再跑")

chat_urls = [f"{BASE}/chat/completions"]
if not BASE.endswith("/v1"):
    chat_urls.append(f"{BASE}/v1/chat/completions")

ok = False
for url in chat_urls:
    print(f"\n[POST] {url}")
    print(f"       model = {MODEL}")
    try:
        r = requests.post(
            url,
            headers={**H, "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": "只回答两个字：收到"}],
                "temperature": 0,
                "max_tokens": 10,
            },
            timeout=60,
        )
    except Exception as e:
        print(f"       连接失败：{type(e).__name__}: {e}")
        continue

    print(f"       HTTP {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            content = json.dumps(data, ensure_ascii=False)[:300]
        print(f"       回答：{content!r}")
        print(f"       usage：{data.get('usage')}")
        ok = True
        break

    print(f"       响应：{r.text[:400]}")

print("\n" + "=" * 62)
if ok:
    print("[通过] 配置可用。把这几行填进 .env，然后跑 python hello_llm.py")
    print(f"        LLM_BASE_URL={BASE}")
    print(f"        LLM_MODEL={MODEL}")
else:
    print("""
[失败] 调用没通。看上面的 HTTP 状态码：

    401 / 403  → key 不对，或这个计划没有 API 调用权限
                 （很多「订阅制」产品只给自家 CLI 用，不签发裸 key）
    404        → 地址不对：确认 base_url 要不要 /v1
                 ，以及接口是不是 Anthropic 风格 /v1/messages
    400        → model 名字不对：回到上面的模型列表，原样复制
    402 / 429  → 没额度 / 被限流
""")
