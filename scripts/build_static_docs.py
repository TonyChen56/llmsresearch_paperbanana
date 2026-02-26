"""Generate api/static/docs.html from FastAPI OpenAPI schema."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from api.app import app


def _plain_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+", " ", value).strip()
    return text


def _extract_request_example(operation: dict[str, Any]) -> str | None:
    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    for media_type in (
        "application/json",
        "multipart/form-data",
        "application/x-www-form-urlencoded",
    ):
        media = content.get(media_type)
        if not media:
            continue
        if "example" in media:
            return json.dumps(media["example"], ensure_ascii=False, indent=2)
        examples = media.get("examples", {})
        if isinstance(examples, dict) and examples:
            first = next(iter(examples.values()))
            value = first.get("value")
            if value is not None:
                return json.dumps(value, ensure_ascii=False, indent=2)
        schema = media.get("schema")
        if schema is not None:
            return json.dumps(schema, ensure_ascii=False, indent=2)
    return None


def _build_curl_example(
    method: str,
    path: str,
    operation: dict[str, Any],
    example: str | None,
) -> str:
    base = "https://api.paperbanana.me"
    auth = '-H "Authorization: Bearer <PAPERBANANA_API_TOKEN>"'
    method_upper = method.upper()
    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})

    if method_upper in {"GET", "DELETE"}:
        return f'curl -X {method_upper} "{base}{path}" {auth}'

    if "multipart/form-data" in content:
        return (
            f'curl -X {method_upper} "{base}{path}" {auth} \\\n'
            '  -F "generated_image=@generated.png" \\\n'
            '  -F "reference_image=@reference.png" \\\n'
            '  -F "source_context=..." \\\n'
            '  -F "caption=..."'
        )

    body = example or "{}"
    return (
        f'curl -X {method_upper} "{base}{path}" {auth} \\\n'
        '  -H "Content-Type: application/json" \\\n'
        f"  -d '{body}'"
    )


def _collect_endpoints(openapi_schema: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    for path, methods in openapi_schema.get("paths", {}).items():
        for method, operation in methods.items():
            method_lower = method.lower()
            if method_lower not in {"get", "post", "put", "patch", "delete"}:
                continue
            anchor = (
                f"{method_lower}-"
                f"{path.strip('/').replace('/', '-').replace('{', '').replace('}', '')}"
            )
            request_example = _extract_request_example(operation)
            responses = [
                {
                    "code": code,
                    "description": _plain_text(resp.get("description")) or "-",
                }
                for code, resp in operation.get("responses", {}).items()
            ]
            endpoints.append(
                {
                    "anchor": anchor,
                    "path": path,
                    "method_upper": method_lower.upper(),
                    "method_class": method_lower,
                    "summary": _plain_text(operation.get("summary")),
                    "description": _plain_text(operation.get("description")),
                    "tags": operation.get("tags", []),
                    "request_content_types": list(
                        operation.get("requestBody", {}).get("content", {}).keys()
                    ),
                    "request_example": request_example,
                    "responses": responses,
                    "curl_example": _build_curl_example(
                        method_lower,
                        path,
                        operation,
                        request_example,
                    ),
                }
            )
    endpoints.sort(key=lambda x: (x["path"], x["method_upper"]))
    return endpoints


def build_static_docs() -> Path:
    root = Path(__file__).resolve().parent.parent
    template_path = root / "scripts" / "templates"
    output_path = root / "api" / "static" / "docs.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(template_path)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("static_docs_template.html.j2")

    schema = app.openapi()
    endpoints = _collect_endpoints(schema)
    rendered = template.render(
        title=schema.get("info", {}).get("title", "PaperBanana API"),
        version=schema.get("info", {}).get("version", "unknown"),
        summary=_plain_text(schema.get("info", {}).get("description")),
        generated_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        endpoints=endpoints,
    )
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


def main() -> None:
    path = build_static_docs()
    print(f"Generated static docs: {path}")


if __name__ == "__main__":
    main()
