<!-- mcp-name: io.github.llmsresearch/paperbanana -->
<table align="center" width="100%" style="border: none; border-collapse: collapse;">
  <tr>
    <td width="220" align="left" valign="middle" style="border: none;">
      <img src="https://dwzhu-pku.github.io/PaperBanana/static/images/logo.jpg" alt="PaperBanana Logo" width="180"/>
    </td>
    <td align="left" valign="middle" style="border: none;">
      <h1>PaperBanana</h1>
      <p><strong>面向 AI 科研人员的学术插图自动化生成工具</strong></p>
      <p>
        <a href="https://github.com/llmsresearch/paperbanana/actions/workflows/ci.yml"><img src="https://github.com/llmsresearch/paperbanana/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
        <a href="https://pypi.org/project/paperbanana/"><img src="https://img.shields.io/pypi/dm/paperbanana?label=PyPI%20downloads&logo=pypi&logoColor=white" alt="PyPI 下载量"/></a>
        <a href="https://huggingface.co/spaces/llmsresearch/paperbanana"><img src="https://img.shields.io/badge/Demo-HuggingFace-yellow?logo=huggingface&logoColor=white" alt="在线演示"/></a>
        <br/>
        <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+"/></a>
        <a href="https://arxiv.org/abs/2601.23265"><img src="https://img.shields.io/badge/arXiv-2601.23265-b31b1b?logo=arxiv&logoColor=white" alt="arXiv"/></a>
        <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?logo=opensourceinitiative&logoColor=white" alt="License: MIT"/></a>
        <br/>
        <a href="https://pydantic.dev"><img src="https://img.shields.io/badge/Pydantic-v2-e92063?logo=pydantic&logoColor=white" alt="Pydantic v2"/></a>
        <a href="https://typer.tiangolo.com"><img src="https://img.shields.io/badge/CLI-Typer-009688?logo=gnubash&logoColor=white" alt="Typer"/></a>
        <a href="https://ai.google.dev/"><img src="https://img.shields.io/badge/Gemini-Free%20Tier-4285F4?logo=google&logoColor=white" alt="Gemini 免费版"/></a>
      </p>
    </td>
  </tr>
</table>

---

