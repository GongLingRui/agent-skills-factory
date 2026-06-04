# 28. CI/CD 与部署流水线

> 版本：v0.6 · 2026-05-06

---

## 一句话目标

**代码变更从提交到上线的全过程自动化、可回滚、可观测**，让发布不再是心惊胆战的高危操作。

---

## 流水线总览

```
开发者提交代码
  ↓
1. 代码检查（Lint + 安全扫描）
  ↓
2. 单元测试 + 集成测试
  ↓
3. Skill 评测（eval）
  ↓
4. 构建镜像
  ↓
5. Staging 部署 + 冒烟测试
  ↓
6. 人工审批（生产发布）
  ↓
7. 生产灰度发布（Canary）
  ↓
8. 全量发布 / 回滚
```

---

## 阶段详解

### 阶段 1：代码检查

| 检查项 | 工具 | 失败策略 |
|--------|------|---------|
| Python 代码格式 | black + isort | 自动格式化后重跑 |
| TypeScript 代码格式 | prettier + eslint | 阻断合并 |
| 类型检查 | mypy / tsc --noEmit | 阻断合并 |
| 安全扫描（依赖） | safety / npm audit | 高危漏洞阻断合并 |
| 安全扫描（代码） | bandit / semgrep | 高危问题阻断合并 |
| 密钥泄露检测 | git-secrets / truffleHog | 阻断合并 |

---

### 阶段 2：测试

详见 [27-testing-strategy.md](27-testing-strategy.md)。

**运维观测样例校验**（与 [plan.md](../plan.md) §12、`deploy/` 目录）：`.github/workflows/ci.yml` 中 **`observability-samples`** job 对 [`deploy/prometheus/rules/agent_factory.rules.yml`](../deploy/prometheus/rules/agent_factory.rules.yml) 执行 `promtool check rules`，并对 Grafana 大盘 JSON 做语法校验。

**CI 触发规则**：
- 每次 Push 到任意分支 → 跑 lint + unit test
- 每次 PR → 跑 full test（unit + integration + eval + security）
- main 分支 merge → 自动构建镜像并推送到镜像仓库

---

### 阶段 3：构建镜像

**多阶段构建**（以 API Gateway 为例）：

```dockerfile
# Dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY src/ ./src/
ENV PATH=/root/.local/bin:$PATH
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**镜像标签策略**：

| 场景 | 标签 |
|------|------|
| 开发分支构建 | `dev-{branch-name}-{commit-sha}` |
| main 分支构建 | `main-{commit-sha}` |
| 发布候选 | `rc-{version}-{commit-sha}` |
| 正式版本 | `v{version}`（如 `v0.1.0`） |
| 最新稳定版 | `latest`（仅指向已验证的版本） |

---

### 阶段 4：Staging 部署

**部署方式**：Helm + Kubernetes

```bash
# staging 部署命令
helm upgrade --install agent-factory-staging ./helm \
  --namespace staging \
  --set image.tag=main-abc123 \
  --set replicaCount=2 \
  --set resources.requests.cpu=500m \
  --set resources.requests.memory=1Gi
```

**Staging 环境配置**：
- 与生产同构（相同 K8s 版本、相同中间件版本）
- 数据量较小（脱敏生产数据快照）
- 模型调用走 staging 模型集群（或 mock）

**冒烟测试**（Staging 部署后自动执行）：

```bash
# smoke-test.sh
#!/bin/bash
set -e
BASE_URL=https://staging.agent.company.com

# 1. 健康检查
curl -sf $BASE_URL/health || exit 1

# 2. 认证链路
token=$(curl -sf -X POST $BASE_URL/api/v1/auth/exchange -H "Authorization: Bearer $TEST_JWT" -d '{"agent_id":"test-agent"}' | jq -r .token)
curl -sf -X POST $BASE_URL/api/v1/auth/session -d "{\"token\":\"$token\"}"

# 3. Agent 列表
curl -sf $BASE_URL/api/v1/agents

# 4. 一条完整对话（mock 模型响应）
session=$(curl -sf -X POST $BASE_URL/api/v1/agents/test-agent/init | jq -r .session_id)
curl -sf -X POST $BASE_URL/api/v1/agents/test-agent/chat \
  -d "{\"message\":\"hello\",\"session_id\":\"$session\"}"

echo "Smoke test passed!"
```

---

### 阶段 5：生产发布

#### 发布策略

| 策略 | 适用场景 | 操作 |
|------|---------|------|
| **全量发布** | 改 UI 文案、bugfix | 直接更新 deployment，新 Pod 就绪后替换旧 Pod |
| **灰度发布** | 改 prompt、改模型、改 schema | 5% → 25% → 50% → 100%，每阶段观察 30 分钟 |
| **紧急回滚** | 线上事故 | 一键回滚到上一个稳定镜像版本 |

#### 灰度发布流程

```bash
# 1. 部署 canary 版本（5% 流量）
kubectl apply -f k8s/canary-deployment.yaml
kubectl set image deployment/agent-factory-canary app=registry/agent-factory:v0.2.0

