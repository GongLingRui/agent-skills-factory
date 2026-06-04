# Agent App Factory 技术文档

> 本文档体系依据 [prd.md](../prd.md) 完整拆解，覆盖架构、规范、设计、安全、运维等项目方方面面。

---

## 文档索引

| 编号 | 文档 | 说明 |
|------|------|------|
| 01 | [项目概述与核心思想](01-overview.md) | 一句话定义、背景目标、核心思想、明确边界 |
| 02 | [总体架构设计](02-architecture.md) | 总体架构图、模块职责、数据流向、模块间接口 |
| 03 | [Agent App 规范](03-agent-app-spec.md) | agent.yaml 完整规范、目录结构、版本管理、灰度发布 |
| 04 | [Skill Package 规范](04-skill-package-spec.md) | Skill 目录结构、SKILL.md、enterprise.yaml、references、scripts |
| 05 | [RunSpec 详解](05-runspec.md) | RunSpec 定义、schema、不变性、版本化、装载策略 |
| 06 | [API 网关与 SSO](06-api-gateway.md) | API 网关职责、JWT 短令牌交换、portal 集成、session 管理 |
| 07 | [Skill Compiler 设计](07-skill-compiler.md) | 编译流程、合并优先级、权限交集、prompt 拼装 |
| 08 | [Agent Runner 设计](08-agent-runner.md) | 工具调用循环、多轮对话、上下文治理、schema 校验 |
| 09 | [Tool Gateway 设计](09-tool-gateway.md) | Tool Registry、权限硬校验、安检门、熔断限速 |
| 10 | [模型网关与队列](10-model-gateway.md) | 模型路由、fallback、token 预算、并发队列 |
| 11 | [Chat Widget 前端设计](11-chat-widget.md) | 独立子站、SSE 流式、分层存储、Agent 切换、安全加固 |
| 12 | [安全、权限与审计](12-security-audit.md) | RBAC、数据域隔离、审计三档、观测性、MAU 元数据 |
| 13 | [并发与降级策略](13-concurrency.md) | 资源拆池、并发等级、降级触发条件、自动恢复 |
| 14 | [P0-P3 路线图](14-roadmap.md) | 里程碑定义、交付物、验收标准、第一批 Agent |
| 15 | [技术选型](15-tech-stack.md) | 自建 vs 复用、PoC 参考矩阵、前后端技术栈 |
| 16 | [风险与应对](16-risk-mitigation.md) | 主要风险清单、缓解措施、retention gate |
| 17 | [数据模型与 Schema](17-data-models.md) | 核心数据结构、数据库表、接口 schema、枚举值 |
| 18 | [部署与运维](18-deployment-ops.md) | 私有化部署、监控告警、日志、备份、扩容 |
| 19 | [API 接口参考](19-api-reference.md) | 全量接口 OpenAPI 汇总、认证方式、错误码、SSE 协议 |
| 20 | [Redis Key 设计](20-redis-design.md) | Key 命名规范、限流计数器、缓存一致性、容量规划 |
| 21 | [定时任务清单](21-cron-jobs.md) | MAU 体检、审计清理、备份验证、Salt 轮换、缓存预热 |
| 22 | [数据归档策略](22-data-archiving.md) | 热/温/冷分层、归档流程、归档后查询、容灾恢复 |
| 23 | [系统初始化](23-system-init.md) | 种子数据、预设 Tool、首个管理员、初始化检查清单 |
| 24 | [文档解析 Worker](24-document-parser-worker.md) | 文件格式支持、安全沙箱解析、结果结构化、与 Tool Gateway 集成 |
| 25 | [受控脚本 Worker](25-script-worker.md) | 脚本沙箱、Worker 池、gVisor 隔离、审计日志 |
| 26 | [消息队列与异步任务](26-message-queue.md) | Redis Streams、消费者组、死信队列、延迟任务、背压限流 |
| 27 | [测试策略](27-testing-strategy.md) | 单元/集成/E2E 测试、Skill 评测、性能压测、安全测试 |
| 28 | [CI/CD 与部署流水线](28-cicd.md) | 镜像构建、灰度发布、回滚策略、数据库迁移、灾难恢复 |
| 29 | [前端工程结构](29-frontend-structure.md) | 目录结构、组件接口、Zustand Store、API Client、分层存储实现 |
| 30 | [后端工程结构](30-backend-structure.md) | FastAPI 目录结构、依赖注入、中间件链、异常处理、配置加载 |
| 31 | [配置文件总览](31-configuration-reference.md) | 环境变量清单、数据库配置表、模型配置、加载优先级 |
| 32 | [可观测性设计](32-observability-design.md) | Metrics/Logs/Traces 三支柱、Prometheus 指标规范、Grafana 仪表盘分层 |
| 33 | [管理后台设计](33-admin-dashboard-design.md) | 功能模块、权限矩阵、运营控制面板、配置管理 |
| 34 | [P0 交付裁剪规范](34-p0-delivery-spec.md) | P0 字段/功能/组件启用状态表、Compiler 特殊行为、验收 checklist |
| 35 | [开发快速启动指南](35-quickstart.md) | 环境准备、`scripts/bootstrap-dev.sh`、开发工作流、常用端口 |
| 36 | [故障排查手册](36-troubleshooting.md) | 按错误码速查、按场景排查、常用诊断命令 |
| 37 | [生产环境部署 Checklist](37-production-checklist.md) | 部署前检查、部署步骤、部署后验证、回滚准备 |
| 38 | [前端组件详细设计](38-frontend-component-design.md) | StreamingText / ToolCallCard / FileUpload / DegradationBanner 等组件 Props 详表 |
| 39 | [文件处理流水线设计](39-file-pipeline-design.md) | 完整文件生命周期、秒传机制、file_uploads 表结构 |
| 40 | [K8s 部署清单](40-k8s-manifests.md) | Namespace / Deployment / Service / HPA / Ingress 等 YAML 模板 |
| 41 | [Nginx 配置](41-nginx-config.md) | 负载均衡、限流、SSE 长连接、安全 Header、Token Masking |
| 42 | [灾难恢复设计](42-disaster-recovery.md) | RTO/RPO 目标、备份策略、异地灾备、数据库故障恢复 |
| 43 | [代码规范](43-code-guidelines.md) | Python / TypeScript / Git / Code Review 规范 |
| 44 | [开发指南](44-developer-guides.md) | 本地开发环境、调试技巧、常见问题速查 |
| 45 | [安全架构总览](45-security-architecture.md) | STRIDE 威胁建模、敏感数据分级、密钥管理、合规对照 |
| 46 | [日志规范](46-logging-spec.md) | 结构化日志格式、敏感信息脱敏、trace_id 传播、采样策略 |
| 47 | [与 PRD 对齐说明](47-prd-alignment.md) | 实施真相来源、审计写入 vs P0.5 消费端、P0 RunSpec 裁剪、PRD 遗留表述提醒 |
| 48 | [P0.5 压测与安全基线](48-p0.5-load-security-baseline.md) | plan §5、并发冒烟测试、安全响应头、可选 benchmark 脚本 |
| 49 | [MCP 接入评估（P1）](49-mcp-integration-assessment.md) | plan §6：P0 禁用、HTTP Tool 优先、MCP 旁路化条件 |
| 50 | [P2/P3 阶段评估与实施冻结清单](50-p2-p3-phase-assessment.md) | plan §7–§8：脚本 Worker 与网关收口清单、multi-skill 仅评估结论（当前里程碑不交付运行时） |
| 51 | [完整 RBAC 实施规格](51-rbac-implementation-spec.md) | 能力码与角色展开、HTTP 路由映射、Tool Gateway 与 Runner 传参、阶段 B–D 待办 |
| — | [P0 上线评审模板（简）](p0-production-review-template.md) | 签字表与上线前快速核对（细则见 [37](37-production-checklist.md)） |

