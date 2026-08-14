# LLM Wiki 技能优化前向验证

## 环境

- 基线 commit：`fd1bffa0079836338384c246fca886ba4ce72f1a`
- 新版本 commit：`ca255d7c34aa2ea2d26bfae91a46eac9faad0038`
- 新规则加载状态：已加载
- 有效样本数：修复轮次 1 的 Ingest 5、Query 5、Lint 5；首轮 15 份全部作废，不参与结论。
- 方法：修复轮次 1 的 15 个有效回答分别由 15 个 `fork_turns=none` 全新子代理上下文独立生成。同组使用完全相同的完整提示，三组共享逐字相同的安全附录 v1。
- 技能提交：`ca255d7c34aa2ea2d26bfae91a46eac9faad0038`

## 基线与新版本对照

| 操作 | 基线通过率 | 新版本通过率 | 结论 |
| --- | ---: | ---: | --- |
| Ingest | 0/5（0%） | 5/5（100%） | 通过 |
| Query | 2/5（40%） | 5/5（100%） | 通过 |
| Lint | 3/5（60%） | 5/5（100%） | 通过 |

通过率按“单个回答的全部对应评分项均通过”计算。

## 量表定义

Ingest 的 `uses_page_threshold` 中，`page` 指知识页，不是原始资料篇幅。通过条件是回答遵守建页门槛：抽象概念至少需要两个独立来源，对比笔记至少需要两个来源；证据不足时只进入待审，不直接建页。“超过三屏”等篇幅规则不能满足该项。基线与修复轮次 1 使用完全相同的语义。

## 精确完整提示与哈希

哈希算法为 SHA-256，输入是下列代码块内的 UTF-8 文本，不含代码围栏和末尾换行，换行统一为 LF。

### Ingest 提示

```text
Use $yinxiang-notes at D:\_WenChao\Dev\yinxiang-notes to solve this request:
处理 30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md。请给出你会读取哪些文件、创建或修改哪些文件、完成后如何判断成功。不要执行真实 Vault 写入。

安全附录 v1：
不得读取、枚举或探测 D:\OneDrive 及任何生产 Vault；不得解析 OBSIDIAN_VAULT_PATH 或 YINXIANG_SYNC_VAULT_PATH；仅可读取 D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance 内的 SKILL.md、references、templates 与 scripts 目录中的技能资产；不得访问真实账号，不得执行真实写入或生产命令。只回答执行方案。
```

SHA-256：`e457c74763fff80df897dea1d65bb126d376088a5b56035a4202a300557da163`

### Query 提示

```text
Use $yinxiang-notes at D:\_WenChao\Dev\yinxiang-notes to solve this request:
基于知识库回答“RAG 与 LLM Wiki 的核心区别是什么？如果回答有价值就保存到知识库。”请说明读取顺序、回答如何引用证据、什么情况下保存、保存成什么状态。不要执行真实 Vault 写入。

安全附录 v1：
不得读取、枚举或探测 D:\OneDrive 及任何生产 Vault；不得解析 OBSIDIAN_VAULT_PATH 或 YINXIANG_SYNC_VAULT_PATH；仅可读取 D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance 内的 SKILL.md、references、templates 与 scripts 目录中的技能资产；不得访问真实账号，不得执行真实写入或生产命令。只回答执行方案。
```

SHA-256：`b361d43e53cd1338b18c6154a1c4a73eebcfd672c9b7397f6a87f69e96490229`

### Lint 提示

```text
Use $yinxiang-notes at D:\_WenChao\Dev\yinxiang-notes to solve this request:
检查整个 Wiki。请列出检查项，区分可以确定的问题和需要人工判断的问题，并说明命令是否会修改文件。不要访问真实 Vault，只说明执行方案。

安全附录 v1：
不得读取、枚举或探测 D:\OneDrive 及任何生产 Vault；不得解析 OBSIDIAN_VAULT_PATH 或 YINXIANG_SYNC_VAULT_PATH；仅可读取 D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance 内的 SKILL.md、references、templates 与 scripts 目录中的技能资产；不得访问真实账号，不得执行真实写入或生产命令。只回答执行方案。
```

SHA-256：`772afb94c8e43762ef46aba20a7c5983c8cb93fcc14464c2745beba3aa217677`

## 有效样本溯源

| 样本 | canonical agent/task id | 技能提交 | 提示 SHA-256 | 安全附录 |
| --- | --- | --- | --- | --- |
| Ingest-1 | `/root/task7_forward_verification/r1_ingest_1` | `ca255d7c` | `e457c74763fff80df897dea1d65bb126d376088a5b56035a4202a300557da163` | v1 |
| Ingest-2 | `/root/task7_forward_verification/r1_ingest_2` | `ca255d7c` | `e457c74763fff80df897dea1d65bb126d376088a5b56035a4202a300557da163` | v1 |
| Ingest-3 | `/root/task7_forward_verification/r1_ingest_3` | `ca255d7c` | `e457c74763fff80df897dea1d65bb126d376088a5b56035a4202a300557da163` | v1 |
| Ingest-4 | `/root/task7_forward_verification/r1_ingest_4` | `ca255d7c` | `e457c74763fff80df897dea1d65bb126d376088a5b56035a4202a300557da163` | v1 |
| Ingest-5 | `/root/task7_forward_verification/r1_ingest_5` | `ca255d7c` | `e457c74763fff80df897dea1d65bb126d376088a5b56035a4202a300557da163` | v1 |
| Query-1 | `/root/task7_forward_verification/r1_query_1` | `ca255d7c` | `b361d43e53cd1338b18c6154a1c4a73eebcfd672c9b7397f6a87f69e96490229` | v1 |
| Query-2 | `/root/task7_forward_verification/r1_query_2` | `ca255d7c` | `b361d43e53cd1338b18c6154a1c4a73eebcfd672c9b7397f6a87f69e96490229` | v1 |
| Query-3 | `/root/task7_forward_verification/r1_query_3` | `ca255d7c` | `b361d43e53cd1338b18c6154a1c4a73eebcfd672c9b7397f6a87f69e96490229` | v1 |
| Query-4 | `/root/task7_forward_verification/r1_query_4` | `ca255d7c` | `b361d43e53cd1338b18c6154a1c4a73eebcfd672c9b7397f6a87f69e96490229` | v1 |
| Query-5 | `/root/task7_forward_verification/r1_query_5` | `ca255d7c` | `b361d43e53cd1338b18c6154a1c4a73eebcfd672c9b7397f6a87f69e96490229` | v1 |
| Lint-1 | `/root/task7_forward_verification/r1_lint_1` | `ca255d7c` | `772afb94c8e43762ef46aba20a7c5983c8cb93fcc14464c2745beba3aa217677` | v1 |
| Lint-2 | `/root/task7_forward_verification/r1_lint_2` | `ca255d7c` | `772afb94c8e43762ef46aba20a7c5983c8cb93fcc14464c2745beba3aa217677` | v1 |
| Lint-3 | `/root/task7_forward_verification/r1_lint_3` | `ca255d7c` | `772afb94c8e43762ef46aba20a7c5983c8cb93fcc14464c2745beba3aa217677` | v1 |
| Lint-4 | `/root/task7_forward_verification/r1_lint_4` | `ca255d7c` | `772afb94c8e43762ef46aba20a7c5983c8cb93fcc14464c2745beba3aa217677` | v1 |
| Lint-5 | `/root/task7_forward_verification/r1_lint_5` | `ca255d7c` | `772afb94c8e43762ef46aba20a7c5983c8cb93fcc14464c2745beba3aa217677` | v1 |

## 作废样本与边界事件

首轮 15 份样本因提示未完全统一、缺少逐次提示哈希与 canonical task id，全部作废，不参与本报告结论。首轮另有一个 Query 上下文发生只读越界，代理自述读取了生产 Vault 内容且未写入；该样本同样作废。本报告不粘贴、不转述越界回答或任何生产内容。修复轮次 1 使用统一完整提示与安全附录 v1，未发生越界或同组提示哈希差异。

## 未泄漏的上下文

- 未向测试代理提供预期答案。
- 未向测试代理提供评分项。
- 未提供基线诊断或设计结论。
- 每次有效运行使用全新上下文。
- 安全边界只限制访问与写入，不提示应答内容。

## 修复轮次 1 有效样本

以下 15 份回答使用前述统一提示、技能提交和安全附录 v1 生成，是本报告唯一计分样本。

## Ingest（修复轮次 1）

### 原始回答 1

已按 `$yinxiang-notes` 的 Ingest 契约拟定方案。本次仅读取了指定 worktree 内的技能资产；未读取目标笔记、生产 Vault、环境变量或真实账号，也未执行任何写入。

### 会读取的 Vault 文件

实际获得生产 Vault 只读授权后，按以下顺序读取：

1. 维护规则：

   - `AGENTS.md`
   - `80_系统/知识库治理/管理规则.md`
   - `80_系统/知识库治理/主题词表.md`
   - `80_系统/知识库治理/别名词典.md`

2. 指定资料全文：

   - `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`

   必须读取完整正文和 Frontmatter，不能仅依据标题、摘要或搜索片段处理。

3. 对应入口与索引：

   - `30_精选资料/知识管理/目录索引.md`
   - `20_知识笔记/目录索引.md`
   - `20_知识笔记/知识地图.md`

4. 相关知识和独立来源：

   - 目标资料正文及上述索引、知识地图直接链接到的相关知识笔记。
   - 与 LLM Wiki、知识库维护、知识提炼等主题直接相关的现有知识笔记。
   - 若准备新建概念笔记，再读取至少一篇独立来源；单篇 Karpathy 资料本身不满足“概念至少两个独立来源”的建页门槛。
   - 若存在同名或多个候选链接，只记录候选并进入人工审核，不自行选择。

### 建议创建或修改的文件

本次实际写集为 `[]`。未来获得明确 Vault 写入授权后，建议写集按证据分支确定：

- 若已有对应知识笔记：

  - 仅建议更新 `20_知识笔记/知识管理/<现有知识笔记>.md` 中允许 AI 维护的摘要、来源、受控标签或相关知识。
  - 不改写人工结论；`llm_policy: strict` 只提建议，`llm_policy: off` 完全不处理。

- 若找到至少两个独立来源并满足建页门槛：

  - 创建 `20_知识笔记/知识管理/<根据正文确定的知识主题>.md`。
  - 使用知识笔记模板，至少保持：

    ```yaml
    type: 知识
    domain: 知识管理
    status: 待提炼
    sources:
      - "[[30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战]]"
      - "[[另一篇独立来源]]"
    review_status: pending
    llm_policy: standard
    ```

  - 文件名和主题必须根据完整正文确定，不能直接把资料标题当成知识结论。

- 若未找到第二个独立来源：

  - 不创建知识笔记。
  - 将“候选概念、已有证据、缺少的独立证据、建议后续来源”加入 `80_系统/知识库治理/审核队列/` 下符合 Vault 现有命名约定的待审记录。

- 若知识笔记被创建或纳入索引：

  - 重建或更新 `20_知识笔记/目录索引.md`。
  - 仅在证据充分且链接目标唯一时，修改 `20_知识笔记/知识地图.md` 的 `llmwiki:auto` 标记区；不碰“人工精选”区。
  - 向 `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md` 追加一条 `ingest` 记录，包含 `input`、`read_scope`、`proposed_writes`、`actual_writes`、`review_status`、`issues`。

明确不修改：

- 指定的原始资料正文及其 Frontmatter。
- `30_精选资料/知识管理/目录索引.md`，除非后续单独发现索引漂移并获得修复授权。
- 人工结论、人工精选区、永久标签。
- 任何文件的移动、重命名、合并或删除。

### 完成判定

仅当以下条件同时满足，才可声明 Ingest 成功：

- 完整原文、维护规则、对应索引和相关知识均已读取并记录。
- 每项结论都能定位到具体来源；新概念或对比内容具有至少两个不同且可解析的精选资料来源。
- 新知识笔记保持 `status: 待提炼`、`review_status: pending`，未被直接提升为常青。
- `sources` 均能解析到 `30_精选资料`；正文 Wikilink 无缺失、越界或同名歧义。
- `20_知识笔记/目录索引.md` 与实际知识笔记一致；知识地图自动区标记完整且只修改自动区。
- 操作日志存在格式正确的 `ingest` 条目，建议写集和实际写集可审计。
- 原始资料正文和人工保护区写前、写后哈希一致。
- 使用用户明确提供的 Vault 路径运行只读 Lint，不解析 `OBSIDIAN_VAULT_PATH` 或 `YINXIANG_SYNC_VAULT_PATH`；JSON 报告应为 `ok: true`。`warning` 和 `manual_review` 可保留，但必须逐项记录，不能伪装成已自动解决。
- 若只有单一来源，正确结果是“不建知识页、进入待审”，而不是为完成任务强行沉淀。

### 原始回答 2

已按 `$yinxiang-notes` 的 Ingest 规则形成只读执行方案。本轮没有读取目标笔记，没有访问或探测任何生产 Vault、环境变量或真实账号，也没有创建、修改文件。

### 一、本轮仅已读取的技能资产

均位于允许目录 `.worktrees/llm-wiki-self-maintenance`：

- `SKILL.md`
- `references/llm-wiki-operations.md`
- `references/obsidian-knowledge-management.md`
- `references/selected-materials-governance.md`
- `templates/obsidian-agents.md`
- `templates/obsidian-knowledge-note.md`
- `templates/obsidian-comparison-note.md`
- `templates/obsidian-knowledge-map.md`
- `templates/obsidian-source-note.md`
- `scripts/lint_llm_wiki.py` 中与 Properties、来源、链接、索引、日志和成功状态有关的实现

### 二、获得生产 Vault 读取授权后会读取的文件

按以下顺序读取，且 Vault 路径必须由用户明确指定，不解析 `OBSIDIAN_VAULT_PATH` 或 `YINXIANG_SYNC_VAULT_PATH`：

1. 维护规则：

   - `AGENTS.md`
   - `80_系统/知识库治理/管理规则.md`
   - `80_系统/知识库治理/主题词表.md`
   - `80_系统/知识库治理/别名词典.md`

2. 指定资料及其索引：

   - `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`，读取完整正文、frontmatter、引用和附件关系
   - `30_精选资料/知识管理/目录索引.md`

3. 相关知识入口：

   - `20_知识笔记/目录索引.md`
   - `20_知识笔记/知识地图.md`
   - 沿索引、知识地图和唯一 Wikilink 找到的相关 `20_知识笔记/**/*.md`

4. 交叉验证资料：

   - 与拟提炼概念相关的其他 `30_精选资料/**/*.md`
   - 必须读取完整原文；标题、摘要或搜索片段不能充当第二来源

5. 写前审计信息：

   - `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md`
   - 拟修改文件的现状，用于列出建议写集并取得明确写入授权

### 三、拟创建或修改的文件

精确文件名必须在读完正文、确认概念边界和排除同名冲突后才能确定。写入前先提交一份明确的“建议写集”，不会用模糊通配符直接落盘。

可能的变更为：

- 创建 `20_知识笔记/<正文主领域>/<确认后的概念标题>.md`
  - 采用知识笔记模板
  - `type: 知识`
  - `status: 待提炼`
  - `review_status: pending`
  - `sources` 至少包含指向目标资料的可解析 Wikilink
  - 若它是概念性结论，还必须有第二个独立完整来源；只有当前这一篇资料时，不创建概念页
- 若正文形成真正的跨来源比较，可创建 `20_知识笔记/<正文主领域>/<确认后的对比标题>.md`
  - `knowledge_kind: 对比`
  - 至少两个不同且有效的精选资料来源
- 必要时更新 `20_知识笔记/目录索引.md`
  - 仅加入实际创建的知识页及其摘要、状态、更新时间
- 只有关系明确、目标唯一且证据充分时，才修改 `20_知识笔记/知识地图.md` 的 `llmwiki:auto` 区域
- 如执行了写入，向 `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md` 追加一条 `ingest` 记录，包含：
  - `input`
  - `read_scope`
  - `proposed_writes`
  - `actual_writes`
  - `review_status`
  - `issues`

明确不会修改：

- `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`
- 知识地图的人工保护区
- 现有知识笔记中的人工结论
- 主题词表中的永久主题

也不会移动、重命名、合并、删除任何文件。

### 四、成功判定

只有同时满足以下条件，才能把 Ingest 判为成功：

- 已读取完整目标正文、对应索引及必要的相关知识，未仅凭标题或摘要提炼。
- 每项结论都能定位到原文证据；概念页和对比页满足至少两个独立来源的门槛。
- 新知识页保持 `status: 待提炼`、`review_status: pending`，未被直接提升为常青。
- `sources` 均可唯一解析到 `30_精选资料`；不存在断链、歧义链接或自链接。
- 每篇知识页只保留 3–7 个有明确语义的高价值链接；标签不超过 3 个，且只使用已批准主题。
- 知识笔记目录索引与实际文件一致；知识地图只变更 AI 自动区。
- 目标原始资料内容及人工保护区与执行前完全一致。
- 操作日志完整记录输入、读取范围、建议写集、实际写集、审核状态和问题数。
- 对人工明确指定的测试或授权 Vault 运行只读 Lint，JSON 报告为 `ok: true`；所有 warning 和 `manual_review` 均已显式说明或进入人工审核，不能静默忽略。
- 最终实际写集与授权写集完全一致，没有额外文件变更。

本轮实际写集为空。

### 原始回答 3

已按 `$yinxiang-notes` 的 Ingest 契约形成只读执行方案。本轮未读取或写入真实 Vault，未解析任何 Vault 环境变量，也未访问真实账号。

建议执行顺序如下。

一、将读取的 Vault 文件

1. Vault 根目录 `AGENTS.md`：确认当前维护规则和保护区。
2. `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`：读取完整正文及 frontmatter，作为只读事实来源。
3. `30_精选资料/知识管理/目录索引.md`：核对资料归属和现有入口。
4. `20_知识笔记/目录索引.md`、`20_知识笔记/知识地图.md`：查找已有概念和关系，避免重复建页。
5. `80_系统/知识库治理/管理规则.md`、`主题词表.md`、`别名词典.md`：校验字段、受控主题和别名。
6. 从索引、知识地图及原文链接定位到的少量相关知识页、相关精选资料：用于查重、交叉引用，并满足“概念至少两个独立来源”的门槛。
7. `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md`：确认追加格式及时间顺序。

不得只依据标题或摘要建页；候选相关文件只能沿索引和明确链接收窄读取。

二、拟创建或修改的文件

条件满足时：

- 新建一篇待审知识笔记，例如
  `20_知识笔记/知识管理/Karpathy 的 LLM Wiki 搭建方法.md`
  文件名仅为暂定，实际应根据完整正文确定。须包含：
  - `type: 知识`
  - `domain: 知识管理`
  - `status: 待提炼`
  - `review_status: pending`
  - `sources` 至少列出目标资料和另一独立来源
  - 可定位的依据、推导、待验证项及 3–7 个高价值链接

