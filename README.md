# Agent 学习日志

从零手写 Agent，**不用任何框架**。每天一个可运行的小实验 + 一份笔记。

## 进度

| Day | 主题 | 产出 | 状态 |
|---|---|---|---|
| 1 | 模型是个无状态函数 | `hello_llm.py` | ✅ |
| 2 | Token、上下文与采样 | `token_lab.py` | ⬜ |
| 3 | 结构化输出 | `extract.py` | ⬜ |
| 4 | 工具调用的原始协议 | `tool_call.py` | ⬜ |
| 5 | Agent Loop v0 | `agent_loop.py` | ⬜ |
| 6 | 多工具与错误处理 | `agent_loop.py` | ⬜ |
| 7 | 复盘 | `NOTES.md` | ⬜ |

## 目录

```
hello_llm.py         Day 1：单次调用 / 四种 role / 无状态证明
NOTES.md             每日笔记与踩坑记录
.vscode/             launch.json + settings.json，按 F5 直接跑
.env.example         配置模板（复制成 .env 后填写）
```

## 怎么跑

1. VS Code 打开本目录，`Ctrl+Shift+P` → `Python: Select Interpreter` → 选 `.venv`
2. 复制 `.env.example` 为 `.env`，填好 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`
3. 按 `F5`，在弹出列表里选「实验1 / 实验2 / 实验3」

`.env` 已在 `.gitignore` 中，不会进仓库。

## 为什么不用框架

Day 1–7 全部手写 HTTP 与循环。框架把「模型申请调用工具 → 本地执行 → 结果回填」封装成装饰器，
没亲手写过这五步，遇到「模型重复调同一个工具」「arguments 是字符串不是字典」就无从查起。
