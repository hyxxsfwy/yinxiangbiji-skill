# Obsidian Vault 内运行状态实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `OBSIDIAN_VAULT_PATH` 成为每台设备的正式 Vault 根目录，并把精选导出的目录数据库、任务、断点和报告统一保存到 Vault 内可同步的 `.state/yinxiang-notes/`。

**Architecture:** `scripts/runtime.py` 负责读取并验证正式 Vault；新增 `scripts/vault_state.py` 集中派生状态路径、迁移仓库旧状态和管理单写入锁。多领域、单领域及知识库管理命令只消费这两个共享接口，任务 JSON 不再携带设备绝对路径；全量同步改用独立的 `YINXIANG_SYNC_VAULT_PATH`。

**Tech Stack:** Python 3.12、`pathlib`、SQLite、JSON、`unittest`、PowerShell、Obsidian/OneDrive。

## Global Constraints

- 使用简体中文编写文档和 Git Commit 消息。
- 系统环境变量优先于仓库根目录 `.env`。
- `OBSIDIAN_VAULT_PATH` 必须指向存在且包含 `.obsidian` 的正式 Vault 根目录。
- `YINXIANG_SYNC_VAULT_PATH` 只用于全量同步的独立暂存目录。
- Token、NoteStore URL 和 `.env` 不得进入 Vault 状态目录或 Git。
- 状态默认根目录固定为 `<vault>/.state/yinxiang-notes/`。
- 旧仓库 `.state/` 只复制、不移动、不覆盖冲突目标。
- SQLite 不启用 WAL；同一时刻只允许一个写入任务。
- 用户已要求后续不再设置人工确认点，按本计划连续执行并在本地 `main` 完成提交。

---

### Task 1: 正式 Vault 全局配置

**Files:**
- Modify: `scripts/runtime.py`
- Modify: `.env.example`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Produces: `load_vault_root(explicit=None, env_path=None) -> Path`
- Produces: `YINXIANG_SYNC_VAULT_PATH` 配置契约

- [ ] **Step 1: 写 Vault 配置失败测试**

在 `tests/test_runtime.py` 写入真实临时目录测试：环境变量覆盖 `.env`；有效目录必须包含 `.obsidian`；缺失配置、普通目录和 `30_精选资料` 子目录均抛出 `ValueError`。

```python
def test_load_vault_root_uses_device_local_environment_and_validates_marker(self):
    from scripts.runtime import load_vault_root

    with workspace_temp_dir() as temp_dir:
        configured = temp_dir / "vault"
        configured.mkdir()
        (configured / ".obsidian").mkdir()
        env_file = temp_dir / ".env"
        env_file.write_text(
            f"OBSIDIAN_VAULT_PATH={temp_dir / 'wrong'}\n",
            encoding="utf-8",
        )
        with patch.dict(
            os.environ,
            {"OBSIDIAN_VAULT_PATH": str(configured)},
            clear=True,
        ):
            self.assertEqual(
                load_vault_root(env_path=env_file),
                configured.resolve(),
            )
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `python -m unittest tests.test_runtime.RuntimeConfigTests.test_load_vault_root_uses_device_local_environment_and_validates_marker -v`

Expected: FAIL，`load_vault_root` 尚不存在。

- [ ] **Step 3: 实现共享配置加载**

在 `scripts/runtime.py` 增加：

```python
def load_vault_root(explicit=None, env_path=None):
    raw = explicit or load_setting("OBSIDIAN_VAULT_PATH", env_path)
    if not raw:
        raise ValueError("未配置 OBSIDIAN_VAULT_PATH")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir() or not (root / ".obsidian").is_dir():
        raise ValueError(f"不是有效的 Obsidian Vault 根目录: {root}")
    if root.name in {
        "01_收集箱", "10_项目", "20_知识笔记", "30_精选资料",
        "80_系统", "90_归档", "99_废纸篓",
    }:
        raise ValueError("OBSIDIAN_VAULT_PATH 必须指向 Vault 根目录")
    return root
```

同步修改 `.env.example`：

```dotenv
# 正式 Obsidian 知识库根目录；每台设备路径可以不同。
OBSIDIAN_VAULT_PATH=D:\OneDrive\文档\@_Obsidian

