"""Seed PRD §12 sample agents (会议纪要 / 材料起草 / 舆情简报).

Revision ID: 20260508_0007
Revises: 20260508_0006
Create Date: 2026-05-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_0007"
down_revision: Union[str, None] = "20260508_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO agent_apps (
                id, name, description, version, instruction,
                runspec_schema_version, owner, lifecycle_state,
                release_config, model_policy, skill_config, tools_allow,
                knowledge_scopes, audit_config, tags, ui_config,
                enterprise_config,
                degradation_exempt, created_at, updated_at, created_by
            ) VALUES (
                'meeting-minutes-agent',
                '会议纪要助手',
                $d1$高频纪要结构化输出（PRD 样本；与 demo-skill 绑定）。$d1$,
                '0.1.0',
                $i1$你是会议纪要助手。输出结构化纪要，不编造未出现的发言。$i1$,
                1,
                'system',
                'active',
                '{"strategy":"full"}'::jsonb,
                '{"default":"qwen3-32b","fallback":"qwen3-14b"}'::jsonb,
                '{"id":"demo-skill","version_pin":"0.1.0"}'::jsonb,
                '["kb.search","doc.extract","read_reference"]'::jsonb,
                '["group_legal_policy"]'::jsonb,
                '{"level":"minimal","trace_tool_calls": true,"trace_retrieval_ids": true,"retain_days": 90}'::jsonb,
                '["会议","PRD样本"]'::jsonb,
                '{"title":"会议纪要","welcome_message":"粘贴会议录音转写或要点，生成纪要。"}'::jsonb,
                '{"mau_threshold": 0}'::jsonb,
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
                enterprise_config,
                degradation_exempt, created_at, updated_at, created_by
            ) VALUES (
                'material-draft-agent',
                '材料起草助手',
                $d2$公文/材料风格起草（PRD 样本）。$d2$,
                '0.1.0',
                $i2$你是材料起草助手。遵循用户给定要点与层级，避免虚构红头文件编号。$i2$,
                1,
                'system',
                'active',
                '{"strategy":"full"}'::jsonb,
                '{"default":"qwen3-32b","fallback":"qwen3-14b"}'::jsonb,
                '{"id":"demo-skill","version_pin":"0.1.0"}'::jsonb,
                '["kb.search","doc.extract","read_reference"]'::jsonb,
                '["group_legal_policy"]'::jsonb,
                '{"level":"minimal","trace_tool_calls": true,"trace_retrieval_ids": true,"retain_days": 90}'::jsonb,
                '["起草","PRD样本"]'::jsonb,
                '{"title":"材料起草","welcome_message":"输入主题、受众与要点，生成初稿。"}'::jsonb,
                '{"mau_threshold": 0}'::jsonb,
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
                enterprise_config,
                degradation_exempt, created_at, updated_at, created_by
            ) VALUES (
                'public-opinion-brief-agent',
                '舆情简报助手',
                $d3$多源检索与摘要（PRD 样本）。$d3$,
                '0.1.0',
                $i3$你是舆情简报助手。基于检索结果归纳观点，标注信息来源与时间范围。$i3$,
                1,
                'system',
                'active',
                '{"strategy":"full"}'::jsonb,
                '{"default":"qwen3-32b","fallback":"qwen3-14b"}'::jsonb,
                '{"id":"demo-skill","version_pin":"0.1.0"}'::jsonb,
                '["kb.search","doc.extract","read_reference"]'::jsonb,
                '["group_legal_policy"]'::jsonb,
                '{"level":"minimal","trace_tool_calls": true,"trace_retrieval_ids": true,"retain_days": 90}'::jsonb,
                '["简报","PRD样本"]'::jsonb,
                '{"title":"舆情简报","welcome_message":"输入关注主体与时间范围，生成简报要点。"}'::jsonb,
                '{"mau_threshold": 0}'::jsonb,
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
            WHERE id IN (
                'meeting-minutes-agent',
                'material-draft-agent',
                'public-opinion-brief-agent'
            )
            """
        )
    )