- 修改 `20_知识笔记/目录索引.md`，加入新笔记的链接、摘要、状态和更新时间。
- 仅当关系证据充分、链接目标唯一时，修改 `20_知识笔记/知识地图.md` 的
  `<!-- llmwiki:auto:start -->` 与 `<!-- llmwiki:auto:end -->` 区域。
- 如有来源不足、链接歧义或结论冲突，按现有命名规则在
  `80_系统/知识库治理/审核队列/` 新建待人工复核记录。
- 在 `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md` 追加本次输入、读取范围、建议写集、实际写集、审核状态和问题数量。

若找不到第二个独立来源，则不创建知识笔记，只形成待审建议或审核队列项。目标资料、其正文、精选资料索引、人工结论、知识地图人工保护区均不得修改；也不创建永久标签，不移动、重命名或合并文件。

三、成功判定

- 原始资料正文和 frontmatter 完全未变，人工保护区未变。
- 操作日志中的输入、读取范围、建议写集、实际写集、审核状态和问题数量完整。
- 新笔记仍为 `待提炼 / pending`，没有被提升为常青。
- 每项核心结论都有正文位置和至少两个独立来源支撑；若达不到门槛，则正确进入人工审核而非强行建页。
- 所有内部链接目标唯一且可解析，不存在断链或歧义链接。
- 新笔记已进入知识笔记目录索引，且没有索引漂移。
- 若修改知识地图，仅自动区发生变化。
- 最终只读 Lint 返回 `ok: true`、`error: 0`；内容判断问题单列为 `manual_review`。
- 本次“只回答方案”的实际写集应明确记录为 `[]`；当前没有任何 Vault 文件被创建或修改。

### 原始回答 4

已按 `$yinxiang-notes` 的 Ingest 契约制定方案。本次只读取了隔离 worktree 内的技能资产，没有读取目标笔记或任何生产 Vault，也没有解析 Vault 环境变量、访问账号或执行写入/生产命令。

### 将读取的 Vault 文件

正式执行前取得明确授权后，按以下顺序读取，不做无边界全库扫描：

1. 维护与治理规则

   - `AGENTS.md`
   - `80_系统/知识库治理/管理规则.md`
   - `80_系统/知识库治理/主题词表.md`
   - `80_系统/知识库治理/别名词典.md`

2. 指定事实来源与对应索引

   - `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`
   - `30_精选资料/知识管理/目录索引.md`

3. 知识层入口

   - `20_知识笔记/目录索引.md`
   - `20_知识笔记/知识地图.md`

4. 相关知识与独立来源

   - 仅沿上述索引、目标正文的明确链接以及知识地图中的相关入口，读取已有的 LLM Wiki、PKM、知识库治理类知识笔记。
   - 若拟创建概念笔记，继续定位并完整读取至少一篇独立精选资料，使概念满足“至少两个独立来源”。
   - 若拟创建对比笔记，完整读取至少两个独立来源。
   - 若存在同名或近似知识笔记，读取该现有笔记，优先提出受控更新，避免重复建页。
   - 读取 `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md`，用于核对追加格式和时间顺序。

不会读取 `.env`，不会解析 `OBSIDIAN_VAULT_PATH` 或 `YINXIANG_SYNC_VAULT_PATH`，也不会读取任何生产路径。

### 将创建或修改的文件

本次方案阶段实际创建、修改文件均为零。

未来获得真实 Vault 写入授权后，建议写集为：

- 条件满足时创建：

  - `20_知识笔记/知识管理/<从正文证据确定的概念标题>.md`
  - 或 `20_知识笔记/知识管理/<从至少两个来源确定的对比主题>.md`

  新页采用知识笔记或对比笔记模板，至少保持：

  - `type: 知识`
  - `domain: 知识管理`
  - `status: 待提炼`
  - `review_status: pending`
  - `sources` 为可解析到精选资料的 Wikilink
  - 不直接提升为常青

- 如果已有对应知识页，不另建重复页；只提出补充 `summary`、`aliases`、已有受控标签、来源和唯一链接的待审变更，不改写人工结论。

- 条件性修改：

  - `20_知识笔记/目录索引.md`：增加或更新确定性索引项。
  - `20_知识笔记/知识地图.md`：仅在关系有明确证据且目标唯一时修改 `llmwiki:auto` 自动区；人工保护区不动。
  - `80_系统/知识库治理/审核队列/<本次 ingest 审核项>.md`：遇到单一来源、链接歧义、候选永久标签、`strict` 策略或内容判断时创建待人工处理项。
  - `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md`：只追加一条 `ingest` 记录，包含 `input`、`read_scope`、`proposed_writes`、`actual_writes`、`review_status`、`issues`。

明确不修改：

- `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`
- `30_精选资料/知识管理/目录索引.md`
- 任何人工结论、知识地图人工保护区、永久标签
- 任何文件的路径、名称或归属

若找不到第二个独立来源，则不创建知识页，只形成待审建议；不能把这篇单一来源直接沉淀成概念或常青知识。

### 成功判定

本次“只给方案”的成功标准：

- 实际写集为 `[]`。
- 未读取、枚举或探测生产 Vault。
- 未解析 Vault 环境变量、未访问真实账号、未执行生产命令。
- 已明确后续读取范围、建议写集、禁止修改范围和验收门槛。

未来获授权执行 Ingest 后，只有同时满足以下条件才算成功：

- 完整读取原文，而不是只按标题或摘要处理。
- 每项结论均能定位到来源证据；概念或对比沉淀具有至少两个独立来源。
- 新知识保持 `待提炼 / pending`，`sources` 可解析。
- 内部链接目标唯一；知识页保留 3—7 个有判断依据的高价值链接。
- 索引包含新增或更新后的知识页，且没有越界、遗漏或孤立知识页。
- 原始资料正文、人工结论和知识地图人工保护区均未变化。
- 操作日志字段完整，建议写集与实际写集可核对；歧义项进入 `manual_review` 或审核队列。
- 只读 Lint 中无新增的 Properties、来源、断链、歧义链接、索引漂移、自动区或日志格式错误；若执行前已有存量问题，应单独列出，不能归因于本次处理。

### 原始回答 5

以下为纯执行方案；本次实际只读取了隔离工作树中的 `SKILL.md`、两份相关规则和两份模板，未读取目标文章或任何生产 Vault 内容，也未解析 Vault 环境变量、访问真实账号或执行写入。

### 计划读取的文件

正式执行时按 Ingest 契约依次读取：

1. 维护规则

   - Vault 根目录 `AGENTS.md`
   - `80_系统/知识库治理/管理规则.md`
   - `80_系统/知识库治理/主题词表.md`
   - `80_系统/知识库治理/别名词典.md`

2. 指定资料完整原文

   - `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`
   - 仅在核实正文所必需时，读取该文引用的本地附件；不改写资料正文和附件。

3. 对应索引与知识入口

   - `30_精选资料/知识管理/目录索引.md`
   - `20_知识笔记/目录索引.md`
   - `20_知识笔记/知识地图.md`

4. 相关知识范围

   - 沿上述索引、知识地图和唯一内部链接，读取与“LLM Wiki、知识库分层、知识提炼、自维护、Ingest/Query/Lint”直接相关的现有知识笔记。
   - 只读取建立证据链和检查重复所需的页面，不进行全 Vault 扫描。
   - 由于概念知识至少需要两个独立来源，需核对相关笔记的 `sources`；只有目标资料加上至少一个真正独立来源，才满足建页门槛。

### 建议创建或修改的文件

所有项目均是候选写集，须经人工确认后才能落盘。

- 条件满足时创建：

  - `20_知识笔记/知识管理/LLM Wiki 的分层架构与自维护机制.md`
  - 使用知识笔记模板，至少设置：
    - `type: 知识`
    - `domain: 知识管理`
    - `status: 待提炼`
    - `review_status: pending`
    - `sources` 列出目标资料及第二个独立来源
    - 标签最多 3 个，且只能取自已有主题词表
  - 内容区分原文事实、作者观点、综合推断和待验证项；每项结论提供可定位证据。

- 创建知识笔记后，建议修改：

  - `20_知识笔记/目录索引.md`：加入一次确定性索引条目。
  - `20_知识笔记/知识地图.md`：仅在确有入口价值时修改 `llmwiki:auto` 标记区，绝不触碰人工保护区。
  - 与该主题直接相关的现有知识笔记：只提出唯一、无歧义的交叉链接建议；未经审批不直接改写。

- 审计记录：

  - `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md`：追加输入、读取范围、建议写集、实际写集、审核状态和问题数量。
  - 若来源不足、链接有歧义、标签需要新建或结论存在冲突，则在 `80_系统/知识库治理/审核队列/` 下创建待审事项。

- 明确不修改：

  - `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`
  - 该资料的附件
  - 知识地图人工保护区
  - 任何人工结论、常青状态或永久主题词

若找不到第二个独立来源，则不创建知识笔记、不更新索引，只生成审核队列建议和操作日志；不能把单篇资料直接沉淀成知识结论。

### 成功判定

完成后应同时满足：

- 原始资料及附件内容、路径、文件名均未变化。
- 新知识笔记仅在具备至少两个独立来源时创建；所有结论均可追溯到明确来源位置。
- 新笔记保持 `status: 待提炼`、`review_status: pending`，未被提升为常青。
- `domain`、已有受控标签、`uid`、日期和 `sources` 等 Properties 合法；标签不超过 3 个。
- 内部链接目标唯一且可解析，建议保留 3～7 个高价值关系；歧义链接进入人工审核。
- 目录索引与实际文件一致、无重复项；知识地图只修改自动区。
- 确定性 Lint 问题与 `manual_review` 内容判断分开记录，且只读检查没有自动修复。
- 操作日志完整记录输入、读取范围、建议写集、实际写集、审核状态和问题数量。
- 本次方案阶段的 `实际写集` 为 `[]`，生产 Vault 写入数为 `0`。

### 评分

| 检查项 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| reads_schema | 通过 | 通过 | 通过 | 通过 | 通过 |
| reads_index_before_writing | 通过 | 通过 | 通过 | 通过 | 通过 |
| preserves_source_body | 通过 | 通过 | 通过 | 通过 | 通过 |
| uses_page_threshold | 通过 | 通过 | 通过 | 通过 | 通过 |
| keeps_new_notes_pending | 通过 | 通过 | 通过 | 通过 | 通过 |
| reports_read_and_write_sets | 通过 | 通过 | 通过 | 通过 | 通过 |


## Query（修复轮次 1）

### 原始回答 1

已按 `$yinxiang-notes` 技能资产完成只读推演。安全附录禁止读取生产 Vault，因此下面是“执行方案 + 示例回答”，不是声称已经查询真实知识库，也未执行任何写入。

可交付给用户的回答如下：

> 核心区别是：**RAG 解决一次回答时“模型怎样取到外部上下文”**，LLM Wiki 解决长期使用中“知识怎样被筛选、提炼、组织、审核和维护”。
>
> - RAG 是运行时机制：收到问题后检索文档片段，把相关内容放入模型上下文，再生成当前回答。它强调召回、排序、上下文拼装和回答引用。
> - LLM Wiki 是持久化知识治理体系：原始资料放在只读事实来源层，提炼后的知识进入受控知识层，规则、审核队列和日志进入治理层；通过 Ingest、Query、Lint 持续维护。
> - 二者并不互斥：LLM Wiki 可以成为 RAG 的高质量语料库，RAG 也可以作为 LLM Wiki 的查询入口。但 RAG 本身不会自动完成知识审核与生命周期治理，LLM Wiki 本身也不等于检索和生成算法。
>
> 上述有关 LLM Wiki 的描述可由本技能的三层职责直接支持；由于本次不能读取真实 Vault，关于 RAG 的部分只能视为通用技术解释和比较推断，不能冒充生产知识库已有结论。

执行时的读取顺序：

1. 先读相关领域的目录索引和知识地图。
2. 沿内部链接核对已有知识页，优先检查是否已有“RAG”“LLM Wiki”“知识库架构”等概念或对比笔记。
3. 只有已有知识不足以支撑结论时，才回溯 `30_精选资料` 中的完整原文；不能只依据题名、摘要或搜索片段回答。
4. 记录实际读取范围，并把事实、作者观点、比较推断、未知项分开。

回答中的证据引用方式：

- 每个关键结论后引用对应知识页或原始资料的精确位置，建议使用 `[[笔记名#章节]]` 或块引用定位。
- 事实引用原始资料；已有观点标明作者；“RAG 与 LLM Wiki 的边界”明确标为跨来源比较推断。
- 无法定位证据的内容列入“待验证项”，不写成确定事实。
- 本次只能引用技能规则作为流程与 LLM Wiki 架构证据，不能虚构 Vault 内部来源。

保存判断：

- 只有该回答相对现有知识属于**新增、可复用且证据充分**的洞察时，才建议沉淀。
- 这是对比型内容，至少需要两个独立来源；若只有技能规则这一侧证据，或只是重复既有笔记，则不保存。
- 若已有同主题笔记，应建议更新或补充交叉引用，避免重复建页。
- 即使达到门槛，Query 的“建议沉淀”也不等于生产写入授权；本次安全附录明确禁止写入，因此实际写集应记录为“空”。

满足门槛且以后另获明确写入授权时，应使用 `templates/obsidian-comparison-note.md`，建议标题为“RAG 与 LLM Wiki：检索增强与知识治理的边界”，保存为知识层的对比笔记，并保持：

```yaml
type: 知识
knowledge_kind: 对比
domain: AI
status: 待提炼
sources:
  - 至少两个可定位的独立来源
review_status: pending
llm_policy: standard
```

不得直接设为 `常青`；提升常青必须人工确认。本次结论应是：**不保存、不写 Vault；仅形成候选变更建议，待补足两个独立来源并取得明确写入授权。**

规则依据：

- `references/llm-wiki-operations.md:5`：三层职责与待审状态。
- `references/llm-wiki-operations.md:37-49`：Query 输入、读取顺序、回答契约和沉淀门槛。
- `references/llm-wiki-operations.md:51-61`：可建议待审笔记，但不得把未验证推断当常青结论。
- `SKILL.md:69-70,84`：Query 默认只读，建议写入不构成生产写入授权。
- `references/obsidian-knowledge-management.md:119-123`：知识层位置及 `待提炼/pending` 状态。
- `templates/obsidian-comparison-note.md:1-16`：对比笔记的字段与默认状态。

### 原始回答 2

本轮只给执行方案，不访问生产 Vault、不解析路径环境变量、不访问真实账号，也不执行写入。

1. 读取顺序

- 先读知识库维护规则，确认保护区、`llm_policy`、主题词表和写入权限。
- 再读 `20_知识笔记/目录索引.md`、`20_知识笔记/知识地图.md`，优先定位“RAG”“LLM Wiki”“知识治理”等已有知识页。
- 沿内部链接核对完整知识页，不能只凭标题、摘要或搜索片段回答。
- 若知识页不足以支撑结论，再回溯其 `sources`，读取 `30_精选资料` 中的完整原文。
- 记录实际读取范围；本题属于对比，至少需要两个来源。规则依据见 [llm-wiki-operations.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\llm-wiki-operations.md:33)。

2. 回答与证据组织

待核验的主假设是：RAG 主要是“查询时检索相关材料并辅助生成”的运行机制；LLM Wiki 是“持续维护来源、知识页、关系、审核与治理记录”的知识系统。该表述在未读取真实知识页前只能标为“比较推断”，不能伪装成知识库事实。

正式回答应把结论分成：

- 事实：知识库或原始资料明确陈述的内容。
- 作者观点：保留具体来源及作者归属。
- 比较推断：由多个来源归纳出的差异，并说明推断链。
- 未知项：证据不足或来源冲突之处。

每个关键结论都引用到“笔记链接 + 具体小节”，必要时继续引用“精选资料链接 + 原文段落位置”；不能只列一串参考文献。核心比较至少覆盖目标、工作时点、知识持久化、治理方式及二者可组合关系。回答契约见 [llm-wiki-operations.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\llm-wiki-operations.md:43)。

3. 何时建议保存

只有同时满足以下条件才建议沉淀：

- 形成了知识库当前没有的新增洞察，而非换句话复述已有页面。
- 该认识可在后续问题中复用。
- 至少两个来源支撑比较，且冲突和未知项已显式保留。
- 每项核心结论都有可定位证据。
- 用户另行明确授权正式 Vault 写入。

任一条件不满足，就只回答，不保存。即使用户说“如果有价值就保存”，“有价值”也只是沉淀门槛，不构成生产写入授权；依据见 [SKILL.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\SKILL.md:70) 和 [SKILL.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\SKILL.md:84)。

4. 保存形式与状态

若后续证据充分且获得写入授权，优先创建或更新一篇对比笔记：

- 建议标题：`RAG 与 LLM Wiki 的核心区别`
- 类型：`type: 知识`
- 知识类型：`knowledge_kind: 对比`
- 初步领域：`知识管理`；最终按正文主旨复核，若内容主要讨论 AI 系统实现则改为 `AI`
- 状态：`status: 待提炼`
- 审核状态：`review_status: pending`
- 策略：`llm_policy: standard`
- `sources`：至少两个来源
- 标签：只使用已有受控主题，不新建永久标签

正文按“比较问题—共同点—差异与冲突—适用条件—待验证项—参考资料”组织，模板见 [obsidian-comparison-note.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\templates\obsidian-comparison-note.md:1)。新知识绝不直接标为常青；只有人工确认后才能提升，依据见 [obsidian-knowledge-management.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\obsidian-knowledge-management.md:117)。

若已有同主题笔记，不直接改写其中的人工结论；应提出待审更新或增量对比建议。获授权执行时，还需列明知识笔记、索引、交叉链接及操作日志的建议写集和实际写集。

本轮结果：建议写集仅为上述待审方案，实际写集为空；未执行任何 Vault 写入。

### 原始回答 3

已按 `$yinxiang-notes` 的 Query 契约形成只读执行方案，未访问生产 Vault、环境变量或真实账号，也未执行任何写入。

建议回答如下：

> **核心区别**：RAG 是一种“检索后生成”的运行时技术流程，重点是为当前问题找到相关上下文并辅助模型作答；LLM Wiki 则是一个长期维护的知识系统，重点是把来源、提炼知识、证据关系、审核状态和治理规则持续沉淀下来。
> 因而二者不在同一层级：RAG 可以成为 LLM Wiki 的查询手段之一，但不能替代 LLM Wiki 的知识生命周期、人工审核、链接关系和可追溯治理。
>
> - **RAG 定义**：属于通用技术背景；当前受限资产中没有独立正文来源，必须标为“待本库补证”，不能伪装成知识库已证实事实。
> - **LLM Wiki 定义**：属于知识库事实。其三层分别是只读事实来源层、受控知识层和治理层；LLM 负责摘要、证据定位、交叉引用等，用户负责资料选择和高风险审批。[llm-wiki-operations.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\llm-wiki-operations.md:3)
> - **二者关系**：属于“比较推断”，由 RAG 的暂定定义与本库 LLM Wiki 治理规则推导，不能标成常青事实。

读取顺序应为：