# 可选：全量同步使用的独立暂存目录，不能指向正式知识库。
YINXIANG_SYNC_VAULT_PATH=D:\OneDrive\文档\@_Obsidian_全量同步暂存
```

- [ ] **Step 4: 运行配置测试**

Run: `python -m unittest tests.test_runtime tests.test_config -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add scripts/runtime.py .env.example tests/test_runtime.py tests/test_config.py
git commit -m "统一正式 Vault 全局配置"
```

### Task 2: Vault 状态路径、迁移和运行锁

**Files:**
- Create: `scripts/vault_state.py`
- Create: `tests/test_vault_state.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `load_vault_root() -> Path`
- Produces: `VaultStatePaths.for_vault(vault: Path) -> VaultStatePaths`
- Produces: `migrate_legacy_state(paths, legacy_root) -> MigrationReport`
- Produces: `runtime_write_lock(paths, task_id, recover_stale=False)` 上下文管理器

- [ ] **Step 1: 写路径派生和无损迁移失败测试**

测试字面路径：

```python
paths = VaultStatePaths.for_vault(vault)
self.assertEqual(
    paths.catalog,
    vault / ".state" / "yinxiang-notes" / "export-catalog.sqlite3",
)
self.assertEqual(paths.jobs.name, "jobs")
self.assertEqual(paths.runs.name, "runs")
self.assertEqual(paths.reports.name, "reports")
self.assertEqual(paths.single_domain.name, "single-domain")
```

创建旧 `export-AI-abc.json`、`multi-export-task.json`、`jobs/task.json` 和 `reports/task.json`，断言首次迁移复制并记录 SHA-256，第二次迁移不重复，冲突目标触发 `StateMigrationConflict` 且不覆盖。

- [ ] **Step 2: 运行迁移测试并确认 RED**

Run: `python -m unittest tests.test_vault_state.VaultStatePathTests tests.test_vault_state.LegacyMigrationTests -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现路径和迁移模块**

新增不可变数据类：

```python
@dataclass(frozen=True)
class VaultStatePaths:
    root: Path
    catalog: Path
    jobs: Path
    runs: Path
    reports: Path
    single_domain: Path
    migrations: Path
    lock: Path

    @classmethod
    def for_vault(cls, vault):
        root = Path(vault).resolve() / ".state" / "yinxiang-notes"
        return cls(
            root=root,
            catalog=root / "export-catalog.sqlite3",
            jobs=root / "jobs",
            runs=root / "runs",
            reports=root / "reports",
            single_domain=root / "single-domain",
            migrations=root / "migrations",
            lock=root / "active-run.lock",
        )
```

迁移只允许以下相对模式：

```python
("export-catalog.sqlite3", "export-*.json", "multi-export-*.json",
 "jobs/*.json", "reports/*.json")
```

单领域旧 `export-*.json` 写入 `single-domain/`，其他文件保留相对职责目录。复制使用临时文件加原子替换；清单记录源、目标、大小和 SHA-256。

- [ ] **Step 4: 写运行锁失败测试**

测试首次独占创建、同进程第二次拒绝、锁内容包含设备/进程/任务/时间、上下文退出删除，以及 `recover_stale=True` 只允许清理无法确认仍活跃的锁。

- [ ] **Step 5: 运行锁测试并确认 RED**

Run: `python -m unittest tests.test_vault_state.RuntimeLockTests -v`

Expected: FAIL，`runtime_write_lock` 尚不存在。

- [ ] **Step 6: 实现运行锁**

使用 `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` 独占创建 JSON 锁。锁来自本机且 PID 存活时始终拒绝覆盖；其他设备或未知 PID 默认拒绝，只有 `recover_stale=True` 才在保留原锁审计副本后重建。

- [ ] **Step 7: 运行状态模块测试**

Run: `python -m unittest tests.test_vault_state -v`

Expected: PASS。

- [ ] **Step 8: 提交**

```powershell
git add scripts/vault_state.py tests/test_vault_state.py .gitignore
git commit -m "增加 Vault 状态目录与迁移锁"
```

### Task 3: 多领域任务去设备路径并迁入 Vault 状态区

**Files:**
- Modify: `scripts/export_multi_domain.py`
- Modify: `templates/multi-domain-export-job.json`
- Modify: `tests/test_export_multi_domain.py`

**Interfaces:**
- Consumes: `load_vault_root()`
- Consumes: `VaultStatePaths.for_vault()`
- Consumes: `migrate_legacy_state()`、`runtime_write_lock()`
- Produces: `load_job(path, vault) -> ExportJob`
- Produces: `_job_id(job)`，不包含 Vault 绝对路径

- [ ] **Step 1: 写跨设备任务和默认路径失败测试**

新增测试：模板无 `vault`；相同日期/领域/关键词在两个不同临时 Vault 中生成相同任务 ID；旧 `vault` 字段被忽略；目录、运行状态和报告默认落入两个 Vault 各自的 `.state/yinxiang-notes/`。

- [ ] **Step 2: 运行测试并确认 RED**

Run: `python -m unittest tests.test_export_multi_domain.MultiDomainJobTests.test_job_id_is_device_path_independent tests.test_export_multi_domain.CommandLinePathTests -v`

Expected: FAIL，当前任务仍要求 `vault`，默认状态仍在仓库。

- [ ] **Step 3: 重构任务加载和 CLI 默认值**

将接口改为：

```python
def normalize_job(payload, vault):
    ...
    return ExportJob(
        since=since,
        until=until,
        vault=Path(vault).resolve(),
        domains=domains,
    )

