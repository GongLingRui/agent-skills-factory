# 12. 安全、权限与审计

> 版本：v0.6 · 2026-05-06

---

## 权限校验落在系统层（不是 prompt 层）

prompt 里写"你不能用这个工具"是**不可靠的**——模型可能忘、可能被绕过。**真正的权限必须在 Tool Gateway 硬校验**。

每次工具调用都校验：

- 调用者身份
- Agent ID
- RunSpec ID
- 工具权限
- 输入参数合法性
- 数据域权限
- 超时和频率

---

## 审计分级（默认开 minimal，绝不允许 off）

**P0 起就默认 minimal 级，工程量极小但合规底线守住**。

### 三档审计

| 档位 | trace 内容 | 适用阶段 |
|------|-----------|---------|
| **minimal**（P0 默认） | user_id_hash / agent_id / run_id / tool_calls / token / cost / error / retrieval_ids | **P0/P1，不允许 off** |
| **standard**（P1+） | minimal + prompt 摘要 + retrieval 命中文档 ID | P1 起按合规要求开启 |
| **full**（P2+） | standard + 完整 prompt + 完整 output | 重点 Agent 或合规调查时开启 |

### 关键约束

- agent.yaml 的 audit.level 字段**不允许设为 off**——schema 校验阶段拒绝
- minimal 级的存储成本可忽略（每会话 ~5KB），不构成工程负担
- prompt / output 内容默认不 trace（给业务部门留隐私空间），但**工具调用 + 检索 ID + 错误码必须留**

---

## 用户记忆分层存储（不全装 localStorage）

**企业内网共享电脑、终端管控、清缓存策略是真实风险，不能无脑全装**。改为**按数据敏感度分三层**：

| 数据类型 | 存哪里 | TTL | 加密 |
|---------|--------|-----|------|
| 轻偏好（最近 Agent / UI 设置 / 收藏 / 主题） | **localStorage** | 永久 | 否 |
| 对话历史（消息文本 / 时间戳） | **IndexedDB**（dexie.js 包装） | 30 天 TTL | 可选 SubtleCrypto |
| 敏感文件内容（合同正文 / 公文附件 / 上传文档） | **不持久化**（仅会话内存） | 关 tab 即清 | N/A |

### 机制

- IndexedDB 用 dexie.js 包装（容量大 / 异步 / 索引查询）
- TTL 由 widget 后台定时任务清理过期记录
- 加密 key 派生自用户 SSO（PBKDF2 + 用户 ID hash + salt）
- **敏感文件内容不写任何持久化层**——上传后只在会话内存中处理，会话结束 / 关 tab 即释放
- UI 显式提示："本地存储 30 天后自动清理。共享电脑请勾选退出时清除会话。"

### 好处

- 服务器零业务存储成本
- 合规边界干净（轻偏好 + 对话历史在用户终端，敏感文件不落任何盘）
- 央企共享电脑场景下，敏感数据不会被下一个用户翻出来

### 剩余风险与边界

- **跨设备失效**：用户换电脑会丢历史——提供 export/import JSON 手动迁移
- **用户主动清缓存 / 浏览器清理**：UI 显式提示
- **IndexedDB 加密为可选**：用户开了忘了密码 = 数据废掉；不开 = 共享电脑可见

---

## 敏感文件临时存储安全（对象存储 temp 桶）

上传的合同/公文等敏感文件在解析前可能暂存于对象存储（MinIO）`temp/` 桶，必须满足以下安全约束：

| 约束 | 要求 |
|------|------|
| **服务端加密** | temp 桶必须启用 SSE-S3 或 SSE-KMS，确保静态数据加密 |
| **生命周期策略** | 24 小时自动删除（Object Lifecycle Rule），不留长期副本 |
| **桶访问策略** | 仅 core 服务和 doc-worker 有读写权限，其他服务只读或无权 |
| **网络隔离** | temp 桶不暴露外网 URL，仅内网服务间通过 VPC 访问 |
| **审计** | 所有 temp 桶写操作记录到 MinIO audit log，保留 90 天 |
| **敏感文件不上本地磁盘** | 服务端处理流程：内存缓冲区 → 直传 MinIO temp/ → doc-worker 流式读取解析 → 删除 temp 对象。禁止写入 `/tmp` 或本地文件系统 |

**PostgreSQL 绝不保留文件内容**：`file_uploads` 表只存元数据（file_id、文件名、大小、状态），`extracted_text_path` 指向对象存储路径，不存文本内容。

### 与服务器审计的协调

