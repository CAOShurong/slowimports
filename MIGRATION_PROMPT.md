# AI Takeover Prompt

将下面这段提示词交给新的 AI。若新 AI 能访问本地项目目录，不需要粘贴旧聊天记录。

```text
你正在接手一个由其他 AI 或人工推进过的项目。

先声明你的能力层级：A. 可读写项目并运行命令；B. 只能读取所提供文件；
C. 只能看到本次聊天中粘贴或上传的内容。

首先读取并遵守 AI_START_HERE.md，然后依次读取 PROJECT_CONTEXT.md、
HANDOFF.md，以及 DECISIONS.md 中与当前任务有关的条目。

如果你具备项目文件和 Python 3.10+ 执行能力，可直接使用
`.ai/project_memory.py` 运行 fingerprint、check、hash-file 和 export；
不需要安装 Codex Skill。

不要把 HANDOFF.md 当作绝对真相。请结合实际文件、Git 状态、数据版本和可用的
测试、渲染或仿真结果进行核验。无法执行的检查必须标成 NOT_RUN；发现矛盾时
先报告，不要擅自抹平。

开始工作前，请简要说明：
1. 当前目标；
2. 已确认状态；
3. 尚未确认或已经过时的信息；
4. 你准备执行的下一步。

完成实质工作、暂停或再次转交前，按 AI_START_HERE.md 的规则更新
HANDOFF.md；持久决策写入 DECISIONS.md。不要写入密码、Token、个人秘密、
未经验证的断言或私有思维过程。
```

如果新 AI 无法访问本地文件，请先生成并上传 `AI_CONTEXT_BUNDLE_*.md`，
再上传当前任务真正需要的代码、文档、图片或数据。
