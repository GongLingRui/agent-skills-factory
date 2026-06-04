# Agent App Factory 架构与业务逻辑图

> 本文档整合项目中的核心架构设计，以 Mermaid 图表形式呈现，便于理解与沟通。

---

## 1. 整体架构概览

### 1.1 系统架构图

```mermaid
graph TB
    subgraph Client["客户端层"]
        User["用户/Business System"]
        Widget["Chat Widget<br/>(React+SSE)"]
    end

    subgraph Gateway["网关层"]
        APIGW["API Gateway<br/>(Auth/RBAC/RateLimit)"]
    end

    subgraph Core["核心业务层"]
        Registry["Agent App Registry<br/>(注册中心)"]
        Compiler["Skill Compiler<br/>(装配车间)"]
        Runner["Agent Runner<br/>(执行引擎)"]
    end

    subgraph Infrastructure["基础设施层"]
        ModelGW["Model Gateway<br/>(模型路由/限流/降级)"]
        ToolGW["Tool Gateway<br/>(工具注册/鉴权/审计)"]
        MinIO["MinIO/S3<br/>(对象存储)"]
        Redis["Redis<br/>(Streams/分布式锁)"]
        PG["PostgreSQL<br/>(持久化)"]
    end

    subgraph External["外部服务"]
        ExternalTools["External Tools<br/>(kb.search, doc.extract, etc.)"]
        ModelProvider["Model Provider<br/>(OpenAI兼容)"]
    end

    User --> Widget
    Widget --> APIGW
    APIGW --> Registry
    APIGW --> Compiler
    Registry --> Compiler
    Compiler --> Runner
    Runner <--> ModelGW
    Runner <--> ToolGW
    ModelGW --> ModelProvider
    ToolGW --> ExternalTools
    ToolGW --> MinIO
    Runner --> Redis
    Registry --> PG

    style User fill:#f9f,stroke:#333,stroke-width:2px
    style Widget fill:#bbf,stroke:#333,stroke-width:2px
    style APIGW fill:#f96,stroke:#333,stroke-width:2px
    style Registry fill:#9f9,stroke:#333,stroke-width:2px
    style Compiler fill:#9f9,stroke:#333,stroke-width:2px
    style Runner fill:#ff9,stroke:#333,stroke-width:2px
```

### 1.2 组件关系图

```mermaid
graph LR
    A["agent.yaml<br/>(声明式配置)"] -->|1: 注册| B["Agent Registry"]
    C["Skill Package<br/>(技能包)"] -->|2: 注册| B
    B -->|3: 编译请求| D["Skill Compiler"]
    D -->|4: 生成| E["RunSpec<br/>(出厂订单)"]
    E -->|5: 执行| F["Agent Runner"]
    F -->|6: 调用| G["Model Gateway"]
    F -->|7: 调用| H["Tool Gateway"]
    G -->|8: 请求| I["Model Provider"]
    H -->|9: 调用| J["External Services"]

    style A fill:#e1e5,stroke:#333
    style C fill:#e1e5,stroke:#333
    style E fill:#ff9,stroke:#333
    style F fill:#ff9,stroke:#333
```

---

## 2. 核心流程图

### 2.1 Agent 创建与部署流程

```mermaid
flowchart TD
    Start([开始]) --> A[开发者编写 agent.yaml]
    A --> B[编写 Skill Package]
    B --> C{校验 agent.yaml 格式}
    C -->|失败| E[返回错误信息]
    C -->|成功| D[上传至 Agent Registry]
    D --> F[Skill Compiler 编译检查]
    F --> G{编译成功?}
    G -->|失败| H[标记错误/版本不兼容]
    G -->|成功| I[生成 RunSpec]
    I --> J[部署至 Agent Runner 池]
    J --> K([完成])

    style Start fill:#9f9
    style K fill:#9f9
    style E fill:#f99
    style H fill:#f99
```

### 2.2 用户请求处理流程