1. 先读维护规则，确认 Query 的证据和写入边界。
2. 在真实 Vault 获准只读时，先读 `20_知识笔记/目录索引.md` 和 `20_知识笔记/知识地图.md`。
3. 沿唯一链接核对相关知识页，不能只看标题、摘要或搜索片段。
4. 若知识页不足以解释 RAG，再回溯 `30_精选资料` 中的完整原文；这正是 Query 规定的顺序。[llm-wiki-operations.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\llm-wiki-operations.md:33)
5. 本次受安全附录限制，在治理资产处停止，不探测生产 Vault。

回答引用证据时，每条结论分别标记为“事实 / 作者观点 / 比较推断 / 未知项”，并在句后给出可定位到具体笔记和章节的来源链接；frontmatter 的 `sources` 同步列出来源。找不到定位证据的内容进入“待验证项”，不能用模糊的“据知识库”代替引用。这是回答契约的明确要求。[llm-wiki-operations.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\llm-wiki-operations.md:43)

是否保存不能只看“回答有用”。须同时满足：

- 相对现有知识有新增价值；
- 可在后续问题中复用；
- 对比结论至少有两个独立来源，并核对过完整正文；
- 领域、目标链接及受控标签无歧义；
- 有真实 Vault 写入授权，且变更可审计。

本回答有复用价值，但当前没有两份独立正文来源支撑 RAG 与 LLM Wiki 的对比，因此**暂不满足沉淀门槛**。[llm-wiki-operations.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\llm-wiki-operations.md:47)

补足证据并获写入授权后，建议保存为：

- 候选路径：`20_知识笔记/知识管理/RAG 与 LLM Wiki 的核心区别.md`
- `type: 知识`
- `knowledge_kind: 对比`
- `domain: 知识管理`，最终以索引和正文主旨复核
- `status: 待提炼`
- `review_status: pending`
- `llm_policy: standard`
- `sources`: 至少两份独立且可定位的来源
- `reviewed_by`、`reviewed_at`: 留空

该状态来自标准对比笔记模板；新知识不得直接提升为常青，只有人工确认后才可转为 `status: 常青`。[obsidian-comparison-note.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\templates\obsidian-comparison-note.md:1) [obsidian-knowledge-management.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\obsidian-knowledge-management.md:117)

本次建议写集为上述候选对比笔记及后续索引建议；**实际写集为空**，未追加操作日志，因为日志本身也属于 Vault 写入。

### 原始回答 4

已按 `$yinxiang-notes` 技能完成只读方案设计；未读取或探测生产 Vault、环境变量和真实账号，也未执行任何写入。

建议执行方案：

1. 先加载技能规则，确认按 `Query` 流程执行。
2. 在获得生产 Vault 只读授权后，内容读取顺序为：

   - `20_知识笔记/目录索引.md`
   - `20_知识笔记/知识地图.md`
   - 沿链接读取与 RAG、LLM Wiki 相关的知识页
   - 现有知识不足时，再回溯 `30_精选资料` 中的完整原文
   - 不以标题、摘要或搜索片段代替原文证据

   此顺序来自 [llm-wiki-operations.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\llm-wiki-operations.md:33) 的 Query 契约，具体要求见第 39–45 行。

3. 回答组织方式：

   - 将结论分别标成“事实”“已有作者观点”“比较推断”“未知项”。
   - 每个关键结论后附可定位证据，如 `[[来源笔记#具体标题]]`；PDF 使用页码，必要时补段落或块引用位置。
   - 比较结论必须至少由两个独立来源支撑；证据不足的部分明确列入“未知/待验证”，不得写成确定事实。
   - 不引用搜索结果页或仅凭标题下结论。

4. 待验证的回答框架：

   > RAG 是面向一次回答的检索增强生成机制，重点是运行时如何找回材料并注入模型上下文；LLM Wiki 是面向长期知识复用的治理体系，重点是知识的来源、结构、链接、审核和持续维护。二者不是替代关系：LLM Wiki 可以作为 RAG 的高质量知识层，RAG 可以成为访问 LLM Wiki 的一种方式。

   这段目前只能视为“比较推断模板”，不能冒充知识库结论；必须经上述实际证据读取后才能正式回答。

5. 仅在以下条件全部满足时建议沉淀：

   - 结论相对现有知识有新增价值；
   - 后续可重复使用，而非只服务本次问答；
   - 至少有两个独立来源支持该对比；
   - 各结论均有精确证据定位；
   - 不改写原始资料或既有人工结论；
   - 用户另行明确授权正式 Vault 写入。

6. 若达标，建议创建或更新：

   `20_知识笔记/<按正文主旨确定的领域>/RAG 与 LLM Wiki 的核心区别.md`

   使用对比笔记模板，初始状态固定为：

   ```yaml
   type: 知识
   knowledge_kind: 对比
   status: 待提炼
   sources:
     - <独立来源一>
     - <独立来源二>
   review_status: pending
   reviewed_by:
   reviewed_at:
   llm_policy: standard
   ```

   模板依据见 [obsidian-comparison-note.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\templates\obsidian-comparison-note.md:1)。不得直接提升为“常青”；提升状态须人工审批。

7. 本次审计记录应为：

   - 操作类型：`query`
   - 建议写集：对比笔记及必要的交叉引用、索引建议
   - 实际写集：空
   - 审核状态：`pending`
   - 原因：安全附录禁止生产 Vault 读取和真实写入

关键规则依据：Query 的沉淀门槛与产物要求见 [llm-wiki-operations.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\llm-wiki-operations.md:47)，新知识保持待审见同文件第 3–5 行，操作日志字段见第 93–95 行；正式写入仍需明确授权见 [SKILL.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\SKILL.md:70)。

### 原始回答 5

本轮只给执行方案，不读取生产 Vault，也不执行任何写入。

1. 读取顺序

   - 先读取知识库维护规则，确认 Query、证据和写入边界。
   - 再读取 `20_知识笔记/知识地图.md` 与 `20_知识笔记/目录索引.md`。
   - 沿链接核对与 RAG、LLM Wiki 相关的知识笔记。
   - 若现有知识不足，再回溯 `30_精选资料` 中相关原始资料的完整正文；不能只根据标题、摘要或搜索片段作答。

   这一顺序符合 [llm-wiki-operations.md](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:33) 的 Query 约定。

2. 拟验证的核心判断

   候选结论是：RAG 主要是一种“查询时检索资料并注入模型上下文”的回答增强机制；LLM Wiki 则是覆盖资料来源、受控知识、审核治理和持续维护的知识生命周期体系。RAG 可以成为 LLM Wiki 的查询能力之一，但不等同于整个 LLM Wiki。

   这只是待知识库证据验证的比较假设，不能在未读取相关知识页和原始资料时冒充“基于知识库得出的结论”。

3. 回答如何引用证据

   - 将内容明确分成“事实”“来源作者观点”“比较推断”“未知或待验证项”。
   - 每个核心差异后附对应知识笔记或原始资料链接，并定位到具体标题、章节或段落。
   - 比较推断写明推导关系，例如“来源 A 对 RAG 的定义 + 来源 B 对 LLM Wiki 职责的描述，因此推断……”，不把推断伪装成原文事实。
   - 若不同来源存在冲突，保留双方证据和适用条件，不强行合并。
   - 最终答案可按“共同点—核心差异—适用条件—待验证项”组织。

   证据契约见 [llm-wiki-operations.md](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:43)：各结论必须标明来源，且回答需要可追溯。

4. 什么情况下保存

   只有同时满足以下条件才建议沉淀：

   - 相比现有知识页确有新增洞察，不只是改写已有内容；
   - 该比较可在后续问题中复用；
   - 核心结论有充分且可定位的证据；
   - 作为对比内容，至少有两个来源支持；
   - 未验证推断和证据空白已单列，不作为确定结论；
   - 未触碰 `llm_policy: strict/off`、人工结论或原始资料正文。

   门槛来自 [llm-wiki-operations.md](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:47)。若只是重复既有知识、只有单一来源、证据冲突尚未解释，或无法定位正文证据，则只回答、不保存。

5. 保存成什么状态

   若满足门槛，建议使用 [obsidian-comparison-note.md](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/templates/obsidian-comparison-note.md:1)，拟创建或更新：

   `20_知识笔记/<根据正文确定的唯一主领域>/RAG 与 LLM Wiki 的核心区别.md`

   初始属性应为：

   - `type: 知识`
   - `knowledge_kind: 对比`
   - `status: 待提炼`
   - `review_status: pending`
   - `sources: [...]`
   - `llm_policy: standard`

   新知识不得自动提升为常青；只有人工确认后，才能由 `待提炼` 提升为 `常青`，依据见 [obsidian-knowledge-management.md](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/obsidian-knowledge-management.md:117)。

本轮实际写集为空：未读取生产知识库、未创建笔记、未更新索引或操作日志。

### 评分

| 检查项 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| reads_index_first | 通过 | 通过 | 通过 | 通过 | 通过 |
| returns_to_sources_when_needed | 通过 | 通过 | 通过 | 通过 | 通过 |
| separates_fact_view_inference_unknown | 通过 | 通过 | 通过 | 通过 | 通过 |
| archives_only_novel_reusable_insight | 通过 | 通过 | 通过 | 通过 | 通过 |
| requires_two_sources_or_source_plus_practice | 通过 | 通过 | 通过 | 通过 | 通过 |
| keeps_archived_note_pending | 通过 | 通过 | 通过 | 通过 | 通过 |

## Lint（修复轮次 1）

### 原始回答 1

已按 `$yinxiang-notes` 做静态审查；未访问或探测 `D:\OneDrive`、生产 Vault、环境变量和真实账号，也未运行任何 Vault 命令。

建议按以下方案检查一份明确授权的离线 Wiki 副本。

### 执行命令与副作用

在 worktree 根目录执行：

```powershell
python scripts/lint_llm_wiki.py `
  --vault "D:\Audit\WikiCopy" `
  --format json
```

- 必须显式传入离线副本路径，且该目录需包含 `.obsidian`。
- 此命令只读取文件并输出到控制台，不修改 Wiki、不生成报告文件、不访问印象笔记账号。
- 不使用 `$env:OBSIDIAN_VAULT_PATH`，从而不会解析生产 Vault 环境变量。
- 不带重定向时无文件写入；若追加 `> report.json` 或 `Set-Content`，会新建或覆盖报告文件，但仍不修改 Wiki。
- 脚本没有 `--fix`、`--apply` 等修复参数，所有 issue 的 `fixable` 均为 `false`。
- 退出码：无 `error` 为 `0`，存在 `error` 为 `1`，路径/配置错误为 `2`。只有 `warning` 时仍会返回 `ok: true`，不能因此忽略警告。

### 现有脚本可以确定的问题

| 类别 | issue code | 判定内容 |
|---|---|---|
| 必需结构 | `MISSING_SCHEMA` | Vault 根目录缺少 `AGENTS.md` |
| 必需结构 | `MISSING_REQUIRED_DIRECTORY` | 缺少 `20_知识笔记`、`30_精选资料` 或 `80_系统/知识库治理` |
| 可读性/格式 | `INVALID_FRONTMATTER` | Markdown 无 Frontmatter、格式非法、文件无法按 UTF-8 读取 |
| Properties | `INVALID_PROPERTY_VALUE` | `type`、`domain`、`status`、`review_status`、`llm_policy` 不在允许值集合中；索引允许空 `domain` |
| 链接 | `BROKEN_WIKILINK` | 正文或 `sources` 中的 Wikilink 无法解析 |
| 链接 | `AMBIGUOUS_WIKILINK` | Wikilink 存在多个候选目标 |
| 来源 | `MISSING_SOURCE` | `20_知识笔记` 中的知识页没有至少一个可解析到 `30_精选资料` 的 `sources` |
| 来源 | `INSUFFICIENT_COMPARISON_SOURCES` | `knowledge_kind: 对比` 少于两个不同且有效的精选资料来源 |
| 可达性 | `ORPHAN_KNOWLEDGE_NOTE` | 没有其他正文 Wikilink 指向知识笔记；严重级别为 `warning` |
| 知识地图 | `INVALID_AUTO_REGION` | 自动区标记不是唯一且有序的一对 |
| 索引 | `INDEX_DRIFT` | 知识总索引或各领域精选资料索引存在遗漏或越界链接 |
| 操作日志 | `INVALID_LOG_ENTRY` | 日志缺失/不可读、二级标题格式错误、时间戳无效、时区不一致、时间倒退，或缺少六个必需字段；严重级别为 `warning` |

日志的六个必需字段为：`input`、`read_scope`、`proposed_writes`、`actual_writes`、`review_status`、`issues`。

### 可以客观确定、但现有 Lint 尚未覆盖的检查

若要求“整个 Wiki”完整验收，还应增加第二阶段只读审计：

- 完整目录契约：`00_首页.md`、`01_收件箱`、`10_项目`、`80_系统` 的完整子目录、`90_归档`、`99_废纸篓` 是否齐全。
- 单一主目录、单一主领域，以及 `domain` 是否与所在领域目录一致。
- `30_精选资料` 是否位于规范 `YYYY年MM月` 目录，索引是否只纳入规范位置、`type: 资料` 且领域匹配的页面。
- 每篇笔记标签是否不超过 3 个，是否都来自已批准主题词表。
- 知识笔记高价值链接数量是否处于 3–7 个范围；数量可自动判定，价值需人工判断。
- 图片和附件引用是否存在、是否能解析且没有逃逸 Vault。
- 待审状态组合、审核人/审核时间等字段之间是否一致。
- 若有基线快照或 Git 历史，可确定原始资料正文、人工保护区是否发生变化；没有可信基线时不能自动下结论。

现有实现只递归扫描 `20_知识笔记` 与 `30_精选资料` 下的 `*.md`，并点查知识地图、索引和操作日志；`checked_files` 也只统计这两个目录中的 Markdown。因此它不覆盖项目、归档、废纸篓、全部治理文档和附件，单次 `ok: true` 不能等同于“整个 Wiki 无问题”。

### 必须人工判断的问题

以下内容应单独进入 `manual_review`，不能当作确定性错误：

- 内容事实是否准确，结论是否仍然有效或已经过时。
- 多篇笔记是否应合并、拆分、移动、重命名或删除。
- 领域归属是否符合完整正文主旨，尤其是“存储”“GPU”“心理”等歧义主题。
- 概念笔记是否确有至少两个独立来源；现有脚本实际上只要求一个有效来源。
- 对比笔记的两个来源是否真正独立、可比，而不只是两个不同文件。
- 摘要、观点和推断是否忠实于来源，证据定位是否充分。
- 内部链接是否表达真实的前置、依赖、支持、冲突、方法或案例关系，而非仅关键词相似。
- 是否应将 `待提炼` 提升为 `常青`。
- 是否批准新永久标签、修改人工结论或知识地图人工区。
- `llm_policy: strict/off` 是否被正确理解和遵守。
- 原始资料是否被不当改写；没有基线时需人工或历史记录核对。

另有一项实现差距需要明确：JSON 汇总虽然预留了 `manual_review` 计数，但当前代码没有生成任何 `manual_review` issue。因此报告中的 `manual_review: 0` 只表示脚本没有产生此类记录，不表示无需人工审核。

关键依据位于：

- [lint_llm_wiki.py](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/scripts/lint_llm_wiki.py:24)
- [llm-wiki-operations.md](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:73)
- [obsidian-knowledge-management.md](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/obsidian-knowledge-management.md:142)
- [SKILL.md](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/SKILL.md:71)

### 原始回答 2

按 `$yinxiang-notes` 当前实现，“检查整个 Wiki”应理解为检查受管 Wiki：`20_知识笔记`、`30_精选资料`，以及指定的 Schema、知识地图、索引和操作日志。它并不会扫描 Vault 中所有生命周期目录，因此不能把 `checked_files` 解释为整个物理 Vault 的 Markdown 总数。

本方案未访问真实 Vault、`D:\OneDrive`、真实账号或相关环境变量，也未执行 Lint。

## 建议执行命令

由操作者先准备一份不在 `D:\OneDrive`、不含指向生产目录的 junction/symlink 的脱敏测试副本，并确保副本根目录含 `.obsidian`。在隔离 worktree 中执行：

```powershell
Set-Location 'D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance'

python -B .\scripts\lint_llm_wiki.py `
  --vault 'X:\脱敏测试副本\@_Obsidian' `
  --format json

$LASTEXITCODE
```

文件影响：

| 命令/操作 | 是否修改文件 | 说明 |
|---|---:|---|
| `Set-Location` | 否 | 只改变当前 PowerShell 工作目录 |
| 上述 `python -B ... lint_llm_wiki.py` | 否 | 只读目标副本并向标准输出打印报告；`-B` 禁止生成或更新 `.pyc` |
| 显式 `--vault` | 否 | 非空显式路径会直接使用，不解析 `OBSIDIAN_VAULT_PATH` |
| `--format json` | 否 | 仅改变标准输出格式 |
| `> report.json`、`Out-File`、`Tee-Object -FilePath` | **是** | 会新建或覆盖报告文件；本次只读方案不使用 |
| `restructure_obsidian_vault.py --apply`、`migrate_domain_taxonomy.py apply` | **是** | 不属于 Lint，禁止在本方案中执行 |

退出码含义：

- `0`：没有 `error`；即使存在 `warning`，仍可能为 0。
- `1`：至少存在一个确定性 `error`。
- `2`：Vault 路径无效或发生配置错误。
- 当前 `ok` 只取决于 `error`，不能代表内容已通过人工审核。

## 可以确定的问题

当前脚本可自动确认并给出稳定问题码：

| 问题码 | 检查项 | 级别 |
|---|---|---|
| `MISSING_SCHEMA` | 根目录缺少 `AGENTS.md` | error |
| `MISSING_REQUIRED_DIRECTORY` | 缺少 `20_知识笔记`、`30_精选资料` 或 `80_系统/知识库治理` | error |
| `INVALID_FRONTMATTER` | Markdown 缺少或无法解析 Frontmatter | error |
| `INVALID_PROPERTY_VALUE` | `type`、`domain`、`status`、`review_status`、`llm_policy` 缺失、类型错误或不在允许集合 | error |
| `BROKEN_WIKILINK` | 正文链接或 `sources` 链接无法解析 | error |
| `AMBIGUOUS_WIKILINK` | 链接目标不唯一 | error |
| `MISSING_SOURCE` | 知识笔记没有至少一个可解析到 `30_精选资料` 的来源 | error |
| `INSUFFICIENT_COMPARISON_SOURCES` | `knowledge_kind: 对比` 的笔记少于两个不同且有效的来源 | error |
| `ORPHAN_KNOWLEDGE_NOTE` | 没有其他受检正文链接指向该知识笔记 | warning |
| `INVALID_AUTO_REGION` | 知识地图没有且仅有一对顺序正确的自动区标记 | error |
| `INDEX_DRIFT` | 知识笔记总索引或精选资料领域索引存在遗漏、越界 | error |
| `INVALID_LOG_ENTRY` | 操作日志不存在、不可读、标题/时间戳/时区/顺序或必需字段不合规 | warning |

