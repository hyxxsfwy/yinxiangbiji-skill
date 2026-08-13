# Obsidian 精选资料重分类与治理

## 主流程与决策语义

对 `30_精选资料` 做全局重扫或重新归类时，以 `reclassify_selected_materials.py` 为主工具。先运行 `audit` 取得全库证据，再由人工把需要执行的决定写入 JSON；未写入决定文件的资料不变。

固定受管十二领域为：AI、Quant、信息技术、投资理财、知识管理、健康医学、中医、两性情感、个人成长、科技产业、自然科学、历史与社会。每个领域的索引只收录 `30_精选资料/<domain>/YYYY年MM月/*.md` 中 frontmatter 为 `type: 资料` 且 `domain` 与当前领域完全匹配的文档。

领域契约升级只自动执行“软件工程”到“信息技术”的目录、frontmatter 和精确链接迁移。其余既有资料由 `audit` 生成建议，未经人工 decisions 不自动移动或移入废纸篓。

| 决策 | 适用条件 | 执行动作 |
|---|---|---|
| `keep` | 当前领域正确且仍值得保留 | 不移动；可按证据维护受控链接 |
| `move` | 文档错域，但有明确目标领域且值得保留 | 移到目标领域，更新 `domain`，复制附件并重建索引 |
| `trash` | 文档不属于受管范围，或已确认无保留价值 | 移到可恢复的 `99_废纸篓/30_精选资料/` 镜像路径 |
| `pending` | 目标领域、保留价值或链接关系仍不确定 | 不写入 decisions，保留原位等待人工判断 |

审计结果中的 `unclassified` 视为 `pending`，不能直接推断为 `trash`。错域只说明当前位置不正确；只要目标领域明确且资料值得保留，就必须使用 `move`。

## `audit / apply / verify`

完整参数先运行 `python scripts/reclassify_selected_materials.py --help` 查看。未提供 `--vault` 时，脚本从当前设备的 `OBSIDIAN_VAULT_PATH` 加载正式 Vault；报告默认写入 `<vault>/.state/yinxiang-notes/reports/`。

```powershell
# audit：扫描全库，生成分类、链接和待人工确认的审计报告
python scripts/reclassify_selected_materials.py audit

# apply：仅执行显式 decisions；固定确认词之外一律拒绝
python scripts/reclassify_selected_materials.py apply --decisions "decisions.json" --confirm RECLASSIFY_SELECTED_MATERIALS

# verify：根据同一 decisions 独立验证已执行结果
python scripts/reclassify_selected_materials.py verify --decisions "decisions.json"
```

`audit` 不移动或删除业务文件。`verify` 对业务资料只读，但会写验证报告到状态目录。`apply` 与 `verify` 必须使用同一份 UTF-8 decisions；只有用户明确授权后才能运行 `apply`。

## 显式 decisions JSON

根节点固定为对象，必须且只能包含 `moves`、`trash`、`links`。路径相对 `30_精选资料/`，使用正斜杠：

```json
{
  "moves": {
    "健康医学/2026年01月/关系沟通.md": "两性情感"
  },
  "trash": [
    "AI/2026年01月/无保留价值资料.md"
  ],
  "links": {
    "AI/2026年01月/Agent 架构.md": [
      "AI/2026年01月/Agent 状态.md"
    ],
    "AI/2026年01月/Agent 状态.md": [
      "AI/2026年01月/Agent 架构.md"
    ]
  }
}
```

- `moves` 是“来源相对路径 → 目标领域”的对象。目标领域必须受支持，且不能与来源领域相同。
- `trash` 是确认移入可恢复废纸篓的路径列表；同一资料不能同时出现在 `moves` 和 `trash`。
- `links` 是“来源相对路径 → 目标路径列表”的对象。不得自链接或重复，每篇最多 3 条，所有边必须显式双向对称。
- `keep` 与 `pending` 不作为写操作字段；不需要变更的资料不写入对象。

## 全局审计与写入预检

`audit` 扫描整个 `30_精选资料`，读取正文与当前领域，输出每篇资料的分类证据、建议决定和现有链接问题。人工必须复核建议，尤其是 `unclassified`、低证据、并列领域和同名目标。

`apply` 在任何业务写入前统一预检 decisions：

- 所有路径均位于 `30_精选资料` 内，来源存在，目标领域与目标路径合法；
- `moves` 与 `trash` 不重叠，目标同路径异内容时中止；
- 本地附件源与目标可解析，目标冲突时使用内容哈希区分，不覆盖不同内容；
- `links` 端点存在于精选资料，不能包含 `trash` 端点，移动后的两端路径可重映射；
- 链接严格双向、每篇不超过 3 条，预检失败时不产生部分移动或删除。

## 快照、附件、链接与索引

通过预检后，`apply` 先为所有将移动、移入废纸篓或改写链接的 Markdown，以及全部既存索引，创建 ZIP 快照和 SHA-256 清单。快照不包含附件副本；来源附件仍保留。

`move` 保留正文和来源元数据，更新 frontmatter 的 `domain`，把本地附件复制到目标领域的 `_attachments/`，并改写相对引用；来源附件仍保留。`trash` 保留可恢复副本及其本地附件，不把无保留价值判断扩展到其他错域资料。

自动链接只写入受管理的 `llmwiki:auto-links` 区域，按路径稳定排序；重复执行保持幂等，空链接决定移除受管理区域而不改正文或人工链接。写入完成后全量重建全部十二个领域的 `目录索引.md`；每份索引仅包含规范 `YYYY年MM月` 目录下 `type: 资料` 且 `domain` 匹配当前领域的文档。

执行阶段出现异常时，工具使用执行前快照回滚本批业务改动，并在失败报告中保留快照位置、`completed`、`pending` 和具体问题；若回滚本身不完整，问题列表会明确列出未恢复项。

## 验证门禁

`verify --decisions` 至少检查：

- `moves` 的来源已消失，目标文件存在且 `domain` 等于目标领域；
- `trash` 只存在于废纸篓镜像路径，相关本地附件仍可解析；
- 受管理链接与 decisions 一致、严格双向、端点存在且没有歧义；
- 全部十二个领域的索引存在，且与规范 `YYYY年MM月` 目录下 `type: 资料`、`domain` 匹配的真实文档集合完全一致；
- 所有核验路径均位于 Vault 内。

`apply` 会先生成快照与 SHA-256 清单，并在写入后同时验证快照和结果；仍须再运行独立 `verify` 核对落盘状态。只有报告 `ok: true` 且问题列表为空时，才能声明重分类完成。

## 旧 `curate_selected_materials.py` 兼容边界

旧工具仅用于继续执行既有的逐篇审阅数组，不承担全库重扫或跨领域 `move`。旧清单根节点是数组，每项字段精确为 `path`、`decision`、`reason`、`topic`、`links`，其中 `decision` 只接受 `keep` 或 `trash`：

```json
[
  {
    "path": "AI/2026年01月/保留资料.md",
    "decision": "keep",
    "reason": "正文与当前领域一致",
    "topic": "Agent 工程",
    "links": []
  }
]
```

兼容命令：

```powershell
python scripts/curate_selected_materials.py --review "旧审阅清单.json"
python scripts/curate_selected_materials.py --review "旧审阅清单.json" --apply --confirm CURATE_SELECTED_MATERIALS
python scripts/curate_selected_materials.py --review "旧审阅清单.json" --verify
```

需要重扫、重分类、移动错域但有价值的资料时，必须回到本页主流程。
