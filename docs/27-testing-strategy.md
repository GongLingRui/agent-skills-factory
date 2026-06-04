# 27. 测试策略

> 版本：v0.6 · 2026-05-06

---

## 一句话目标

**在每个阶段都有对应的测试防线**，从单元到集成到端到端，从功能到性能到安全，确保系统在生产环境不翻车。

---

## 测试金字塔

```
         ┌─────────┐
         │  E2E    │  ← 端到端（用户视角，覆盖核心路径）
         │  10%    │     数量少，价值高
        ┌┴─────────┴┐
        │ Integration│  ← 集成测试（模块间交互）
        │    20%    │     API 契约、数据库、缓存一致性
       ┌┴───────────┴┐
       │    Unit      │  ← 单元测试（函数/类级别）
       │    70%      │     数量多，执行快，覆盖分支
       └─────────────┘
```

---

## 单元测试（Unit）

### 覆盖目标

| 模块 | 目标覆盖率 | 重点测试内容 |
|------|-----------|-------------|
| Skill Compiler | ≥80% | prompt 拼装顺序、权限交集计算、版本解析 |
| Agent Runner | ≥75% | 状态机转换、max_turns 处理、上下文截断 |
| Tool Gateway | ≥80% | 权限校验、参数 schema 校验、路由逻辑 |
| Model Gateway | ≥70% | fallback 链、token 预算扣减、降级策略 |
| API Gateway | ≥75% | JWT 验签、参数校验、路由转发 |
| 数据模型层 | ≥80% | CRUD、字段校验、索引查询 |

### 测试原则

- **所有纯函数必须测**：输入确定、输出确定、无副作用
- **所有状态机必须测**：每个状态转移至少一个用例
- **所有错误分支必须测**：不要只测 happy path
- **Mock 外部依赖**：数据库、Redis、模型接口、外部工具全部 mock

### 示例（Skill Compiler）

```python
def test_compiler_prompt_priority():
    """platform_policy 必须排在 prompt_parts 第一位"""
    result = compile(agent_id="test", user_id="u1", department="legal")
    assert result.prompt_parts[0].role == "platform_policy"

def test_compiler_risk_tier_mapping():
    """high risk_tier 必须注入强制复核提示"""
    result = compile(agent_id="high-risk-agent", ...)
    high_prompt = [p for p in result.prompt_parts if "风险等级：高" in p.content]
    assert len(high_prompt) == 1
    assert "禁止编造依据" in high_prompt[0].content

def test_compiler_permission_intersection_empty():
    """权限交集为空时返回 400"""
    with pytest.raises(CompileError) as exc:
        compile(agent_id="test", user_id="no-perm-user", ...)
    assert exc.value.code == "NO_TOOLS_AVAILABLE"
```

---

## 集成测试（Integration）

### 覆盖目标

| 场景 | 测试内容 |
|------|---------|
| **认证链路** | portal-JWT → exchange → session cookie → 心跳 → 过期 |
| **Agent 生命周期** | 注册 → 编译 → 对话 → 版本升级 → 灰度命中 → 回滚 |
| **RunSpec 不变性** | 编译后修改 agent.yaml，已运行会话不受影响 |
| **工具调用循环** | chat → tool_call → tool_result → 下一轮 → complete |
| **文件上传链路** | upload → 解析 → 存储 → doc.extract → 模型消费 |
| **Checkpoint 恢复** | 运行中刷新 → resume → 继续执行（不重新编译） |
| **并发控制** | 同一 session 同时发两条消息 → 排队 → 顺序处理 |
| **降级链路** | 模型超时 → fallback → 再超时 → 降级提示 |

### 测试环境

- **数据库**：Docker 启动 PostgreSQL + Redis，每次测试后 truncate 数据
- **外部服务**：模型接口、文档解析服务用 WireMock / Mountebank 模拟
- **对象存储**：使用 MinIO Docker 容器

### 示例（端到端对话）

```python
def test_chat_full_loop():
    """完整对话循环：用户发消息 → 模型调用工具 → 返回结果"""
    # 1. init
    session = client.post("/agents/contract-review/init").json()

    # 2. chat（模型返回 tool_calls）
    with client.stream("POST", f"/agents/contract-review/chat",
                       json={"message": "审查合同", "session_id": session["session_id"]}) as stream:
        events = list(stream.iter_sse())

    # 3. 验证事件序列
    assert events[0].event == "tool_call"
    assert events[1].event == "tool_result"
    assert events[-1].event == "done"
    assert json.loads(events[-1].data)["schema_valid"] is not None
```

