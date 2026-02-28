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
DEFAULT_SOURCE_CONTEXT = """The Transformer model follows an encoder-decoder structure using stacked self-attention and fully connected layers.

Encoder: Stack of N=6 identical layers. Each layer has two sub-layers: (1) multi-head self-attention, and (2) position-wise feed-forward network. Residual connections around each sub-layer, followed by layer normalization.

Decoder: Stack of N=6 identical layers. In addition to the two encoder sub-layers, the decoder inserts a third sub-layer for multi-head cross-attention over the encoder output. Masked self-attention prevents attending to subsequent positions.

Multi-Head Attention: Linearly project queries, keys, values h times, perform scaled dot-product attention in parallel, concatenate and project again.

Positional Encoding: Sinusoidal positional encodings added to input embeddings.
"""
DEFAULT_CAPTION = "The Transformer - model architecture (Vaswani et al., 2017)"


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


def _load_optional_env_value(key_name: str) -> str | None:
    env_path = _project_root() / ".env"
    if not env_path.exists():
        return None

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != key_name:
            continue
        val = value.strip().strip("'\"")
        return val or None
    return None


def _build_headers(base_url: str, token: str, content_type: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Origin": base_url,
        "Referer": f"{base_url}/static/docs.html",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _http_json(
    method: str,
    url: str,
    token: str,
    base_url: str,
    payload: dict[str, Any] | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    data = None
    headers = _build_headers(base_url=base_url, token=token)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    for attempt in range(max_retries + 1):
        req = Request(url=url, method=method.upper(), data=data, headers=headers)
        try:
            with urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")
            if exc.code == 403 and "1010" in err:
                raise RuntimeError(
                    f"HTTP 403 {url}\n"
                    f"{err}\n\n"
                    "检测到 Cloudflare 1010 拦截（不是 token 错误）。\n"
                    "请在 Cloudflare/WAF 放行该域名的当前客户端访问，或改用未拦截的子域名。"
                ) from exc
            if exc.code in {429, 500, 502, 503, 504} and attempt < max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise RuntimeError(f"HTTP {exc.code} {url}\n{err}") from exc
        except URLError as exc:
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise RuntimeError(f"请求失败: {url}\n{exc}") from exc

    raise RuntimeError(f"请求失败: {url}")


def _download_binary(url: str, token: str, base_url: str, max_retries: int = 3) -> tuple[bytes, str]:
    for attempt in range(max_retries + 1):
        req = Request(url=url, method="GET", headers=_build_headers(base_url=base_url, token=token))
        try:
            with urlopen(req, timeout=300) as resp:
                content = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                return content, content_type
        except HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 500, 502, 503, 504} and attempt < max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise RuntimeError(f"下载失败 HTTP {exc.code} {url}\n{err}") from exc
        except URLError as exc:
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise RuntimeError(f"下载失败: {url}\n{exc}") from exc
    raise RuntimeError(f"下载失败: {url}")


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

    if args.prompt_file:
        prompt_path = Path(args.prompt_file).expanduser().resolve()
        if not prompt_path.exists():
            print(f"错误: 提示词文件不存在: {prompt_path}", file=sys.stderr)
            return 2
        source_context = prompt_path.read_text(encoding="utf-8")
    else:
        source_context = DEFAULT_SOURCE_CONTEXT

    base_url = (args.base_url or BASE_URL).rstrip("/")
    submit_url = f"{base_url}/api/v1/tasks/generate"
    payload: dict[str, Any] = {
        "source_context": source_context,
        "communicative_intent": args.caption,
        "refinement_iterations": args.refinement_iterations,
        "optimize_inputs": args.optimize_inputs,
    }
    providers_payload = {
        "vlm_provider": args.vlm_provider,
        "vlm_model": args.vlm_model,
        "image_provider": args.image_provider,
        "image_model": args.image_model,
    }
    providers_payload = {k: v for k, v in providers_payload.items() if v}
    if providers_payload:
        payload["providers"] = providers_payload

    print(f"[1/3] 提交任务: {submit_url}")
    submit_resp = _http_json(
        "POST",
        submit_url,
        token,
        base_url,
        payload,
        max_retries=args.network_retries,
    )
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
        try:
            status = _http_json(
                "GET",
                status_url,
                token,
                base_url,
                max_retries=args.network_retries,
            )
        except RuntimeError as exc:
            print(f"  轮询请求异常，继续重试: {exc}", file=sys.stderr)
            time.sleep(args.poll_interval_seconds)
            continue
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
    content, content_type = _download_binary(
        artifact_full_url,
        token,
        base_url,
        max_retries=args.network_retries,
    )

    output_dir = Path(__file__).resolve().parent
    ext = _guess_extension(content_type, artifact_url)
    output_path = output_dir / f"{args.output_name}{ext}"
    output_path.write_bytes(content)

    status_dump = output_dir / f"task_{task_id}.json"
    status_dump.write_text(json.dumps(final_status, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已保存图片: {output_path}")
    print(f"已保存状态: {status_dump}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="测试提交生成任务接口并下载图片")
    parser.add_argument(
        "--base-url",
        default=os.getenv("PAPERBANANA_API_BASE_URL") or BASE_URL,
        help="API 根地址（默认 https://api1.paperbanana.me）",
    )
    parser.add_argument(
        "--prompt-file",
        default=None,
        help="可选：提示词文件路径；不传则使用脚本内置的 Transformer 提示词",
    )
    parser.add_argument(
        "--caption",
        default=DEFAULT_CAPTION,
        help="图表标题",
    )
    parser.add_argument(
        "--output-name",
        default="transformer",
        help="输出图片文件名（不含后缀），默认 transformer",
    )
    parser.add_argument("--refinement-iterations", type=int, default=1, help="精化迭代次数")
    parser.add_argument("--optimize-inputs", action="store_true", help="是否启用输入优化")
    parser.add_argument(
        "--vlm-provider",
        default=os.getenv("PB_VLM_PROVIDER") or _load_optional_env_value("VLM_PROVIDER"),
        help="可选：覆盖 VLM provider（如 kie/openai/gemini）",
    )
    parser.add_argument(
        "--vlm-model",
        default=os.getenv("PB_VLM_MODEL") or _load_optional_env_value("VLM_MODEL"),
        help="可选：覆盖 VLM 模型名",
    )
    parser.add_argument(
        "--image-provider",
        default=os.getenv("PB_IMAGE_PROVIDER") or _load_optional_env_value("IMAGE_PROVIDER"),
        help="可选：覆盖图像 provider（如 kie_nano_banana/openai_imagen）",
    )
    parser.add_argument(
        "--image-model",
        default=os.getenv("PB_IMAGE_MODEL") or _load_optional_env_value("IMAGE_MODEL"),
        help="可选：覆盖图像模型名",
    )
    parser.add_argument("--poll-interval-seconds", type=int, default=5, help="轮询间隔秒数")
    parser.add_argument("--timeout-seconds", type=int, default=1800, help="轮询超时秒数")
    parser.add_argument("--network-retries", type=int, default=3, help="单次请求的网络重试次数")
    return parser


if __name__ == "__main__":
    cli_args = build_parser().parse_args()
    raise SystemExit(run(cli_args))
