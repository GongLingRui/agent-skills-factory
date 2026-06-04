"""Placeholder Skill rows for agents/*/agent.yaml (sync_agents_from_repo).

Revision ID: 20260510_0001
Revises: 20260509_0009
Create Date: 2026-05-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260510_0001"
down_revision: str | None = "20260509_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Compiler-facing defaults (docs/04); no quotes inside JSON.
_PKG_JSON = (
    '{"tools":{"require":[],"optional":[]},'
    '"knowledge_scopes":{"suggest":[]},'
    '"enterprise":{"risk_tier":"low"}}'
)

_IDS_ORDERED = (
    ("ai-product-design", "AI产品设计", "产品设计规格与需求结构化输出"),
    ("personal-growth-plan", "个人成长规划", "成长路径与计划起草"),
    ("research-report", "调研报告", "调研分析与报告撰写"),
    ("project-proposal", "项目申报", "项目建议书与申报素材"),
    ("planning-report", "规划报告", "战略规划与规划文本"),
    ("work-summary", "工作总结", "述职与工作复盘"),
    ("leadership-speech", "讲话稿", "致辞与发言稿"),
    ("contract-to-plan", "合同转化方案", "合同条款落地与执行计划"),
    ("official-document", "公文辅助", "公文风格与结构起草"),
    ("meeting-minutes", "会议纪要", "结构化纪要提取"),
)


def upgrade() -> None:
    """Insert stub skills referenced by repository agents/ (ON CONFLICT skip)."""
    values_parts: list[str] = []
    for sid, title, blurb in _IDS_ORDERED:
        esc_title = title.replace("'", "''")
        esc_blurb = blurb.replace("'", "''")
        desc_suffix = "（仓库占位登记）"
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