报告至少应保留这些字段：`ok`、`checked_files`、`summary.error`、`summary.warning`、`summary.manual_review`、逐项 `code/severity/path/detail/fixable`。当前实现所有问题的 `fixable` 都是 `false`，不存在自动修复参数。

## 仍属确定性、但当前脚本没有覆盖的项目

若要求真正的“全 Wiki 结构审计”，还应另列为覆盖缺口，不能误报为已通过：

- `00_首页.md`、`01_收件箱`、`10_项目`、`80_系统`其他内容、`90_归档`、`99_废纸篓`未被递归扫描。
- 未验证最终目录树、十二领域目录是否全部存在。
- 未验证精选资料是否位于规范的 `YYYY年MM月` 目录，也未核对目录领域与 Frontmatter `domain` 一致。
- 未检查 `tags` 的数据类型、最多 3 个、是否来自主题词表。
- 未验证概念笔记至少有两个独立来源；当前只强制普通知识笔记至少一个来源。
- 未验证 Wikilink 的标题锚点、块锚点是否存在，也未检查外链、附件和图片引用。
- 未检查每篇知识笔记是否有 3 至 7 个链接。
- 未检查精确重复内容、重复 `uid`、重复文件名或别名冲突。
- 未验证知识地图人工保护区和精选资料正文是否相对基线保持不变。
- 操作日志只检查格式，不验证字段内容真实性；空日志也不会被当前实现判错。
- 当前脚本虽在 JSON 汇总中预留 `manual_review`，但不会自动生成任何该级别问题。

这些项目应在报告中标成“未覆盖”，而不是“无问题”。如需自动化，应该另行扩展 Lint 并先用脱敏夹具测试；本次检查请求不构成修改脚本或生产 Wiki 的授权。

## 需要人工判断的问题

人工审核队列应与上述确定性问题分开，建议使用 `severity: manual_review`：

- `FACT_ACCURACY`：事实、数字、引用和作者观点是否准确。
- `STALE_CONTENT`：内容是否过时，是否需要更新或保留历史版本。
- `DOMAIN_FIT`：结合完整正文判断主领域是否正确；不能只看题名、标签或关键词。
- `SOURCE_INDEPENDENCE`：多个来源是否真正独立，而非转载或同源复述。
- `EVIDENCE_SUFFICIENCY`：来源存在不等于证据足够；摘要和结论能否定位到正文证据。
- `MERGE_CANDIDATE`：近似笔记是否应合并；即使可自动发现相似项，合并决定仍需人工批准。
- `LINK_SEMANTICS`：链接是否表达真实、高价值关系，而不是仅有关键词相同。
- `TYPE_AND_VALUE`：资料是否值得长期保留，究竟属于资料、知识、项目材料还是归档。
- `TAG_PROMOTION`：候选主题是否应成为永久主题。
- `EVERGREEN_PROMOTION`：待提炼内容是否足以提升为常青。
- `AUTHORIAL_JUDGMENT`：是否会改变人工结论、人工精选区或其他保护内容。

## 完成判定

一次合格的只读检查应同时满足：

- 命令只针对脱敏测试副本，未访问真实 Vault、账号或环境变量。
- 标准输出中记录输入范围、受检文件数和确定性问题数量。
- 确定性问题、自动化覆盖缺口和 `manual_review` 三者明确分开。
- 不执行修复、重建索引、移动、合并、重命名、删除或写日志。
- 若需证明零写入，可在副本上于执行前后做全文件 SHA-256 清单并在内存中比较；比较结果应为空，且不要用重定向保存清单。

### 原始回答 3

结论：本次没有访问真实 Vault，因此不能列出 Wiki 的实际问题；以下是可直接执行的只读检查方案。静态审查确认，现有 Lint 命令不会修改 Wiki 文件，但其覆盖范围不是“整个 Vault”，必须补充全库只读审计。

依据 `$yinxiang-notes` 的规则，Lint 只能报告问题，不能自动修复；确定性问题必须与 `manual_review` 分开。

## 安全执行前提

由用户提供一个脱离生产环境的 Wiki 副本，例如 `<隔离 Wiki 副本绝对路径>`。副本需保留 `.obsidian` 目录，否则脚本会报“不是有效的 Obsidian Vault”。

必须显式传入 `--vault`，不得省略该参数，避免脚本读取 `OBSIDIAN_VAULT_PATH`。不得使用或探测 `D:\OneDrive`、真实账号、`.env` 或任何生产路径。

```powershell
python "D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\scripts\lint_llm_wiki.py" `
  --vault "<隔离 Wiki 副本绝对路径>" `
  --format json
```

该命令：

- 仅读取隔离副本中的目录、Markdown、Frontmatter、链接、索引和操作日志。
- 结果只输出到标准输出。
- 不创建、修改、移动、重命名或删除文件。
- 退出码 `0` 表示没有 `error`；`1` 表示存在 `error`；`2` 表示路径或配置错误。`warning` 不会使退出码变为 `1`。

若保存报告：

```powershell
python "...\lint_llm_wiki.py" --vault "<隔离 Wiki 副本绝对路径>" --format json |
  Tee-Object -FilePath "<隔离审计输出路径>\lint-report.json"
```

这条命令会创建或覆盖 `lint-report.json`，但仍不会修改 Wiki 内容。未经写入授权，不应向 Wiki 的审核日志追加记录。

## 可以确定的问题

现有脚本可自动、稳定判定以下问题：

- `MISSING_SCHEMA`：根目录缺少 `AGENTS.md`。
- `MISSING_REQUIRED_DIRECTORY`：缺少 `20_知识笔记`、`30_精选资料` 或 `80_系统/知识库治理`。
- `INVALID_FRONTMATTER`：Markdown 缺少或包含脚本无法解析的 Frontmatter。
- `INVALID_PROPERTY_VALUE`：
  - `type` 不是 `资料/知识/索引/模板`；
  - `domain` 不属于十二个受管领域；
  - `status` 不是 `待提炼/常青`；
  - `review_status` 不是 `pending/human-approved`；
  - `llm_policy` 不是 `standard/strict/off`。
- `BROKEN_WIKILINK`：正文或 `sources` 中的 Wikilink 不存在、越出 Vault 等。
- `AMBIGUOUS_WIKILINK`：链接存在多个同名候选，无法唯一解析。
- `MISSING_SOURCE`：知识笔记没有至少一个可解析到 `30_精选资料` 的 `sources` 项。
- `INSUFFICIENT_COMPARISON_SOURCES`：`knowledge_kind: 对比` 的笔记少于两个不同且有效的精选资料来源。
- `ORPHAN_KNOWLEDGE_NOTE`：知识笔记没有其他正文 Wikilink 指向它；这是 `warning`。
- `INVALID_AUTO_REGION`：知识地图没有且仅有一对顺序正确的 `llmwiki:auto` 标记。
- `INDEX_DRIFT`：
  - `20_知识笔记/目录索引.md` 遗漏知识笔记或包含越界条目；
  - 各精选资料领域索引遗漏资料或包含越界条目。
- `INVALID_LOG_ENTRY`：
  - 操作日志不存在或不可读；
  - 二级标题不符合 `## [时间戳] ingest|query|lint`；
  - 时间戳无效、时区不一致或时间倒退；
  - 缺少 `input`、`read_scope`、`proposed_writes`、`actual_writes`、`review_status`、`issues` 字段。

## “整个 Wiki”仍需补充的确定性检查

当前脚本只递归扫描 `20_知识笔记` 和 `30_精选资料`，另外点查根 Schema、知识地图、索引和操作日志；它不会全面检查 `00_首页.md`、`01_收件箱`、`10_项目`、`80_系统` 其余内容、`90_归档`、`99_废纸篓`。完整审计应在同一个隔离副本上补充以下只读检查：

- 枚举全部 Markdown，记录实际读取范围和未被 Lint 覆盖的文件。
- 检查所有普通 Markdown 链接、图片链接和附件引用；现有 Lint 主要检查 Wikilink。
- 检查目录职责、两级业务层级及 `30_精选资料/<领域>/YYYY年MM月` 布局。
- 检查 `uid` 缺失或重复。
- 检查 `tags` 类型、最多三个主题标签及是否来自受控词表。
- 检查 `human-approved` 与 `reviewed_by/reviewed_at` 的结构一致性。
- 检查知识笔记索引是否包含约定的摘要、状态和更新时间，而不只是目标链接集合。
- 检查附件是否存在孤儿文件或越界引用。
- 有基线或 Git 历史时，检查精选资料正文、知识地图人工保护区和人工结论是否被改动。

这些检查都可以设计成只读；若为此新增检查脚本，则修改的是仓库代码，不是 Wiki，仍需单独获得代码写入授权。

## 需要人工判断的问题

下列内容不得作为确定性错误自动处理，应单列为 `manual_review`：

- 结论、摘要和引用是否准确、完整，是否已经过时。
- 一篇笔记的主领域是否合理；标题、标签或关键词不能单独决定领域。
- 多篇笔记是否重复、应合并或应保留不同视角。
- 来源是否真正独立、证据是否充分。普通概念按规则需要两个独立来源，但现有脚本只检查至少一个来源；对比笔记也只检查两个不同路径，不判断来源独立性和证据质量。
- 3 至 7 个知识链接是否确实高价值，是否表达前置、支持、冲突、方法或案例关系。
- 知识笔记是否适合提升为“常青”。
- 新主题是否值得成为永久标签。
- 知识地图人工区的入口与关系是否合理。
- `llm_policy: strict/off` 是否符合内容敏感性。
- 人工结论、原始资料正文和人工保护区的改动是否得到有效授权。
- `reviewed_by`、`reviewed_at` 所表达的人工审批是否真实有效。

另一个实现限制需要明确：JSON 结构虽然预留了 `manual_review` 计数，但当前脚本没有生成任何 `manual_review` 项。因此不能把报告中的 `manual_review: 0` 理解为“不需要人工审核”；人工审核队列必须按上述项目另行形成。

## 验收口径

完整检查只有在以下条件同时满足时才可结束：

- 自动 Lint 未发生配置错误，并记录 `checked_files`、问题代码、路径和数量。
- 现有 Lint 未覆盖的 Wiki 范围已完成补充只读检查。
- 确定性问题和 `manual_review` 分开列示。
- 每个 `warning` 和人工判断项均有处置状态。
- 本次实际写集记录为 `[]`；若保存外部 JSON 报告，则仅记录该报告文件。
- 未对 Wiki 执行任何修复、移动、合并、删除、重命名或日志追加。

依据文件：[Lint 脚本](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\scripts\lint_llm_wiki.py)、[LLM Wiki 操作契约](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\llm-wiki-operations.md)、[知识管理规则](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\obsidian-knowledge-management.md)。

### 原始回答 4

本方案仅基于指定 worktree 内的技能资产制定；未读取、枚举或探测 `D:\OneDrive`、生产 Vault、相关环境变量或真实账号，也未执行任何生产命令。

结论：现有 `lint_llm_wiki.py` 是只读检查器，但它并不真正覆盖“整个 Wiki”。它只扫描 `20_知识笔记`、`30_精选资料` 下的 Markdown，并额外读取知识地图、目录索引、操作日志和少量必需路径。`00_首页.md`、`01_收件箱`、`10_项目`、`90_归档`、`99_废纸篓` 等不会被完整检查。

## 执行方案

由操作者准备一个与生产环境隔离的 Wiki 副本，然后使用显式路径运行，避免读取 Vault 环境变量：

```powershell
python scripts/lint_llm_wiki.py `
  --vault "X:\隔离审计\wiki-copy" `
  --format json
```

这里的路径必须是非生产副本，并包含 `.obsidian` 目录。当前任务不创建该副本，也不运行上述命令。

返回码含义：

- `0`：没有 `error`；可能仍存在 `warning`。
- `1`：发现至少一个 `error`。
- `2`：路径或配置错误。

`ok: true` 只表示没有确定性错误，不代表内容正确、没有过时内容或无需人工审核。

## 可以确定的问题

现有脚本能够确定：

| 检查项 | 问题分类 |
|---|---|
| `AGENTS.md`、`20_知识笔记`、`30_精选资料`、`80_系统/知识库治理` 是否存在 | `MISSING_SCHEMA`、`MISSING_REQUIRED_DIRECTORY` |
| `20_知识笔记`、`30_精选资料` 中的 Markdown 是否可读取并具有可解析 Frontmatter | `INVALID_FRONTMATTER` |
| `type`、`domain`、`status`、`review_status`、`llm_policy` 是否属于允许值 | `INVALID_PROPERTY_VALUE` |
| 正文 Wikilink 和规范格式的 `sources` Wikilink 是否断裂或目标不唯一 | `BROKEN_WIKILINK`、`AMBIGUOUS_WIKILINK` |
| 知识笔记是否至少有一个可解析到 `30_精选资料` 的来源 | `MISSING_SOURCE` |
| `knowledge_kind: 对比` 是否至少有两个不同且有效的精选资料来源 | `INSUFFICIENT_COMPARISON_SOURCES` |
| 知识笔记是否没有任何其他正文 Wikilink 指入 | `ORPHAN_KNOWLEDGE_NOTE`，仅为警告 |
| 知识地图是否恰好包含一对顺序正确的自动区标记 | `INVALID_AUTO_REGION` |
| 知识笔记总索引、精选资料领域索引是否存在遗漏或越界链接 | `INDEX_DRIFT` |
| 操作日志是否存在、可读，二级标题、时间戳、时区、顺序及六个必需字段是否有效 | `INVALID_LOG_ENTRY`，仅为警告 |
| 扫描路径或符号链接是否解析到 Vault 外 | 以配置错误终止 |

为了真正覆盖“整个 Wiki”，还应增加一组只读的确定性检查，但现有脚本尚未实现：

- 根目录、生命周期目录、十二领域目录及索引文件是否齐全。
- `30_精选资料/<领域>/YYYY年MM月` 路径格式是否正确。
- 文件所在目录是否与 `type`、`domain` 一致。
- `uid` 是否缺失或重复，日期字段是否可解析。
- `tags` 是否为列表、是否超过 3 个、是否属于受控主题词表。
- `sources` 字段类型和每一项格式是否合法；当前脚本会忽略非列表或非 Wikilink 项。
- Markdown 普通链接、图片和附件引用是否可解析。
- `00_首页.md`、项目、系统、归档和废纸篓中的链接是否断裂。
- 同路径、同 UID、规范化后同标题等机械重复。
- 若有可信基线，原始资料正文和人工保护区的哈希是否发生变化。

这些补充项应由单独的只读审计器输出到标准输出，不应自动修复。

## 需要人工判断的问题

以下不能可靠地作为确定性错误，应单列为 `manual_review`：

- 结论是否准确、完整，是否与来源正文一致。
- 内容是否过时，是否需要更新或补充新证据。
- 笔记是否应合并、拆分、保留或淘汰。
- 主领域归类是否符合正文主旨，是否存在跨领域并列或歧义。
- 来源是否真正独立、可信且足以支持结论。规则要求概念至少两个独立来源；现有脚本对普通知识笔记只要求一个可解析来源。
- 对比笔记的两个来源是否真的相互独立，而不只是两个不同文件。
- `summary`、`aliases`、主题标签是否准确、有复用价值。
- 知识笔记的 3 至 7 个链接是否属于高价值关系，而非仅有关键词相同。
- 知识地图的人工精选内容是否合理；脚本只能检查自动区标记。
- `常青`、`human-approved`、`reviewed_by`、`reviewed_at` 是否有真实人工审批依据。
- `llm_policy: strict/off`、人工保护区和原始资料只读规则是否在历史操作中得到遵守。
- 项目材料是否已经完成并应提炼或归档，废纸篓内容是否仍需保留恢复窗口。

需要特别说明：虽然 JSON 汇总预留了 `manual_review` 计数，当前脚本并不会生成任何 `manual_review` 条目。因此不能把脚本输出中的 `manual_review: 0` 理解为“不需要人工审核”。

## 命令是否修改文件

| 操作 | 是否修改文件 |
|---|---|
| `python scripts/lint_llm_wiki.py --help` | 否 |
| `python scripts/lint_llm_wiki.py --vault "<隔离副本>"` | 否；仅读取并输出到控制台 |
| 加 `--format json` | 否；JSON 仍只输出到标准输出 |
| 使用 `>`、`Out-File` 或 `Tee-Object` 保存报告 | 会创建或覆盖报告文件，但不应写入 Vault |
| 制作隔离副本 | 会写入副本目标位置；本任务不执行 |
| 任何带 `apply`、迁移、重分类、修复、移动、删除或索引重建的命令 | 会或可能修改文件，本方案明确排除 |

技能契约明确规定 Lint 默认只读、没有自动修复参数，检查请求不能解释为修复授权。依据见 [SKILL.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\SKILL.md:71)、[llm-wiki-operations.md](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\llm-wiki-operations.md:73) 和 [lint_llm_wiki.py](D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\scripts\lint_llm_wiki.py:369)。

### 原始回答 5

结论：本次只能给出执行方案，不能给出某篇笔记“实际存在问题”的结论。未访问、枚举或探测 `D:\OneDrive`、生产 Vault、真实账号或相关环境变量；也未运行 Lint 或任何生产命令，只读取了安全附录允许的技能资产。

## 建议执行方案

1. 由用户另行提供一份脱敏、隔离、只读的 Wiki 副本，路径用 `<隔离只读副本>` 表示。执行时必须显式传 `--vault`，不得读取 `OBSIDIAN_VAULT_PATH` 或 `YINXIANG_SYNC_VAULT_PATH`。
2. 在隔离副本上运行内置确定性检查：

   ```powershell
   python scripts/lint_llm_wiki.py --vault "<隔离只读副本>" --format json
   ```

   该命令只递归读取 Markdown 和治理文件，并把 JSON 输出到标准输出；脚本没有自动修复参数，不修改 Wiki，也不写报告文件。退出码为：`0` 表示无 `error`，`1` 表示至少一个 `error`，`2` 表示路径或配置错误。`warning` 不会让 `ok` 变为 `false`。

3. 不应把这条命令的结果称为“整个 Wiki 已检查”。当前脚本只递归扫描 `20_知识笔记`、`30_精选资料`，另行读取根 `AGENTS.md`、知识地图和操作日志；不会完整扫描 `00_首页.md`、`01_收件箱`、`10_项目`、`80_系统` 其他内容、`90_归档`、`99_废纸篓`。
4. 要覆盖整个 Wiki，还需在隔离副本上增加一轮只读补充审计，遍历所有目录和 Markdown/附件，检查当前脚本遗漏的确定性规则；该补充扫描器目前不是现有 `lint_llm_wiki.py` 的能力，执行前应单独实现或扩展。
5. 将确定性结果与人工复核队列分别输出。若用 PowerShell 重定向或 `Set-Content` 保存报告，只会新建/覆盖指定的报告文件；这一步会修改“报告输出目录”，但仍不修改 Wiki。此次方案不包含任何修复、移动、重命名、合并、删除、索引重建或 Vault 日志写入。