def load_job(path, vault):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if "vault" in payload:
        print("警告：任务文件中的 vault 字段已废弃，使用 OBSIDIAN_VAULT_PATH")
    return normalize_job(payload, vault)
```

任务 ID 载荷删除 `vault`，增加固定 `"version": 2`。CLI 在读取凭据前加载正式 Vault、构造 `VaultStatePaths`、迁移旧状态，再派生：

```python
catalog = args.catalog or paths.catalog
state = args.state_file or paths.runs / f"multi-export-{task_id}.json"
report = args.report_file or paths.reports / f"{task_id}.json"
```

写入任务运行时使用 `runtime_write_lock()` 包裹 `run_export_job()`。

- [ ] **Step 4: 更新任务模板**

删除 `vault` 字段，保留日期和领域关键词；JSON 必须能被 UTF-8 严格解析。

- [ ] **Step 5: 运行多领域测试**

Run: `python -m unittest tests.test_export_multi_domain tests.test_export_catalog tests.test_export_integrity -v`

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add scripts/export_multi_domain.py templates/multi-domain-export-job.json tests/test_export_multi_domain.py
git commit -m "让多领域任务跨设备复用 Vault 状态"
```

### Task 4: 单领域导出与知识库命令统一使用全局 Vault

**Files:**
- Modify: `scripts/export_search_results.py`
- Modify: `scripts/restructure_obsidian_vault.py`
- Modify: `scripts/curate_selected_materials.py`
- Modify: `scripts/sync_to_obsidian.py`
- Modify: `tests/test_export_search_results.py`
- Modify: `tests/test_vault_restructure.py`
- Modify: `tests/test_curate_selected_materials.py`
- Modify: `tests/test_sync_integrity.py`

**Interfaces:**
- Consumes: `load_vault_root(explicit=None)`
- Consumes: `VaultStatePaths.for_vault()`
- Produces: `derive_domain_target(vault, domain, explicit=None) -> Path`

- [ ] **Step 1: 写单领域默认目标失败测试**

测试未传 `--target` 时，`AI` 自动写入 `<vault>/30_精选资料/AI`，状态写入 `<vault>/.state/yinxiang-notes/single-domain/export-AI.json`；显式目标越出对应领域目录时在加载凭据前失败。

- [ ] **Step 2: 运行单领域测试并确认 RED**

Run: `python -m unittest tests.test_export_search_results.CommandLineTests.test_global_vault_derives_domain_target_and_state -v`

Expected: FAIL，`--target` 当前必填且状态在仓库。

- [ ] **Step 3: 实现单领域路径派生**

新增：

```python
def derive_domain_target(vault, domain, explicit=None):
    expected = Path(vault).resolve() / "30_精选资料" / domain
    candidate = Path(explicit).resolve() if explicit else expected
    if candidate != expected:
        raise ValueError(f"目标目录必须是 {expected}")
    return candidate
```

`--target` 改为可选；CLI 从全局 Vault 派生目标和 `single-domain/export-<domain>.json`。状态文件名不再依赖设备绝对路径哈希。

- [ ] **Step 4: 写知识库命令默认 Vault 测试**

分别调用重组、审核和验证 CLI：未传 `--vault` 时使用临时 `.env`/环境变量中的正式 Vault；显式 `--vault` 仍通过根目录验证。

- [ ] **Step 5: 实现管理命令默认值**

三个管理命令将 `--vault` 从 `required=True` 改为可选，并在实际动作前调用 `load_vault_root(args.vault)`。

- [ ] **Step 6: 写全量同步配置隔离失败测试**

设置：

```python
OBSIDIAN_VAULT_PATH = formal_vault
YINXIANG_SYNC_VAULT_PATH = staging_vault
```

断言 `sync_to_obsidian.py` 未传 `--vault` 时选择暂存目录；只配置正式 Vault 时必须报“请配置 YINXIANG_SYNC_VAULT_PATH”，不得退回正式 Vault。

- [ ] **Step 7: 实现全量同步配置隔离**

