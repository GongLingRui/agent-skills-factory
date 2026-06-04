# 仓库内 Agent 声明（`agent.yaml`）

本目录存放 **Agent App** 的 `agent.yaml`，并与 **同目录下 `skill/`** 内嵌的
Skill 包配套（见 `prd.md` 第五节、`docs/03-agent-app-spec.md`）。用于：

- 对照 `POST /api/v1/agents` 注册时的请求体（见 [docs/03-agent-app-spec.md](../docs/03-agent-app-spec.md)）；
- 通过 `backend/scripts/sync_agents_from_repo.py` 推送到 PostgreSQL（与迁移占位 Skill 行配合）。

每个 Agent 目录结构为：`agent.yaml` + **`skill/`**（`SKILL.md` + `references/` 等，
见 [docs/04-skill-package-spec.md](../docs/04-skill-package-spec.md)）。完整元数据需运行：

```bash
cd backend && uv run python scripts/sync_skills_from_repo.py
```

（与迁移 `20260512_0002` 等占位行配合；认证方式与 `sync_agents_from_repo.py` 相同。）

若需临时扫描旧式根目录 `skills/<id>/`，可设置环境变量 `SKILLS_DIR` 为该父路径，
脚本将只遍历其下一层子目录。

前端「应用库」调用 `GET /api/v1/agents`，列出的是 **Agent 应用**（表 `agent_apps`），
不是 `skills` 表。仅同步 Skill 不会多出卡片；需为每个对外应用编写本目录下的
`agent.yaml`（`skill.id` 与 `skill/SKILL.md` frontmatter `name` 一致）并运行
`sync_agents_from_repo.py`。

运行时以数据库中的 `agent_apps` 为准；**改 YAML 或 `skill/` 后需同步脚本或 API**，
否则联调仍读旧版。

## 目录说明

| 目录 | 绑定 Skill（`skill.id`） | 说明 |
|------|--------------------------|------|
| `demo-agent/` | `demo-skill` | 默认联调 / 冒烟（迁移 0003–0004） |
| `ai-product-design-agent/` | `ai-product-design` | 产品设计规格书 |
| `meeting-minutes-agent/` | `meeting-minutes` | 会议纪要 / 转写整理 |
| `contract-to-plan-agent/` | `contract-to-plan` | 合同 → 执行方案 |
| `work-summary-agent/` | `work-summary` | 工作总结 / 述职 |
| `leadership-speech-agent/` | `leadership-speech` | 领导讲话稿 |
| `official-document-agent/` | `official-document` | 公文升华 |
| `research-report-agent/` | `research-report` | 研究报告 |
| `project-proposal-agent/` | `project-proposal` | 立项建议书 |
| `planning-report-agent/` | `planning-report` | 规划报告 |
| `personal-growth-plan-agent/` | `personal-growth-plan` | 个人成长与学习规划 |
| `problem-essence-analyst-agent/` | `problem-essence-analyst` | 问题本质分析 |
| `data-logic-translator-agent/` | `data-logic-translator` | 数据逻辑转译 |
| `consulting-pitch-forge-agent/` | `consulting-pitch-forge` | 咨询说服叙事 |
| `compliance-dialectic-analyst-agent/` | `compliance-dialectic-analyst` | 合规辩证分析 |
| `client-meeting-strategist-agent/` | `client-meeting-strategist` | 客户会议策略 |
| `business-presentation-generator-agent/` | `business-presentation-generator` | 业务演示文稿（HTML 幻灯片） |

数据库中另有迁移种子 **`policy-qa-agent`**、**`contract-review-agent`**（绑定 `demo-skill`），仅作 P0 样本，目录未镜像到此文件夹。

## 同步命令

```bash
cd backend && uv run python scripts/sync_agents_from_repo.py
cd backend && uv run python scripts/sync_skills_from_repo.py
```

（具体参数与基座 URL 以各脚本内说明为准。）

Skill 隔离测试脚本已置于本目录 `run-skill-test.sh`（相对路径以 `agents/` 为根，
第一个参数为如 `work-summary-agent/skill`）。
