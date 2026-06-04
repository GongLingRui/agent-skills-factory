"""Redis pub/sub hooks when Skill Registry rows change (prd §8.5 cache notify).

Downstream workers or portal adapters may SUBSCRIBE to ``SKILL_UPDATED_CHANNEL``.
"""

from __future__ import annotations

import json
import logging

from agent_factory.infra.redis import get_redis

logger = logging.getLogger(__name__)

SKILL_UPDATED_CHANNEL = "af:skill:updated"


async def publish_skill_changed(
    *,
    skill_id: str,
    version: str,
    action: str,
) -> None:
    """Publish a lightweight JSON message (best-effort; never raises).

    Args:
        skill_id: Skill primary id.
        version: Skill version string.
        action: ``created`` | ``updated`` | ``deprecated``.
    """
    payload = json.dumps(
        {
            "skill_id": skill_id,
            "version": version,
            "action": action,
        },
        separators=(",", ":"),
    )
    try:
        redis = get_redis()
        subs = await redis.publish(SKILL_UPDATED_CHANNEL, payload)
        logger.debug(
            "skill notify channel=%s subscribers=%s",
            SKILL_UPDATED_CHANNEL,
            subs,
        )
    except Exception:
        logger.warning(
            "skill notify skipped skill_id=%s version=%s",
            skill_id,
            version,
            exc_info=True,
        )
