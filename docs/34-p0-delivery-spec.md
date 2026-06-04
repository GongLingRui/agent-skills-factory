# 34. P0 交付裁剪规范

> 版本：v0.6 · 2026-05-06

**相关**：[05-runspec.md](05-runspec.md)（P0 典型形状与完整形态对照）、[47-prd-alignment.md](47-prd-alignment.md)（与 PRD 口径、审计写入 vs P0.5）。

---

## 目的

P0 阶段（声明式 Agent App + 用户入口）需要快速上线 MVP，部分功能/字段在 P0 阶段**禁用、留空或固定默认值**。本文档明确 P0 阶段 RunSpec 字段、Skill 功能、系统特性的启用状态，确保前后端开发边界清晰。

---

## P0 阶段 RunSpec 字段启用表

| RunSpec 字段 | P0 状态 | 说明 |
|-------------|---------|------|
| `runspec_schema_version` | ✅ 启用 | 固定为 `1` |
| `run_id` | ✅ 启用 | 正常生成 |
| `agent_id` | ✅ 启用 | 正常生成 |
| `agent_version` | ✅ 启用 | 正常生成 |
| `skill_id` | ✅ 启用 | 正常生成 |
| `skill_version` | ✅ 启用 | 正常生成 |
| `skill_package_hash` | ✅ 启用 | 正常计算 |
| `user_id` | ✅ 启用 | 正常生成 |
| `department` | ✅ 启用 | 正常生成 |
| `prompt_parts` | ✅ 启用 | 完整拼装（含 platform_policy / org_policy / agent_instruction / risk_tier / SKILL.md / always_references） |
| `lazy_references` | ✅ 启用 | 正常生成路径列表 |
| `indexed_references` | ✅ 启用 | 正常生成 scope 列表 |
| `allowed_tools` | ✅ 启用 | 完整计算权限交集 |
| `retrieval_scopes` | ✅ 启用 | 完整计算权限交集 |
| `script_hooks` | ❌ 禁用 | **固定为空对象 `{}`** |
| `output_schema` | ✅ 启用 | 正常生成名称 |
| `runtime` | ✅ 启用 | 完整生成（model / fallback / max_turns / timeout / max_tokens） |
| `audit` | ✅ 启用 | 完整生成，默认 `level: minimal` |

**关键约束**：`script_hooks` 在 P0 阶段必须为空，Compiler 遇到 Skill 包声明了 `scripts` 时：**忽略脚本声明，不报错，不写入 RunSpec**。

---

## P0 阶段 Skill 包功能启用表

| Skill 功能 | P0 状态 | 说明 |
|-----------|---------|------|
| `SKILL.md` 主体指令 | ✅ 启用 | 完整加载 |
| `enterprise.yaml` 执行字段 | ✅ 启用 | `tools`、`knowledge_scopes`、`output_schema`、`limits` 正常读取 |
| `enterprise.yaml` risk_tier | ✅ 启用 | 正常映射为 prompt |
| `references/` always 加载 | ✅ 启用 | 拼进 prompt_parts |
| `references/` on_demand 加载 | ✅ 启用 | 写入 lazy_references，运行时通过 read_reference 读取 |
| `references/` indexed 加载 | ✅ 启用 | 写入 indexed_references |
| `scripts/` build-time | ✅ 启用 | CI 校验、评测可用 |
| `scripts/` preprocess | ❌ 禁用 | **忽略**，P2 才开放 |
| `scripts/` postprocess | ❌ 禁用 | **忽略**，P2 才开放 |
| `schemas/` | ✅ 启用 | 输出校验 |
| `evals/` | ✅ 启用 | 评测集，Skill 入库前必须跑通 |
| `templates/` | ✅ 启用 | load_policy=always 时拼进 prompt |

---

## P0 阶段系统特性启用表