**关键**：本地存储路线**不与 minimal 审计冲突**——关键审计事件（工具调用、异常、错误码）仍由服务器侧记录最小元数据，但不含 prompt / output 内容。详见 [10.2 审计分级](#审计分级默认开-minimal绝不允许-off)。

---

## SSO / JWT 短令牌交换（portal 集成）

**前提**：portal 已用 JWT 做 SSO，agent factory 复用 portal 的认证体系，不重新做登录。

完整流程、接口定义和实现细节见 [06-api-gateway.md](06-api-gateway.md)。本节只从**安全视角**阐述关键设计：

### 为什么用短令牌交换而不是直接传 portal-JWT

- portal-JWT 一般生命周期长（小时级），泄漏代价大
- short-lived JWT 5 分钟过期，绑定单个 agent + 单次会话，泄漏影响极小
- portal-JWT 的 claim 可能不直接含 agent factory 需要的 scope；交换时按规则重新组装
- 央企合规审计能区分"portal 认证事件"和"agent 调用事件"——**双层留痕**

### 安全要点

- short-lived JWT 用 agent factory 自己的私钥签发，单次使用（jti 防重放）
- session cookie 默认有效期 30 分钟，**不绑定 agent_id**——支持 Agent 切换不用重新换 token
- 后续 API 调用走 session cookie，不再用 short-lived JWT

---

## MAU 计算的最小服务器元数据

**张力**：用户对话内容存浏览器本地（§10.3），但 retention gate（§15.1）需要服务器知道"谁用了哪个 Agent"才能算 MAU。两者怎么共存？

**方案**：服务器只记**最小元数据**，**不含对话内容**：

```yaml
agent_usage_log（每次会话开始时写一条）:
  user_id_hash: <SHA-256(user_id + salt)>   # 不存明文 user_id
  agent_id: contract-review-agent
  date: 2026-05-06                          # 只到日，不到秒
  count: 3                                  # 当日使用次数（同 user_id_hash 同 agent_id 累加）
```

**特点**：

- **用户身份哈希化**：合规友好，不能反查具体用户
- **时间粒度按日**：不能用于行为重建
- **只记次数 / 不记内容**：跟 localStorage 路线不冲突
- **retention 90 天**：超期自动归档，不长期留存

**MAU 算法**：过去 30 天内对该 agent_id 有 ≥1 次 hash 不同的 user_id_hash → 计入该 agent 的 MAU。

---

## 观测性（运维 metrics，与审计分开）

**容易混淆的边界**：

- **审计**：合规留档，每次执行的细节（每行一条），事后追查用
- **观测性**：运维仪表盘，系统健康度的实时聚合（每秒一条），实时报警用

两者数据源可能重合，但消费端、保留期、查询模式都不同。**P0 阶段 minimal 审计已默认开启（§10.2），观测性同样不能省**——没有 metrics 等于运维瞎跑。

### 观测性指标分三层

**系统层**：

- 请求量（QPS）
- P50 / P95 / P99 延迟
- 错误率
- 队列长度
- 资源池利用率（LLM / 文档解析 / 脚本 worker）

**Agent 层**：

- 每个 Agent 的请求量 / 错误率 / P99
- token 消耗 trend
- ui_config 渲染成功率（前端上报）

**业务层**：

- DAU / MAU（按 §10.5）
- 每日新增 Agent 数
- 每日新增对话数
- 用户反馈率（前端 thumbs up/down 上报）

**工具栈**：**Prometheus + Grafana**（企业内网兼容好，开源免费）。可选 OpenTelemetry 做分布式 trace。

---

## MAU 元数据 salt 管理方案

`user_id_hash` 使用 **SHA-256(user_id + salt)** 计算，salt 管理规则：

- **初始化**：平台部署时由运维在 K8s Secret（或等效密钥管理系统）中写入 32 字节随机 salt
- **轮换周期**：每季度轮换一次，轮换触发时旧 salt 保留 90 天（与 `audit.retain_days` 对齐），新 hash 使用新 salt
- **访问控制**：salt 仅审计模块可读，应用代码不直接访问明文 salt
- **备份**：salt 与数据库备份分离存储，恢复时需同时恢复 salt 才能重算 hash

### 双 Salt 期间 MAU 计算去重

salt 轮换期间，同一 user_id 用新旧 salt 会生成两个不同的 hash。MAU 统计时必须去重：

```python
def count_mau(agent_id, start_date, end_date):
    # 1. 分别查新旧 salt 的结果
    old_hashes = query("SELECT DISTINCT user_id_hash FROM agent_usage_logs ...")
    new_hashes = query("SELECT DISTINCT user_id_hash FROM agent_usage_logs ...")

    # 2. 如果日志记录了 user_id_hash 的生成 salt 版本（推荐）
    # 直接 UNION 即可，因为 DISTINCT 是按 hash 去重的
    # 但一个用户会在两个 salt 下各出现一次

    # 3. 去重方案：在 agent_usage_logs 表中增加 salt_version 字段
    # 统计时按 user_id_hash + salt_version 分别计数，再对实际 user_id 去重
    # 由于 user_id 本身不存储，只能采用估算：
    # 取两个集合的并集大小，减去估算的交集（按重叠日期比例）
```

**实际工程方案**：在 `agent_usage_logs` 表中增加 `salt_version` 字段（`VARCHAR(8)`），轮换期间写入新版本号。MAU 统计时：
- 单 salt_version 期：直接 `COUNT(DISTINCT user_id_hash)`
- 双 salt_version 重叠期：分别统计两个 version 的独立 hash 数，取较大值作为估算（保守策略：不重复计数）

保守估算公式：`MAU = MAX(count_old, count_new)`，避免同一用户被重复计入。

## RBAC 权限模型

### 角色定义

| 角色 | 权限范围 | 典型持有人 |
|------|---------|-----------|
| `platform_admin` | 全平台管理：Agent/Skill/Tool 增删改、降级开关、审计查看 | 平台运维团队 |
| `department_admin` | 本部门管理：本部门 Agent 配置修改、灰度发布、用户权限分配 | 业务部门负责人 |
| `agent_owner` | 单个 Agent 管理：修改自己创建的 Agent 的 ui_config / prompt | 业务 Agent 创建者 |
| `user` | 仅使用权限：查看有权限的 Agent 列表、发起对话 | 普通员工 |

### 权限颗粒度

| 权限码 | 说明 | 归属角色 |
|--------|------|---------|
| `agent.read` | 查看 Agent 列表和详情 | user+ |
| `agent.write` | 创建、修改 Agent | agent_owner, department_admin |
| `agent.admin` | 下架、灰度控制、版本管理 | platform_admin, department_admin |
| `skill.publish` | 注册、升级 Skill | platform_admin |
| `skill.read` | 查看 Skill 列表 | department_admin+ |
| `tool.admin` | 注册、禁用 Tool | platform_admin |
| `audit.read` | 查看审计日志 | platform_admin |
| `degradation.control` | 手动触发降级 | platform_admin |

### 权限生效机制

- 用户权限缓存 TTL：5 分钟（Redis）
- 权限变更后最长 5 分钟生效（不实时生效，避免每次请求都查 RBAC）
- Tool Gateway 每次调用时实时校验权限（不受缓存影响，但读取的是缓存中的权限列表）

## Prompt 注入攻击检测与防御

Prompt 注入是 LLM 系统核心安全风险。本系统采用**多层防御**，不依赖单一措施。

### 检测规则（Input Guardrails）

用户输入进入模型前，由 Agent Runner 的 `Input Sanitizer` 按以下规则检测：

| 规则类别 | 检测模式 | 处理动作 |
|---------|---------|---------|
| **指令覆盖** | 匹配 "忽略之前指令" / "forget previous" / "you are now" / "system prompt" 等关键词 | 阻断，返回 `"检测到非法指令，已拦截"`，记审计日志 |
| **角色扮演逃逸** | 匹配 "DAN" / "jailbreak" / "开发者模式" 等已知越狱前缀 | 阻断，返回 `"请求被拒绝"`，记审计日志 |
| **分隔符注入** | 检测输入中包含 `\n\nHuman:` / `<|end|>` / `[/INST]` 等模型分隔符 | 转义或移除分隔符，继续处理，记 warning 日志 |
| **隐藏字符** | 检测零宽字符（U+200B-U+200F）、RTL 覆盖（U+202E）等 | 移除隐藏字符，继续处理 |
| **超长输入** | 单条消息 token 数 > `max_input_tokens`（默认 4000） | 截断并提示"输入过长，已截断" |
| **代码执行试探** | 匹配 `exec(` / `eval(` / `__import__` / `subprocess` 等代码执行模式 | 标记为高风险，降低 `queue_priority` 并增加审计级别 |

### 防御层架构

```
用户输入
  ↓
Layer 1: Input Sanitizer（关键词 / 模式匹配）
  ↓
Layer 2: 结构校验（JSON Schema 校验工具调用参数）
  ↓
Layer 3: Tool Gateway 权限硬校验（RunSpec 白名单 ∩ 用户权限）
  ↓
Layer 4: 模型输出 Parser（拒绝执行未在白名单中的工具调用）
  ↓
Layer 5: 审计日志（所有异常输入留痕，事后追查）
```

### 事后追溯

一旦检测到注入尝试：

- 立即记录到 `security_events` 表（`event_type = PROMPT_INJECTION_ATTEMPT`）
- 包含：user_id、agent_id、输入摘要（前 200 字符）、触发规则、timestamp
- 24 小时内同一 user_id 触发 ≥3 次 → 自动降低该用户所有请求的 `queue_priority` 到 1
- 24 小时内同一 user_id 触发 ≥10 次 → 通知 platform_admin，人工审查

---

## widget 安全 Mitigations

JWT 在 URL 里虽然 5 分钟过期 + 一次性，但仍存在 5 个泄露面：

- 浏览器历史
- 公司代理 / 防火墙日志
- HTTP Referer header
- 第三方分析脚本
- 截图分享

**Mitigations 清单（每条都不可省）**：

| 措施 | 防什么 |
|------|--------|
| widget 加载后**立即从 URL 删除 token** | 浏览器历史泄露 |
| Referrer-Policy: no-referrer | Referer header 泄露 |
| CSP（Content Security Policy）严格模式 | 第三方脚本注入 |
| HTTPS only + HSTS | 网络嗅探 |
| token 一次性 jti | 重放攻击 |
| widget 禁用第三方 SDK | 数据外泄 |
| 后端日志 access log 自动 mask URL 中的 token 参数 | 日志取证泄露 |
