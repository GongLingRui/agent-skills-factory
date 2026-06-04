# 45. 安全架构总览

> 版本：v0.6 · 2026-05-06

---

## 安全分层模型

```
┌─────────────────────────────────────────┐
│           边界安全（Perimeter）          │
│  Nginx / WAF / IP 白名单 / DDoS 防护     │
├─────────────────────────────────────────┤
│           认证安全（Authentication）       │
│  SSO / JWT 短令牌 / Session Cookie / MFA │
├─────────────────────────────────────────┤
│           授权安全（Authorization）        │
│  RBAC / RunSpec 白名单 / Tool Gateway 4层 │
├─────────────────────────────────────────┤
│           数据安全（Data）                │
│  加密传输 / 加密存储 / 脱敏 / TTL 清理     │
├─────────────────────────────────────────┤
│           运行时安全（Runtime）            │
│  沙箱 / 限流 / 熔断 / 降级 / 审计         │
├─────────────────────────────────────────┤
│           供应链安全（Supply Chain）       │
│  镜像扫描 / 依赖审计 / 密钥管理            │
└─────────────────────────────────────────┘
```

---

## 威胁建模（STRIDE）

| 威胁 | 影响 | 缓解措施 |
|------|------|---------|
| **Spoofing**（伪造身份） | 攻击者冒充合法用户 | JWT 签名 + 过期时间 + jti 防重放 |
| **Tampering**（篡改数据） | 修改 RunSpec 或工具参数 | RunSpec 不可变 + 参数 schema 校验 + hash 校验 |
| **Repudiation**（否认操作） | 用户否认发起过某请求 | 审计日志（不可篡改）+ jti 一次性标记 |
| **Information Disclosure**（信息泄露） | prompt/output 被未授权访问 | 分层存储（敏感文件不落盘）+ 日志脱敏 + RBAC |
| **Denial of Service**（拒绝服务） | 系统被流量压垮 | 多层限流（IP/用户/全局）+ 降级 + 队列 + HPA |
| **Elevation of Privilege**（权限提升） | 普通用户获得管理员权限 | RBAC 最小权限 + 后端二次校验 + 操作审计 |

---

## 敏感数据分级

| 级别 | 数据类型 | 存储 | 传输 | 留存期 |
|------|---------|------|------|--------|
| **极度敏感** | 合同正文、公文附件、用户上传文件 | 仅会话内存（不落盘） | TLS 1.3 | 会话结束即清 |
| **高度敏感** | 对话历史、prompt/output | IndexedDB（可选加密）/ 审计 DB | TLS 1.3 | 30 天（前端）/ 90 天（审计） |
| **中度敏感** | user_id、部门信息 | PostgreSQL + Redis | TLS 1.3 | 永久（哈希化存储） |
| **公开** | Agent 配置、Skill 元数据 | PostgreSQL + Redis | TLS 1.3 | 永久 |

---

## 密钥管理

| 密钥类型 | 存储方式 | 轮换周期 | 访问控制 |
|---------|---------|---------|---------|
| JWT 签名私钥 | K8s Secret / HashiCorp Vault | 每季度 | 仅 API Gateway 可读 |
| 数据库密码 | K8s Secret / Vault | 每季度 | 仅 Core 服务可读 |
| 模型 API Key | K8s Secret / Vault | 每季度 | 仅 Model Gateway 可读 |
| MAU salt | K8s Secret | 每季度 | 仅审计模块可读 |
| MinIO 访问密钥 | K8s Secret | 每半年 | 按服务分配独立密钥 |

---

## 合规对照

| 合规要求 | 实现位置 |
|---------|---------|
| 数据最小化 | [12-security-audit.md](12-security-audit.md) §MAU 最小元数据 |
| 访问日志留存 | [12-security-audit.md](12-security-audit.md) §审计分级 |
| 用户同意 | [11-chat-widget.md](11-chat-widget.md) §加密开关显式提示 |
| 数据可删除 | [11-chat-widget.md](11-chat-widget.md) §导出/导入 + 手动清理 |
| 传输加密 | [41-nginx-config.md](41-nginx-config.md) §SSL/TLS 配置（TLSv1.2 TLSv1.3） |
| 静态加密 | [12-security-audit.md](12-security-audit.md) §temp 桶 SSE-S3 |
| 权限最小化 | [12-security-audit.md](12-security-audit.md) §RBAC |

---

## 与现有文档的衔接

- **RBAC 详细规则** → [12-security-audit.md](12-security-audit.md) §RBAC
- **Prompt 注入防御** → [12-security-audit.md](12-security-audit.md) §Prompt 注入攻击检测与防御
- **审计与日志** → [12-security-audit.md](12-security-audit.md) §审计分级
- **Nginx 安全配置** → [41-nginx-config.md](41-nginx-config.md)
- **文件存储安全** → [39-file-pipeline-design.md](39-file-pipeline-design.md)
- **Widget 安全** → [11-chat-widget.md](11-chat-widget.md) §安全加固
