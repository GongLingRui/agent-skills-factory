"""Seed policy-QA and contract-review sample agents (plan §11).

Revision ID: 20260508_0005
Revises: 20260508_0004
Create Date: 2026-05-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_0005"
down_revision: Union[str, None] = "20260508_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Insert seeds.

    - JSON booleans use ``": true"`` not ``":true"`` — ``sa.text()`` binds ``:name``.
    - Each ``'::jsonb`` cast stays on the **same line** as its opening quote; splitting
      across lines produces two adjacent SQL string literals and breaks the cast.
    """
    op.execute(
        sa.text(
            """
            INSERT INTO agent_apps (
                id, name, description, version, instruction,
                runspec_schema_version, owner, lifecycle_state,
                release_config, model_policy, skill_config, tools_allow,
                knowledge_scopes, audit_config, tags, ui_config,
                degradation_exempt, created_at, updated_at, created_by
            ) VALUES (
                'policy-qa-agent',
                '制度问答助手',
                $desc1$基于内部制度与知识库的问答（P0 样本；验证 kb.search / 权限域）。$desc1$,
                '0.1.0',
                $inst1$你是制度问答助手。须依据知识库与制度作答；不确定时明确标注「需人工复核」。$inst1$,
                1,
                'system',
                'active',
                '{"strategy":"full"}'::jsonb,
                '{"default":"qwen3-32b","fallback":"qwen3-14b"}'::jsonb,
                '{"id":"demo-skill","version_pin":"0.1.0"}'::jsonb,
                '["kb.search","doc.extract","read_reference"]'::jsonb,
                '["group_legal_policy"]'::jsonb,
                '{"level":"minimal","trace_tool_calls": true,"trace_retrieval_ids": true,"retain_days": 90}'::jsonb,
                '["政策","知识库"]'::jsonb,
                '{"title":"制度问答","welcome_message":"请描述要查询的制度要点或关键词。"}'::jsonb,
                false,
                NOW(), NOW(),
                'migration'
            )
            ON CONFLICT (id) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO agent_apps (
                id, name, description, version, instruction,
                runspec_schema_version, owner, lifecycle_state,
                release_config, model_policy, skill_config, tools_allow,
                knowledge_scopes, audit_config, tags, ui_config,
                degradation_exempt, created_at, updated_at, created_by
            ) VALUES (
                'contract-review-agent',
                '合同审查助手',
                $desc2$合同条款风险辅助审查（P0 样本；验证 doc.extract / 工具轨迹）。$desc2$,
                '0.1.0',
                $inst2$你是合同审查助手。结合制度与模板指出风险点；涉及法律效力时标注「需人工复核」。$inst2$,
                1,
                'system',
                'active',
                '{"strategy":"full"}'::jsonb,
                '{"default":"qwen3-32b","fallback":"qwen3-14b"}'::jsonb,
                '{"id":"demo-skill","version_pin":"0.1.0"}'::jsonb,
                '["kb.search","doc.extract","read_reference"]'::jsonb,
                '["contract_templates","group_legal_policy"]'::jsonb,
                '{"level":"minimal","trace_tool_calls": true,"trace_retrieval_ids": true,"retain_days": 90}'::jsonb,
                '["法律","合同"]'::jsonb,
                '{"title":"合同审查","welcome_message":"上传合同或粘贴条款以开始审查。"}'::jsonb,
                false,
                NOW(), NOW(),
                'migration'
            )
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM agent_apps
            WHERE id IN ('policy-qa-agent', 'contract-review-agent')
            """
        )
    )