```mermaid
sequenceDiagram
    participant U as User
    participant W as Chat Widget
    participant G as API Gateway
    participant R as Agent Registry
    participant C as Skill Compiler
    participant Run as Agent Runner
    participant M as Model Gateway
    participant T as Tool Gateway

    U->>W: 发起对话请求
    W->>G: 转发请求(JWT Token)
    G->>G: 验证JWT/鉴权/限流
    G->>R: 查询Agent配置
    R-->>G: 返回Agent元信息
    G->>C: 请求编译RunSpec
    C->>C: 编译Agent+Skill
    C-->>G: 返回RunSpec
    G->>Run: 创建执行会话
    Run->>M: 请求模型推理
    M->>M: 路由/限流
    M-->>Run: 返回推理结果
    alt 需要调用工具
        Run->>T: 调用工具
        T->>T: 鉴权/审计
        T-->>Run: 返回工具结果
    end
    Run-->>G: 最终响应
    G-->>W: SSE流式返回
    W-->>U: 展示结果
```

### 2.3 Skill Compiler 编译流程

```mermaid
flowchart TD
    A([收到编译请求]) --> B[加载 agent.yaml]
    B --> C[解析 skill id 和 version]
    C --> D[从 Registry 获取 Skill Package]
    D --> E{获取成功?}
    E -->|否| F[返回错误: Skill不存在]
    E -->|是| G[校验 Skill 版本兼容性]
    G --> H{版本兼容?}
    H -->|否| I[返回错误: 版本冲突]
    H -->|是| J[合并 instruction + system prompt]
    J --> K[解析工具清单 permissions]
    K --> L[生成 RunSpec JSON]
    L --> M[签名 RunSpec]
    M --> N([返回 RunSpec])

    style F fill:#f99
    style I fill:#f99
    style N fill:#9f9
```

---

## 3. 业务逻辑图

### 3.1 多租户隔离模型

```mermaid
graph TB
    subgraph EnterpriseA["企业 A"]
        A1["Dept A1"]
        A2["Dept A2"]
    end
    subgraph EnterpriseB["企业 B"]
        B1["Dept B1"]
        B2["Dept B2"]
    end

    TenantGW["Tenant Gateway<br/>(租户隔离)"]
    RBAC["RBAC<br/>(角色权限控制)"]
    AgentPool["Agent Pool<br/>(Agent注册/发布)"]

    EnterpriseA --> TenantGW
    EnterpriseB --> TenantGW
    TenantGW --> RBAC
    RBAC --> AgentPool

    style TenantGW fill:#f96
    style RBAC fill:#f96
```

### 3.2 工具调用鉴权流程

```mermaid
flowchart TD
    A[Agent Runner 请求调用工具] --> B[检查 RunSpec permissions]
    B --> C{工具在白名单中?}
    C -->|否| D[拒绝调用]
    C -->|是| E[检查用户RBAC权限]
    E --> F{有权限?}
    F -->|否| D
    F -->|是| G[Tool Gateway 执行]
    G --> H[记录审计日志]
    H --> I[执行工具逻辑]
    I --> J[返回结果给 Runner]

    style D fill:#f99
    style J fill:#9f9
```

### 3.3 模型路由与降级

```mermaid
flowchart LR
    A[请求] --> B{主模型可用?}
    B -->|是| C[使用主模型]
    B -->|否| D{备用模型1可用?}
    D -->|是| E[使用备用模型1]
    D -->|否| F{备用模型2可用?}
    F -->|是| G[使用备用模型2]
    F -->|否| H[返回错误/限流]

    C --> I[返回结果]
    E --> I
    G --> I

    style H fill:#f99
    style I fill:#9f9
```

### 3.4 会话与消息存储策略

```mermaid
graph TB
    subgraph Client["客户端分层存储"]
        L1["Layer 1: 完整消息"]
        L2["Layer 2: 摘要"]
        L3["Layer 3: 元数据"]
    end

    subgraph Server["服务端审计"]
        A1["审计日志<br/>(Tool Gateway写入)"]
        A2["元数据索引<br/>(Registry查询)"]
    end

    L1 -.->|加密存储本地| L2
    L2 -.->|定期上传| A2

    style L1 fill:#bbf
    style L2 fill:#bfb
    style L3 fill:#f9f
    style A1 fill:#ff9
```

