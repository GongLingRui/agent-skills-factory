# 23. 系统初始化与种子数据

> 版本：v0.6 · 2026-05-06

---

## 首次部署流程

```
基础设施就绪（K8s / VM / 物理机）
  ↓
部署 PostgreSQL、Redis、MinIO
  ↓
运行初始化脚本（本章节）
  ↓
部署 Core 服务、API Gateway、Worker
  ↓
验证初始化数据
  ↓
创建首个 platform_admin 账号
  ↓
系统就绪
```

---

## 种子数据清单

### 1. 默认角色

```sql
INSERT INTO roles (id, name, description) VALUES
('platform_admin', '平台管理员', '全平台管理：Agent/Skill/Tool 增删改、降级开关、审计查看'),
('department_admin', '部门管理员', '本部门管理：Agent 配置修改、灰度发布、用户权限分配'),
('agent_owner', 'Agent 所有者', '单个 Agent 管理：修改 ui_config / prompt'),
('user', '普通用户', '仅使用权限：查看有权限的 Agent、发起对话');
```

### 2. 默认权限

```sql
INSERT INTO permissions (id, name, resource, action) VALUES
('agent.read', '查看 Agent', 'agent', 'read'),
('agent.write', '创建修改 Agent', 'agent', 'write'),
('agent.admin', '下架灰度管理', 'agent', 'admin'),
('skill.publish', '注册升级 Skill', 'skill', 'publish'),
('skill.read', '查看 Skill', 'skill', 'read'),
('tool.admin', '注册禁用 Tool', 'tool', 'admin'),
('audit.read', '查看审计日志', 'audit', 'read'),
('degradation.control', '手动触发降级', 'degradation', 'control');
```

### 3. 角色-权限关联

```sql
INSERT INTO role_permissions (role_id, permission_id) VALUES
-- platform_admin：所有权限
('platform_admin', 'agent.read'),
('platform_admin', 'agent.write'),
('platform_admin', 'agent.admin'),
('platform_admin', 'skill.publish'),
('platform_admin', 'skill.read'),
('platform_admin', 'tool.admin'),
('platform_admin', 'audit.read'),
('platform_admin', 'degradation.control'),

-- department_admin
('department_admin', 'agent.read'),
('department_admin', 'agent.write'),
('department_admin', 'agent.admin'),
('department_admin', 'skill.read'),

-- agent_owner
('agent_owner', 'agent.read'),
('agent_owner', 'agent.write'),

-- user
('user', 'agent.read');
```

### 4. 默认 Platform Policy

```sql
INSERT INTO platform_policies (id, version, prompt, enabled) VALUES
('default', 1,
'你是央企内部智能助手。你的回答必须：
1. 不涉及国家秘密、商业秘密
2. 不给出法律意见替代专业律师
3. 不泄露其他用户信息
4. 不确定时明确标注"需人工复核"
5. 引用公司制度时必须标注文号和生效日期',
 true);
```

### 5. 预设 Tool（P0 必备）

```sql
INSERT INTO tools (id, version, name, description, input_schema, output_schema,
                   permission_required, timeout_seconds, rate_limit, implementation, status) VALUES
('kb.search', '1.0.0', '知识库检索',
 '在内部知识库中检索与 query 相关的文档片段',
 '{"type":"object","properties":{"query":{"type":"string"},"scope":{"type":"string"},"top_k":{"type":"integer","default":10}},"required":["query"]}',
 '{"type":"object","properties":{"results":{"type":"array","items":{"type":"object","properties":{"doc_id":{"type":"string"},"content":{"type":"string"},"score":{"type":"number"}}}}}}',
 '["knowledge.read"]', 10,
 '{"per_user":60,"per_agent":500,"global":1000}',
 '{"type":"http_api","endpoint":"https://kb.internal/search"}',
 'active'),

('doc.extract', '1.0.0', '文档解析',
 '解析上传的文档（PDF/DOCX/TXT），提取正文内容；支持按页码或分块按需拉取',
 '{"type":"object","properties":{"file_id":{"type":"string"},"format":{"type":"string","enum":["text","markdown","structured"],"default":"text"},"page_start":{"type":"integer","description":"起始页码（1-based，可选）"},"page_end":{"type":"integer","description":"结束页码（含，可选）"},"chunk_index":{"type":"integer","description":"分块序号，超长文件分块后按需拉取（可选）"}},"required":["file_id"]}',
 '{"type":"object","properties":{"content":{"type":"string"},"pages":{"type":"integer"},"chunks_total":{"type":"integer"},"current_chunk":{"type":"integer"},"sections":{"type":"array"}}}',
 '["document.read"]', 60,
 '{"per_user":20,"per_agent":100,"global":500}',
 '{"type":"http_api","endpoint":"http://doc-worker.internal:8080/extract"}',
 'active'),

('read_reference', '1.0.0', '读取 Skill 引用',
 '按名称读取 Skill Package 中 on_demand 的 reference 文件',
 '{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}',
 '{"type":"object","properties":{"content":{"type":"string"},"source":{"type":"string"}}}',
 '[]', 5,
 '{"per_user":120,"per_agent":1000,"global":5000}',
 '{"type":"internal_function","endpoint":"skill_registry.read_reference"}',
 'active');
```

