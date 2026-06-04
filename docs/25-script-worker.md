# 25. 受控脚本 Worker 池设计

> 版本：v0.6 · 2026-05-06

---

## 一句话职责

**在严格沙箱中执行 Skill 包声明的预处理 / 后处理脚本**，隔离风险、防逃逸、全审计。

**类比**：化学实验室的通风橱——脚本在里面跑，接触不到外部网络，跑完自动清场，全程监控录像。

---

## 为什么必须受控

Claude 原生允许 Claude 通过 bash 执行 scripts/ 下的脚本。**本系统不允许**：

| 风险 | 场景 | 本系统对策 |
|------|------|-----------|
| 恶意代码执行 | Skill 包被篡改，植入木马 | 脚本静态分析 + 沙箱执行 |
| 网络外泄 | 脚本把数据发到外部服务器 | 沙箱禁止网络 |
| 依赖投毒 | pip install 恶意包 | 禁止安装依赖，只用系统预装库 |
| 越权文件访问 | 脚本读取 /etc/passwd | 只读临时目录 + chroot |
| 资源耗尽 | 死循环 / 内存炸弹 | CPU / 内存 / 时间限制 |

---

## 脚本类型与生命周期

| 类型 | 运行时 | 权限 | 说明 |
|------|--------|------|------|
| **build-time** | CI/CD | 无限制 | 校验、生成 schema、跑 eval——**不进入生产** |
| **preprocess** | 生产，受控 Worker | 受限 | 文档清洗、格式标准化、输入校验 |
| **postprocess** | 生产，受控 Worker | 受限 | 输出格式化、后校验、敏感信息脱敏 |
| **arbitrary** | **禁止** | — | 不允许任意运行时插件 |

---

## 脚本声明（enterprise.yaml）

```yaml
scripts:
  preprocess:
    - id: normalize_contract_text
      entry: scripts/normalize_contract_text.py
      mode: controlled_worker
      timeout_seconds: 10
      network: false
      filesystem: temp_only
      max_memory_mb: 512
      allowed_runtime: python3.11
      input_schema: schemas/normalize-input.json
      output_schema: schemas/normalize-output.json
```

**字段说明**：

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 脚本唯一标识 |
| `entry` | 是 | 入口文件路径（相对 Skill 包根目录） |
| `mode` | 是 | 必须为 `controlled_worker` |
| `timeout_seconds` | 否 | 默认 10 秒 |
| `network` | 否 | 默认 `false` |
| `filesystem` | 否 | `temp_only`（默认）/ `read_only` |
| `max_memory_mb` | 否 | 默认 512 |
| `allowed_runtime` | 否 | `python3.11` / `node20`，默认 `python3.11` |
| `input_schema` | 否 | 输入参数 JSON Schema |
| `output_schema` | 否 | 输出结果 JSON Schema |

---

## Worker 池架构

```
┌─────────────────┐      ┌─────────────────────────────┐      ┌─────────────────┐
│  Tool Gateway   │─────>│      Script Worker Pool     │─────>│   Audit Log     │
│  (路由脚本调用)  │      │  ┌─────┐ ┌─────┐ ┌─────┐   │      │  (执行记录)      │
└─────────────────┘      │  │ W-1 │ │ W-2 │ │ W-3 │... │      └─────────────────┘
                         │  └──┬──┘ └──┬──┘ └──┬──┘   │
                         │     └───────┼───────┘      │
                         │        任务队列 (Redis)      │
                         └─────────────────────────────┘
                                    │
                                    ↓
                         ┌─────────────────────────────┐
                         │        沙箱运行时            │
                         │  • gVisor / Firecracker VM  │
                         │  • 或 seccomp-bpf + chroot   │
                         └─────────────────────────────┘
```

### 部署模式

| 模式 | 技术 | 隔离强度 | 启动延迟 | 适用场景 |
|------|------|---------|---------|---------|
| **gVisor** | 用户态内核 | 高 | ~100ms | 默认推荐，安全与性能平衡 |
| **Firecracker MicroVM** | KVM 轻量虚拟机 | 最高 | ~200ms | 高敏感脚本、部门要求物理隔离 |
| **seccomp + chroot** | Linux 原生 | 中 | ~10ms | 低敏感、高频短脚本 |

**默认使用 gVisor**，启动延迟对脚本执行（通常秒级）可忽略。

---

## 沙箱安全策略

### 网络隔离