---

## 4. 数据模型关系图

### 4.1 核心实体关系

```mermaid
erDiagram
    Agent ||--o{ AgentVersion : has
    Agent ||--o{ AgentPermission : has
    AgentVersion ||--|| RunSpec : generates
    Skill ||--o{ SkillVersion : has
    SkillVersion ||--o{ ToolBinding : uses
    RunSpec ||--o{ ToolPermission : grants
    User ||--o{ Role : belongs
    Role ||--o{ Permission : has
    Session ||--o{ Message : contains
    Session ||--|| AgentVersion : runs

    Agent {
        string id PK
        string name
        string owner_dept
        timestamp created_at
    }
    AgentVersion {
        string version
        string agent_id FK
        string instruction
    }
    RunSpec {
        json spec_data
        string signature
        timestamp compiled_at
    }
    Skill {
        string id PK
        string name
    }
    ToolPermission {
        string tool_name
        string runspec_id FK
    }
    Session {
        string session_id PK
        string user_id FK
        string agent_id FK
        string status
    }
```

### 4.2 RunSpec 结构

```mermaid
graph LR
    subgraph RunSpec["RunSpec (出厂订单)"]
        RS1["instruction<br/>(执行指令)"]
        RS2["system_prompt<br/>(系统提示)"]
        RS3["tools[]<br/>(可用工具清单)"]
        RS4["model_config<br/>(模型配置)"]
        RS5["permissions<br/>(权限边界)"]
        RS6["meta<br/>(元数据/签名)"]
    end
```

---

## 5. 部署架构图

### 5.1 K8s 部署拓扑

```mermaid
graph TB
    subgraph K8s["Kubernetes Cluster"]
        subgraph Ingress["Ingress"]
            ING["Ingress Controller"]
        end

        subgraph Frontend["Frontend Pods"]
            FE["Chat Widget<br/>(3 replicas)"]
        end

        subgraph Backend["Backend Pods"]
            API["API Server<br/>(5 replicas)"]
            RUN["Agent Runner<br/>(N replicas)"]
            COMP["Skill Compiler<br/>(2 replicas)"]
        end

        subgraph Data["Data Layer"]
            PG["PostgreSQL<br/>(Primary+Replica)"]
            REDIS["Redis Cluster<br/>(3 nodes)"]
            MINIO["MinIO<br/>(Distributed)"]
        end

        subgraph Monitor["Monitoring"]
            PRO["Prometheus"]
            GRAF["Grafana"]
        end
    end

    ING --> FE
    FE --> API
    API --> COMP
    API --> RUN
    RUN --> PG
    RUN --> REDIS
    RUN --> MINIO
    RUN --> ModelExt["External Model API"]
    COMP -.--> PG
    API -.--> PG
    PRO -->|monitor| K8s
    GRAF -->|visualize| PRO

    style K8s fill:#e8e8e8,stroke:#333
    style Data fill:#ffe
```

### 5.2 开发环境架构

```mermaid
graph LR
    A[Dev Machine] -->|docker-compose| B[Local Services]
    B --> PG[[PostgreSQL]]
    B --> REDIS[[Redis]]
    B --> MINIO[[MinIO]]

    A -->|pnpm dev| FE[[Frontend<br/>localhost:5173]]
    A -->|uvicorn| BE[[Backend<br/>localhost:8000]]
```

---

## 6. 安全架构图

### 6.1 JWT 认证流程

```mermaid
sequenceDiagram
    participant U as User
    participant W as Widget
    participant AP as Auth Portal
    participant G as API Gateway
    participant B as Backend

    U->>AP: 登录获取短期JWT
    AP-->>U: 返回JWT (expires: 15min)
    U->>W: 发起请求+JWT
    W->>G: 转发请求+JWT
    G->>G: 验证JWT签名
    G->>G: 检查部门/角色
    G->>B: 转发请求(+Claims)
    B->>B: 业务处理
    B-->>G: 响应
    G-->>W: SSE响应
    W-->>U: 展示
```

### 6.2 Tool Gateway 安全校验

