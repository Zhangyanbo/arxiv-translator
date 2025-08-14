# ArXiv 论文翻译器

本项目使用大语言模型（LLM）自动将 $\LaTeX$ 格式的论文翻译成中文，并完整保留原始的 LaTeX 格式、公式和排版。

## 主要功能

- **智能文本切分**: 能够识别 $\LaTeX$ 文档结构，将正文从模板中分离，并在段落、环境等安全位置进行切分，保证了翻译上下文的连贯性。
- **保留 $\LaTeX$ 语法**: 在翻译过程中，所有的 $\LaTeX$ 命令、公式、环境等都会被完整保留，仅翻译纯文本内容。
- **高质量翻译**: 通过精心设计的 Prompt，引导 AI 模型进行专业、流畅的翻译，避免了翻译腔和常见的语法错误。

## 使用方法

### 1. 安装依赖

首先，请确保你已经安装了 Python。然后通过 pip 安装项目所需的依赖包：

```bash
pip install -r requirements.txt
```

### 2. 配置 API 密钥

在项目根目录下创建一个名为 `.env` 的文件，并将你的 Gemini API 密钥保存在其中。

```text
GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

你可以从 [Google AI for Developers](https://ai.google.dev/gemini-api/docs/api-key?hl=zh-cn) 获取你的 API 密钥。

### 3. 运行翻译

使用以下命令来运行翻译程序：

```bash
python main.py --source <你的LaTeX文件路径>
```

你还可以使用一些可选参数：

- `--save_path`: 指定翻译后文件的保存路径（默认为 `translated.txt`）。
- `--chunk_size`: 每个翻译块的大小（默认为 3000 字符）。
- `--model`: 使用的 Gemini 模型（默认为 `gemini-2.5-flash`，可选 `gemini-2.5-pro`）。

例如：

```bash
python main.py --source my_paper.tex --save_path my_paper_translated.tex
```

### 4. 编译译文

翻译完成后，你需要在生成的 `.tex` 文件头部手动添加 CTeX 包，以支持中文显示：

```latex
\usepackage[UTF8, scheme = plain, fontset = fandol]{ctex}
```

之后，使用 **XeLaTeX** 引擎编译该文件，即可生成带中文的 PDF 文档。

## 代码结构简介

为了方便二次开发和自定义，这里简要介绍一下主要的代码模块。

### `main.py`

这是程序的入口文件。它负责解析命令行参数，初始化 `LaTeXTranslator` 类，并调用其 `translate` 方法来启动整个翻译流程。

### `translator.py`

这个文件包含了翻译功能的核心逻辑。

- **`Translator` class**: 一个围绕 Gemini API 的底层封装。它负责维护与模型的会话（chat），发送待翻译的文本块，并接收和解析翻译结果。其中的 `system_prompt` 对模型的翻译行为和风格进行了详细的指导。
- **`LaTeXTranslator` class**: 上层控制器。它接收完整的 LaTeX 文本，通过调用 `texsplit.py` 中的 `latex_cut` 函数进行智能切分。然后，它会遍历所有文本块，使用 `Translator` 实例进行翻译，并将最终结果重新组合成完整的、可编译的 LaTeX 文档。

### `texsplit.py`

该模块提供了智能切分 LaTeX 源码的功能。

- **`latex_cut(tex: str, L: int)` function**: 这是此模块的核心。它首先会利用 `pylatexenc` 库解析 LaTeX 文档，找到 `\begin{document}` 和 `\end{document}` 之间的正文部分。接着，它会寻找合适的切分点（如段落之间、顶层环境的边界），以避免在行内公式或复杂命令中进行切分。函数最终返回一个包含“文档模板”和多个“文本块”的字典，供 `LaTeXTranslator` 使用。

## License

[MIT License](https://opensource.org/licenses/MIT)