| 特性 | P0 状态 | 说明 |
|------|---------|------|
| Agent App 注册中心 | ✅ 启用 | 完整功能 |
| Skill Compiler | ✅ 启用 | 完整功能（script_hooks 输出空对象） |
| Agent Runner 工具调用循环 | ✅ 启用 | 完整功能 |
| Tool Gateway 权限校验 | ✅ 启用 | 完整功能 |
| 模型网关 + 队列 | ✅ 启用 | 完整功能 |
| API 网关 + SSO | ✅ 启用 | `/auth/exchange` + session cookie |
| Chat Widget MVP | ✅ 启用 | SSE 流式、文件上传、分层存储 |
| Portal 集成 | ✅ 启用 | window.open 新 tab |
| Agent 版本管理 | ✅ 启用 | full / canary / pinned |
| Agent 灰度发布 | ✅ 启用 | percent / target_departments |
| RunSpec 不变性 | ✅ 启用 | 核心约束 |
| Checkpoint 机制 | ✅ 启用 | 页面刷新恢复 |
| Schema 校验 | ✅ 启用 | JSON Schema 校验 + 最多 2 次重试 |
| 审计（minimal） | ✅ 启用 | 默认开启，不允许 off |
| Token 预算 | ✅ 启用 | 层级预算 + 超限处理 |
| 限流（IP / 用户 / 全局） | ✅ 启用 | 入口限流 + Tool Gateway 限流 |
| 熔断 | ✅ 启用 | Tool Gateway 错误率熔断 |
| 降级策略 | ✅ 启用 | 6 级降级，手动 + 自动恢复 |
| 文档解析 Worker | ✅ 启用 | 同步解析（<10MB），大文件流式 |
| 受控脚本 Worker | ❌ 禁用 | P0 不部署 Worker 池 |
| MCP 工具接入 | ❌ 禁用 | P1 评估 |
| 用户反馈（👍/👎） | ✅ 启用 | 前端展示 + 后端存储 |
| Agent 切换 | ✅ 启用 | 顶栏下拉，不换 token |
| 本地历史 + 导出导入 | ✅ 启用 | localStorage + IndexedDB |
| 加密（SubtleCrypto） | ⚠️ 可选 | 默认关闭，UI 可开启 |
| 移动端响应式 | ✅ 启用 | 三档断点适配 |
| 消息队列（Redis Streams） | ✅ 启用 | 审计、checkpoint、quota 异步写入 |
| 定时任务 | ✅ 启用 | MAU 体检、会话清理、健康探测、降级恢复、缓存预热 |
| 数据归档 | ⚠️ 简化 | minimal 审计 90 天后物理删除；standard/full 标记 archived 但不自动转对象存储 |
| 备份 | ✅ 启用 | PG 全量 + Redis RDB |
| CI/CD | ✅ 启用 | 镜像构建、staging 冒烟、生产灰度 |

---

## P0 阶段 Prompt 注入检测降级行为

P0 阶段审计级别固定为 `minimal`，无法动态提升。当 Input Sanitizer 检测到"代码执行试探"等高风险输入时：

| 动作 | P0 行为 | P1+ 行为 |
|------|---------|---------|
| 降低 `queue_priority` | ✅ 生效 | ✅ 生效 |
| 记录 warning 日志 | ✅ 生效 | ✅ 生效 |
| 提升审计级别（如从 minimal 提升到 standard） | ❌ **不执行**（P0 不支持动态调整审计级别） | ✅ 生效 |

**工程实现**：P0 阶段检测到注入试探时，仅降低优先级 + 记 warning 日志，不触发审计级别变更。P1 后接入动态审计级别调整。

---

## P0 阶段 Tool 可用清单

| Tool | P0 状态 | 说明 |
|------|---------|------|
| `kb.search` | ✅ 启用 | 知识库检索 |
| `doc.extract` | ✅ 启用 | 文档解析（<10MB 同步，大文件异步） |
| `read_reference` | ✅ 启用 | 按需读取 Skill reference |
| 内部 API（OA/ERP 等） | ❌ 禁用 | P1 按需求逐个接入 |
| MCP Server | ❌ 禁用 | P1 评估 |
| 受控脚本 | ❌ 禁用 | P2 开放 |

---

## P0 阶段前端组件裁剪

| 组件 | P0 状态 | 说明 |
|------|---------|------|
| 顶栏（Agent 名称 + 头像 + 用户） | ✅ 启用 | |
| 顶栏 Agent 下拉切换 | ✅ 启用 | 收藏 + 最近 |
| 消息流（SSE 流式渲染） | ✅ 启用 | |
| 输入框 + 发送 | ✅ 启用 | |
| 文件上传 | ✅ 启用 | 前端预检 + 后端二次校验 |
| 快捷指令 | ✅ 启用 | 按 ui_config 渲染 |
| 侧栏历史列表 | ✅ 启用 | |
| 导出 / 导入 JSON | ✅ 启用 | |
| 👍 / 👎 反馈 | ✅ 启用 | |
| 加密开关 | ⚠️ 可选 | 默认隐藏 |
| 移动端适配 | ✅ 启用 | |
| 浏览器兼容性降级提示 | ✅ 启用 | |

---

## Compiler P0 行为：遇到带 scripts 的 Skill 包

```python
def compile_runspec(agent_yaml, skill_package, user_context):
    # ... 正常编译流程 ...

    # P0 特殊处理：忽略 scripts 声明
    if skill_package.enterprise.get("scripts"):
        logger.info(
            "Skill %s declares scripts, ignoring in P0",
            skill_package.id
        )
        run_spec.script_hooks = {}
    else:
        run_spec.script_hooks = {}

    # ... 继续生成其他字段 ...
    return run_spec
```

**不报错、不阻塞**：Skill Creator 产出的 Skill 包即使包含 `scripts/` 目录，P0 阶段也能正常入库和绑定，只是脚本不进入生产运行。

---

## SSE 错误事件与 Runner 状态映射

P0 阶段前端收到的 SSE `error` 事件与后端 Runner 内部状态的映射关系：

