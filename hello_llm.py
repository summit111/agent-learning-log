"""Day 1：把大模型当成一个「无状态的 HTTP 接口」来认识它。

在 VS Code 里运行（三选一）：
    · 按 F5  → 选「实验1 / 实验2 / 实验3」调试配置（.vscode/launch.json 已配好）
    · 右上角 ▷ 「Run Python File」，默认跑实验 1
    · 集成终端：python hello_llm.py roles

本文件不使用任何 Agent 框架，连 SDK 都不用，直接发 HTTP。
目的就是让你看清：所谓 Agent，底层不过是一次次这样的请求。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

try:  # Windows 控制台编码兜底
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


# --------------------------------------------------------------------------
# 1. 极简 .env 加载器（不引入额外依赖）
# --------------------------------------------------------------------------
def load_env(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # setdefault：系统环境变量优先，方便临时覆盖
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()

API_KEY = os.environ.get("LLM_API_KEY", "").strip()
BASE_URL = os.environ.get("LLM_BASE_URL", "").strip().rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "").strip()
# opencode 网关要求带一个「会话标识」，否则 /chat/completions 直接 400 MissingSessionID。
# 只用于路由与会话亲和，值稳定即可，不必是真实会话 id。
SESSION_ID = os.environ.get("LLM_SESSION_ID", "agent-learning-log").strip()


# --------------------------------------------------------------------------
# 2. 唯一的网络函数：发一次请求，原样返回 JSON
# --------------------------------------------------------------------------
def chat(messages: list[dict], temperature: float = 0.7, **extra: Any) -> dict:
    """messages 里有什么，模型就看到什么 —— 没有任何隐藏的「记忆」。"""
    if not API_KEY or not BASE_URL or not MODEL:
        sys.exit("配置不全：.env 里的 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 三行都要填")

    payload = {"model": MODEL, "messages": messages, "temperature": temperature, **extra}

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    # 只有 opencode 的 zen/go 端点要这个头，按域名判断，别把非标准头发给别家
    if "opencode.ai" in BASE_URL:
        headers["x-opencode-session"] = SESSION_ID

    resp = requests.post(
        f"{BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=120,
    )

    if resp.status_code != 200:
        # 把服务端原话打出来，比抛一个 HTTPError 有用得多
        sys.exit(f"请求失败 HTTP {resp.status_code}\n{resp.text[:1000]}")

    return resp.json()


def hr(title: str) -> None:
    print("\n" + "=" * 62)
    print(title)
    print("=" * 62)


# --------------------------------------------------------------------------
# 实验 1：单次调用
# --------------------------------------------------------------------------
def exp1_single_call() -> None:
    hr("实验 1：发一次请求，看模型返回的原始 JSON")

    messages = [
        {"role": "system", "content": "你是一个简洁的助手，回答不超过 30 个字。"},
        {"role": "user", "content": "用一句话解释什么是 AI Agent。"},
    ]

    print(">>> 发出去的 messages：")
    print(json.dumps(messages, ensure_ascii=False, indent=2))

    data = chat(messages)

    print("\n>>> 服务端返回的原始 JSON：")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    print("\n>>> 逐字段拆解：")
    print(f"    id      = {data.get('id')}")
    print(f"    model   = {data.get('model')}")

    choice = data["choices"][0]
    reason = choice.get("finish_reason")
    reason_meaning = {
        "stop": "模型自然说完了",
        "length": "被 max_tokens 截断了（回答不完整）",
        "tool_calls": "模型想调用工具（Day 4 的主角）",
    }.get(reason, "其它")
    print(f"    choices[0].finish_reason = {reason!r}   # {reason_meaning}")
    print(f"    choices[0].message.role  = {choice['message'].get('role')!r}")
    print(f"    choices[0].message.content = {choice['message'].get('content')!r}")

    usage = data.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    print("\n>>> usage —— 不是账单，是你的「上下文预算表」：")
    print(f"    输入 {prompt_tokens:>6} tok  ← 你塞进去的全部内容（system + 历史 + 以后要加的工具 schema）")
    print(f"    输出 {completion_tokens:>6} tok  ← 模型生成的内容，下一轮又会变成输入")

    print("""
