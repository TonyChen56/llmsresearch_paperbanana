# PaperBanana Copilot 指引

## 构建与测试

```bash
# 开发环境安装
pip install -e ".[dev,openai,google]"

# 运行完整测试
pytest tests/ -v

# 运行单个测试文件
pytest tests/test_pipeline/test_types.py -v

# 按名称运行单个测试
pytest tests/ -k "test_critique_result_needs_revision" -v

# 代码检查
ruff check paperbanana/ mcp_server/ tests/ scripts/

# 代码格式化
ruff format paperbanana/ mcp_server/ tests/ scripts/
```

CI 在 Linux/macOS/Windows 上运行 Python 3.10–3.12 的 lint、测试和包构建。所有测试必须在没有 `GOOGLE_API_KEY` 的情况下通过——测试中 mock 所有外部 provider。

## 架构

PaperBanana 是一个从文本生成出版级学术图表的多智能体框架，采用**两阶段多 Agent 流水线**：

**Phase 0 — 输入优化（可选）：** InputOptimizer 并行运行两个 VLM 调用（上下文增强 + 标题锐化）
**Phase 1 — 线性规划：** Retriever → Planner → Stylist  
**Phase 2 — 迭代精炼：** Visualizer ↔ Critic（最多 N 轮）

核心架构分层：

- **`paperbanana/core/`** — 流水线编排器（`pipeline.py`）、Pydantic 数据类型（`types.py`）、基于 pydantic-settings 的配置（`config.py`）、运行恢复（`resume.py`）。`Settings` 从环境变量、`.env` 文件或 YAML 配置加载。
- **`paperbanana/agents/`** — 所有 Agent 继承自 `BaseAgent`（`base.py`），封装 `VLMProvider` 并通过 `load_prompt()` 从 `prompts/` 加载提示词模板。Agent 包括：Retriever、Planner、Stylist、Visualizer、Critic、InputOptimizer。
- **`paperbanana/providers/`** — `base.py` 中定义抽象基类 `VLMProvider` 和 `ImageGenProvider`。具体实现在 `vlm/`（OpenAI、Gemini、OpenRouter）和 `image_gen/`（OpenAI、Google Imagen、OpenRouter）。`ProviderRegistry`（`registry.py`）是工厂类。
- **`prompts/`** — 文本提示词模板，按类型分目录（`diagram/`、`plot/`、`evaluation/`），使用 `{placeholder}` 格式化。禁止在 Python 代码中内联提示词。
- **`paperbanana/evaluation/`** — VLM-as-Judge 评分系统，4 个维度：忠实度、可读性、简洁性、美观度。
- **`mcp_server/`** — FastMCP 服务器，暴露三个工具：`generate_diagram`、`generate_plot`、`evaluate_diagram`。
- **`data/reference_sets/`** — 13 个精选方法论图表示例，供 Retriever Agent 进行上下文学习。

## 编码约定

- **全异步**：流水线和所有 Agent 使用 `async/await`。测试使用 `pytest-asyncio`，配置 `asyncio_mode = "auto"`。
- **Pydantic 模型承载所有数据类型**：输入、输出、配置和中间结果均为 `BaseModel` 子类，序列化使用 `model_dump()`。
- **Provider 模式**：新增 provider 需实现 `providers/base.py` 中的 `VLMProvider` 或 `ImageGenProvider`，然后在 `ProviderRegistry` 中注册。
- **提示词模板在 `prompts/` 中，不在代码里**：Agent 提示词是 `.txt` 文件，使用 `{placeholder}` 替换。
- **配置优先级**：`Settings` 合并顺序为 环境变量 → `.env` 文件 → YAML 配置 → CLI 参数。API Key 仅从环境变量读取（`OPENAI_API_KEY`、`GOOGLE_API_KEY`、`OPENROUTER_API_KEY`）。
- **Ruff 统一 lint/格式化**：行宽 100，目标 Python 3.10，规则集：E, F, I, N, W。
- **structlog 日志**：使用 `structlog.get_logger()` 配合关键字参数，不要在日志调用中使用 f-string。
- **入口点**：CLI 通过 Typer（`paperbanana.cli:app`），MCP 服务器通过 FastMCP（`mcp_server.server:main`）。
- **测试 mock 所有外部 provider**：测试中禁止真实 API 调用，使用 `unittest.mock` / pytest fixtures mock provider 响应。