将 argparse 默认值改为：

```python
default=load_setting("YINXIANG_SYNC_VAULT_PATH")
```

并更新帮助和错误信息。

- [ ] **Step 8: 运行相关测试**

Run: `python -m unittest tests.test_export_search_results tests.test_vault_restructure tests.test_curate_selected_materials tests.test_sync_integrity -v`

Expected: PASS。

- [ ] **Step 9: 提交**

```powershell
git add scripts/export_search_results.py scripts/restructure_obsidian_vault.py scripts/curate_selected_materials.py scripts/sync_to_obsidian.py tests/test_export_search_results.py tests/test_vault_restructure.py tests/test_curate_selected_materials.py tests/test_sync_integrity.py
git commit -m "统一知识库命令的 Vault 路径"
```

### Task 5: README、Skill 和行为契约

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `tests/test_skill_documentation.py`
- Modify: `docs/superpowers/specs/2026-07-28-vault-scoped-runtime-state-design.md`

**Interfaces:**
- Consumes: Tasks 1–4 的最终命令和路径
- Produces: 跨设备配置、状态迁移、并发限制和故障排查说明

- [ ] **Step 1: 写 Skill 行为失败测试**

测试文档必须能指导执行者：

- 把 `OBSIDIAN_VAULT_PATH` 识别为每台设备正式根目录；
- 把 `YINXIANG_SYNC_VAULT_PATH` 识别为全量同步暂存区；
- 使用 `<vault>/.state/yinxiang-notes/export-catalog.sqlite3`；
- 不在任务 JSON 保存 `vault`；
- 旧状态复制不删除；
- 不允许两台设备同时执行导出。

- [ ] **Step 2: 运行文档测试并确认 RED**

Run: `python -m unittest tests.test_skill_documentation.SkillDocumentationTests.test_device_local_vault_and_synced_state_contract -v`

Expected: FAIL，现有文档仍描述仓库 `.state/` 和任务绝对路径。

- [ ] **Step 3: 更新 README 和 Skill**

命令示例统一使用：

```powershell
$vault = $env:OBSIDIAN_VAULT_PATH
New-Item -ItemType Directory -Force `
  "$vault\.state\yinxiang-notes\jobs" | Out-Null
Copy-Item templates\multi-domain-export-job.json `
  "$vault\.state\yinxiang-notes\jobs\2026-q2.json"
python scripts/export_multi_domain.py `
  --job "$vault\.state\yinxiang-notes\jobs\2026-q2.json"
```

说明 `.env` 每设备不同、状态随 Vault 同步、Token 不同步、旧状态保留，以及必须等待上一设备完成同步后再换设备运行。

- [ ] **Step 4: 运行 Skill 测试**

Run: `python -m unittest tests.test_skill_documentation -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add README.md SKILL.md tests/test_skill_documentation.py docs/superpowers/specs/2026-07-28-vault-scoped-runtime-state-design.md
git commit -m "更新跨设备 Vault 状态使用规则"
```

### Task 6: 全量验证和本地集成

**Files:**
- Verify: all modified files

**Interfaces:**
- Consumes: Tasks 1–5
- Produces: 可在本地 `main` 使用的最终实现

- [ ] **Step 1: 运行全量测试**

Run: `python -m unittest discover -s tests -p "test_*.py"`

Expected: 全部通过，0 failures、0 errors。

- [ ] **Step 2: 运行静态和命令验证**

```powershell
python -m compileall -q scripts tests
python scripts/export_multi_domain.py --help
python scripts/export_search_results.py --help
python scripts/sync_to_obsidian.py --help
python -c "import json, pathlib; json.loads(pathlib.Path('templates/multi-domain-export-job.json').read_text(encoding='utf-8'))"
git diff --check
```

Expected: 全部退出码为 0。

- [ ] **Step 3: 扫描凭据和状态文件**

```powershell
rg -n "S=s[0-9]+:U=[0-9a-f]+:E=" .env.example README.md SKILL.md scripts tests templates
git status --short
```

Expected: 无真实 Developer Token；没有 `.env`、SQLite、运行状态或 Obsidian 正文进入提交。

- [ ] **Step 4: 独立代码审阅**

审阅范围从设计提交 `1799c10` 到当前 HEAD，重点检查路径越界、迁移覆盖、锁清理、跨设备任务 ID、凭据泄漏和正式/暂存 Vault 混用。修复所有 Critical/Important 后重新运行全量验证。

- [ ] **Step 5: 合并回本地 main**

实现若位于隔离分支，则快进合并到本地 `main`，在合并结果上再次运行：

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

不推送远程，除非用户另行要求。