---

## 快速导航

- **如果你是架构评审人员**：先看 [01](01-overview.md) → [02](02-architecture.md) → [05](05-runspec.md)
- **如果你是后端开发**：先看 [02](02-architecture.md) → [07](07-skill-compiler.md) → [08](08-agent-runner.md) → [09](09-tool-gateway.md) → [30](30-backend-structure.md) → [35](35-quickstart.md)
- **如果你是前端开发**：先看 [11](11-chat-widget.md) → [06](06-api-gateway.md) → [29](29-frontend-structure.md) → [38](38-frontend-component-design.md) → [35](35-quickstart.md)
- **如果你是安全/合规**：先看 [12](12-security-audit.md) → [16](16-risk-mitigation.md) → [45](45-security-architecture.md)
- **如果你是项目经理**：先看 [01](01-overview.md) → [14](14-roadmap.md) → [16](16-risk-mitigation.md) → [34](34-p0-delivery-spec.md) → [47](47-prd-alignment.md)（与 PRD 口径对齐）
- **如果你是运维人员**：先看 [18](18-deployment-ops.md) → [20](20-redis-design.md) → [21](21-cron-jobs.md) → [22](22-data-archiving.md) → [28](28-cicd.md) → [40](40-k8s-manifests.md) → [41](41-nginx-config.md) → [42](42-disaster-recovery.md) → [46](46-logging-spec.md) → [31](31-configuration-reference.md) → [32](32-observability-design.md) → [37](37-production-checklist.md)
- **如果你是 DBA / 数据治理**：先看 [17](17-data-models.md) → [22](22-data-archiving.md) → [21](21-cron-jobs.md)
- **如果你是 QA / 测试**：先看 [27](27-testing-strategy.md) → [14](14-roadmap.md) → [34](34-p0-delivery-spec.md)
- **如果你是 DevOps**：先看 [28](28-cicd.md) → [18](18-deployment-ops.md) → [26](26-message-queue.md) → [40](40-k8s-manifests.md) → [41](41-nginx-config.md) → [46](46-logging-spec.md) → [31](31-configuration-reference.md) → [32](32-observability-design.md) → [37](37-production-checklist.md)
- **如果你是平台管理员 / 运营**：先看 [33](33-admin-dashboard-design.md) → [32](32-observability-design.md) → [12](12-security-audit.md) → [19](19-api-reference.md)
- **如果你正在处理线上故障**：先看 [36](36-troubleshooting.md) → [32](32-observability-design.md) → [46](46-logging-spec.md) → [18](18-deployment-ops.md) → [42](42-disaster-recovery.md)