> **免责声明**：本项目是论文 *"PaperBanana: Automating Academic Illustration for AI Scientists"*（作者：Dawei Zhu、Rui Meng、Yale Song、Xiyu Wei、Sujian Li、Tomas Pfister 和 Jinsung Yoon，[arXiv:2601.23265](https://arxiv.org/abs/2601.23265)）的**非官方、社区驱动的开源实现**。本项目**与原论文作者或 Google Research 无任何关联，亦未获其背书**。实现基于公开论文，可能与原始系统存在差异。

一个从文本描述生成发表级学术图表和统计图的 agentic 框架。支持 OpenAI（GPT-5.2 + GPT-Image-1.5）、Azure OpenAI / Foundry 和 Google Gemini。

- 带迭代精化的两阶段多智能体流水线
- 多种 VLM 和图像生成 provider（OpenAI、Azure、Gemini）
- 输入优化层，提升生成质量
- 自动精化模式，支持带用户反馈的运行续跑
- CLI、Python API 和 MCP 服务器（IDE 集成）
- Claude Code 技能：`/generate-diagram`、`/generate-plot`、`/evaluate-diagram`

<p align="center">
  <img src="assets/img/hero_image.png" alt="PaperBanana 以论文为输入，输出图表" style="max-width: 960px; width: 100%; height: auto;"/>
</p>

---

## 快速开始

### 前置条件

- Python 3.10+
- OpenAI API key（[platform.openai.com](https://platform.openai.com/api-keys)）或 Azure OpenAI / Foundry 端点
- 或 Google Gemini API key（免费，[Google AI Studio](https://makersuite.google.com/app/apikey)）

### 第一步：安装

```bash
pip install paperbanana
```

或从源码安装（开发模式）：

```bash
git clone https://github.com/llmsresearch/paperbanana.git
cd paperbanana
pip install -e ".[dev,openai,google]"
```

### 第二步：配置 API Key

```bash
cp .env.example .env
# 编辑 .env 并填入你的 API key：
#   OPENAI_API_KEY=your-key-here
#
# Azure OpenAI / Foundry：
#   OPENAI_BASE_URL=https://<resource>.openai.azure.com/openai/v1
```

或使用 Gemini 配置向导：

```bash
paperbanana setup
```

### 第三步：生成图表

```bash
paperbanana generate \
  --input examples/sample_inputs/transformer_method.txt \
  --caption "Overview of our encoder-decoder architecture with sparse routing"
```

启用输入优化和自动精化：

```bash
paperbanana generate \
  --input my_method.txt \
  --caption "Overview of our encoder-decoder framework" \
  --optimize --auto
```

输出保存至 `outputs/run_<timestamp>/final_output.png`，同时保存所有中间迭代结果和元数据。

---

## 工作原理

PaperBanana 实现了一个包含最多 7 个专业智能体的多智能体流水线：

**Phase 0 — 输入优化（可选，`--optimize`）：**

0. **Input Optimizer** 并行运行两个 VLM 调用：
   - **Context Enricher**：将原始方法文本结构化为图表就绪格式（组件、流程、分组、输入/输出）
   - **Caption Sharpener**：将模糊的标题转化为精确的视觉规格说明

**Phase 1 — 线性规划：**

1. **Retriever**：从精选的 13 个方法论图表参考集中选取最相关的示例，涵盖 agent/推理、视觉/感知、生成/学习、科学/应用等领域
2. **Planner**：通过对检索示例的 in-context learning，生成目标图表的详细文字描述
3. **Stylist**：依据 NeurIPS 风格指南（配色方案、布局、排版）对描述进行视觉美化

**Phase 2 — 迭代精化：**

4. **Visualizer**：将描述渲染为图像
5. **Critic**：对照源上下文评估生成图像，并提供修订描述以解决问题
6. 步骤 4-5 重复固定轮次（默认 3 轮），或直到 Critic 满意为止（`--auto`）

## Provider 支持

| 组件 | Provider | 模型 | 备注 |
|------|----------|------|------|
| VLM（规划、评审） | OpenAI | `gpt-5.2` | 默认 |
| 图像生成 | OpenAI | `gpt-image-1.5` | 默认 |
| VLM | Google Gemini | `gemini-2.0-flash` | 免费版 |
| 图像生成 | Google Gemini | `gemini-3-pro-image-preview` | 免费版 |
| VLM / 图像 | OpenRouter | 任意支持的模型 | 灵活路由 |

Azure OpenAI / Foundry 端点自动检测——将 `OPENAI_BASE_URL` 设置为你的端点即可。

---

## CLI 参考

### `paperbanana generate` — 方法论图表

```bash
# 基础生成
paperbanana generate \
  --input method.txt \
  --caption "Overview of our framework"

# 启用输入优化和自动精化
paperbanana generate \
  --input method.txt \
  --caption "Overview of our framework" \
  --optimize --auto

# 基于用户反馈续跑最新一次运行
paperbanana generate --continue \
  --feedback "Make arrows thicker and colors more distinct"

# 续跑指定运行
paperbanana generate --continue-run run_20260218_125448_e7b876 \
  --iterations 3
```

| 参数 | 简写 | 说明 |
|------|------|------|
| `--input` | `-i` | 方法文本文件路径（新运行必填） |
| `--caption` | `-c` | 图表标题 / 传达意图（新运行必填） |
| `--output` | `-o` | 输出图像路径（默认：自动生成至 `outputs/`） |
| `--iterations` | `-n` | Visualizer-Critic 精化轮次（默认：3） |
| `--auto` | | 循环直到 Critic 满意（配合 `--max-iterations` 安全上限） |
| `--max-iterations` | | `--auto` 模式的安全上限（默认：30） |
| `--optimize` | | 通过并行上下文丰富和标题优化预处理输入 |
| `--continue` | | 从 `outputs/` 中最新一次运行续跑 |
| `--continue-run` | | 从指定运行 ID 续跑 |
| `--feedback` | | 续跑时传给 Critic 的用户反馈 |
| `--vlm-provider` | | VLM provider 名称（默认：`openai`） |
| `--vlm-model` | | VLM 模型名称（默认：`gpt-5.2`） |
| `--image-provider` | | 图像生成 provider（默认：`openai_imagen`） |
| `--image-model` | | 图像生成模型（默���：`gpt-image-1.5`） |
| `--format` | `-f` | 输出格式：`png`、`jpeg` 或 `webp`（默认：`png`） |
| `--config` | | YAML 配置文件路径（参见 `configs/config.yaml`） |
| `--verbose` | `-v` | 显示详细的智能体进度和耗时 |

### `paperbanana plot` — 统计图

```bash
paperbanana plot \
  --data results.csv \
  --intent "Bar chart comparing model accuracy across benchmarks"
```

| 参数 | 简写 | 说明 |
|------|------|------|
| `--data` | `-d` | 数据文件路径，CSV 或 JSON（必填） |
| `--intent` | | 图表的传达意图（必填） |
| `--output` | `-o` | 输出图像路径 |
| `--iterations` | `-n` | 精化轮次（默认：3） |

### `paperbanana evaluate` — 质量评估

使用 VLM-as-a-Judge 对生成图表与人工参考图进行对比评估：

```bash
paperbanana evaluate \
  --generated diagram.png \
  --reference human_diagram.png \
  --context method.txt \
  --caption "Overview of our framework"
```

| 参数 | 简写 | 说明 |
|------|------|------|
| `--generated` | `-g` | 生成图像路径（必填） |
| `--reference` | `-r` | 人工参考图像路径（必填） |
| `--context` | | 源上下文文本文件路径（必填） |
| `--caption` | `-c` | 图表标题（必填） |

按 4 个维度评分（依论文的层级聚合方式）：
- **主要维度**：Faithfulness（忠实度）、Readability（可读性）
- **次要维度**：Conciseness（简洁性）、Aesthetics（美观性）

### `paperbanana setup` — 首次配置

```bash
paperbanana setup
```

交互式向导，引导你获取 Google Gemini API key 并保存至 `.env`。

---

## Python API

```python
import asyncio
from paperbanana import PaperBananaPipeline, GenerationInput, DiagramType
from paperbanana.core.config import Settings

settings = Settings(
    vlm_provider="openai",
    vlm_model="gpt-5.2",
    image_provider="openai_imagen",
    image_model="gpt-image-1.5",
    optimize_inputs=True,   # 启用输入优化
    auto_refine=True,       # 循环直到 Critic 满意
)

pipeline = PaperBananaPipeline(settings=settings)

result = asyncio.run(pipeline.generate(
    GenerationInput(
        source_context="Our framework consists of...",
        communicative_intent="Overview of the proposed method.",
        diagram_type=DiagramType.METHODOLOGY,
    )
))

print(f"输出路径: {result.image_path}")
```

续跑上一次运行：

```python
from paperbanana.core.resume import load_resume_state

state = load_resume_state("outputs", "run_20260218_125448_e7b876")
result = asyncio.run(pipeline.continue_run(
    resume_state=state,
    additional_iterations=3,
    user_feedback="Make the encoder block more prominent",
))
```

完整示例参见 `examples/generate_diagram.py` 和 `examples/generate_plot.py`。

---

## MCP 服务器

PaperBanana 内置 MCP 服务器，可与 Claude Code、Cursor 或任何兼容 MCP 的客户端配合使用。通过 `uvx` 无需本地克隆即可使用，添加以下配置：

```json
{
  "mcpServers": {
    "paperbanana": {
      "command": "uvx",
      "args": ["--from", "paperbanana[mcp]", "paperbanana-mcp"],
      "env": { "GOOGLE_API_KEY": "your-google-api-key" }
    }
  }
}
```

暴露三个 MCP 工具：`generate_diagram`、`generate_plot`、`evaluate_diagram`。

仓库还附带 3 个 Claude Code 技能：
- `/generate-diagram <file> [caption]` — 从文本文件生成方法论图表
- `/generate-plot <data-file> [intent]` — 从 CSV/JSON 数据生成统计图
- `/evaluate-diagram <generated> <reference>` — 对照人工参考图评估生成图表

完整配置说明（Claude Code、Cursor、本地开发）参见 [`mcp_server/README.md`](mcp_server/README.md)。

---

## 配置

默认配置在 `configs/config.yaml`，可通过 CLI 参数或自定义 YAML 覆盖：

```bash
paperbanana generate \
  --input method.txt \
  --caption "Overview" \
  --config my_config.yaml
```

关键配置项：

```yaml
vlm:
  provider: openai           # openai、gemini 或 openrouter
  model: gpt-5.2

image:
  provider: openai_imagen    # openai_imagen、google_imagen 或 openrouter_imagen
  model: gpt-image-1.5

pipeline:
  num_retrieval_examples: 10
  refinement_iterations: 3
  # auto_refine: true        # 循环直到 Critic 满意
  # max_iterations: 30       # auto_refine 模式的安全上限
  # optimize_inputs: true    # 预处理输入以提升生成质量
  output_resolution: "2k"

reference:
  path: data/reference_sets

output:
  dir: outputs
  save_iterations: true
  save_metadata: true
```

环境变量（`.env`）：

```bash
# OpenAI（默认）
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1    # 或 Azure 端点
OPENAI_VLM_MODEL=gpt-5.2                      # 覆盖模型
OPENAI_IMAGE_MODEL=gpt-image-1.5              # 覆盖模型

# Google Gemini（备选，免费）
GOOGLE_API_KEY=your-key
```

---

## 项目结构

```
paperbanana/
├── paperbanana/
│   ├── core/          # 流水线编排、类型定义、配置、运行恢复、工具函数
│   ├── agents/        # Optimizer、Retriever、Planner、Stylist、Visualizer、Critic
│   ├── providers/     # VLM 和图像生成 provider 实现
│   │   ├── vlm/       # OpenAI、Gemini、OpenRouter VLM provider
│   │   └── image_gen/ # OpenAI、Gemini、OpenRouter 图像生成 provider
│   ├── reference/     # 参考集管理（13 个精选示例）
│   ├── guidelines/    # 风格指南加载器
│   └── evaluation/    # VLM-as-Judge 评估系统
├── configs/           # YAML 配置文件
├── prompts/           # 所有 agent 和评估的提示模板
│   ├── diagram/       # context_enricher、caption_sharpener、retriever、planner、stylist、visualizer、critic
│   ├── plot/          # 统计图专用提示变体
│   └── evaluation/    # faithfulness、conciseness、readability、aesthetics
├── data/
│   ├── reference_sets/  # 13 个经过验证的方法论图表
│   └── guidelines/      # NeurIPS 风格美学指南
├── examples/          # 完整示例脚本和样本输入
├── scripts/           # 数据整理和构建脚本
├── tests/             # 测试套件
├── mcp_server/        # IDE 集成 MCP 服务器
└── .claude/skills/    # Claude Code 技能（generate-diagram、generate-plot、evaluate-diagram）
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev,openai,google]"

# 运行测试
pytest tests/ -v

# 代码检查
ruff check paperbanana/ mcp_server/ tests/ scripts/

# 代码格式化
ruff format paperbanana/ mcp_server/ tests/ scripts/
```

## 引用

本项目为**非官方**实现。如使用本项目，请引用**原始论文**：

```bibtex
@article{zhu2026paperbanana,
  title={PaperBanana: Automating Academic Illustration for AI Scientists},
  author={Zhu, Dawei and Meng, Rui and Song, Yale and Wei, Xiyu
          and Li, Sujian and Pfister, Tomas and Yoon, Jinsung},
  journal={arXiv preprint arXiv:2601.23265},
  year={2026}
}
```

**原始论文**：[https://arxiv.org/abs/2601.23265](https://arxiv.org/abs/2601.23265)

## 免责声明

本项目是基于公开论文的独立开源重新实现，与原论文作者、Google Research 或北京大学无任何关联，亦未获其背书。实现可能与论文中描述的原始系统存在差异，请自行判断使用。

## 许可证

MIT
