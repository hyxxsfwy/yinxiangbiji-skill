# Obsidian 精选资料治理

## 决策模型

先对每篇资料做正向判断，再生成脚本可执行的显式清单：

| 决策 | 适用条件 | 后续动作 |
|---|---|---|
| `keep` | 领域正确、仍有引用价值，当前位置合理 | 保留原文；只维护人工确认的受控链接 |
| `move` | 内容值得保留，但生命周期或目录归类错误 | 交给 Vault 重组或另一次明确的重分类任务，不用链接伪装搬运 |
| `trash` | 错域、无保留价值或明确进入可恢复删除阶段 | 移入 `99_废纸篓/30_精选资料/` 镜像路径并保留所需附件 |
| `pending` | 证据不足、链接有歧义或需要人工决定 | 不写入；补充证据后重新审核 |

`move` 与 `pending` 是治理层决策，不是当前 `curate_selected_materials.py` 的可执行值。当前脚本保持兼容边界：清单根节点必须是数组，每项字段精确为 `path`、`decision`、`reason`、`topic`、`links`，且 `decision` 只接受 `keep` 或 `trash`。需要移动时先完成独立重分类；待定项不能伪装成 `keep`。

## 显式决策 JSON

路径相对 `30_精选资料/`，使用 POSIX 分隔符。保留项的链接目标必须也在清单中、决定为 `keep`，并显式写出反向边；`trash` 项的 `links` 必须为空。

```json
[
  {
    "path": "AI/月份/Agent 架构.md",
    "decision": "keep",
    "reason": "正文讨论 Agent 架构，领域与目录一致",
    "topic": "Agent 工程",
    "links": ["AI/月份/Agent 状态.md"]
  },
  {
    "path": "AI/月份/Agent 状态.md",
    "decision": "keep",
    "reason": "正文讨论 Agent 状态，领域与目录一致",
    "topic": "Agent 工程",
    "links": ["AI/月份/Agent 架构.md"]
  },
  {
    "path": "AI/月份/错域资料.md",
    "decision": "trash",
    "reason": "正文主旨不属于当前领域",
    "topic": "错域",
    "links": []
  }
]
```

每篇保留资料最多 3 条人工确认、语义明确的双向链接；仅关键词相同不构成关系，没有明确关联时保持空数组。

## `audit / apply / verify`

先运行 `--help` 核对当前参数。以下命令的 `--review` 指向本次显式清单：

```powershell
# audit：默认预览和全局预检，不修改 Vault
python scripts/curate_selected_materials.py --review "审阅清单.json"

# apply：获得明确授权后执行
python scripts/curate_selected_materials.py --review "审阅清单.json" --apply --confirm CURATE_SELECTED_MATERIALS

# verify：对已执行结果做只读验证
python scripts/curate_selected_materials.py --review "审阅清单.json" --verify
```

`--apply` 与 `--verify` 互斥；执行只接受固定确认词 `CURATE_SELECTED_MATERIALS`。未提供 `--vault` 时从当前设备的 `OBSIDIAN_VAULT_PATH` 加载正式 Vault。

## 全局预检

写入前必须完成整个 `30_精选资料` 的预检，而不是只检查准备移动的条目：

- 清单精确覆盖全部非索引 Markdown，路径唯一、存在、位于 Vault 内且不含向上穿越；
- 字段完整，`reason` 与 `topic` 非空，决策处于兼容集合；
- 每条自动链接的目标唯一、在清单内、决定为 `keep` 且反向边存在；
- `trash` 没有链接，单篇链接不超过 3 条且不重复；
- 废纸篓目标、附件目标与待修改 Markdown 不存在同路径异内容冲突；
- 当前 Vault 没有其他活动写锁，旧状态迁移不会覆盖异内容文件。

任一问题都应在创建快照或写入前中止，并保持业务文件不变。

## 快照、附件与写入

执行前为所有将修改或移动的 Markdown 及其本地附件创建 ZIP 快照和 SHA-256 清单。错域资料移动到 `99_废纸篓/30_精选资料/` 的镜像路径；被其引用的本地附件复制到可继续解析的镜像位置，不能因移动而产生断链。

原始正文保持不变。自动链接只写入受管理的 `llmwiki:auto-links` 区域，按路径稳定排序，重复执行结果幂等；清单链接变空时移除整个受管理区域，不触碰正文或人工链接。

完成写入后重建受影响领域的 `目录索引.md`，并把逐篇决策、理由、主题和链接写入审核日志。索引是可重建视图，不保存人工评语。

## 验证契约

验证必须覆盖：

- `keep` 文件仍在规范路径，`trash` 文件只在废纸篓镜像路径；
- 移动后的 Markdown 与所有本地附件引用可解析；
- 受管理链接与清单一致、严格双向、数量受控且没有歧义；
- 领域索引存在、条目可打开，未引用被移走的资料；
- ZIP 快照与 SHA-256 清单覆盖全部实际变更；
- 审核日志存在且逐篇记录可追溯；
- Vault 外没有写入，真实印象笔记账号和凭据未被访问。

只有 `apply` 后的内置验证与独立 `verify` 都通过，才能声明治理完成。