>>> 你现在应该接受的事实：
    1. 这是一次普通的 HTTP POST，没什么魔法。
    2. 返回的是一个 JSON，答案在 choices[0].message.content 里。
    3. 「模型」只负责生成文本：它没有记忆、没有状态、不会执行任何东西。
    4. usage.prompt_tokens 才是真正要盯的数字 ——
       窗口是有限的，Agent 之所以会「忘事」，往往就是这里先撞到了顶。
""")


# --------------------------------------------------------------------------
# 实验 2：四种 role
# --------------------------------------------------------------------------
def exp2_roles() -> None:
    hr("实验 2：同一个问题，只换 system，看行为怎么变")

    question = "介绍一下你自己。"
    system_prompts = [
        "你是一位严谨的技术面试官，回答要克制、不超过 40 字。",
        "你是一只话痨的猫，每句话末尾都要加「喵」。",
    ]

    for sp in system_prompts:
        messages = [
            {"role": "system", "content": sp},
            {"role": "user", "content": question},
        ]
        data = chat(messages, temperature=0.3)
        print(f"\n[system] {sp}")
        print(f"[回答]   {data['choices'][0]['message']['content']}")

    print("""
>>> 结论：system 不是什么「设置项」，它就是 messages 数组里的第一条普通消息。
    模型看到的是所有消息拼起来的一整段文本，只是被打了不同的标记。

    四种 role 的语义（记住这张表，能用一整年）：
      system    —— 规则、人设、输出格式约束。放最前面
      user      —— 人的输入
      assistant —— 模型自己说过的话（Day 4 里它「申请调用工具」也在这）
      tool      —— 工具执行的结果（Day 4 才会用到）

    ⚠️ 易错点：很多人以为 system 有特殊权限。没有。
       它只是排在最前面的一条消息，所以「用户让我忽略 system」这种事才可能发生 ——
       这就是 Day 14 安全问题的起点。
""")


# --------------------------------------------------------------------------
# 实验 3：无状态
# --------------------------------------------------------------------------
def exp3_history() -> None:
    hr("实验 3：证明「模型不记得上一轮」")

    q1 = "我叫小明，请记住我的名字。"
    r1 = chat([{"role": "user", "content": q1}])
    a1 = r1["choices"][0]["message"]["content"]
    print(f"[第 1 轮] user      : {q1}")
    print(f"[第 1 轮] assistant : {a1}")
    print(f"[第 1 轮] prompt_tokens = {r1['usage']['prompt_tokens']}")

    q2 = "我叫什么名字？"

    print("\n--- 反面教材：只把新问题发过去 ---")
    r2 = chat([{"role": "user", "content": q2}])
    print(f"[第 2 轮] 模型回答 : {r2['choices'][0]['message']['content']}")
    print("    ↑ 它不知道你叫小明，因为这次请求里没有任何上一轮的内容。")
    print(f"    ↑ prompt_tokens 只有 {r2['usage']['prompt_tokens']}，因为真的只有一句话。")

    print("\n--- 正确做法：把完整历史一起发过去 ---")
    r3 = chat([
        {"role": "user", "content": q1},
        {"role": "assistant", "content": a1},
        {"role": "user", "content": q2},
    ])
    print(f"[第 2 轮] 模型回答 : {r3['choices'][0]['message']['content']}")
    print("    ↑ 这次它知道了。")
    print(f"    ↑ prompt_tokens 涨到 {r3['usage']['prompt_tokens']}")

    ratio = r3["usage"]["prompt_tokens"] / max(r2["usage"]["prompt_tokens"], 1)
    print(f"    ↑ 是只发一句时的 {ratio:.1f} 倍。这个倍数，就是「记忆」的代价。")

    print("""
>>> 两句话总结：
    1. 「记忆」不是模型的能力，是你每次请求时自己带上的上下文。
    2. 上下文越长越慢、越容易丢中间信息（lost in the middle），最后撞上窗口上限。
       所以「上下文工程」不是玄学，是「带什么、怎么带得省」的权衡。
""")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "single"
    routes = {
        "single": exp1_single_call,
        "roles": exp2_roles,
        "history": exp3_history,
    }
    if step not in routes:
        sys.exit(f"未知参数 {step!r}，可用：single / roles / history")
    routes[step]()
