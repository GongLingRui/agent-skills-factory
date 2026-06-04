# 44. 开发者指南

> 版本：v0.6 · 2026-05-06

---

## 本地开发环境搭建

### 依赖

- Python 3.11+
- Node.js 20+
- Docker + Docker Compose
- Git

### 一键启动

```bash
# 1. 克隆代码
git clone https://github.com/company/agent-factory.git
cd agent-factory

# 2. 启动基础设施（PG + Redis + MinIO）
docker-compose -f docker-compose.dev.yml up -d

# 3. 安装 Python 依赖
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 4. 数据库迁移
alembic upgrade head

# 5. 启动后端
uvicorn src.main:app --reload --port 8000

# 6. 启动前端（新终端）
cd widget
npm install
npm run dev
```

### 默认端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Core API | 8000 | FastAPI 主服务 |
| Widget | 5173 | Vite dev server |
| PostgreSQL | 5432 | 开发数据库 |
| Redis | 6379 | 开发缓存 |
| MinIO | 9000 | 开发对象存储 |
| MinIO Console | 9001 | MinIO 管理界面 |

---

## 添加新 Tool

1. **定义 Schema**：在 `tool_registry/schemas/` 下新增 `{tool_id}_input.json` 和 `{tool_id}_output.json`
2. **注册 Tool**：在 `tool_registry/registry.yaml` 中添加条目
3. **实现 Handler**：在 `src/tools/handlers/` 下新增 `{tool_id}.py`，实现 `execute(params: dict) -> dict`
4. **权限配置**：在 RBAC 系统中为需要的角色分配 `tool.{tool_id}` 权限
5. **双签审批**：提交审批工单，安全负责人评审通过后上线

---

## 添加新 Agent

1. **准备 Skill**：确认 Skill 已在 Skill Registry 中注册并通过评测
2. **编写 agent.yaml**：

```yaml
id: my-new-agent
name: 我的新助手
skill_id: my-skill
skill_version: "0.1.0"
departments:
  - my-dept
ui_config:
  welcome_message: "您好，我是新助手"
limits:
  max_turns: 6
```

3. **上传配置**：通过管理后台或 API `POST /api/v1/agents` 上传
4. **权限分配**：在 RBAC 中为用户分配 `agent.read` 权限
5. **测试**：通过 widget 或 curl 测试完整对话链路

---

## 调试技巧

### 后端调试

```bash
# 查看实时日志
docker logs -f agent-factory-core

# 进入容器调试
docker exec -it agent-factory-core bash

# 直接调某个接口
curl -s http://localhost:8000/api/v1/agents | jq

# 测试 Skill Compiler（不启动服务）
python -c "from src.compiler import compile; print(compile('contract-review-agent', 'u123'))"
```

### 前端调试

```bash
# 查看网络请求（widget 中）
# Chrome DevTools → Network → 筛选 EventStream 查看 SSE

# 查看 IndexedDB 内容
# Chrome DevTools → Application → IndexedDB → AgentFactoryDB

# 模拟 SSE 事件（用于开发）
curl -N -H "Accept: text/event-stream" \
  http://localhost:8000/api/v1/agents/test-agent/chat \
  -d '{"message":"hello","session_id":"test"}'
```

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `alembic upgrade head` 失败 | 数据库连接不上 | 检查 docker-compose.dev.yml 中的 PG 是否启动 |
| SSE 连接 401 | session cookie 未携带 | 确认 `/auth/exchange` + `/auth/session` 已正常走完 |
| 模型返回空 | mock 模型未启动 | 检查 `docker-compose.dev.yml` 中的 wiremock 服务 |
| 文件上传失败 | MinIO 未配置 | 检查 `MINIO_ENDPOINT` 环境变量 |
| 前端热更新慢 | Vite HMR 问题 | 重启 `npm run dev` |

---

## 与现有文档的衔接

- **技术选型** → [15-tech-stack.md](15-tech-stack.md)
- **API 参考** → [19-api-reference.md](19-api-reference.md)
- **测试策略** → [27-testing-strategy.md](27-testing-strategy.md)
- **代码规范** → [43-code-guidelines.md](43-code-guidelines.md)
