"""Placeholder Skill rows for repository Agent 内嵌 Skill 包（sync_skills_from_repo）。

Revision ID: 20260512_0002
Revises: 20260512_0001
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260512_0002"
down_revision: str | None = "20260512_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PKG_JSON = (
    '{"tools":{"require":[],"optional":[]},'
    '"knowledge_scopes":{"suggest":[]},'
    '"enterprise":{"risk_tier":"low"}}'
)

_IDS_ORDERED = (
    (
        "business-presentation-generator",
        "业务演示文稿生成",
        "单文件 HTML 幻灯片与路演材料",
    ),
    (
        "client-meeting-strategist",
        "客户会议策略",
        "会前准备、对话策略与红队检验",
    ),
    (
        "compliance-dialectic-analyst",
        "合规辩证分析",
        "法规冲突与辩证合成输出",
    ),
    (
        "consulting-pitch-forge",
        "咨询说服叙事",
        "诊断框架与说服型交付",
    ),
    (
        "data-logic-translator",
        "数据逻辑转译",
        "指标口径与业务语义对齐",
    ),
    (
        "problem-essence-analyst",
        "问题本质分析",
        "根因与模式识别方法论",
    ),
)


def upgrade() -> None:
    """Insert stub skills for ``agents/*/skill/SKILL.md`` bundles (ON CONFLICT skip)."""
    values_parts: list[str] = []
    for sid, title, blurb in _IDS_ORDERED:
        esc_title = title.replace("'", "''")
        esc_blurb = blurb.replace("'", "''")
        desc_suffix = "（仓库 Skill 包占位；运行 sync_skills_from_repo 写入正文）"
        esc_desc = (blurb + desc_suffix).replace("'", "''")
        pkg_hash = f"seed-{sid}".replace("'", "''")
        values_parts.append(
            f"('{sid}', '0.1.0', '{esc_title} Skill', '{esc_desc}', "
            f"'{esc_blurb}', 'low', '{pkg_hash}', 'active', '{_PKG_JSON}'::jsonb)"
        )
    sql = (
        "INSERT INTO skills (\n"
        "  id, version, name, description, when_to_use,\n"
        "  risk_tier, skill_package_hash, status, package_metadata\n"
        ") VALUES\n  "
        + ",\n  ".join(values_parts)
        + "\nON CONFLICT (id, version) DO NOTHING"
    )
    op.execute(sa.text(sql))


def downgrade() -> None:
    ids = "', '".join(s for s, _, _ in _IDS_ORDERED)
    op.execute(
        sa.text(
            f"""
            DELETE FROM skills
            WHERE version = '0.1.0'
              AND id IN ('{ids}')
              AND skill_package_hash LIKE 'seed-%'
            """
        )
    )