| SSE error code | Runner 内部状态 | 触发场景 | 前端行为 | 是否可恢复 |
|---------------|----------------|---------|---------|-----------|
| `SESSION_EXPIRED` | `session_timeout` | 30 分钟无活动 | 自动调用 `/init` 开新会话，提示"会话已过期" | 是（新会话） |
| `MODEL_TIMEOUT` | `model_timeout` | 模型 60s 无响应 | 显示重试按钮，保留已输入的问题 | 是（重试） |
| `RATE_LIMITED` | `rate_limited` | 触发用户/Agent/全局限流 | 显示倒计时，自动重试或提示"服务繁忙" | 是（等待后） |
| `TOOL_UNAVAILABLE` | `tool_offline` | Tool Gateway 熔断或手动下线 | 提示"部分工具暂不可用"，继续回答但可能不完整 | 是（降级回答） |
| `SCHEMA_VALIDATION_FAILED` | `schema_fail` | 输出不符合 JSON Schema | 展示原始输出 + 橙色警示"格式异常，已记录" | 否（已结束） |
| `MAX_TURNS_REACHED` | `max_turns` | 达到 `max_turns` 上限 | 提示"本轮对话已达上限，请开新会话" | 是（新会话） |
| `RUNSPEC_VERSION_MISMATCH` | `version_error` | RunSpec schema 版本不兼容 | 强制刷新页面 | 是（刷新后） |
| `INTERNAL_ERROR` | `internal_error` | 未预期的服务端异常 | 提示"系统异常，请稍后重试"，带重试按钮 | 是（重试） |

### Runner 向 SSE 发送 error 的伪代码

```python
async def runner_loop(run_spec, session):
    try:
        # ... 正常执行 ...
        pass
    except SessionTimeout:
        await sse_send_error("SESSION_EXPIRED", "会话已过期", retryable=False)
        await session_manager.close(session.id)
    except ModelTimeout:
        await sse_send_error("MODEL_TIMEOUT", "模型响应超时", retryable=True)
        # 不关闭 session，允许重试
    except ToolUnavailable as e:
        await sse_send_error("TOOL_UNAVAILABLE", str(e), retryable=True)
        # 降级：继续执行但标记 tool 不可用
    except SchemaValidationFailed:
        await sse_send_error("SCHEMA_VALIDATION_FAILED", "输出格式校验失败", retryable=False)
        # 已生成内容作为 raw_output 返回，前端展示
    except MaxTurnsReached:
        await sse_send_error("MAX_TURNS_REACHED", "达到最大对话轮数", retryable=False)
        await session_manager.close(session.id)
    except Exception as e:
        logger.exception("Runner internal error")
        await sse_send_error("INTERNAL_ERROR", "系统内部错误", retryable=True)
```

---

## P0 验收 checklist

- [ ] 用户从 portal 点击 Agent → 正常打开 widget → 可对话
- [ ] SSE 流式输出正常，工具调用卡片正常展示
- [ ] 文件上传 <10MB 同步解析，模型可引用文件内容
- [ ] Agent 切换不用重新换 token，历史独立
- [ ] 页面刷新后从 checkpoint 恢复，不丢失上下文
- [ ] 审计日志正常写入（minimal 级）
- [ ] 限流、熔断、降级可手动触发并生效
- [ ] CI 流水线通过（lint + unit + integration；Skill **eval** 闭环属 P1）
- [ ] Staging 冒烟测试通过
- [ ] 安全测试通过（JWT、权限、XSS、文件上传）

---

## 与本仓库实现的对应（持续对照）

| 上文条目 | 仓库侧落地 |
|----------|------------|
| `script_hooks = {}`、Skill 声明 scripts 不阻塞 | `core/compiler.py`；单测 `tests/unit/test_p0_delivery_spec.py` |
| P0 样本 Agent（制度问答 + 合同审查） | 迁移 `20260508_0005_seed_policy_contract_agents.py`：`policy-qa-agent`、`contract-review-agent`（另含 `demo-agent`） |
| 自动化质量门禁 | `backend/scripts/verify_p0.py`（ruff + pytest）；GitHub Actions `.github/workflows/ci.yml`（含 PostgreSQL 上 `alembic upgrade head` + DB 冒烟） |
| 门户集成演示 | `examples/portal-widget-host.html` |
| 首次上线评审（签字） | 模板 [p0-production-review-template.md](p0-production-review-template.md)，细则仍以 [37-production-checklist.md](37-production-checklist.md) 为准 |
| P2/P3（运行时脚本、DAG/Router 等） | **不在 P0/P1 裁剪范围内**；路线图与冻结清单见 [50-p2-p3-phase-assessment.md](50-p2-p3-phase-assessment.md)，仍须保持本文「`script_hooks` 恒 `{}`」直至专项排期 |

上述 checklist **仍需联调/Staging/安全的人工勾选**；编码门禁不能替代业务与安全签收。