---

## Skill 评测（Eval）

### 为什么需要

单元/集成测试验证**代码逻辑正确**，但无法验证**模型输出质量**。Skill 评测专门评估模型在特定任务上的表现。

### 评测集（evals/）

每个 Skill 包必须包含 `evals/skill_cases.jsonl`：

```jsonl
{"input": "请审查这份合同的付款条款", "expected_tools": ["doc.extract", "kb.search"], "expected_schema": "contract-review-report", "min_score": 0.8}
{"input": "这份合同有没有风险？", "expected_contains": ["风险等级", "修改建议"], "forbidden_contains": ["我无法判断"], "min_score": 0.9}
```

### 自动评分维度

| 维度 | 方法 | 权重 |
|------|------|------|
| **工具调用正确性** | 实际调用工具是否在 expected_tools 内 | 30% |
| **Schema 合规** | 输出是否通过 JSON Schema 校验 | 20% |
| **内容完整性** | 输出是否包含 expected_contains 关键词 | 25% |
| **安全性** | 输出是否包含 forbidden_contains 违禁词 | 15% |
| **幻觉检测** | 引用制度是否真实存在于知识库 | 10% |

### 评测执行

```bash
# 批量跑评测集
python -m eval.run --skill-id clause-review --version 0.1.0 --cases evals/skill_cases.jsonl

# 输出报告
{
  "skill_id": "clause-review",
  "version": "0.1.0",
  "total_cases": 50,
  "passed": 45,
  "failed": 5,
  "avg_score": 0.87,
  "failures": [
    {"case_id": 12, "input": "...", "reason": "schema_validation_failed", "score": 0.6}
  ]
}
```

### 评测门禁

- **Skill 包入库前**：必须通过全部评测用例（score ≥ min_score）
- **Agent 升级前**：对比新旧版本评测结果，新版本的平均分不得低于旧版本
- **月度回归**：所有 active Agent 的 Skill 每月跑一遍评测集，分数下降自动告警

---

## 性能测试

### 压测目标

| 指标 | 目标值 | 测试方法 |
|------|--------|---------|
| API 网关 QPS | ≥500/s | Locust / k6 持续压测 |
| 模型调用 P99 延迟 | <5s | 模拟并发用户调 chat 接口 |
| 编译延迟 P99 | <100ms | 批量编译请求 |
| 数据库连接池 | ≤80% 使用率 | 监控 + 压测 |
| Redis 内存增长 | <1GB/天 | 7x24 持续运行观察 |

### 压测场景

1. **正常负载**：100 并发用户，每用户 5 轮对话
2. **峰值负载**：500 并发用户，持续 10 分钟
3. **长尾场景**：单用户上传 50MB 文件，观察系统稳定性
4. **降级场景**：模型集群半不可用，验证 fallback 链生效

---

## 安全测试

| 测试项 | 方法 | 频率 |
|--------|------|------|
| **JWT 安全性** | 尝试伪造 token、重放攻击、过期 token | 每次发版 |
| **权限越界** | 低权限用户访问高权限 Agent / 工具 | 每次发版 |
| **SQL 注入** | 在输入框注入 payload | 每次发版 |
| **XSS** | 在消息中植入 script 标签 | 每次发版 |
| **文件上传安全** | 上传伪装扩展名的可执行文件 | 每次发版 |
| **沙箱逃逸** | 在脚本中尝试网络访问、文件越界 | P2 每次发版 |
| **敏感信息泄露** | 检查日志是否 mask token、user_id | 每次发版 |

---

## 测试环境管理

| 环境 | 用途 | 数据 |
|------|------|------|
| **dev** | 本地开发，单测/集成测 | 内存数据库 + mock |
| **ci** | CI 流水线自动跑测试 | Docker 启动 PG + Redis + MinIO |
| **staging** | 预发布，跑全量测试 + 压测 | 脱敏生产数据快照 |
| **prod** | 生产，仅跑探测（smoke test） | 真实数据 |

**环境隔离**：
- 各环境使用独立的数据库 schema / Redis db index
- staging 的数据每日凌晨从生产脱敏同步
- 禁止在 prod 跑任何写入型测试

---

## CI 测试流水线

