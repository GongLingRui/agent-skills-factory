#!/usr/bin/env python3
"""将仓库 ``agents/*/agent.yaml`` 推送到服务端注册表（写入 PostgreSQL）。

仅编辑磁盘上的 YAML **不会**更新前端可见配置；Widget 列表来自
``GET /api/v1/agents``（即数据库中的 ``agent_apps``）。

认证（任选其一）：

1. **Bearer（推荐脚本/CI）** 在仓库根目录 ``.env`` 或 ``backend/.env`` 里设置
   ``ADMIN_API_TOKEN``（与运行 ``uvicorn`` 时一致；``backend/.env`` 覆盖同名键）——
   这是**你自己定义的密钥**，不是平台发放的；任意足够长的随机字符串即可，
   保存后**重启后端**，脚本与本文件读取同一变量。
2. **开发会话 Cookie** 开启 ``DEV_WIDGET_AUTH_BYPASS`` 并用浏览器打开 Widget 登录后，
   从开发者工具 Application → Cookies 复制 ``session_id``，再设置环境变量
   ``WIDGET_SESSION_ID``（无需 ``ADMIN_API_TOKEN``）。

用法::

    cd backend && uv run python scripts/sync_agents_from_repo.py

可选环境变量:
``API_BASE``、``AGENT_FACTORY_ROOT``、``AGENTS_DIR``、``SESSION_COOKIE_NAME``。

若 PUT/POST 失败，请检查 YAML 中 ``skill.id`` 是否在数据库 ``skills`` 中存在。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))
from local_env import (
    dotenv_files_contain_admin_token,
    load_env_for_sync_scripts,
    repo_and_backend_dotenv_paths,
)


def _repo_root() -> Path:
    # backend/scripts/this.py -> parents[2] = repo root
    return Path(__file__).resolve().parents[2]


def _auth_headers() -> dict[str, str]:
    token = (os.environ.get("ADMIN_API_TOKEN") or "").strip()
    sid = (os.environ.get("WIDGET_SESSION_ID") or "").strip()
    cookie_name = (os.environ.get("SESSION_COOKIE_NAME") or "session_id").strip()

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        return headers
    if sid:
        headers["Cookie"] = f"{cookie_name}={sid}"
        return headers

    root_e, back_e = repo_and_backend_dotenv_paths(Path(__file__))
    tried = [p for p in (root_e, back_e) if p.is_file()]
    paths_hint = (
        "已尝试读取: " + "、".join(str(p) for p in tried)
        if tried
        else (
            "未找到仓库根目录或 backend 下的 .env；"
            "可复制 backend/.env.example 为 backend/.env 并设置 ADMIN_API_TOKEN。"
        )
    )
    file_missing_token = (
        tried
        and not dotenv_files_contain_admin_token(Path(__file__))
        and not (os.environ.get("WIDGET_SESSION_ID") or "").strip()
    )
    extra = ""
    if file_missing_token:
        extra = (
            "\n说明: 已找到 .env 文件，但其中没有非空的 ADMIN_API_TOKEN= 行；"
            "请对照 backend/.env.example 添加后重试。\n"
        )
    print(
        "错误: 未配置认证。任选其一：\n"
        "  1) 在 .env 中设置非空的 ADMIN_API_TOKEN，"
        "重启 uvicorn 后再运行本脚本；\n"
        "  2) 设置 WIDGET_SESSION_ID=浏览器 Cookie 中 session_id（开发绕过登录后）。\n"
        f"{paths_hint}{extra}\n"
        "若 shell 里 export 过空变量（如 ADMIN_API_TOKEN=），请先 unset 再运行。",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    load_env_for_sync_scripts(Path(__file__))

    root = Path(os.environ.get("AGENT_FACTORY_ROOT", _repo_root()))
    agents_dir = Path(os.environ.get("AGENTS_DIR", root / "agents"))
    base = os.environ.get("API_BASE", "http://127.0.0.1:8000/api/v1").rstrip("/")

    headers = _auth_headers()

    paths = sorted(agents_dir.glob("*/agent.yaml"))
    if not paths:
        print(f"错误: 在 {agents_dir} 下未找到 */agent.yaml", file=sys.stderr)
        sys.exit(1)

    ok = 0
    with httpx.Client(timeout=120.0) as client:
        for p in paths:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or "id" not in raw:
                print(f"跳过（无效 YAML）: {p}", file=sys.stderr)
                continue
            aid = str(raw["id"])
            put_url = f"{base}/agents/{aid}"
            r = client.put(put_url, headers=headers, json=raw)
            if r.status_code == 404:
                r = client.post(f"{base}/agents", headers=headers, json=raw)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = ""
                try:
                    body = r.json()
                    detail = json.dumps(body, ensure_ascii=False)
                    nested = (
                        body.get("error") if isinstance(body, dict) else None
                    )
                    if (
                        isinstance(nested, dict)
                        and nested.get("code") == "SKILL_NOT_FOUND"
                    ):
                        print(
                            "提示: 数据库里还没有 YAML 中引用的 Skill。"
                            "请先执行: cd backend && alembic upgrade head",
                            file=sys.stderr,
                        )
                except Exception:
                    detail = (r.text or "")[:500]
                print(
                    f"失败 {aid}: {r.status_code} {detail}",
                    file=sys.stderr,
                )
                raise exc from None
            action = "updated" if r.request.method == "PUT" else "created"
            print(f"{action}\t{aid}\t{p.relative_to(root)}")
            ok += 1

    print(f"完成: {ok} 个 agent 已同步到注册表。", file=sys.stderr)


if __name__ == "__main__":
    main()