### 6. 默认模型配置

模型配置不存数据库，存于配置文件（`config/models.yaml`），部署时挂载：

```yaml
models:
  qwen3-32b:
    provider: local
    endpoint: http://qwen3-32b.internal:8000/v1
    max_tokens: 32768
    rpm: 100
    tpm: 100000
    health_endpoint: http://qwen3-32b.internal:8000/health

  qwen3-14b:
    provider: local
    endpoint: http://qwen3-14b.internal:8000/v1
    max_tokens: 32768
    rpm: 200
    tpm: 200000
    health_endpoint: http://qwen3-14b.internal:8000/health

  qwen3-8b:
    provider: local
    endpoint: http://qwen3-8b.internal:8000/v1
    max_tokens: 32768
    rpm: 500
    tpm: 500000
    health_endpoint: http://qwen3-8b.internal:8000/health

  bge-m3:
    provider: local
    endpoint: http://bge-m3.internal:8000/v1
    type: embedding
    batch_size: 32
```

### 7. 系统配置表（通用 KV）

```sql
CREATE TABLE system_config (
    key VARCHAR(64) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(64)
);

-- 初始配置
INSERT INTO system_config (key, value) VALUES
('runspec_schema_version_current', '1'),
('degradation.default_level', '0'),
('audit.default_level', 'minimal'),
('audit.default_retain_days', '90'),
('session.default_timeout_minutes', '30'),
('mau.threshold.default', '5'),
('agent.max_versions_keep', '10'),
('skill.max_versions_keep', '50');
```

---

## 初始化脚本

### 自动初始化（推荐）

```bash
# 首次启动时，Core 服务检测数据库是否为空
# 若空，自动执行种子数据插入
python -m agent_factory init --auto

# 输出：
# [INFO] Database is empty, running initialization...
# [INFO] Inserted 4 roles
# [INFO] Inserted 8 permissions
# [INFO] Inserted 11 role-permission mappings
# [INFO] Inserted 1 platform policy
# [INFO] Inserted 3 preset tools
# [INFO] System initialized. Please create the first platform_admin.
```

### 手动初始化

```bash
# 仅执行 DDL + 种子数据，不启动服务
python -m agent_factory init --seed-only

# 验证数据完整性
python -m agent_factory init --verify
```

---

## 首个管理员账号创建

初始化完成后，系统没有用户账号。需通过 CLI 创建首个 platform_admin：

```bash
python -m agent_factory admin create \
  --user-id admin001 \
  --name "系统管理员" \
  --department "it-department" \
  --role platform_admin

# 输出临时密码，首次登录后强制修改
# [INFO] Admin created. Temporary password: xK9#mP2$vL
```

**安全约束**：

- 必须通过服务器本地 CLI 执行（不能走 API，防止未授权创建）
- 创建后写入审计日志（`audit_type: admin_created`）
- 临时密码 24 小时内有效，过期需重新生成

---

## 初始化检查清单

| 检查项 | 验证命令 | 预期结果 |
|--------|---------|---------|
| 角色数据 | `SELECT COUNT(*) FROM roles` | 4 |
| 权限数据 | `SELECT COUNT(*) FROM permissions` | 8 |
| Platform Policy | `SELECT * FROM platform_policies WHERE enabled = true` | 1 条 |
| 预设 Tool | `SELECT COUNT(*) FROM tools WHERE status = 'active'` | ≥ 3 |
| 系统配置 | `SELECT COUNT(*) FROM system_config` | ≥ 8 |
| Redis 连通性 | `redis-cli ping` | PONG |
| MinIO 连通性 | `mc ls local/agent-factory` | 无报错 |
| 模型健康 | `curl http://qwen3-32b.internal:8000/health` | 200 OK |
