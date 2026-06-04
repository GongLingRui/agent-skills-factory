# P0 首次上线评审模板（简版）

> 与 [37-production-checklist.md](37-production-checklist.md) 配套：**细则与命令仍以 37 为准**；本页仅提供签字表与快速勾选。

**项目名称**：________________  

**评审日期**：________________  

**参与角色**：产品 / 研发 / 运维 / 安全（勾选到场）

---

## 签字表

| 角色 | 姓名 | 结论（通过 / 带条件 / 不通过） | 备注 |
|------|------|----------------------------------|------|
| 产品负责人 | | | |
| 研发负责人 | | | |
| 运维负责人 | | | |
| 安全 / 合规（如需） | | | |

---

## 上线前快速核对（摘自 P0 范围）

- [ ] `JWT_SECRET` / `PORTAL_*` / `DATABASE_URL` / `REDIS_URL` 已按环境注入，无明文入库
- [ ] `alembic upgrade head` 已在目标库执行，种子 Agent（含 `policy-qa-agent`、`contract-review-agent`）可见
- [ ] Widget 域名已加入 `ALLOWED_ORIGINS`
- [ ] `POST /auth/exchange` → `POST /auth/session` 联调通过（portal JWT）
- [ ] 网关 SSE `proxy_read_timeout` ≥ 站点约定（见 [41-nginx-config.md](41-nginx-config.md)）
- [ ] `/metrics`、`minimal` 审计写入与健康检查按运维策略接入

**条件通过时的遗留项与截止日期**：

```
（自由文本）
```
