# 16. 风险与应对

> 版本：v0.6 · 2026-05-06

---

## 主要风险清单

| 风险 | 说明 | 应对 |
|------|------|------|
| Skill 文档质量参差 | 直接影响 Agent 质量 | 模板、评测集、版本管理（依赖 Skill Creator 上游） |
| 工具权限靠 prompt | 不可靠 | **Tool Gateway 硬校验** |
| 过早开放任意脚本 | 复杂度失控 | P2 后只允许受控 worker |
| 万能入口太早 | 变黑盒路由 | 先做明确 Agent App，P3 才考虑 Router |
| reference 过大 | prompt 膨胀 | on_demand / indexed 加载 |
| 多并发打满模型 | 延迟不可控 | 队列、限流、fallback、降级 |
| **审计欠债延伸到上线** | 过不了合规 | **P0 默认 minimal 审计，不允许 off** |
| **localStorage 跨设备失效** | 用户体验断崖 | export/import JSON、UI 显式提示 |
| **localStorage 装敏感数据** | 共享电脑泄露 | §10.3 三层存储：localStorage 仅放轻偏好；对话历史用 IndexedDB + TTL + 可选加密；敏感文件不持久化 |
| **IndexedDB 加密 key 丢失** | 用户开了加密忘了 SSO 密码即数据废 | UI 默认不开加密，开启时显式警告 + 提供导出未加密备份 |
| **数量爆炸但无人用** | 平台死亡 | retention gate（30 天 MAU 阈值 → 自动归档） |
| **widget JWT URL 泄露** | 凭证被窃取 | §10.7 七条 mitigations 全做，不省 |
| **Skill 版本升级破坏现有 Agent** | 已上线 Agent 突然变形 | Skill 升级走灰度（§8.5），RunSpec 钉死版本 |
| **MAU 元数据合规被质疑** | 法务卡上线 | §10.5 哈希 + 日粒度 + 90 天 retention，与 portal 数据脱钩 |
| **Tool 新增滥用** | 攻击面失控 | 仅平台管理员能加，过双签审批（§8.6） |
| **多轮对话超模型上下文** | 突然报错 | max_turns 自动结束 + token 接近上限提示开新会话（§7.5） |
| **Agent 升级直接全量** | 一次升级炸全平台 | 灰度发布 + 一键回滚（§11.5） |

---

## KPI 双约束（数量 × MAU）怎么机械化

**两个 KPI 同时保证会让架构出现一条隐含设计要求：Agent 生命周期不能只有"上线"，必须有"归档"。**

> **"数量"拉力 → 工厂模式**
> ↓
> 一 agent 一 skill / Skill Creator 自动化 / 审批快通道
>
> **"MAU"拉力 → 评测闸门 + 用户反馈 + 自动归档**
> ↓
> Agent 上线 30 天 / 60 天 / 90 天有 MAU 体检
> 不达标 → 不删，从默认推荐位下架，进 **deprecated registry**（cold registry）
> 业务部门可申请重新激活，但需重新评测

### retention gate 机制

这个 **retention gate** 机制有三个好处：

1. **数量 KPI 不被噪音稀释**——deprecated registry 里的 Agent 不计入"活跃 Agent 数"
2. **MAU KPI 不被低质量 Agent 拖死**——默认推荐位永远是高 MAU 的
3. **业务部门有反馈循环**——他们的 Agent 被冷藏会促使他们改 Skill / 改 prompt / 改输出格式

### 实施成本

极低：Agent App 注册中心加一个 lifecycle_state 字段（active / cold / archived）+ 一个夜间 cron 跑 MAU 阈值检查。这个机制本身就是 Agent App Factory 的"出厂质检 + 召回机制"。

---

## 高风险项专项应对

### 审计合规风险（最高优先级）

**风险**：P0 上线时没有审计，合规审查不通过，项目被叫停。

**应对**：

- P0 起 audit.level 默认 minimal，schema 校验拒绝 off
- minimal 级只存元数据（~5KB/会话），无工程负担
- 审计日志独立存储，与业务数据隔离
- P0.5 阶段接入审计消费端（查询面板、报表导出），审计写入本身已在 P0 完成

### JWT 泄露风险

**风险**：short-lived JWT 在 URL 中传递，存在泄露面。

**应对**：

- 5 分钟过期 + 一次性 jti
- widget 加载后立即从 URL 删除
- Referrer-Policy: no-referrer
- CSP 严格模式
- HTTPS only + HSTS
- 禁用第三方 SDK
- 后端日志 mask token 参数

### 共享电脑数据泄露风险

**风险**：企业内网存在共享电脑，localStorage / IndexedDB 数据可能被下一个用户看到。

**应对**：

- 敏感文件内容不持久化（仅会话内存）
- 对话历史用 IndexedDB + 30 天 TTL
- 提供可选 SubtleCrypto 加密（默认关闭，开启时显式警告）
- UI 提示"共享电脑请勾选退出时清除会话"

### Agent 升级事故风险

**风险**：一次全量升级导致大量 Agent 行为异常。

**应对**：

- P0 起就有版本管理
- 灰度发布（percent + target_departments）
- 一键回滚（pinned_version）
- RunSpec 钉死版本，已运行会话不受影响

---

## 评审问题清单（PRD §15.2）

以下问题供架构评审、技术选型和上线前检查使用：

| 编号 | 问题 | 当前方案立场 |
|------|------|-------------|
| 1 | Agent App 是否比通用动态 Skill Router 更适合企业内网？ | **是**——一 agent 一 skill 写死，确定性优先 |
| 2 | Skill 作为能力编译层是否足以支撑大量业务 Agent？ | **是**——配置即 Agent，共享底座 |
| 3 | references/ 的加载策略选 prompt 拼接、检索索引，还是混合？ | **混合**——always 拼进 prompt，on_demand 运行时拉，indexed 进检索 |
| 4 | scripts/ 是 P0 就出现，还是先限制为 build-time/eval？ | **P0 限制为 build-time**，P2 才开放受控运行时 |
| 5 | Tool Gateway 的权限模型够不够硬？ | **五层交集**（Agent ∩ Skill ∩ 用户 ∩ 部门 ∩ Gateway 策略） |
| 6 | 多并发瓶颈主要会在模型、文档解析、检索，还是脚本 worker？ | **模型**是首要瓶颈，其次是文档解析 |
| 7 | RunSpec schema_version 字段从第一天就加？ | **是**——已作为方案默认（§7.6） |
| 8 | PoC 起点用 pydantic-ai + nanobot 借鉴的组合，还是单基座 fork？ | **组合借鉴，不 fork**（§13.2） |
| 9 | Skill Registry 的版本升级走热加载还是冷部署？灰度阈值多少？ | **小版本热加载，大版本灰度**（§8.5） |
| 10 | Tool Registry 的双签审批流程谁来定？ | **平台管理员 + 安全团队**（§8.6） |
| 11 | MAU 元数据的 user_id_hash salt 怎么管理 / 多久轮换？ | **K8s Secret 管理，每季度轮换**——轮换时保留旧盐 90 天用于历史数据比对，新数据用新盐；详见 [12-security-audit.md](12-security-audit.md) §MAU 元数据合规 |
| 12 | widget 的 Agent 切换 UX 是顶栏下拉还是侧栏抽屉？ | **顶栏下拉**（§4.5.5），用户认知成本更低 |
| 13 | Agent 灰度发布的"目标部门"由谁决定？ | **业务部门 owner 提议，平台管理员审批** |