# 2. 配置 Ingress 权重（5% → canary, 95% → stable）
kubectl patch ingress agent-factory -p '{"metadata":{"annotations":{"nginx.ingress.kubernetes.io/canary":"true","nginx.ingress.kubernetes.io/canary-weight":"5"}}}'

# 3. 观察 30 分钟（错误率、延迟、模型输出质量）
# 4. 逐步提升权重：25% → 50% → 100%
# 5. 100% 后，canary 变 stable，删除旧 stable
```

**灰度观察指标**：

| 指标 | 通过标准 | 失败动作 |
|------|---------|---------|
| 错误率 | < 0.5% | 自动回滚 |
| P99 延迟 | < 基线 120% | 自动回滚 |
| 模型输出评分 | ≥ 基线平均分 | 人工决定是否回滚 |
| 用户反馈 thumbs_down 率 | < 5% | 人工决定是否回滚 |

**SSE 长连接与灰度的关系**：

- **灰度仅影响新会话**：Ingress 权重控制的是 `/init`、`/chat` 等 HTTP 请求的入口路由
- **已建立的 SSE 长连接不会被切断**：已有连接保持在原 Pod（stable 或 canary）直到会话自然结束或客户端断开
- **已运行会话不受影响**：RunSpec 不变性保证已编译的会话继续使用旧版本，不受灰度切换影响
- **切流后新用户全部进入 canary**：当权重调整到 100% canary 后，所有新 `/init` 请求都路由到 canary Pod，stable Pod 等待已有连接全部结束后下线

---

## 回滚策略

### 自动回滚

触发条件（满足任一）：
- 灰度阶段错误率 > 1% 持续 2 分钟
- 灰度阶段 P99 延迟 > 基线 150% 持续 5 分钟
- 健康检查失败 > 3 次

动作：
1. 自动将 Ingress 权重切回 100% stable
2. 删除 canary deployment
3. 告警通知（企微/邮件）

### 手动回滚

```bash
# 回滚到上一个版本
helm rollback agent-factory-prod 1

# 或指定镜像版本
kubectl set image deployment/agent-factory app=registry/agent-factory:v0.1.9
```

**回滚约束**：
- 回滚只影响**新会话**（RunSpec 不变性保证已运行会话不受影响）
- 数据库 schema 变更不可逆时，禁止自动回滚，必须人工处理

---

## 数据库迁移

### 迁移规范

1. **每个迁移一个文件**，命名格式：`YYYYMMDD_HHMMSS_description.py`
2. **迁移必须可回滚**（downgrade 函数必须实现）
3. **禁止删除列**（除非有明确的数据归档方案）
4. **大表加索引**使用 `CONCURRENTLY`，避免锁表

### 迁移流水线

```bash
# CI 阶段验证迁移
alembic upgrade head          # 执行升级
alembic downgrade base        # 验证可回滚
alembic upgrade head          # 再次升级

# Staging 自动执行
alembic upgrade head