```mermaid
flowchart TD
    A[Tool Call Request] --> B[检查 Tool Registry]
    B --> C{工具已注册?}
    C -->|否| D[拒绝: 未知工具]
    C -->|是| E[检查签名/时间戳]
    E --> F{校验通过?}
    F -->|否| G[拒绝: 请求伪造]
    F -->|是| H[检查 RBAC 权限]
    H --> I{用户有权限?}
    I -->|否| J[拒绝: 权限不足]
    I -->|是| K[执行工具 + 审计日志]
    K --> L[返回结果]

    style D fill:#f99
    style G fill:#f99
    style J fill:#f99
    style L fill:#9f9
```

---

## 7. 目录结构图

### 7.1 项目整体结构

```mermaid
graph TD
    ROOT["agent-factory/"]
    ROOT --> PRD["prd.md<br/>(需求文档)"]
    ROOT --> PLAN["plan.md<br/>(开发计划)"]
    ROOT --> CLAUDE["CLAUDE.md<br/>(项目指引)"]
    ROOT --> DOCS["docs/<br/>(51份技术文档)"]
    ROOT --> BACKEND["backend/<br/>(Python/FastAPI)"]
    ROOT --> FRONTEND["frontend/<br/>(React/TypeScript)"]
    ROOT --> AGENTS["agents/<br/>(11个Agent声明)"]
    ROOT --> DEPLOY["deploy/<br/>(K8s配置)"]
    ROOT --> ALEMBIC["alembic/<br/>(DB迁移)"]

    DOCS --> D01["01-overview.md"]
    DOCS --> D02["02-architecture.md"]
    DOCS --> D03["03-agent-registry.md"]
    DOCS --> D04["04-skill-package-spec.md"]
    DOCS --> D05["05-runspec.md"]
    DOCS --> D07["07-skill-compiler.md"]
    DOCS --> D08["08-agent-runner.md"]
    DOCS --> D11["11-chat-widget.md"]
    DOCS --> D19["19-api-reference.md"]
    DOCS --> D30["30-backend-structure.md"]
    DOCS --> D34["34-p0-delivery-spec.md"]

    style ROOT fill:#e8f4ff,stroke:#333,stroke-width:2px
```

### 7.2 后端目录结构

```mermaid
graph TD
    BACKEND["backend/"]
    BACKEND --> SRC["src/agent_factory/"]
    SRC --> API["api/v1/<br/>(路由)"]
    SRC --> CORE["core/<br/>(核心逻辑)"]
    SRC --> SERVICES["services/<br/>(服务层)"]
    SRC --> INFRA["infra/<br/>(基础设施)"]
    SRC --> WORKERS["workers/<br/>(后台任务)"]
    SRC --> MIDDLEWARE["middleware/<br/>(中间件)"]
    SRC --> CONFIG["config/<br/>(配置)"]

    API --> agents_py["agents.py"]
    API --> skills_py["skills.py"]
    API --> tools_py["tools.py"]
    API --> auth_py["auth.py"]
    API --> audit_py["audit.py"]

    CORE --> compiler_py["compiler.py"]
    CORE --> runner_service_py["runner_service.py"]
    CORE --> tool_gateway_py["tool_gateway.py"]
    CORE --> model_gateway_py["model_gateway.py"]

    INFRA --> db_py["db.py"]
    INFRA --> redis_py["redis.py"]
    INFRA --> minio_py["minio_client.py"]
```

---

## 8. Agent 声明示例

### 8.1 agent.yaml 结构

```mermaid
graph LR
    subgraph agent_yaml["agent.yaml"]
        A1["id: demo-agent"]
        A2["name: Demo Agent"]
        A3["version: 0.1.0"]
        A4["instruction: ..."]
        A5["skill:"]
        A6["  id: demo-skill"]
        A7["  version_pin: 0.1.0"]
        A8["release:"]
        A9["  strategy: full"]
    end
```

---

## 9. 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-05-11 | 初始文档，包含9个核心图示 |

---

*本文档使用 Mermaid 语法，可直接在 GitHub、GitLab、VS Code 等支持 Mermaid 的平台渲染。*