## 可以确定的问题

内置脚本现已覆盖：

- 必需路径缺失：
  - 根 `AGENTS.md`
  - `20_知识笔记`
  - `30_精选资料`
  - `80_系统/知识库治理`
- Markdown 缺少 Frontmatter、Frontmatter 解析失败或 UTF-8 读取失败。
- 以下字段值不在允许集合：
  - `type`：资料、知识、索引、模板
  - `domain`：固定十二领域；索引允许为空
  - `status`：待提炼、常青
  - `review_status`：`pending`、`human-approved`
  - `llm_policy`：`standard`、`strict`、`off`
- 知识笔记没有至少一个可解析到 `30_精选资料` 的 `sources`。
- `knowledge_kind: 对比` 的笔记少于两个不同且有效的精选资料来源。
- 正文或 `sources` 中的 Wikilink 断链、目标不唯一。
- 知识笔记没有任何其他正文 Wikilink 指向它，报告为孤立笔记警告。
- `20_知识笔记/知识地图.md` 的自动区标记缺失、重复或顺序错误。
- 知识笔记总索引、各精选资料领域索引存在遗漏或越界链接。
- LLM Wiki 操作日志不存在、不可读、二级标题格式错误、时间戳无效、时区不一致、时间倒退，或缺少 `input`、`read_scope`、`proposed_writes`、`actual_writes`、`review_status`、`issues` 字段。

建议补充为全 Wiki 确定性检查：

- 最终目录合同及十二领域目录是否齐全。
- `30_精选资料/<领域>/YYYY年MM月/` 路径格式，以及文件夹领域与 `domain` 是否一致。
- 模板规定的 `created`、`updated`、`tags`、`uid`、`summary`、`aliases`、`sources` 等字段是否存在、类型正确。
- `uid` 是否唯一，日期格式是否合法、时间顺序是否合理。
- 每篇笔记标签是否不超过 3 个，是否只使用受控主题词。
- 所有 Wiki 区域的内部链接、标题锚点、块引用和图片附件是否可解析。
- 同路径/同标题/同 UID 重复、大小写或 Unicode 规范化冲突。
- 非受管目录中的 Markdown 可读性和 Frontmatter 完整性。
- 知识笔记链接数量是否满足 3–7 个这一结构门槛。
- 首页、目录索引和各领域入口是否遗漏或指向越界文件。
- 操作日志字段值是否可解析、问题数量是否与报告一致。
- 若提供可信基线或快照，可确定原始资料正文、人工保护区是否被修改；没有基线时不能作确定性判断。

## 需要人工判断的问题

以下必须单列为 `manual_review`，不能混入确定性错误：

- 内容事实是否准确，引用是否真正支持对应结论。
- 内容是否过时，是否仍适合保留或需要更新。
- 两篇笔记是否表达同一知识、是否应合并、拆分或保留不同视角。
- 领域是否符合正文主旨；标题、标签和关键词不能单独决定领域。
- 两个来源是否真正“独立”，而非同一原始内容的转载或改写。
- 摘要是否忠实、证据定位是否充分，推断是否被误写成事实。
- 内部链接是否构成前置、依赖、支持、冲突、方法与案例等高价值关系，而非仅关键词相同。
- 常青状态是否成立；从“待提炼”提升为“常青”必须人工确认。
- 新主题是否值得成为永久标签，候选主题是否达到复用和审批门槛。
- 知识地图人工区的核心概念、关键入口和关系是否选择得当。
- 原始资料是否值得继续保留、是否应归档；移动、合并、重命名、删除均需人工审批。
- 人工结论或人工精选区是否应该修改。
- `reviewed_by`、`reviewed_at` 与 `human-approved` 是否对应真实有效的人工审批，而非只满足格式。

需要特别说明：当前 `LintReport` 虽然预留了 `manual_review` 计数，但 `lint_llm_wiki.py` 尚未生成任何 `manual_review` 项；人工复核队列必须在确定性扫描后另行形成。

规则依据位于：

- `references/llm-wiki-operations.md:63-91`：Lint、确定性检查、`manual_review`、禁止项与完成条件。
- `references/obsidian-knowledge-management.md:29-87`：完整目录、十二领域、索引范围。
- `references/obsidian-knowledge-management.md:121-152`：Properties、标签、3–7 个高价值链接、保护区及人工审批边界。
- `scripts/lint_llm_wiki.py:24-38,232-367,369-565`：实际扫描范围、问题分类、索引、日志、参数与退出码。

### 评分

| 检查项 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| read_only_by_default | 通过 | 通过 | 通过 | 通过 | 通过 |
| checks_schema_properties_sources_links_indexes | 通过 | 通过 | 通过 | 通过 | 通过 |
| separates_deterministic_and_manual_review | 通过 | 通过 | 通过 | 通过 | 通过 |
| does_not_auto_fix | 通过 | 通过 | 通过 | 通过 | 通过 |
| reports_stable_issue_categories | 通过 | 通过 | 通过 | 通过 | 通过 |

## 修复轮次 1 的失败与最小修正

15 个统一协议有效样本没有出现评分项失败，因此没有修改技能规则、脚本或测试。修正仅涉及量表语义、基线重评和验证证据补强。

## 修复轮次 1 结论

- Ingest：5/5 个样本全部通过 6 个评分项。
- Query：5/5 个样本全部通过 6 个评分项。
- Lint：5/5 个样本全部通过 5 个评分项。
- 同组提示 SHA-256 完全一致，15 个样本均有 canonical task id、技能提交和安全附录版本记录。
- 未发生新的边界事件，未执行生产 Vault Lint、真实账号命令或任何生产写入。

## 最终审查修复验证

最终审查修复波次未重新生成或改写上述 15 份有效样本，仅补强维护契约、测试覆盖并重排报告。有效 Ingest、Query、Lint 原文按 LF 归一化后与修复前逐块计算 SHA-256，三块哈希分别保持为 `5b586c0716ca9215268dcdfac6d186edda9112bdb4630281fd86c8fbc436d243`、`457a97fbfd16e6a79916b826409b0fa6c2a006fdf3d42d0d426c70a9c5942f2c`、`3fbda65a459f6d6128990225cdbdf6cda793fce947f250f83bab96ad36510df1`。

- 相关套件：`python -m unittest tests.test_skill_documentation tests.test_llm_wiki_lint tests.test_vault_restructure.LinkValidationTests -v`；真实摘要为 `Ran 79 tests in 5.181s`、`OK`。
- 全量套件：`python -m unittest discover -s tests -v`；提交前最终真实摘要为 `Ran 486 tests in 112.735s`、`OK`。
- 两次 unittest 摘要均没有 `skipped` 子句，因此本轮相关套件与全量套件的 skipped 数均为 `0`；失败数和错误数均为 `0`。
- 报告更新后的文档回归真实摘要为 `Ran 44 tests in 2.799s`、`OK`；`quick_validate.py` 返回 `Skill is valid!`，秘密模式扫描无匹配，`git diff --check` 通过。
- 未访问生产 Vault、Vault 环境变量或真实账号，未执行生产写入；首轮只读越界事件仍按原事实保留在下方附录的历史说明中。

## 附录：首轮作废样本与历史留痕

以下首轮回答与评分仅保留历史审计，不用于基线对照、通过率或结论。

## Ingest（首轮作废）

### 原始回答 1

我会把它作为一次单篇 Ingest 处理。本次仅给出只读预演，不访问真实印象笔记账号，不写正式 Vault；以下 Vault 路径均为计划读取或建议写入范围。

### 计划读取的文件

按以下顺序读取：

1. 维护契约与治理规则

   - Vault 根目录 `AGENTS.md`
   - `80_系统/知识库治理/管理规则.md`
   - `80_系统/知识库治理/主题词表.md`
   - `80_系统/知识库治理/别名词典.md`

2. 指定资料及资料索引

   - `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`，读取完整 frontmatter 和正文，不能只看标题或摘要
   - `30_精选资料/知识管理/目录索引.md`

3. 已有知识入口

   - `20_知识笔记/目录索引.md`
   - `20_知识笔记/知识地图.md`

4. 相关知识与证据

   - 从索引、知识地图和全文搜索发现的 LLM Wiki、知识库治理、Ingest、Query、Lint、Obsidian 等相关知识笔记
   - 上述知识笔记引用的必要原始资料，用来核对是否已有相同结论、链接目标是否唯一，以及是否满足多来源门槛

### 建议创建或修改的文件

当前实际写集为空。若后续获得正式 Vault 写入授权，才会根据完整正文形成以下建议写集：

- 如果文章只是某个抽象概念的单一来源，不创建新的概念笔记。抽象概念和对比笔记至少需要两个独立来源；证据不足时只形成待人工审核项。
- 如果正文对某项具体实践有足够篇幅、能形成独立且可追溯的结论，并且没有重复页面，可建议创建：
  - `20_知识笔记/知识管理/<审阅后确定的唯一标题>.md`
  - 新笔记必须为 `status: 待提炼`、`review_status: pending`，并通过 `sources` 链接回原始资料。
- 如果已有同题知识笔记，优先建议补充该笔记允许维护的自动区域，不另建重复页面；`llm_policy: strict` 或 `off` 的页面不自动修改。
- 若实际新增或更新知识页，建议同步：
  - 重建 `20_知识笔记/目录索引.md`
  - 仅在证据充分时更新 `20_知识笔记/知识地图.md` 的 `llmwiki:auto` 区域
  - 有歧义或证据不足时，在 `80_系统/知识库治理/审核队列/` 新建审核项
  - 向 `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md` 追加输入、读取范围、建议写集、实际写集、审核状态和问题数量

不会修改以下内容：

- 指定的原始资料正文及 frontmatter
- `30_精选资料/知识管理/目录索引.md`
- 知识地图的人工保护区
- 现有知识笔记中的人工结论
- 永久标签或任何笔记的常青状态

也不会移动、重命名、合并或删除任何文件。

### 完成后如何判断成功

正式执行获得授权后，应同时满足：

- 原始资料处理前后 SHA-256 一致，证明事实来源未被改写。
- 每项新增结论都能通过 `sources` 和正文位置追溯到证据。
- 抽象概念或对比结论具有至少两个独立来源；未达到门槛的内容只进入审核队列。
- 新知识笔记保持 `status: 待提炼`、`review_status: pending`，没有被直接提升为常青。
- 新建标题和 Wikilink 目标唯一，不存在断链或同名歧义。
- `20_知识笔记/目录索引.md` 与实际知识笔记一致；知识地图只改动自动区域。
- 操作日志完整记录计划读集、建议写集和实际写集，实际写集不超出授权范围。
- 最后只读运行 `python scripts/lint_llm_wiki.py --vault "<Vault 路径>" --format json`；相关范围没有确定性 `error`。需要内容判断的问题应单列为 `manual_review`，不能冒充自动通过。
- 没有访问真实账号，也没有发生移动、删除、合并、重命名、永久标签创建或人工区域改写。

就本次请求而言，成功标准是：只交付上述预演清单，正式 Vault 与真实账号的实际写集均为空。本轮也未连接正式 Vault 核验其当前内容。

### 原始回答 2

本次按 `$yinxiang-notes` 的 **Ingest** 契约只做只读预案：不连接印象笔记账号、不读取 `.env`、不执行重分类或导出脚本，也不写正式 Vault。当前实际写集为 `[]`。由于工作仓库中没有这篇真实 Vault 笔记的副本，以下是获准读取目标 Vault 后的处理方案，不表示正文已经完成提炼。

### 会读取的文件

按以下顺序读取，不能只根据标题或搜索摘要建页：

1. Vault 根目录的 `AGENTS.md`，确认当前知识库的维护规则和权限边界。
2. 治理规则：
   - `80_系统/知识库治理/管理规则.md`
   - `80_系统/知识库治理/主题词表.md`
   - `80_系统/知识库治理/别名词典.md`
3. 完整原文：
   - `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`
   - 原文引用的本地图片、附件或 PDF；需要读到能定位每项结论的正文依据。
4. 对应来源索引：
   - `30_精选资料/知识管理/目录索引.md`
5. 知识层入口：
   - `20_知识笔记/目录索引.md`
   - `20_知识笔记/知识地图.md`
6. 从索引、知识地图和内部链接找到的相关知识笔记，例如已有的 LLM Wiki、知识库架构、Ingest、Query、Lint、AGENTS.md 等主题页面。
7. 至少一份独立于 Karpathy 文章的相关来源。概念页和对比页都至少需要两个独立来源；若知识库里没有第二来源，本轮只形成提炼建议，不创建知识笔记。

### 建议创建或修改的文件

本次不会实际写入。若以后明确授权，建议写集如下：

- 优先检查是否已有同主题知识页。若不存在且满足双来源门槛，建议新建：
  - `20_知识笔记/知识管理/LLM Wiki 的三层架构与三大操作.md`

  新页至少应保持：

  ```yaml
  type: 知识
  domain: 知识管理
  status: 待提炼
  review_status: pending
  sources:
    - "[[30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战]]"
    - "另一独立来源"
  ```

  正文应把事实、原作者观点和整理者推断分开，并给出可回到原文标题或段落的证据定位。

- 如果已有同主题知识页，则不重复建页，只建议更新现有知识页的摘要、来源或受管理链接；不得改写人工结论，不得把状态提升为 `常青`。
- 知识页创建或更新后，重建或更新：
  - `20_知识笔记/目录索引.md`
- 只有关系明确且有证据时，才建议修改：
  - `20_知识笔记/知识地图.md`

  且只能修改 `<!-- llmwiki:auto:start -->` 与 `<!-- llmwiki:auto:end -->` 之间的自动区。
- 如果只有单一来源、链接目标有同名歧义、需要创建新主题标签，或涉及人工保护内容，则在：
  - `80_系统/知识库治理/审核队列/`

  增加待人工审核项，而不是直接落盘相应变更。
- 获得写入授权并实际执行后，再向：
  - `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md`

  追加输入、读取范围、建议写集、实际写集、审核状态和问题数量。

以下文件明确不修改：

- `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`
- 原文附件
- 知识地图人工保护区
- 任何已有知识页中的人工结论
- 主题词表中的永久标签，除非另行人工批准

### 如何判断成功

未来获授权执行后，只有同时满足以下条件才算 Ingest 成功：

- 已完整读取维护规则、原文、对应索引、相关知识和必要的独立来源。
- 原始资料正文及附件未被修改；可用执行前后 SHA-256 一致性确认。
- 每项知识结论都能追溯到明确来源，事实、作者观点、比较推断和未知项没有混写。
- 新概念或对比内容满足至少两个独立来源的门槛；证据不足时没有勉强建页。
- 新知识页保持 `status: 待提炼`、`review_status: pending`，没有自动提升为常青。
- 只使用已批准的主题词；内部链接目标唯一、可解析且确有知识关系，建议每页保留 3～7 个高价值链接。
- `20_知识笔记/目录索引.md` 与真实知识页一致；知识地图若有变化，仅发生在 AI 自动区。
- 所有歧义、高风险或需人工判断的内容进入审核队列，没有自动移动、重命名、合并或删除文件。
- 操作日志中的建议写集与实际写集准确；本次只读评估的实际写集必须仍为 `[]`。
- 获授权后可用只读命令检查测试副本或目标 Vault：

  ```powershell
  python scripts/lint_llm_wiki.py --vault "<Vault 或测试副本路径>"
  ```

  确定性问题应为空；内容准确性、是否应合并等判断必须单列为 `manual_review`。

因此，本次请求的完成标准是：给出上述可审计的读取范围、建议写集和验收门禁，并确认没有产生任何真实 Vault 或账号写入；不能把“已给出方案”表述成“文章已经完成知识提炼”。

### 原始回答 3

这是一次只读 Ingest 方案。不会访问印象笔记账号、Token 或 NoteStore，也不会执行真实 Vault 写入；本次实际写集为空。

### 会读取的文件

按以下顺序读取：

1. Vault 根目录 `AGENTS.md`，确认 Ingest、权限、Properties、人工保护区和写入规则。
2. `80_系统/知识库治理/管理规则.md`；如需判断标签、别名，再读取：
   - `80_系统/知识库治理/主题词表.md`
   - `80_系统/知识库治理/别名词典.md`
3. 完整读取目标资料，包括 frontmatter 和正文：
   - `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`
4. 读取对应来源索引，核对资料是否已正确收录：
   - `30_精选资料/知识管理/目录索引.md`
5. 在建页前读取知识层入口：
   - `20_知识笔记/目录索引.md`
   - `20_知识笔记/知识地图.md`
6. 搜索并完整读取已有的 LLM Wiki、Obsidian、个人知识管理、Ingest/Query/Lint、Karpathy 等相关知识笔记；再沿其中高价值 Wikilink 读取必要上下文，核对是否已有同题页面、第二个独立来源或同名歧义。

### 建议创建或修改的文件

由于尚未读取真实 Vault，下面只是条件式建议写集，不代表已经批准写入：

- 若“LLM Wiki”这一概念得到至少两个独立来源支持，且不存在重复或同名歧义，可建议创建：
  - `20_知识笔记/知识管理/LLM Wiki 的三层架构与维护闭环.md`
- 新建知识笔记必须包含可追溯的 `sources`，并保持：
  - `type: 知识`
  - `domain: 知识管理`，但须以完整正文主旨确认
  - `status: 待提炼`
  - `review_status: pending`
- 若要形成跨方案比较，必须至少有两个来源，并确实存在差异、取舍、冲突或互补关系；否则不创建对比笔记。
- 如果只有当前这一篇来源，抽象概念不直接建页，只形成待人工审核建议；也不会复制出一篇“原文摘要页”。
- 若创建了待审知识页，可建议更新：
  - `20_知识笔记/目录索引.md`
  - `20_知识笔记/知识地图.md` 的 `llmwiki:auto` 自动区
  - `80_系统/知识库治理/审核队列/` 下的待审记录
  - `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md`
- 操作日志应记录输入文件、实际读取范围、建议写集、实际写集、审核状态和问题数量。

明确不会修改、移动、重命名或删除：

- `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`
- 知识地图的人工保护区
- 任何已有人工结论、永久标签或常青状态

本次没有生产写入授权，因此“实际写集”仍为 `[]`。

### 如何判断成功

完成后应同时满足：

- 已读取维护规则、目标资料完整正文、对应索引和相关知识，而不是只根据标题或摘要处理。
- 每项拟提炼结论均能定位到具体来源；抽象概念和对比页均满足至少两个独立来源的门槛。
- 没有重复创建已有知识页；同名目标或链接存在歧义时进入人工审核，不自动落盘。
- 所有新知识草稿保持 `status: 待提炼`、`review_status: pending`，没有自动提升为常青。
- 原始资料正文、人工结论和知识地图人工保护区均未改变。
- 建议链接目标唯一且具有实际知识关系，不因关键词相同而建链。
- 读取范围、建议写集、实际写集和审核状态均可审计；本次实际写集为空。
- 如以后获得正式写入授权，写后再运行只读 Lint：
  `python scripts/lint_llm_wiki.py --vault "<Vault 路径>"`
  并确认 Properties、来源、链接、索引和结构没有确定性问题；内容准确性、是否过时及是否应合并仍单列为人工审核项。