```yaml
network:
  outbound: false           # 禁止所有出向连接
  inbound: false            # 禁止所有入向连接
  unix_socket: false        # 禁止 Unix Domain Socket
```

### 文件系统隔离

```yaml
filesystem:
  root: /tmp/sandbox_xxx    # 临时根目录，脚本只能看到这里
  read_only_paths:          # 只读挂载（系统预装库）
    - /usr/lib/python3.11
    - /usr/local/lib/python3.11
  write_paths:              # 可写路径（仅限临时目录）
    - /tmp/sandbox_xxx/work
  max_size_mb: 100          # 临时目录大小上限
```

### 资源限制

```yaml
resources:
  cpu_quota: 1.0            # 最多 1 核
  memory_limit_mb: 512      # 内存上限
  max_processes: 10         # 最大进程数
  timeout_seconds: 10       # 执行超时
  max_file_descriptors: 64  # 文件句柄上限
```

---

## 执行流程

```
Agent Runner 调用脚本工具（如 normalize_contract_text）
  ↓
Tool Gateway 接收调用请求
  ↓
1. 参数校验（按 input_schema）
2. 权限校验：脚本 id 是否在 RunSpec.script_hooks 白名单
3. 从 Skill Registry 拉取脚本文件（校验 hash）
  ↓
提交到 Script Worker 任务队列
  ↓
空闲 Worker 领取任务
  ↓
沙箱初始化（创建临时根目录、挂载只读库）
  ↓
执行脚本（stdout / stderr 捕获）
  ↓
结果校验（按 output_schema）
  ↓
返回结果给 Agent Runner
  ↓
清理沙箱（删除临时目录、回收资源）
  ↓
写入审计日志（脚本 id / 输入摘要 / 输出摘要 / 执行时间 / 资源用量）
```

---

## 审计与可观测性

每次脚本执行必须记录：

```yaml
script_audit_log:
  log_id: log_001
  run_id: run_20260507_001
  session_id: sess_abc123
  script_id: normalize_contract_text
  skill_id: clause-review
  skill_version: 0.1.0

  input_digest: sha256_abc...       # 输入参数摘要
  output_digest: sha256_def...      # 输出结果摘要
  stdout: "..."                     # 标准输出（前 1KB）
  stderr: ""                        # 标准错误
  exit_code: 0

  resource_usage:
    cpu_seconds: 0.5
    memory_peak_mb: 128
    io_read_bytes: 1024
    io_write_bytes: 512

  latency_ms: 1500
  timestamp: "2026-05-07T14:30:00Z"
```

**存储**：写入 `audit_logs` 表（`tool_calls` 字段内嵌脚本执行记录），保留 90 天。

---

## 错误处理

| 错误场景 | 响应 | 处理方式 |
|---------|------|---------|
| 脚本超时 | `SCRIPT_TIMEOUT` | 强制终止沙箱进程，返回"脚本执行超时"给模型 |
| 内存超限 | `MEMORY_LIMIT_EXCEEDED` | OOM Killer 触发，返回"脚本资源耗尽" |
| 沙箱逃逸尝试 | `SANDBOX_VIOLATION` | 立即终止，上报安全告警， Skill 包标记待审查 |
| 输出 schema 校验失败 | `OUTPUT_SCHEMA_INVALID` | 返回错误给模型，让模型决定是否重试 |
| 脚本文件 hash 不匹配 | `INTEGRITY_CHECK_FAILED` | 拒绝执行，返回"脚本完整性校验失败" |
| Worker 池满载 | `WORKER_POOL_FULL` | 排队等待；超过 30 秒则返回"服务繁忙" |

---

## 与 P2 路线图的关系

受控脚本 Worker 是 **P2 阶段**核心交付物：

- P0：scripts/ 仅用于 build-time（CI 校验和评测）
- P1：scripts/ 继续 build-time，开始设计 Worker 架构
- **P2：Worker 池上线，preprocess / postprocess 脚本进入生产**
- P3：支持更复杂的脚本编排（多步骤流水线）

---

## 预装依赖白名单

Worker 沙箱内预装的库（禁止运行时安装新依赖）：

**Python 3.11**：
- `json`, `re`, `datetime`, `collections`, `typing`（标准库）
- `pydantic`（数据校验）
- `markdown`, `beautifulsoup4`（文本处理）
- `python-docx`, `openpyxl`, `pdfplumber`（文档处理）

**Node.js 20**：
- 仅内置模块 + `zod`（schema 校验）

业务部门如需新增依赖，须提交审批，由平台团队打包进新镜像后统一升级。
