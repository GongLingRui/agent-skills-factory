#!/usr/bin/env python3
"""将仓库内 Skill 包同步到 Skill 注册表（POST/PUT ``/api/v1/skills``）。

默认扫描 ``agents/*/skill/SKILL.md``（与 ``prd.md`` 第五节 Agent 目录一致）。
若设置环境变量 ``SKILLS_DIR`` 为某目录路径，则改为扫描该目录下一层子目录
（兼容旧布局 ``skills/<id>/``）。

把 Claude 形态的目录（见 ``docs/04-skill-package-spec.md``）编译为
``package_metadata``：``skill_instruction``、``reference_files``、``lazy_refs``、
``file_manifest``、``eval_cases`` 等，供 Compiler 与 ``read_reference`` 使用。

认证与 ``sync_agents_from_repo.py`` 相同（``ADMIN_API_TOKEN`` 或
``WIDGET_SESSION_ID``）；优先从仓库根 ``.env`` 再读 ``backend/.env``（后者覆盖同名键）。

用法::

    cd backend && uv run python scripts/sync_skills_from_repo.py

可选环境变量:
``API_BASE``、``AGENT_FACTORY_ROOT``、``AGENTS_DIR``、``SKILLS_DIR``（覆盖默认扫描）、
``SESSION_COOKIE_NAME``、``SKILL_VERSION``（默认 ``0.1.0``）。

首次部署请先 ``alembic upgrade head``（含本仓库 Skill 占位行），再运行本脚本
写入完整 ``package_metadata``。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))
from local_env import (
    dotenv_files_contain_admin_token,
    load_env_for_sync_scripts,
    repo_and_backend_dotenv_paths,
)

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from agent_factory.services.repo_skill_bundle import load_skill_bundle_from_directory


def _repo_root() -> Path:
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
        "错误: 未配置认证。请在 .env 中设置非空的 ADMIN_API_TOKEN，"
        "或设置 WIDGET_SESSION_ID（开发绕过登录后的 Cookie）。\n"
        f"{paths_hint}{extra}\n"
        "若已在 shell 里 export 过空变量（如 ADMIN_API_TOKEN=），请先 unset 再运行。",
        file=sys.stderr,
    )
    sys.exit(1)
    return headers


def main() -> None:
    load_env_for_sync_scripts(Path(__file__))

    root = Path(os.environ.get("AGENT_FACTORY_ROOT", _repo_root()))
    agents_dir = Path(os.environ.get("AGENTS_DIR", root / "agents"))
    skills_dir_override = (os.environ.get("SKILLS_DIR") or "").strip()
    base = os.environ.get("API_BASE", "http://127.0.0.1:8000/api/v1").rstrip("/")
    version = (os.environ.get("SKILL_VERSION") or "0.1.0").strip()

    headers = _auth_headers()

    if skills_dir_override:
        skills_dir = Path(skills_dir_override)
        dirs = sorted(
            p
            for p in skills_dir.iterdir()
            if p.is_dir() and (p / "SKILL.md").is_file()
        )
        hint = str(skills_dir)
    else:
        dirs = sorted(
            agent / "skill"
            for agent in agents_dir.iterdir()
            if agent.is_dir() and (agent / "skill" / "SKILL.md").is_file()
        )
        hint = f"{agents_dir}/*/skill/"
    if not dirs:
        print(
            f"错误: 未找到 Skill 包（含 SKILL.md）。已检查: {hint}。"
            "默认应在 agents/<agent>/skill/；或设置 SKILLS_DIR 指向旧式 skills/ 父目录。",
            file=sys.stderr,
        )
        sys.exit(1)

    ok = 0
    with httpx.Client(timeout=120.0) as client:
        for d in dirs:
            try:
                try:
                    rel_storage = d.resolve().relative_to(
                        root.resolve()
                    ).as_posix()
                except ValueError:
                    rel_storage = (Path("skills") / d.name).as_posix()
                body = load_skill_bundle_from_directory(
                    d,
                    version=version,
                    storage_path=rel_storage,
                )
            except ValueError as exc:
                print(f"跳过 {d.name}: {exc}", file=sys.stderr)
                continue
            sid = str(body["id"])
            post_url = f"{base}/skills"
            r = client.post(post_url, headers=headers, json=body)
            if r.status_code == 409:
                put_url = f"{base}/skills/{sid}"
                upd = {
                    "name": body.get("name"),
                    "description": body.get("description"),
                    "when_to_use": body.get("when_to_use"),
                    "owner": body.get("owner"),
                    "risk_tier": body.get("risk_tier"),
                    "skill_package_hash": body.get("skill_package_hash"),
                    "storage_path": body.get("storage_path"),
                    "package_metadata": body.get("package_metadata"),
                }
                r = client.put(
                    put_url,
                    headers=headers,
                    params={"version": version},
                    json={k: v for k, v in upd.items() if v is not None},
                )
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = ""
                try:
                    detail = json.dumps(r.json(), ensure_ascii=False)
                except Exception:
                    detail = (r.text or "")[:500]
                print(f"失败 {sid}: {r.status_code} {detail}", file=sys.stderr)
                raise exc from None
            print(f"synced\t{sid}\t{d.relative_to(root)}")
            ok += 1

    print(f"完成: {ok} 个 Skill 已同步。", file=sys.stderr)


if __name__ == "__main__":
    main()