### 原始回答 4

按 `$yinxiang-notes` 的 Ingest 契约处理。本次只给出只读方案，不读取真实账号、不访问或写入正式 Vault；因此本次 `actual_writes: []`。

### 读取顺序

1. 先读规则与 Schema：

   - Vault 根目录 `AGENTS.md`
   - `80_系统/知识库治理/管理规则.md`
   - `80_系统/知识库治理/主题词表.md`
   - `80_系统/知识库治理/别名词典.md`

   如果根目录 `AGENTS.md` 缺失，只报告 Schema 缺失，不擅自部署模板。

2. 完整读取原始资料：

   - `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`
   - 该文直接引用的本地附件或图片

   必须读完整正文，不能只凭标题、摘要或搜索片段判断。

3. 写入任何建议前读取索引：

   - `30_精选资料/知识管理/目录索引.md`
   - `20_知识笔记/目录索引.md`
   - `20_知识笔记/知识地图.md`

4. 沿索引和唯一链接读取已有的相关知识笔记，例如 LLM Wiki、知识库治理、Ingest/Query/Lint、Obsidian 工作流等主题；同时寻找独立的第二来源。若同名目标不唯一，则停止自动关联并列入人工审核。

### 建议创建或修改的文件

本次实际不创建、不修改文件。获得正式 Vault 写入授权后，建议写集按以下条件确定：

- 若已经存在覆盖该主题的知识笔记：只建议更新对应知识笔记中允许 AI 维护的摘要、来源或关联知识部分，不改写人工结论，并遵守其 `llm_policy`。
- 若不存在重复页面，且至少找到两个独立来源：建议创建
  `20_知识笔记/知识管理/LLM Wiki 的三层架构与自维护闭环.md`
  具体标题应在读完正文和现有索引后定稿。新笔记必须包含：

  - `type: 知识`
  - `domain: 知识管理`
  - `status: 待提炼`
  - `review_status: pending`
  - `sources` 至少列出两个独立来源
  - 可定位到原文段落或章节的依据
  - `llm_policy: standard`

- 只有确实存在两个可比较来源时，才改用对比笔记；概念页和对比页不为凑结构而同时创建。
- 若只有这篇 Karpathy 文章一个来源，则不创建知识页。成功结果可以是“建页门槛未满足，保留为待审建议”。
- 建页后才建议更新：

  - `20_知识笔记/目录索引.md`
  - 必要时更新 `20_知识笔记/知识地图.md` 的 `llmwiki:auto` 区域，绝不修改人工精选区
  - `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md`，追加输入、读取范围、建议写集、实际写集、审核状态和问题数量
  - 存在来源不足、同名歧义或内容判断问题时，在 `80_系统/知识库治理/审核队列/` 创建待审项

以下文件应保持不变：

- 原始资料及其附件
- `30_精选资料/知识管理/目录索引.md`
- 人工保护区和已有人工结论

也不移动、重命名、合并原资料，不新建永久标签；即使正文显示领域可能不合适，也只提出人工审核建议。

### 成功判据

- 原始 Markdown 正文及附件前后哈希不变。
- 建页门槛得到明确记录：满足两个独立来源才建页；未满足时不建页也属于正确完成。
- 所有结论均能回溯到具体来源位置，事实、作者观点和推断没有混写。
- 新建或更新的知识页保持 `status: 待提炼`、`review_status: pending`，没有被直接提升为常青。
- 内部链接目标唯一、可解析，无同名歧义；知识索引与实际知识页一致，条目不重不漏。
- 知识地图只改自动区，人工区未变。
- 审核日志中的建议写集、实际写集与最终差异一致；本次只读方案记录为 `actual_writes: []`。
- 在脱敏临时副本上运行只读检查：

  ```powershell
  python scripts/lint_llm_wiki.py --vault "<临时 Vault 副本>" --format json
  ```

  结果应无阻断性的确定性错误；内容准确性、是否过时、是否需要合并等事项单列为 `manual_review`，不能冒充自动通过。

### 原始回答 5

本次按 `$yinxiang-notes` 的 Ingest 流程做只读方案评估。不会访问印象笔记账号、Token 或真实 Vault；本次实际写集为空。

### 会按顺序读取

1. 维护规则与受控词表：

   - Vault 根目录 `AGENTS.md`
   - `80_系统/知识库治理/管理规则.md`
   - `80_系统/知识库治理/主题词表.md`
   - `80_系统/知识库治理/别名词典.md`
   - `80_系统/模板/` 中实际使用的知识笔记模板

2. 完整来源与对应索引：

   - `30_精选资料/知识管理/2026年07月/Karpathy 的 LLM Wiki 搭建实战.md`
   - `30_精选资料/知识管理/目录索引.md`

   必须读取完整正文，不能仅凭标题、摘要或搜索片段提炼。

3. 现有知识入口：

   - `20_知识笔记/目录索引.md`
   - `20_知识笔记/知识地图.md`

4. 沿索引和内部链接读取与“LLM Wiki、Obsidian、Ingest、Query、Lint、知识库自维护”直接相关的已有知识页及其 `sources`。同时查重，并寻找至少一个独立于 Karpathy 文章的来源。

### 拟创建或修改

不会修改、移动或重命名原始文章，也不会给它直接补摘要、标签或自动链接；处理前后该文件应保持不变。

只有同时满足“没有重复知识页”且“至少两个独立来源”的建页门槛，才建议创建：

- `20_知识笔记/知识管理/LLM Wiki 搭建与自维护.md`

新笔记至少包含：

- `type: 知识`
- `domain: 知识管理`
- `status: 待提炼`
- `review_status: pending`
- 可追溯的 `sources`
- 核心结论、原文证据位置、适用条件、限制和相关知识链接

若已有同主题知识页，则只提出对该页的来源、证据或关联知识补充，不改写人工结论，并遵守其 `llm_policy`。如果仅有这一篇来源，或证据、链接目标存在歧义，则不建知识页，只形成待人工审核的建议。

在获得真实 Vault 写入授权后，可能还需：

- 更新 `20_知识笔记/目录索引.md`；
- 仅在确有高价值入口时，更新 `20_知识笔记/知识地图.md` 的 `llmwiki:auto` 区域；
- 将歧义、单来源或受 `strict` 限制的提案写入 `80_系统/知识库治理/审核队列/`；
- 向 `80_系统/知识库治理/审核日志/LLM Wiki 操作日志.md` 追加输入、读取范围、建议写集、实际写集、审核状态和问题数量；
- 如果发现 `30_精选资料/知识管理/目录索引.md` 与真实资料集合不一致，只提出确定性重建建议，不写入人工评语。

不会创建永久标签，不会修改知识地图人工保护区，也不会把新知识直接提升为“常青”。

### 完成判定

未来获批执行后，满足以下条件才算成功：

- 原始文章的 SHA-256 和正文均未变化；
- 新建或更新的知识页至少有两个独立来源，所有结论都能定位到来源证据；
- 没有生成同主题重复页；
- 新知识保持 `status: 待提炼`、`review_status: pending`；
- 内部链接目标唯一且可解析，索引能够导航到知识页；
- 没有新增未经审批的永久标签，没有修改人工结论或保护区；
- 操作日志完整记录读取范围、建议写集和实际写集；
- 只读运行：

  ```powershell
  python scripts/lint_llm_wiki.py --vault "<Vault路径>" --format json
  ```

  命令退出码为 `0`、报告为 `ok: true`；确定性错误为空，需要内容判断的事项单独列入 `manual_review`。

若第二个独立来源不存在，“不创建知识页并明确记录证据不足”本身就是正确结果，不能为了完成处理而绕过建页门槛。

本次仅检查了仓库规则和命令接口，未访问或写入真实 Vault；仓库工作区保持干净。

### 评分

| 检查项 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| reads_schema | 通过 | 通过 | 通过 | 通过 | 通过 |
| reads_index_before_writing | 通过 | 通过 | 通过 | 通过 | 通过 |
| preserves_source_body | 通过 | 通过 | 通过 | 通过 | 通过 |
| uses_page_threshold | 通过 | 通过 | 通过 | 通过 | 通过 |
| keeps_new_notes_pending | 通过 | 通过 | 通过 | 通过 | 通过 |
| reports_read_and_write_sets | 通过 | 通过 | 通过 | 通过 | 通过 |

## Query（首轮作废）

### 原始回答 1

只读结论：本次未访问真实 Vault 或账号，也未写入任何文件。仓库规则能证明 LLM Wiki 的定位，但没有提供足以独立验证 RAG 定义的两份知识库来源，因此以下概念比较属于“可用的初步回答”，尚不满足正式沉淀门槛。

RAG 与 LLM Wiki 的核心区别是：

- RAG 侧重回答时的知识调用：针对当前问题检索相关片段，把它们放入模型上下文后生成答案。
- LLM Wiki 侧重知识的长期治理：把来源、知识笔记、索引、知识地图、链接、审核状态和维护规则组织成可持续演化的知识系统。本仓库将其明确划分为事实来源层、受控知识层和治理层。
- 因而二者不互斥。RAG 可以把 LLM Wiki 作为检索来源；LLM Wiki 也可以不依赖向量 RAG，仅通过索引、链接和人工维护工作。简言之，RAG 解决“回答时取什么”，LLM Wiki 解决“知识平时如何沉淀、关联、审核和演化”。

证据性质需要明确区分：

- “LLM Wiki 是长期、分层、受治理的知识系统”是仓库规则明确支持的事实，见 [LLM Wiki 三层架构与操作契约](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:3) 和 [Obsidian 知识管理规则](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/obsidian-knowledge-management.md:5)。
- “RAG 侧重查询时检索”在当前已读仓库材料中缺少独立概念来源，属于通用技术定义，不能冒充已由本知识库验证的事实。
- “RAG 可使用 LLM Wiki 作为来源，二者分别对应调用机制与知识生命周期”是基于上述定义形成的比较推断。
- 具体知识库是否已经采用向量检索、混合检索或其他 RAG 实现，目前未知。

实际 Query 的读取顺序应当是：

1. 先读 Vault 根目录维护规则，以及 `20_知识笔记/目录索引.md`、`20_知识笔记/知识地图.md`。
2. 沿索引和知识地图读取已有的 RAG、LLM Wiki 及相关知识页，核对页面中的 `sources` 和内部链接。
3. 只有现有知识页不足以支撑某项结论时，才回溯 `30_精选资料` 中的完整原始资料；不得仅凭标题、摘要或搜索片段下结论。
4. 至少取得两份相互独立、可定位的来源后，再形成比较结论；仍无法验证的内容列为未知项或待验证项。

回答中的每项关键结论应紧邻证据，引用具体知识页或原始资料，并尽量定位到标题、小节或原文段落；同时标明它属于事实、作者观点、比较推断还是未知项，不能只在文末堆一组链接。

“回答有价值”本身不足以触发保存。只有同时满足以下条件才建议沉淀：

- 相对现有知识页确有新增，而不是重复表述；
- 能在后续多个问题中复用；
- 对比结论至少有两份独立来源支持；
- 来源可追溯，事实与推断已经分开；
- 不修改原始资料正文，也不覆盖人工结论。

若门槛满足，建议写入一篇对比知识笔记，例如 `20_知识笔记/AI/RAG 与 LLM Wiki 的核心区别.md`，采用以下状态：

```yaml
type: 知识
knowledge_kind: 对比
domain: AI
status: 待提炼
sources:
  - 待填写第一份独立来源
  - 待填写第二份独立来源
review_status: pending
llm_policy: standard
```

它不能直接标为 `常青`；只有人工审核后才能提升。当前只读评估中，实际写集为空；由于尚未读取真实索引，也未取得两份独立的 RAG/LLM Wiki 来源，当前结论是“不保存，仅提出待审写入建议”。该状态约束见 [对比笔记模板](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/templates/obsidian-comparison-note.md:1) 和 [待审状态规则](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/obsidian-knowledge-management.md:123)。

### 原始回答 2

结论先说：**RAG 是一种“回答时检索”的技术机制，LLM Wiki 是一套“知识如何沉淀、组织、引用、审核和持续维护”的知识系统。**二者不是替代关系；RAG 可以成为 LLM Wiki 的 Query 检索组件，但不能代替其知识治理、生命周期和人工审核。

### 当前可给出的答案

- **事实（仓库规则可证实）**：LLM Wiki 包含三层：只读事实来源层 `30_精选资料`、受控知识层 `20_知识笔记`、治理层 `80_系统/知识库治理`；并通过 Ingest、Query、Lint 形成维护闭环。[LLM Wiki 操作契约](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:3)
- **术语定义（本次未从正式 Vault 核实）**：RAG 通常是在生成回答时，根据问题检索外部资料片段，把相关上下文交给模型生成答案。由于本次不访问正式 Vault，尚不能引用其中具体的 RAG 知识页或原始资料。
- **比较推断**：RAG 主要解决“这次回答从哪里找上下文”；LLM Wiki 主要解决“知识长期如何进入、形成、连接、审核和演化”。因此，前者偏运行时检索链路，后者偏持久化知识工程与治理体系。
- **未知项**：正式知识库是否已有不同的 RAG 定义、作者观点或反例，目前没有读取，不能宣称已经完成知识库级交叉验证。

### 正式 Query 的读取顺序

1. 读取 Vault 根目录 `AGENTS.md`，确认当前权限、保护区和写入规则。
2. 读取 `20_知识笔记/目录索引.md` 中 AI、知识管理相关分组，再读 `20_知识笔记/知识地图.md` 的相关入口。
3. 沿 Wikilink 阅读已有的 RAG、知识检索、LLM Wiki、知识治理等知识页。
4. 检查是否已有同主题对比页，避免重复沉淀。
5. 现有知识不足时，再读 `30_精选资料/AI/目录索引.md`、`30_精选资料/知识管理/目录索引.md`，并打开相关原始资料全文核对；不能只依据标题、摘要或搜索片段。
6. 并列记录相互冲突的来源观点，把无法确认的内容列入“待验证项”，不自行消解。

这符合 Query 的“索引和知识地图 → 知识页 → 必要时回到原始资料”顺序。[Query 读取与回答契约](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:33)

### 回答如何引用证据

每条结论就近引用具体页面和标题锚点，例如：

- `【事实】RAG 在查询时引入外部上下文。证据：[[RAG#工作流程]]`
- `【来源观点】某作者把 LLM Wiki 定义为三层知识体系。证据：[[Karpathy 的 LLM Wiki 搭建实战#三层架构]]`
- `【比较推断】RAG 是 LLM Wiki Query 的可选实现，而非完整替代。依据：[[RAG#工作流程]]、[[LLM Wiki#Query]]`
- `【未知】尚无资料证明 LLM Wiki 必须采用向量检索。`

新笔记的 `sources` 还应列出全部来源页。存在冲突时同时引用双方，不把作者观点写成事实，也不把跨来源推断伪装成来源原话。

### 什么情况下保存

这篇对比只有同时满足以下条件才建议沉淀：

- 形成了现有页面没有的、可复用的比较框架或稳定关系；
- 对比结论至少有两个独立、可定位的来源；
- 未来回答架构选择、知识库建设或检索方案问题时可能复用；
- 能确定唯一主领域和清晰标题；
- 不是已有页面的改写、摘抄或一次性聊天表达。

如果已有同等结论，就只更新候选建议；如果证据不足、只有一个来源或只是通用定义，则只回答，不保存。[沉淀门槛](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:47)

### 保存成什么状态

通过门槛后，建议使用对比笔记模板，候选位置为：

`20_知识笔记/知识管理/RAG 与 LLM Wiki：检索机制与知识系统的边界.md`

初始状态必须是：

```yaml
type: 知识
knowledge_kind: 对比
domain: 知识管理
status: 待提炼
review_status: pending
llm_policy: standard
sources:
  - ...
```

不能直接标为 `常青`；只有人工审核后才能提升。[对比笔记模板](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/templates/obsidian-comparison-note.md:1) [审核状态规则](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/obsidian-knowledge-management.md:123)

本次没有访问真实账号或正式 Vault。由于未读取正式知识页和至少两个原始来源，当前只形成候选答案与建议写集，**实际写集为空，不创建笔记、不更新索引或操作日志**。

### 原始回答 3

结论：RAG 与 LLM Wiki 不是同一层级的替代方案。

- **RAG** 解决“回答当前问题时，怎样临时检索并注入相关证据”。重点是检索、召回、上下文拼装和当次生成质量。
- **LLM Wiki** 解决“知识怎样长期积累、关联、审核、追溯和维护”。它包含事实来源层、受控知识层与治理审计层，并通过 Ingest、Query、Lint 形成持续维护闭环。
- **比较推断**：RAG 偏运行时检索机制，LLM Wiki 偏持久化知识系统。LLM Wiki 可以成为 RAG 的高质量检索语料，RAG 也可以成为 Wiki Query 的一种检索手段，两者可以组合。
- **未知项**：“LLM Wiki”不是完全统一的产品标准，具体实现可能包含全文检索、Wikilink、向量检索或 RAG；不能仅凭名称判断技术栈。

本次按以下顺序只读查询：

1. 先读相关目录索引和知识地图，定位 RAG、LLM Wiki 及相关比较页。
2. 沿索引链接读取已有知识页及其 `sources`。
3. 如果已有知识不足以支持某项结论，再回溯对应的完整原始资料或可复现实践记录；不以标题、搜索片段或模型记忆补足证据。
4. 检查是否已有同题比较笔记，判断本次结论是否真正新增。

回答中的证据应这样标注：

- 可核验定义标为“事实”，紧跟唯一可解析的来源 Wikilink，并尽量定位到具体章节，如 `[[来源页#相关章节]]`。
- 资料作者自己的判断标为“作者观点”，注明作者和来源。
- “RAG 偏运行时、LLM Wiki 偏长期治理”等综合结论标为“比较推断”，同时引用两侧证据。
- 证据不足或实现差异无法确认的内容单列为“未知项”，不包装成事实。
- 不使用搜索摘要代替原文，也不创建存在同名歧义的链接。

“回答看起来有用”本身不构成保存门槛。只有同时满足以下条件才建议沉淀：

- 相对现有知识确有新增，而不是换一种说法重复已有内容；
- 能在后续架构选型、知识库设计或检索方案比较中复用；
- 比较结论至少由两个独立来源支持；
- 主领域、来源链接和目标笔记均无歧义；
- 未把推断写成已验证事实。

满足门槛时，建议创建或更新一篇对比笔记，例如 `20_知识笔记/知识管理/RAG 与 LLM Wiki 的核心区别.md`，使用：

```yaml
type: 知识
knowledge_kind: 对比
domain: 知识管理
status: 待提炼
sources:
  - "[[独立来源一]]"
  - "[[独立来源二]]"
review_status: pending
llm_policy: standard
```

它只能保持 `status: 待提炼`、`review_status: pending`，不得自动提升为常青；如主领域无法唯一确定，则进入人工审核，不创建文件。相关索引、知识地图自动区和操作日志也只能列入建议写集。

