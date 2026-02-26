#!/usr/bin/env python3
"""提交生成任务并轮询到完成后下载图片到 api_test 目录。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


BASE_URL = "https://api1.paperbanana.me"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_token_from_env_file() -> str | None:
    env_path = _project_root() / ".env"
    if not env_path.exists():
        return None

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "PAPERBANANA_API_TOKEN":
            continue
        token = value.strip().strip("'\"")
        if token:
            return token
    return None


def _http_json(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url=url, method=method.upper(), data=data, headers=headers)
    try:
        with urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}\n{err}") from exc
    except URLError as exc:
        raise RuntimeError(f"请求失败: {url}\n{exc}") from exc


def _download_binary(url: str, token: str) -> tuple[bytes, str]:
    req = Request(url=url, method="GET", headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(req, timeout=300) as resp:
            content = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            return content, content_type
    except HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"下载失败 HTTP {exc.code} {url}\n{err}") from exc
    except URLError as exc:
        raise RuntimeError(f"下载失败: {url}\n{exc}") from exc


def _guess_extension(content_type: str, artifact_url: str) -> str:
    if "png" in content_type:
        return ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "webp" in content_type:
        return ".webp"
    if "json" in content_type:
        return ".json"
    suffix = Path(artifact_url).suffix
    return suffix if suffix else ".bin"


def run(args: argparse.Namespace) -> int:
    token = os.getenv("PAPERBANANA_API_TOKEN") or _load_token_from_env_file()
    if not token:
        print("错误: 未找到 PAPERBANANA_API_TOKEN（环境变量或项目根目录 .env）。", file=sys.stderr)
        return 2

    prompt_path = Path(args.prompt_file).expanduser().resolve()
    if not prompt_path.exists():
        print(f"错误: 提示词文件不存在: {prompt_path}", file=sys.stderr)
        return 2
    source_context = prompt_path.read_text(encoding="utf-8")

    base_url = BASE_URL
    submit_url = f"{base_url}/api/v1/tasks/generate"
    payload: dict[str, Any] = {
        "source_context": source_context,
        "communicative_intent": args.caption,
        "refinement_iterations": args.refinement_iterations,
        "optimize_inputs": args.optimize_inputs,
    }

    print(f"[1/3] 提交任务: {submit_url}")
    submit_resp = _http_json("POST", submit_url, token, payload)
    task_id = submit_resp.get("task_id")
    if not task_id:
        print(f"错误: 提交返回中缺少 task_id: {submit_resp}", file=sys.stderr)
        return 1
    print(f"任务已提交 task_id={task_id}")

    status_url = f"{base_url}/api/v1/tasks/{task_id}"
    deadline = time.time() + args.timeout_seconds
    final_status: dict[str, Any] | None = None

    print("[2/3] 轮询状态...")
    while time.time() < deadline:
        status = _http_json("GET", status_url, token)
        state = str(status.get("status", ""))
        progress = status.get("progress") or "-"
        print(f"  status={state:<10} progress={progress}")
        if state in {"completed", "failed"}:
            final_status = status
            break
        time.sleep(args.poll_interval_seconds)

    if final_status is None:
        print("错误: 轮询超时", file=sys.stderr)
        return 1

    if final_status.get("status") != "completed":
        print(f"错误: 任务失败: {final_status.get('error')}", file=sys.stderr)
        return 1

    result = final_status.get("result") or {}
    artifact_url = result.get("artifact_url") or f"/api/v1/tasks/{task_id}/artifact"
    artifact_full_url = urljoin(f"{base_url}/", artifact_url.lstrip("/"))

    print(f"[3/3] 下载产物: {artifact_full_url}")
    content, content_type = _download_binary(artifact_full_url, token)

    output_dir = Path(__file__).resolve().parent
    ext = _guess_extension(content_type, artifact_url)
    output_path = output_dir / f"generated_{task_id}{ext}"
    output_path.write_bytes(content)

    status_dump = output_dir / f"task_{task_id}.json"
    status_dump.write_text(json.dumps(final_status, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已保存图片: {output_path}")
    print(f"已保存状态: {status_dump}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="测试提交生成任务接口并下载图片")
    parser.add_argument(
        "--prompt-file",
        default=str(_project_root() / "examples" / "sample_inputs" / "transformer_method.txt"),
        help="项目内提示词文件路径",
    )
    parser.add_argument(
        "--caption",
        default="Overview of our encoder-decoder architecture with sparse routing",
        help="图表标题",
    )
    parser.add_argument("--refinement-iterations", type=int, default=2, help="精化迭代次数")
    parser.add_argument("--optimize-inputs", action="store_true", help="是否启用输入优化")
    parser.add_argument("--poll-interval-seconds", type=int, default=5, help="轮询间隔秒数")
    parser.add_argument("--timeout-seconds", type=int, default=600, help="轮询超时秒数")
    return parser


if __name__ == "__main__":
    cli_args = build_parser().parse_args()
    raise SystemExit(run(cli_args))