```yaml
# .github/workflows/ci.yml 示例
stages:
  - lint
  - unit_test
  - integration_test
  - eval_test
  - security_scan
  - build_image

unit_test:
  script:
    - pytest tests/unit/ --cov=src --cov-report=xml --cov-fail-under=75

integration_test:
  script:
    - docker-compose -f tests/docker-compose.yml up -d
    - pytest tests/integration/ -v
    - docker-compose -f tests/docker-compose.yml down

eval_test:
  script:
    - python -m eval.run --all-skills --fail-under 0.8

security_scan:
  script:
    - bandit -r src/
    - safety check
    - trivy image $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
```

---

## E2E 测试设计

### 覆盖场景

| 场景 | 测试路径 | 断言点 |
|------|---------|--------|
| **完整对话闭环** | portal → widget → 输入 → SSE 流式 → done | 收到 `done` 事件；消息流包含 user + assistant |
| **工具调用链路** | 上传合同 → chat → tool_call(kb.search) → tool_result → 最终回答 | 事件序列：message → tool_call → tool_result → message → done |
| **Agent 切换** | Agent A 对话 → 顶栏切换 Agent B → 新对话 | session_id 变更；历史消息隔离；ui_config 刷新 |
| **文件上传解析** | 拖拽 PDF → 上传进度 → 发送 → doc.extract 调用 | file_id 生成；SSE 中出现 tool_call(doc.extract)；回答引用文件内容 |
| **会话恢复** | 对话中刷新页面 → resume → 继续 | session_id 不变；历史消息完整恢复；RunSpec 不重新编译 |
| **降级触发** | 触发降级 → chat → 收到 degradation 事件 → 继续 | SSE 中出现 `degradation` 事件；UI 显示预警条 |
| **权限拒绝** | 低权限用户访问高权限 Agent | 后端返回 403；widget 展示"无权限"错误页 |
| **会话过期** | 等待 30 分钟 → 再次发送 | SSE 返回 `SESSION_EXPIRED`；widget 自动调用 `/init` |

### 测试工具

- **后端 E2E**：`pytest` + `httpx`（支持 SSE 流式读取）+ `testcontainers`（Docker 启动完整依赖栈）
- **前端 E2E**：`Playwright`（模拟真实浏览器行为，支持文件上传、SSE 事件监听、localStorage/IndexedDB 操作）

### E2E 测试环境

```yaml
# tests/e2e/docker-compose.e2e.yml
version: '3.8'
services:
  app:
    build: ../..
    environment:
      - DATABASE_URL=postgresql://postgres:test@postgres:5432/test
      - REDIS_URL=redis://redis:6379/0
      - MINIO_ENDPOINT=minio:9000
    depends_on:
      - postgres
      - redis
      - minio
      - mock-model
  postgres:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: test
  redis:
    image: redis:7
  minio:
    image: minio/minio:latest
    command: server /data
  mock-model:
    image: wiremock/wiremock:3x
    volumes:
      - ./mocks/model:/home/wiremock
```

### Playwright 前端 E2E 示例

```typescript
// tests/e2e/widget/chat.spec.ts
import { test, expect } from '@playwright/test';

test('complete chat loop', async ({ page }) => {
  // 1. 模拟 portal 打开 widget（带 token）
  await page.goto('/apps/contract-review-agent?token=test-jwt');

  // 2. 等待初始化完成
  await expect(page.locator('[data-testid="chat-input"]')).toBeEnabled();

  // 3. 输入消息并发送
  await page.fill('[data-testid="chat-input"]', '审查这份合同');
  await page.click('[data-testid="send-button"]');

  // 4. 等待 SSE 流式输出完成
  await expect(page.locator('[data-testid="message-assistant"]')).toBeVisible();
  await expect(page.locator('[data-testid="streaming-done"]')).toBeVisible({ timeout: 30000 });

  // 5. 验证消息存在
  const messages = await page.locator('[data-testid="message"]').count();
  expect(messages).toBeGreaterThanOrEqual(2); // user + assistant

  // 6. 验证反馈按钮出现
  await expect(page.locator('[data-testid="feedback-up"]')).toBeVisible();
});
```

---

## 测试左移与右移

- **左移（开发阶段）**：
  - 开发者本地跑单元测试通过后再提 PR
  - PR 触发 CI 全量测试，失败自动 block merge
- **右移（生产阶段）**：
  - 生产环境部署 smoke test（调通 `/health` 和一条 chat 链路）
  - 持续监控错误率、延迟、模型输出质量
  - 用户反馈（thumbs down）自动关联到对应 run_id，供复盘