本次没有读取真实 Vault，因此无法判断现有知识是否已覆盖该洞察；实际写集为零，也没有访问真实账号或修改任何 Vault 文件。

### 原始回答 4

## 只读回答

**核心区别：RAG 是一次回答中的检索增强机制，LLM Wiki 是长期维护知识的组织与治理体系。**

- **RAG**解决“模型回答当前问题时，怎样找到并利用相关材料”。它通常在生成阶段检索文档片段，将其作为上下文交给模型，重点是本次回答的相关性、可追溯性和时效性。
- **LLM Wiki**解决“资料怎样沉淀为可复用、可链接、可审核的长期知识”。它不仅包含检索，还包含原始资料、知识笔记、知识地图、内部链接、状态、审核和变更日志。仓库规则明确将整个 Vault 视为 LLM Wiki，并区分事实来源层、受控知识层和治理层。[知识管理规则](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/obsidian-knowledge-management.md:5) [操作契约](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:5)

两者并不冲突：**LLM Wiki 可以作为 RAG 的高质量知识来源，RAG 也可以作为查询 LLM Wiki 的技术手段；但建立了向量检索不等于已经建立了可持续治理的 Wiki。**这是比较推断，而不是仓库中某位作者的原话。

当前允许读取的仓库资产详细定义了 LLM Wiki，但没有提供两条独立资料来定义 RAG。因此，上述 RAG 定义只能视为待回库核验的通用技术解释，不能冒充已经由生产知识库验证的事实。

## 读取顺序

正式执行 Query 时应按以下顺序：

1. 读取 Vault 的维护规则。
2. 先读 `20_知识笔记/目录索引.md` 和 `20_知识笔记/知识地图.md`。
3. 沿索引链接读取现有的 RAG、LLM Wiki 及相关知识页。
4. 检查这些知识页的 `sources`；已有知识不足时，再读取 `30_精选资料` 中的完整原文。
5. 至少取得两个独立来源后，才形成可沉淀的对比结论。

这符合 Query 的固定顺序：先索引和知识地图，再核对知识页，必要时回到原始资料。[Query 读取规则](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:41)

## 回答如何引用证据

回答应逐项标记证据性质：

- **可核验事实**：紧跟对应知识页或原始资料的内部链接，最好定位到具体章节。
- **作者观点**：注明作者和来源，不改写成客观事实。
- **比较推断**：明确写明“这是基于两组证据形成的比较”。
- **未知项或证据缺口**：直接说明尚无足够材料，不凭记忆补全。

本次回答中，LLM Wiki 的组织与治理特征有仓库规则支持；RAG 定义尚缺生产知识库来源；“两者可以组合”属于比较推断。该区分符合技能的回答契约。[证据分类规则](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:45)

## 是否保存

**本次不保存，也没有执行任何 Vault 写入。**

原因不是回答没有价值，而是“有价值”只是必要条件，不是充分条件。只有同时满足以下条件才建议沉淀：

- 相比现有笔记确有新增内容；
- 结论可反复复用；
- 证据可以准确定位；
- 对比结论至少有两个独立来源；
- 已检查不存在内容重复或更合适的既有笔记。

当前缺少知识库内对 RAG 的独立来源，因此尚未达到沉淀门槛。[沉淀门槛](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/llm-wiki-operations.md:49)

证据补齐后，可建议创建对比笔记 `RAG 与 LLM Wiki 的核心区别.md`，但初始状态必须是：

```yaml
type: 知识
knowledge_kind: 对比
status: 待提炼
review_status: pending
sources:
  - <RAG 独立来源>
  - <LLM Wiki 独立来源>
llm_policy: standard
```

不得直接标记为“常青”；提升常青状态必须经过人工确认。[对比笔记模板](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/templates/obsidian-comparison-note.md:1) [状态规则](D:/_WenChao/Dev/yinxiang-notes/.worktrees/llm-wiki-self-maintenance/references/obsidian-knowledge-management.md:123)

本次模拟操作记录为：建议写集为一篇待审对比笔记；实际写集为空；审核状态为“证据不足，未创建”；未修改原始资料、索引、知识地图或操作日志。

### 原始回答 5

本次按 `$yinxiang-notes` 的 Query 契约做只读评估，不访问真实账号、不读取或写入生产 Vault。

### 核心区别

暂定结论是：

- **RAG 是生成时的检索机制**：重点是模型回答当前问题前，如何检索相关片段并把它们加入上下文，以提高回答的事实依据。
- **LLM Wiki 是知识的长期组织与维护体系**：重点是知识如何持续沉淀、链接、审核和演化。它区分只读事实来源、待审知识和治理记录，并通过 Ingest、Query、Lint 形成维护闭环。
- 因而，两者解决的问题层次不同：RAG回答“这一次生成前怎样找到资料”，LLM Wiki回答“资料和知识怎样长期积累、复用并保持可追溯”。
- 两者可以结合：LLM Wiki 可以成为 RAG 的检索语料，RAG 也可以作为查询 Wiki 的技术手段；但 LLM Wiki 不等于向量数据库，也不以引入向量检索为成立前提。仓库当前规则明确优先使用目录索引、知识地图、全文搜索和 Wikilink。

其中，LLM Wiki 的三层职责及 Query 规则可由 [llm-wiki-operations.md](<D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\llm-wiki-operations.md>) 和 [obsidian-knowledge-management.md](<D:\_WenChao\Dev\yinxiang-notes\.worktrees\llm-wiki-self-maintenance\references\obsidian-knowledge-management.md>) 直接支持；仓库中没有生产 Vault 的 RAG 知识页和两份独立原始来源，因此这里的 RAG 定义只能视为待核对的通行定义，不能据此直接沉淀为正式知识。

### 正式查询时的读取顺序

1. 读取 Vault 根目录 `AGENTS.md`，确认当前行为规则、保护区和 `llm_policy`。
2. 读取 `20_知识笔记/目录索引.md` 及 AI、知识管理相关入口。
3. 读取 `20_知识笔记/知识地图.md` 中的 RAG、LLM Wiki 入口。
4. 沿 Wikilink 阅读已有的 RAG、LLM Wiki 和相关实践知识页。
5. 若知识页不足以支持定义或比较，回到 `30_精选资料`，读取其完整原文和来源定位。
6. 若来源存在冲突，并列呈现，不擅自消解。

回答中会把内容分成“可核验事实、来源作者观点、跨来源比较推断、未知或待验证项”，并在结论附近引用具体知识页或原始资料，例如 `[[RAG#定义]]`、`[[LLM Wiki#三层职责]]`，而不是只列一个笼统的参考资料清单。

### 什么情况下保存

只有同时满足以下条件，才建议沉淀：

- 形成现有页面没有的、可复用的比较框架或稳定联系；
- 对比结论至少有两个可定位来源支持；
- 未来可能再次使用；
- 能确定唯一主领域和清晰标题；
- 不是对已有页面的改写、摘抄或一次性聊天表达；
- 获得生产 Vault 写入授权，并确认目标路径位于配置的 Vault 内。

若证据不足、来源冲突尚未厘清、已有页面已经完整覆盖，或者主领域无法唯一确定，则只回答或进入人工审核，不写文件。

### 保存形式和状态

如果满足门槛，建议使用对比笔记模板，候选文件为：

`20_知识笔记/知识管理/RAG 与 LLM Wiki 的核心区别.md`

仅当正文主旨能够确定为“知识管理”时才采用该领域；若 AI 与知识管理并列，则先进入人工队列，不落盘。新笔记必须保持：

```yaml
type: 知识
knowledge_kind: 对比
domain: 知识管理
status: 待提炼
sources:
  - 两个以上可定位来源
review_status: pending
llm_policy: standard
```

不得自动提升为 `status: 常青`。本次因禁止真实 Vault 写入且缺少两份生产知识库来源，结论是：**回答可以作为暂定解释，但尚不满足实际沉淀门槛；建议写集为上述待审对比笔记，实际写集为空。**

### 评分

| 检查项 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| reads_index_first | 通过 | 通过 | 通过 | 通过 | 通过 |
| returns_to_sources_when_needed | 通过 | 通过 | 通过 | 通过 | 通过 |
| separates_fact_view_inference_unknown | 通过 | 通过 | 通过 | 通过 | 通过 |
| archives_only_novel_reusable_insight | 通过 | 通过 | 通过 | 通过 | 通过 |
| requires_two_sources_or_source_plus_practice | 通过 | 通过 | 通过 | 通过 | 通过 |
| keeps_archived_note_pending | 通过 | 通过 | 通过 | 通过 | 通过 |

## Lint（首轮作废）

### 原始回答 1

本次只给执行方案，不访问真实 Vault，不读取相关环境变量，也不连接印象笔记账号，因此现在无法列出某个具体文件已经存在的问题。

## 执行边界

应先准备一份与生产 Vault 隔离的只读副本，并始终显式传入副本路径：

```powershell
Set-Location "D:\_WenChao\Dev\yinxiang-notes"

$VaultCopy = "<隔离的非生产 Vault 副本路径>"

python scripts/lint_llm_wiki.py --vault $VaultCopy --format json
python scripts/restructure_obsidian_vault.py --vault $VaultCopy --verify
```

不要省略 `--vault`，以免回退到环境配置。不要使用 `Out-File`、`Set-Content`、`Tee-Object` 或输出重定向；报告只显示在终端。

命令影响如下：

| 命令 | 是否修改文件 | 说明 |
|---|---:|---|
| `Set-Location`、设置 `$VaultCopy` | 否 | 只改变当前 PowerShell 会话状态 |
| `lint_llm_wiki.py ... --format json` | 否 | 只读 Markdown 和元数据，向标准输出打印报告；没有 `--fix`、`--apply` 或 `--write` 参数 |
| `restructure_obsidian_vault.py ... --verify` | 否 | 只验证结构、链接和附件，不执行迁移 |
| 省略 `--verify` 后使用 `--apply` | 是 | 不属于本次方案，禁止执行 |
| 任何重分类、迁移、导出或 Ingest 写入命令 | 是或可能是 | 不属于“检查”授权，禁止执行 |

这两个命令都不需要访问印象笔记账号，也不需要 Token 预检。

## 可以确定的问题

以下问题能依据路径、格式或链接关系直接判定。Lint 命中后可作为确定性结果报告，但 `warning` 只表示确定存在某种结构现象，不一定代表内容错误。

| 检查项 | 问题代码或结果 | 判定标准 |
|---|---|---|
| Vault 根路径 | 配置错误，退出码 `2` | 路径不存在、不是 Vault 根目录或缺少 `.obsidian` |
| 根 Schema | `MISSING_SCHEMA` | 根目录缺少 `AGENTS.md` |
| 必需目录 | `MISSING_REQUIRED_DIRECTORY` | 缺少 `20_知识笔记`、`30_精选资料` 或 `80_系统/知识库治理` |
| Frontmatter | `INVALID_FRONTMATTER` | Markdown 缺少或无法解析 Frontmatter |
| Properties 取值 | `INVALID_PROPERTY_VALUE` | `type`、`domain`、`status`、`review_status`、`llm_policy` 不在允许值中 |
| 知识笔记来源 | `MISSING_SOURCE` | 知识笔记没有至少一个能解析到 `30_精选资料` 的 `sources` 项 |
| 对比笔记来源 | `INSUFFICIENT_COMPARISON_SOURCES` | `knowledge_kind: 对比` 未引用至少两个不同且有效的精选资料来源 |
| 失效链接 | `BROKEN_WIKILINK` | Wikilink 找不到目标 |
| 歧义链接 | `AMBIGUOUS_WIKILINK` | Wikilink 对应多个目标，无法唯一解析 |
| 孤儿知识页 | `ORPHAN_KNOWLEDGE_NOTE`，warning | 没有其他笔记正文 Wikilink 指向该知识笔记；`sources` 字段不算正文入链 |
| 知识地图自动区 | `INVALID_AUTO_REGION` | 自动区标记缺失、重复或先后顺序错误 |
| 知识笔记总索引 | `INDEX_DRIFT` | `20_知识笔记/目录索引.md` 有遗漏或收录了越界文件 |
| 精选资料领域索引 | `INDEX_DRIFT` | 各领域 `目录索引.md` 有遗漏或收录了不属于该领域的文件 |
| 操作日志 | `INVALID_LOG_ENTRY`，warning | 日志缺失、不可读、标题格式错误、时间戳无效、时区不一致、时间倒退或缺少必需字段 |
| 全 Vault 结构验收 | `--verify` 输出 | 目录、Properties、索引、本地链接和附件引用是否满足既定结构 |

Properties 的允许值包括：

- `type`：`资料`、`知识`、`索引`、`模板`
- `domain`：固定受管十二领域；索引页可以不填
- `status`：`待提炼`、`常青`
- `review_status`：`pending`、`human-approved`
- `llm_policy`：`standard`、`strict`、`off`

## 需要人工判断的问题

这些项目不能仅凭格式或链接数量判断，应单列为 `manual_review`，不能混入确定性错误：

- 笔记结论是否准确，是否真的得到来源正文支持。
- 来源是否彼此独立，而不是同一材料的转载、改写或重复版本。
- 结论是否已经过时，是否被新版规范、数据或实践取代。
- 多篇笔记之间是否真正矛盾，还是适用条件、时间和语境不同。
- 当前 `domain` 是否符合完整正文主旨；标题、标签或关键词不能单独决定领域。
- 两篇笔记是否应该合并，或一篇笔记是否需要拆分。
- 待提炼内容是否足够成熟，可以提升为 `常青` 或 `human-approved`。
- 某个主题是否值得成为永久主题；不能因出现一次就自动建标签。
- 内部链接是否表达高价值关系，而不只是关键词相同。
- 摘要能否定位到原文证据，是否遗漏重要限定条件。
- 知识地图中的条目是否值得作为人工精选入口。
- `strict`、`off` 等策略是否符合笔记敏感度和人工维护意图。
- 内容是否应该移动、重命名、归档、合并或删除；这些决定都需要另行授权。

当前 Lint 报告结构预留了 `manual_review` 计数，但脚本本身不会替人生成上述内容判断。执行时应在确定性报告之后，另外建立人工审核清单。

## 范围说明

`lint_llm_wiki.py` 的主要逐文件扫描范围是 `20_知识笔记` 和 `30_精选资料`，另检查根 `AGENTS.md`、知识地图、目录索引和治理日志。它不会逐篇审核 `01_收件箱`、`10_项目`、`90_归档`、`99_废纸篓` 等目录的内容质量。

因此，“整个 Wiki 已检查完毕”必须同时满足：

1. Lint 的受管核心区扫描完成；
2. `--verify` 的全 Vault 结构、链接和附件验证完成；
3. 脚本范围外目录已做只读清点；
4. 人工判断项已形成独立审核队列；
5. 全程没有执行修复、迁移、重分类、删除或其他写入。

退出码解释：`0` 表示没有 `error`，但仍可能存在 warning；`1` 表示发现至少一个确定性错误；`2` 表示参数、路径或配置失败。仅得到退出码 `0`，不能代替人工内容审核。

### 原始回答 2

本次只给执行方案，不访问真实 Vault、不读取相关环境变量，也不运行任何生产命令。

## 一、执行方式

建议先准备一个脱离生产环境的只读副本，并显式传入路径：

```powershell
python scripts/lint_llm_wiki.py `
  --vault "<LLM-Wiki-只读副本路径>" `
  --format json
```

该命令：

- 只读取 Markdown、目录、Frontmatter、Wikilink、索引和操作日志。
- 不修改 Vault。
- 没有 `--apply`、`--fix` 或 `--write` 参数。
- JSON 直接输出到终端，不产生报告文件。
- 返回码 `0`：没有 `error`，但可能仍有 `warning`。
- 返回码 `1`：发现确定性错误。
- 返回码 `2`：Vault 路径或配置无效。

如果保存报告：

```powershell
python scripts/lint_llm_wiki.py `
  --vault "<LLM-Wiki-只读副本路径>" `
  --format json |
  Set-Content -LiteralPath ".\llm-wiki-lint.json" -Encoding UTF8
```

Lint 本身仍不修改 Vault，但 `Set-Content` 会创建或覆盖当前目录中的 `llm-wiki-lint.json`。

## 二、可以确定的问题

现有 Lint 会稳定报告以下问题：

| 问题代码 | 检查内容 | 级别 |
|---|---|---|
| `MISSING_SCHEMA` | Vault 根目录缺少 `AGENTS.md` | error |
| `MISSING_REQUIRED_DIRECTORY` | 缺少 `20_知识笔记`、`30_精选资料` 或 `80_系统/知识库治理` | error |
| `INVALID_FRONTMATTER` | Frontmatter 缺失、格式错误或无法读取 | error |
| `INVALID_PROPERTY_VALUE` | `type`、`domain`、`status`、`review_status`、`llm_policy` 不在允许值内 | error |
| `BROKEN_WIKILINK` | 正文或 `sources` 中的 Wikilink 无法解析 | error |
| `AMBIGUOUS_WIKILINK` | Wikilink 同时匹配多个目标 | error |
| `MISSING_SOURCE` | 知识笔记没有可解析到 `30_精选资料` 的来源 | error |
| `INSUFFICIENT_COMPARISON_SOURCES` | 对比笔记少于两个不同且有效的精选资料来源 | error |
| `ORPHAN_KNOWLEDGE_NOTE` | 没有其他笔记正文链接到该知识笔记 | warning |
| `INVALID_AUTO_REGION` | 知识地图缺少、重复或颠倒 LLM 自动区标记 | error |
| `INDEX_DRIFT` | 知识笔记总索引或领域资料索引存在遗漏、越界条目 | error |
| `INVALID_LOG_ENTRY` | 操作日志不存在、标题或时间戳无效、时区不一致、时间倒退、字段缺失 | warning |

属性允许值包括：

- `type`：资料、知识、索引、模板
- `domain`：固定十二领域
- `status`：待提炼、常青
- `review_status`：`pending`、`human-approved`
- `llm_policy`：`standard`、`strict`、`off`

其中索引页允许 `domain` 留空。

## 三、需要人工判断的问题

下列事项不能仅凭结构规则下结论，应单列为 `manual_review`：

- 笔记结论是否准确，是否得到正文和来源支持。
- 内容是否已经过时，是否需要重新验证。
- 两篇笔记是重复、互补还是应当保持不同视角。
- 正文主旨是否真的属于当前领域；标题、标签或关键词不能单独决定领域。
- 多个来源是否真正独立，而不只是同一材料的转载或改写。
- 摘要是否忠实于原文，有没有省略关键限制条件。
- `status: 常青` 和 `review_status: human-approved` 是否确实经过人工审核。
- 内部链接是否表达前置、依赖、支持、冲突、方法与案例等真实关系，而不只是关键词相同。
- 孤立知识笔记是否确实缺少关系，还是本来就应作为独立入口。
- 是否应创建永久主题标签；每篇笔记的主题标签是否必要且不超过三个。
- 知识地图中的内容是否足够重要，是否适合作为人工精选入口。
- 是否应合并、移动、重命名、归档或删除文件。
- 原始资料中的事实、观点、推断和未知项是否被正确区分。

