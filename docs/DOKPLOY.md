# Dokploy 部署说明（单服务）

## 1. 代码源

在 Dokploy 新建项目，选择本仓库。

构建方式：
- Dockerfile
- Dockerfile 路径：`./Dockerfile`
- 容器端口：`8000`

## 2. 必填环境变量

```bash
PAPERBANANA_API_TOKEN=your-strong-token
VLM_PROVIDER=kie
IMAGE_PROVIDER=kie_nano_banana
KIE_API_KEY=your-kie-key
```

可选环境变量：

```bash
VLM_MODEL=gemini-2.5-flash
IMAGE_MODEL=google/nano-banana
API_MAX_CONCURRENT_TASKS=3
API_TASK_TTL_MINUTES=120
SKIP_SSL_VERIFICATION=false
```

如需切换供应商，可同时配置：
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `OPENROUTER_API_KEY`

## 3. 健康检查

- Path: `/health`
- Expected: HTTP 200 + `{"status":"ok"...}`

## 4. 域名与访问

绑定域名后：
- `https://<domain>/` 会重定向到 `https://<domain>/static/docs.html`
- 业务接口在 `https://<domain>/api/v1/tasks/*`

## 5. 关键说明

1. 任务状态保存在内存中，建议 `uvicorn --workers 1`（Dockerfile 已固定）。
2. 生成文件保存在容器 `outputs/` 目录，建议在 Dokploy 挂载持久卷。
3. `api/static/docs.html` 在镜像构建阶段自动由 OpenAPI 生成。

