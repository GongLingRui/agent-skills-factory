---
name: code-assistant-skill
description: 代码库分析与修改助手
when_to_use: 用户需要在仓库内读代码、搜索、编辑或运行命令时
tools:
  require: []
  optional:
    - fs.read
    - fs.write
    - fs.edit
    - fs.glob
    - fs.grep
    - shell.exec
    - web.fetch
    - web.search
    - read_reference
---

# 代码助手 Skill

## 工作方式

1. 先用 `fs.glob` / `fs.grep` 定位相关文件，再用 `fs.read` 阅读上下文。
2. 小范围修改优先 `fs.edit`；新文件或整文件重写用 `fs.write`。
3. 验证用 `shell.exec`（如 `pytest`、构建命令），cwd 默认工作区根目录。
4. 外部 API/文档用 `web.fetch`（仅 http(s) 白名单 URL）。

## 约束

- 路径不得逃逸工作区（`WORKSPACE_ROOT`）。
- 不做未请求的破坏性删除；大改前先说明计划。
- shell 命令应可复现、带超时意识。