# 生产人工审批后执行（维护窗口）
# 由 DBA 在维护窗口手动执行
```

**生产迁移原则**：
- 小变更（加 nullable 列、加索引）：维护窗口自动执行
- 大变更（改主键、拆表、删列）：人工审批 + 蓝绿部署

---

## 具体 CI/CD 配置示例

### GitHub Actions 完整工作流

```yaml
# .github/workflows/ci-cd.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, release/*]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: agent-factory

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Python lint
        run: |
          pip install black isort mypy bandit
          black --check src/
          isort --check-only src/
          mypy src/
          bandit -r src/ -f json -o bandit-report.json || true
      - name: Frontend lint
        run: |
          cd widget && npm ci && npm run lint && npm run type-check
      - name: Unit tests
        run: |
          pip install -r requirements-test.txt
          pytest tests/unit/ --cov=src --cov-report=xml --cov-fail-under=75
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml

  integration-test:
    runs-on: ubuntu-latest
    needs: lint-and-test
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      minio:
        image: minio/minio:latest
        env:
          MINIO_ROOT_USER: minioadmin
          MINIO_ROOT_PASSWORD: minioadmin
        options: >-
          --health-cmd "curl -f http://localhost:9000/minio/health/live"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/test
          REDIS_URL: redis://localhost:6379/0
          MINIO_ENDPOINT: localhost:9000
        run: |
          pip install -r requirements.txt -r requirements-test.txt
          pytest tests/integration/ -v --tb=short

  build-and-push:
    runs-on: ubuntu-latest
    needs: [lint-and-test, integration-test]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Log in to registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:main-${{ github.sha }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest

  deploy-staging:
    runs-on: ubuntu-latest
    needs: build-and-push
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to staging
        run: |
          helm upgrade --install agent-factory-staging ./helm \
            --namespace staging \
            --set image.tag=main-${{ github.sha }} \
            --set replicaCount=2 \
            --wait --timeout 300s
      - name: Smoke test
        run: |
          sleep 30
          ./scripts/smoke-test.sh https://staging.agent.company.com

  deploy-production:
    runs-on: ubuntu-latest
    needs: deploy-staging
    environment: production
    if: startsWith(github.ref, 'refs/heads/release/')
    steps:
      - uses: actions/checkout@v4
      - name: Deploy canary
        run: |
          helm upgrade --install agent-factory-canary ./helm \
            --namespace prod-canary \
            --set image.tag=main-${{ github.sha }} \
            --set replicaCount=1 \
            --set ingress.canary=true \
            --set ingress.canaryWeight=5
      - name: Wait for observation
        run: sleep 1800  # 30 minutes
      - name: Promote or rollback
        run: |
          if ./scripts/check-canary-metrics.sh; then
            helm upgrade agent-factory-prod ./helm \
              --namespace prod \
              --set image.tag=main-${{ github.sha }} \
              --set ingress.canaryWeight=100
          else
            echo "Canary failed, rolling back"
            helm rollback agent-factory-canary 0
            exit 1
          fi
```

### 环境管理

### K8s 命名空间

```
agent-factory/
├── dev/                  # 开发环境（开发者自行部署）
├── staging/              # 预发布环境
├── prod/                 # 生产环境
├── prod-canary/          # 生产灰度（可选独立 ns）
└── monitoring/           # 监控组件（Prometheus / Grafana）
```

### 配置管理

| 环境 | 配置来源 | 敏感信息 |
|------|---------|---------|
| dev | `.env.local` + docker-compose | 假密钥 |
| staging | K8s ConfigMap + Secret | 独立密钥（与生产隔离） |
| prod | K8s ConfigMap + Secret（外部 KMS 管理） | 生产密钥 |

**敏感信息管理**：
- 数据库密码、模型 API Key、JWT Secret 存于 AWS KMS / HashiCorp Vault
- CI/CD 通过 service account 临时获取密钥，构建完成后立即失效
- 禁止将密钥写入镜像层

---

## 部署组件清单

| 组件 | 部署方式 | 副本数（prod） | HPA |
|------|---------|---------------|-----|
| API Gateway | K8s Deployment | 3 | CPU >70% |
| Skill Compiler | K8s Deployment | 2 | CPU >70% |
| Agent Runner | K8s Deployment | 3 | CPU >70% |
| Tool Gateway | K8s Deployment | 2 | CPU >70% |
| Model Gateway | K8s Deployment | 2 | CPU >70% |
| Doc Worker | K8s Deployment | 5-20 | 队列长度 >1000 |
| Script Worker | K8s Deployment | 5-20 | 队列长度 >1000 |
| Audit Worker | K8s Deployment | 3 | 队列长度 >5000 |
| Checkpoint Worker | K8s Deployment | 2 | 队列长度 >1000 |
| PostgreSQL | 托管 RDS / Cloud SQL | 主+备 | 自动 failover |
| Redis | 托管 Redis Cluster | 主+3 从 | 自动 failover |
| MinIO / S3 | 托管对象存储 | — | — |

---

## 监控与告警

| 告警项 | 触发条件 | 通知渠道 |
|--------|---------|---------|
| 生产错误率飙升 | 错误率 > 1% 持续 2 分钟 | 企微 + 电话 |
| 模型调用超时 | P99 > 10s 持续 5 分钟 | 企微 |
| 数据库连接池耗尽 | 使用率 > 90% 持续 2 分钟 | 企微 + 邮件 |
| Redis 内存告警 | 使用率 > 80% | 企微 |
| 灰度失败 | 自动回滚触发 | 企微 + 电话 |
| 安全事件 | 沙箱逃逸 / 密钥泄露检测 | 企微 + 电话 + 安全组 |

---

## 灾难恢复

| 场景 | RTO | RPO | 恢复方式 |
|------|-----|-----|---------|
| 单 Pod 故障 | <1 分钟 | 0 | K8s 自动重启 + 就绪探针 |
| 单节点故障 | <5 分钟 | 0 | K8s 自动调度到其他节点 |
| 数据库主库故障 | <10 分钟 | <1 分钟 | 自动 failover 到备库 |
| 全集群故障 | <30 分钟 | <5 分钟 | 切换到灾备集群（异地） |
| 数据误删 | <1 小时 | 按备份策略 | 从对象存储恢复快照 |

**备份策略**：
- 数据库：每日凌晨全量备份 + 实时 WAL 归档（保留 30 天）
- 对象存储：版本控制开启，误删可恢复（保留 30 天）
- 配置：Git 版本管理，随时回滚
