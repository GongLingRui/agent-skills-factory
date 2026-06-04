# 43. 代码规范与工程实践

> 版本：v0.6 · 2026-05-06

---

## 命名规范

| 层级 | 规范 | 示例 |
|------|------|------|
| Python 模块 | snake_case | `skill_compiler.py`, `tool_gateway.py` |
| Python 类 | PascalCase | `SkillCompiler`, `RunSpecValidator` |
| Python 函数/变量 | snake_case | `compile_runspec()`, `allowed_tools` |
| Python 常量 | UPPER_SNAKE_CASE | `MAX_TURNS_DEFAULT = 6` |
| TypeScript 文件 | PascalCase（组件）/ camelCase（工具） | `MessageBubble.tsx`, `useAuth.ts` |
| TypeScript 接口 | PascalCase + 前缀 I（可选） | `interface ChatMessage`, `interface IChatState` |
| 数据库表 | snake_case，复数 | `agent_apps`, `audit_logs` |
| 数据库字段 | snake_case | `run_id`, `created_at` |
| Redis Key | 领域:子领域:标识 | `agent:{agent_id}`, `session:{session_id}` |
| API 路径 | kebab-case | `/api/v1/agents/{agent-id}` |
| Git 分支 | kebab-case | `feature/sse-reconnect`, `fix/token-leak` |

---

## Python 代码规范

### 类型注解

```python
# 强制：所有函数参数和返回值必须有类型注解
def compile_runspec(
    agent_id: str,
    user_id: str,
    department: str,
    skill_version_pin: str | None = None,
) -> RunSpec:
    ...

# 强制：复杂数据结构用 TypedDict 或 dataclass
from dataclasses import dataclass

@dataclass(frozen=True)
class RunSpec:
    run_id: str
    agent_id: str
    skill_package_hash: str
    allowed_tools: list[str]
```

### 错误处理

```python
# 自定义异常体系
class AgentFactoryError(Exception):
    """基类"""
    code: str = "UNKNOWN"
    retryable: bool = False

class CompileError(AgentFactoryError):
    code = "COMPILE_ERROR"
    retryable = False

class ModelTimeoutError(AgentFactoryError):
    code = "MODEL_TIMEOUT"
    retryable = True

# 使用：raise ModelTimeoutError("模型响应超过 60 秒")
```

### 异步代码

```python
# 所有 IO 操作必须异步
async def fetch_agent(agent_id: str) -> AgentConfig:
    # 数据库查询
    row = await db.fetch_one("SELECT * FROM agent_apps WHERE id = ?", agent_id)
    # Redis 查询
    cached = await redis.get(f"agent:{agent_id}")
    # HTTP 请求
    resp = await httpx.get(f"http://kb.internal/search?q={query}")
    return AgentConfig(**row)

# 禁止：在 async 函数中使用 time.sleep()
# 正确：await asyncio.sleep(1)
```

---

## TypeScript/React 代码规范

### 组件定义

```typescript
// 函数组件 + 显式返回类型
interface MessageBubbleProps {
  message: ChatMessage;
  showFeedback: boolean;
}

export function MessageBubble({ message, showFeedback }: MessageBubbleProps): JSX.Element {
  // ...
}

// Hook 命名：use + 功能
export function useAuth(): AuthState {
  // ...
}
```

### 状态管理

```typescript
// Zustand store：按功能拆分，禁止大杂烩 store
interface ChatState {
  messages: ChatMessage[];
  status: ChatStatus;
  sendMessage: (text: string) => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  status: 'idle',
  sendMessage: async (text) => {
    const { sessionId } = useSessionStore.getState();
    // ...
  },
}));
```

---

## 文档注释规范

```python
def check_rate_limit(
    user_id: str,
    tool_id: str,
    max_per_minute: int = 60,
) -> None:
    """检查用户调用某工具是否超过限流配额。

    使用 Redis Sorted Set 实现滑动窗口计数器。
    如果超限，抛出 RateLimitExceeded 异常。

    Args:
        user_id: 用户唯一标识
        tool_id: 工具唯一标识
        max_per_minute: 每分钟最大调用次数，默认 60

    Raises:
        RateLimitExceeded: 当当前窗口内请求数 >= max_per_minute

    Example:
        >>> check_rate_limit("u123", "kb.search", max_per_minute=60)
        # 正常通过，无异常
    """
```

---

## 测试规范

```python
# 测试文件命名：test_ + 被测模块名
# test_skill_compiler.py

# 测试类命名：Test + 被测类名
class TestSkillCompiler:
    def test_prompt_priority_platform_first(self):
        """platform_policy 必须排在 prompt_parts 第一位"""
        result = compile(agent_id="test", user_id="u1")
        assert result.prompt_parts[0].role == "platform_policy"

    def test_risk_tier_high_must_inject_warning(self):
        """high risk_tier 必须注入强制复核提示"""
        result = compile(agent_id="high-risk-agent", ...)
        assert any("风险等级：高" in p.content for p in result.prompt_parts)
```

---

## Git 工作流

```
main 分支（保护分支，仅通过 PR 合并）
  ├── feature/*  功能分支
  ├── fix/*      Bug 修复分支
  ├── release/*  发布分支
  └── hotfix/*   紧急修复分支（可从 main 切出，合并后同时打 tag）
```

### Commit Message 规范

```
<type>(<scope>): <subject>

<body>

<footer>

# 示例
feat(compiler): 增加 risk_tier 映射校验

- 校验 enterprise.yaml 中的 risk_tier 必须为 low/medium/high
- 校验 risk_tier_prompt_map 中必须包含对应等级的映射

Closes #123
```

| type | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug 修复 |
| docs | 文档更新 |
| style | 代码格式（不影响功能） |
| refactor | 重构 |
| test | 测试相关 |
| chore | 构建/工具链 |

---

## 与现有文档的衔接

- **技术选型** → [15-tech-stack.md](15-tech-stack.md)
- **测试策略** → [27-testing-strategy.md](27-testing-strategy.md)
- **CI/CD** → [28-cicd.md](28-cicd.md)
