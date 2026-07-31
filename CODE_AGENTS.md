# 项目 Agent 规范

这些规则适用于当前项目及其子目录中的所有文件。

## 语言

- 自然语言内容在非必要情况下都使用中文。
- 只有在 API 名称、命令、代码、文件路径、错误信息、外部协议或用户明确要求时，才使用英文或其他语言。

## 代码组织

- 任何超过 5 行的代码都必须成立单独脚本，并放在 `scripts/` 下。
- 不要在 `SKILL.md`、提示词或说明文档中直接嵌入较长的 Python、Shell 或其他可执行代码。
- 工作流需要可执行逻辑时，创建或更新 `scripts/` 下的脚本，并在文档中引用脚本路径。

## Sub-Agent 提示词

- 所有需要 sub-agent 执行的内容，提示词都必须成立单独的 Markdown 文件，并放在 `sub-agents/` 下。
- 主 agent 不能读取 `sub-agents/` 下的文件内容。
- 使用 sub-agent 提示词时，主 agent 必须启动 sub-agent，并把对应 Markdown 文件路径投递给 sub-agent。
- `sub-agents/` 下的每个文件应只对应一个明确任务或评估角色。

## Python 兼容性

- Python 代码必须兼容 Python 3.8 到 Python 3.13。
- 除非提供兼容回退，否则不要使用 Python 3.8 之后才引入的语法或标准库 API。
- 类型标注优先使用 Python 3.8 兼容写法，例如使用 `Optional[str]`，不要使用 `str | None`。
- 可执行脚本应使用 `#!/usr/bin/env python3`。