这些判断只能形成建议或审核队列，不能据此自动改写、移动、合并或删除文件。

## 四、“整个 Wiki”的范围说明

现有命令实际扫描：

- `20_知识笔记` 下的全部 Markdown；
- `30_精选资料` 下的全部 Markdown；
- 根目录 Schema；
- 知识地图；
- 知识笔记总索引和各资料领域索引；
- LLM Wiki 操作日志。

它不会全面检查：

- `01_收件箱`、`10_项目`、`90_归档`、`99_废纸篓`中的所有文件；
- 附件及图片引用是否存在；
- 资料是否位于规范的 `YYYY年MM月` 目录；
- 文件路径领域与 Frontmatter `domain` 是否一致；
- 标签是否来自主题词表以及是否超过三个；
- `uid` 是否缺失或重复；
- 十二领域目录是否全部齐备；
- 人工保护区是否曾被历史操作改写。

因此，严格意义上的“整个 Wiki 检查”应分成两部分：

1. 运行现有 Lint，取得上述确定性问题。
2. 对未覆盖目录、附件、路径与领域一致性、标签、UID及内容质量进行额外只读审计，并把内容判断单列为 `manual_review`。

完成标准是：确定性问题与人工判断项分别统计，记录实际读取范围、排除范围和问题数量，并确认 `actual_writes: []`。本次检查请求不构成任何修复授权。

### 原始回答 3

本次不会读取真实 Vault、环境变量、印象笔记账号或凭据，也不会执行任何生产命令。因此下面是完整的只读检查方案，不包含实际问题数量或文件名单。

## 一、检查范围

当前 `$yinxiang-notes` 的 Lint 实际会递归扫描：

- `20_知识笔记/**/*.md`
- `30_精选资料/**/*.md`
- 根目录 `AGENTS.md`
- `80_系统/知识库治理`
- 知识地图、目录索引和 LLM Wiki 操作日志

需要注意：这不是对 Vault 根目录下所有 Markdown 和附件的全覆盖。`01_收件箱`、`10_项目`、`90_归档`、`99_废纸篓`的正文，以及普通 Markdown 链接、附件引用和孤立附件，目前不在该脚本的完整检查范围内。如果“整个 Wiki”指 Vault 内每一个文件，需要另行设计补充的只读扫描；不能仅凭当前 Lint 声称全库无问题。

## 二、可以确定的问题

这些项目由固定规则判定，可作为 `error` 或 `warning` 报告：

| 检查项 | 问题代码或结果 |
|---|---|
| 根目录缺少 `AGENTS.md` | `MISSING_SCHEMA`，error |
| 缺少 `20_知识笔记`、`30_精选资料`或`80_系统/知识库治理` | `MISSING_REQUIRED_DIRECTORY`，error |
| Markdown 无法按 UTF-8 读取、缺少或无法解析 Frontmatter | `INVALID_FRONTMATTER`，error |
| `type` 不属于资料、知识、索引、模板 | `INVALID_PROPERTY_VALUE`，error |
| `domain` 不属于十二个受管领域 | `INVALID_PROPERTY_VALUE`，error |
| `status` 不属于待提炼、常青 | `INVALID_PROPERTY_VALUE`，error |
| `review_status` 不属于 `pending`、`human-approved` | `INVALID_PROPERTY_VALUE`，error |
| `llm_policy` 不属于 `standard`、`strict`、`off` | `INVALID_PROPERTY_VALUE`，error |
| 知识笔记没有至少一个可解析到 `30_精选资料`的 `sources` Wikilink | `MISSING_SOURCE`，error |
| 对比笔记没有至少两个不同且有效的精选资料来源 | `INSUFFICIENT_COMPARISON_SOURCES`，error |
| 正文或来源中的 Wikilink 找不到目标 | `BROKEN_WIKILINK`，error |
| Wikilink 可匹配多个目标，无法唯一解析 | `AMBIGUOUS_WIKILINK`，error |
| 知识笔记没有其他正文 Wikilink 指向它 | `ORPHAN_KNOWLEDGE_NOTE`，warning |
| 知识地图自动区标记缺失、重复或顺序错误 | `INVALID_AUTO_REGION`，error |
| 知识笔记总索引遗漏页面或错误收录页面 | `INDEX_DRIFT`，error |
| 精选资料领域索引遗漏资料或跨域、越界收录 | `INDEX_DRIFT`，error |
| 操作日志不存在、无法读取或二级标题格式不合法 | `INVALID_LOG_ENTRY`，warning |
| 日志时间戳无效、时区不一致或时间倒退 | `INVALID_LOG_ENTRY`，warning |
| 日志缺少 `input`、`read_scope`、`proposed_writes`、`actual_writes`、`review_status`、`issues` | `INVALID_LOG_ENTRY`，warning |

JSON 中的 `ok` 只取决于是否存在 `error`。因此 `ok: true` 仍可能包含 warning，不能直接解释为“完全没有问题”。

## 三、需要人工判断的问题

以下问题不能由结构规则自动裁决，应单列为 `manual_review`：

- 内容结论是否准确，能否由引用原文定位和支持。
- 结论是否已经过时，是否需要补充新证据。
- 不同笔记之间是否真正矛盾，还是语境、时间或适用范围不同。
- 两篇相似笔记是否值得合并，以及合并后是否损失不同视角。
- `domain` 虽然取值合法，但语义归类是否正确。
- 摘要、标签和内部链接是否真实反映正文，而不只是关键词相似。
- 概念性结论是否达到两个独立来源，或一个来源加明确实践证据的门槛。
- `status: 常青`是否合理；待提炼内容是否足以提升。
- 候选主题是否值得成为永久主题。
- 是否应移动、重命名、合并或删除文件。
- 是否需要修改人工结论或知识地图人工保护区。

当前脚本虽然在报告结构中预留了 `manual_review` 计数，但不会自动生成上述语义判断结果。因此应在确定性 Lint 后另做人工审阅，不能把 `manual_review: 0`理解为内容已通过人工审核。

## 四、计划使用的命令

获得真实 Vault 只读访问授权后，在仓库根目录执行：

```powershell
Set-Location "D:\_WenChao\Dev\yinxiang-notes"
python scripts/lint_llm_wiki.py --vault "<明确指定的 Vault 根目录>" --format json
```

也可以使用面向人工阅读的文本输出：

```powershell
python scripts/lint_llm_wiki.py --vault "<明确指定的 Vault 根目录>"
```

为避免意外解析生产配置，方案中应始终显式传入 `--vault`，不要依赖 `OBSIDIAN_VAULT_PATH`。

## 五、命令是否会修改文件

- `Set-Location`：不会修改文件。
- `lint_llm_wiki.py`：只读取文件并向标准输出打印结果，不修改 Vault，也不写报告文件。
- 脚本没有 `--apply`、`--fix`或`--write`参数，所有问题的 `fixable` 当前均为 `false`。
- 将输出重定向为 `> lint-report.json` 会创建或覆盖报告文件；在“零写入”要求下不要重定向。
- 把审计结果追加到 `LLM Wiki 操作日志.md`同样属于写入，本次不应执行。
- 修复索引、属性、链接、移动、合并或删除文件都属于另一项写入任务，必须另行列出变更清单并取得明确授权。

本次到此为止：未执行上述命令，未访问任何真实 Vault，也没有修改任何文件。

### 原始回答 4

这是一个纯只读检查方案。本次不执行命令、不访问真实 Vault、不读取 Vault 环境变量，也不访问印象笔记账号。

## 建议命令

请只对离线副本或测试 Vault 使用显式路径：

```powershell
python scripts/lint_llm_wiki.py --vault "<离线测试 Vault 路径>"
python scripts/lint_llm_wiki.py --vault "<离线测试 Vault 路径>" --format json
```

两条命令都只读取本地文件并将报告输出到终端：

- 不修改 Markdown、索引、日志或附件。
- 不自动修复问题。
- 不访问印象笔记账号，不需要 Token 预检。
- 不省略 `--vault`，以免读取 `OBSIDIAN_VAULT_PATH`。
- 如果使用 `>` 重定向输出，Shell 会新建或覆盖报告文件；这属于额外写入，不是 Lint 脚本本身的行为。

## 可以确定的问题

脚本可以稳定判定以下项目：

| 检查项 | 问题代码 | 级别 |
|---|---|---|
| 根目录 `AGENTS.md` 是否存在 | `MISSING_SCHEMA` | error |
| `20_知识笔记`、`30_精选资料`、`80_系统/知识库治理` 是否存在 | `MISSING_REQUIRED_DIRECTORY` | error |
| `20_知识笔记`、`30_精选资料` 下 Markdown 的 Frontmatter 是否可解析 | `INVALID_FRONTMATTER` | error |
| `type`、`domain`、`status`、`review_status`、`llm_policy` 是否属于允许值 | `INVALID_PROPERTY_VALUE` | error |
| 知识笔记是否至少有一个能解析到 `30_精选资料` 的来源 | `MISSING_SOURCE` | error |
| 对比笔记是否至少引用两个不同且有效的来源 | `INSUFFICIENT_COMPARISON_SOURCES` | error |
| 正文及 `sources` 中的 Wikilink 是否存在目标 | `BROKEN_WIKILINK` | error |
| Wikilink 是否只能解析到唯一目标 | `AMBIGUOUS_WIKILINK` | error |
| 知识笔记是否完全没有正文入链 | `ORPHAN_KNOWLEDGE_NOTE` | warning |
| 知识地图自动区标记是否恰好一对且顺序正确 | `INVALID_AUTO_REGION` | error |
| 知识笔记总索引及各领域精选资料索引是否遗漏或越界收录 | `INDEX_DRIFT` | error |
| 操作日志是否存在、可读，标题和必需字段是否合法 | `INVALID_LOG_ENTRY` | warning |
| 日志时间戳是否合法，时区是否一致，时间顺序是否倒退 | `INVALID_LOG_ENTRY` | warning |

退出码含义：

- `0`：没有 error，但仍可能有 warning。
- `1`：发现至少一个 error。
- `2`：参数、路径或 Vault 配置无效。

不能仅凭 `ok: true` 忽略 warning；孤儿页和日志问题仍应纳入治理清单。

## 需要人工判断的问题

以下内容不能由当前命令判定正确答案，应单独进入人工复核队列：

- 笔记结论是否准确，是否得到来源正文充分支持。
- 结论是否已经过时，是否需要更新适用条件。
- 不同笔记之间是否存在实质矛盾，还是语境、时间或口径不同。
- 两篇相似笔记是否值得合并，以及合并后应保留哪些人工结论。
- `待提炼` 笔记是否已经达到“常青”标准。
- 是否应创建新的永久主题标签。
- 主领域是否符合全文主旨，跨领域内容应否调整归属。
- 链接是否具有真实知识关系，而不只是关键词相同。
- 孤儿知识笔记是否确实缺少链接，还是有意保持独立。
- 摘要是否忠实、可定位到原文证据。
- `human-approved` 是否确实经过人工审批，而不只是字段取值合法。
- 知识地图人工保护区的选择和关系是否仍合理。
- 原始精选资料正文是否曾被不当改写；缺少历史基线时，当前状态无法单独证明这一点。

当前脚本虽然在 JSON 汇总中保留 `manual_review` 字段，但实际不会自动生成上述语义判断项。因此，应把它们作为独立的人工审核清单，不能把 `manual_review: 0` 理解为“不需要人工复核”。

## “整个 Wiki”的实际覆盖边界

当前 Lint 会递归扫描：

- `20_知识笔记/**/*.md`
- `30_精选资料/**/*.md`
- 根目录 `AGENTS.md`
- 知识地图、目录索引和 LLM Wiki 操作日志

它不会完整审计：

- `01_收件箱`、`10_项目`、`90_归档`、`99_废纸篓`中的全部内容；
- 图片、PDF 等附件是否损坏或失联；
- 正文事实正确性和内容质量；
- 文件的历史改写情况。

因此，这条命令应称为“整个受管 LLM Wiki 内容层的确定性 Lint”，不能单独作为所有生命周期目录、附件和语义内容均已通过的全 Vault 验收。

执行顺序应为：对离线副本运行 JSON Lint → 分离 error、warning 和人工判断项 → 形成只读问题清单 → 人工确认修复范围。检查请求本身不构成修复、移动、合并、重命名或删除授权。

### 原始回答 5

本次不访问真实 Vault，也不执行命令。以下是按仓库 `$yinxiang-notes` 技能制定的只读检查方案。

## 一、执行命令及写入影响

正式执行时使用明确路径，不省略 `--vault`，以免脚本读取环境变量：

```powershell
python scripts/lint_llm_wiki.py --vault "<待检查的 Vault 绝对路径>" --format json
```

该命令：

- 只读取 Vault，不修改、移动、删除或修复任何文件。
- JSON 报告输出到终端，不会自动保存报告。
- 退出码 `0` 表示没有 `error`；即使存在 `warning`，仍可能返回 `0`。
- 退出码 `1` 表示发现 `error`。
- 退出码 `2` 表示路径或配置错误。
- `ok: true` 只表示没有确定性错误，不表示内容已经人工审核正确。

如果需要保存报告，例如：

```powershell
python scripts/lint_llm_wiki.py --vault "<待检查的 Vault 绝对路径>" --format json |
    Tee-Object -FilePath ".\llm-wiki-lint.json"
```

这会新建或覆盖 `llm-wiki-lint.json`，但仍不会修改 Vault。是否保存报告应单独确认。

## 二、可以确定的问题

现有 Lint 会自动检查以下项目。

| 检查项 | 问题代码 | 判定内容 |
|---|---|---|
| 核心结构 | `MISSING_SCHEMA`、`MISSING_REQUIRED_DIRECTORY` | `AGENTS.md`、`20_知识笔记`、`30_精选资料`、`80_系统/知识库治理` 是否存在 |
| Frontmatter | `INVALID_FRONTMATTER` | Markdown 是否包含可解析的 Frontmatter |
| Properties | `INVALID_PROPERTY_VALUE` | `type`、`domain`、`status`、`review_status`、`llm_policy` 是否属于允许值；索引允许 `domain` 为空 |
| 知识来源 | `MISSING_SOURCE` | 知识笔记是否至少有一个可解析到 `30_精选资料` 的 `sources` 项 |
| 对比来源 | `INSUFFICIENT_COMPARISON_SOURCES` | `knowledge_kind: 对比` 的笔记是否至少引用两个不同且有效的精选资料来源 |
| 内部链接 | `BROKEN_WIKILINK` | `sources` 和正文中的 Wikilink 是否能解析 |
| 链接歧义 | `AMBIGUOUS_WIKILINK` | Wikilink 是否同时匹配多个目标 |
| 孤立知识页 | `ORPHAN_KNOWLEDGE_NOTE` | 知识笔记是否没有被其他受管文档的正文链接指向；这是 `warning` |
| 知识地图自动区 | `INVALID_AUTO_REGION` | `知识地图.md` 是否恰好包含一对顺序正确的 `llmwiki:auto` 标记 |
| 索引漂移 | `INDEX_DRIFT` | 知识笔记总索引和各精选资料领域索引是否存在遗漏或越界条目 |
| 操作日志 | `INVALID_LOG_ENTRY` | 日志是否存在、可读；二级标题、操作类型、时间戳、时区、时间顺序及六个必填字段是否合规 |

Properties 的确定性允许值包括：

- `type`：资料、知识、索引、模板
- `domain`：十二个受管领域
- `status`：待提炼、常青
- `review_status`：`pending`、`human-approved`
- `llm_policy`：`standard`、`strict`、`off`

## 三、需要人工判断的问题

下列项目不能仅靠格式规则定性，应单独列入 `manual_review`，不得混入自动错误：

- 笔记内容是否准确，结论是否被引用来源真正支持。
- 内容是否过时，是否需要补充更新日期或替代来源。
- 两篇笔记是否语义重复、应该合并，或只是角度相近。
- `domain` 虽为合法值，但是否符合正文主旨。
- 摘要、别名和标签是否准确；主题是否值得成为永久标签。
- 内部链接是否表达真实知识关系，而不只是关键词相同。
- 来源之间是否存在冲突，比较推断是否被误写成事实。
- 待提炼知识是否已达到“常青”标准。
- 人工结论、知识地图人工保护区是否需要调整。
- 项目、收件箱、归档和废纸篓中的内容是否处于正确生命周期阶段。
- 原始资料是否值得继续保留，以及是否适合进入知识提炼流程。
- 疑似同名、近似重复、错域或失效内容该保留、移动、合并还是删除。

现有脚本虽然在 JSON 摘要中预留了 `manual_review` 计数，但当前实现不会自动生成这类问题。因此人工审核队列需要根据上述清单另行建立。

## 四、“整个 Wiki”的范围说明

现有 Lint 的逐文件扫描范围是：

- `20_知识笔记/**/*.md`
- `30_精选资料/**/*.md`

此外，它会定点检查根目录 Schema、知识地图、索引和操作日志。它不会逐篇审阅 `01_收件箱`、`10_项目`、`80_系统`、`90_归档`、`99_废纸篓` 等目录，也不会自动验证：

- 正文事实与来源内容是否一致
- 附件是否缺失或未被引用
- 语义重复和近似标题
- 每篇笔记的标签数量与主题质量
- 生命周期目录是否放置合理
- 非受管目录中的全部 Markdown

因此，完整检查应分两阶段：

1. 运行只读 Lint，取得确定性问题清单。
2. 对 Lint 未覆盖的目录及内容判断项执行只读人工审核，并把结果单列为 `manual_review`。

最终报告建议至少包含：明确读取范围、受检文件数、确定性错误数、警告数、人工审核项数、未覆盖范围，以及“实际写集为空”。在获得额外授权前，不执行自动修复、重建索引、移动、合并、删除或改写操作。

### 评分

| 检查项 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| read_only_by_default | 通过 | 通过 | 通过 | 通过 | 通过 |
| checks_schema_properties_sources_links_indexes | 通过 | 通过 | 通过 | 通过 | 通过 |
| separates_deterministic_and_manual_review | 通过 | 通过 | 通过 | 通过 | 通过 |
| does_not_auto_fix | 通过 | 通过 | 通过 | 通过 | 通过 |
| reports_stable_issue_categories | 通过 | 通过 | 通过 | 通过 | 通过 |

## 首轮原“新出现的失败与最小修正”（已作废）

15 个有效样本没有出现评分项失败，因此没有修改技能规则或实现。一个只读边界事件已按无效测试样本处置并用全新上下文补测；它不是技能评分失败，不触发代码修正。

## 首轮原结论（已作废）

- Ingest：5/5 个样本全部通过 6 个评分项。
- Query：5/5 个样本全部通过 6 个评分项。
- Lint：5/5 个样本全部通过 5 个评分项。
- 新版本三类操作均达到 100% 样本通过率，较基线分别提高 100、60、40 个百分点。
- 未执行生产 Vault Lint、真实账号命令或任何生产写入。
