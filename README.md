# Mappo

在 macOS 上盘点与映射 Coding Agent、编辑器和扩展使用过的项目工作区。需要 Python 3.9 或更新版本，使用标准库。默认实时查询，`scan` 同时保存本地索引。

## 安装

把发行文件 `mappo.pyz` 复制到本机后，在终端运行：

```sh
mkdir -p ~/.local/bin
install -m 755 mappo.pyz ~/.local/bin/mappo
~/.local/bin/mappo --version
~/.local/bin/mappo scan
```

如果 `~/.local/bin` 已在 PATH 中，可以直接运行 `mappo`。也可以从源码目录用 `./mappo`，或用 `python3 -B scripts/build_release.py dist/mappo.pyz` 生成单文件。安装和运行均可使用普通账号。

```sh
./mappo agents
./mappo projects --agent workbuddy
./mappo workspaces --agent dsh
./mappo projects --name demo-app --path-contains projects
./mappo projects --agent cursor --since 7d
./mappo workspaces --agent codex --recent
./mappo projects --path ~/Documents --json
./mappo inspect <列表中的ID>
./mappo open <项目ID或名称> --indexed --with cursor
./mappo open <项目ID或名称> --indexed --with terminal
./mappo doctor --agent codebuddy
./mappo scan --json
./mappo web
```

`projects` 按实际路径关联，保留不同 clone、worktree 和远程 URI。`workspaces` 区分原生登记（native）、历史推导（inferred）和显式目录扫描（filesystem）。一个项目可以有多条证据，一个工作区可以有多个根目录。历史 cwd 可能来自临时任务或缓存，不能据此断定用户创建过独立代码项目。使用 `inspect` 查看记录来源。补扫目录产生的 ID 要带相同的 `--path` 查询。

| 工具 | 本地证据 |
| --- | --- |
| Codex | state 数据库的 projects、project_roots 和 threads.cwd，旧版回退到桌面 JSON |
| Cursor、CodeBuddy CN、Trae、VS Code | workspaceStorage 登记和最近打开列表，解析多根工作区配置 |
| CodeBuddy CLI | 本地会话索引、历史 project、限长的会话首尾事件 cwd |
| WorkBuddy | workbuddy.db 的 workspaces 和 sessions.cwd，以及桌面 sessions.json 中的 workDir |
| DeepSeek Harness | workspace.json 的 workspaces 登记、会话投影缓存的 identity.cwd |
| Claude Code | .claude.json 的 projects 和历史 project |
| Antigravity CLI | 会话摘要表的 workspace_uris |
| 编辑器扩展 | 读取工作区数据库中特定扩展的状态键，将该工作区作为推导记录。仅有安装痕迹时不会把宿主的项目分配给扩展 |

## 检索

`projects` 和 `workspaces` 都支持组合过滤。`--name` 对目录名和工作区名称做不区分大小写的子串匹配。`--path-contains` 匹配路径片段；原有的 `--path` 继续用于补扫目录。`--since` 接受 7d、24h、2w、日期或 ISO 时间，无时区输入按本机时区解释。`--recent` 显示所有有时间依据的结果，两种时间查询均按最近在前排序。

`last_activity` 采用 UTC，`activity_source` 标明依据。来源包括工作区登记更新、会话活动或创建时间、命令历史和编辑器本地编辑历史的条目时间。记录反映可确认的最近活动；数据源可能缺少单纯打开目录或更晚的活动。多根工作区中，单文件编辑只计入所属根目录。缺少依据的时间为 null，在普通列表中保留，时间查询会略去。纯文件系统发现没有活动时间。

## 扫描状态

`agents --json` 提供安装位置、数据位置、总体状态和 `issues`。`doctor` 的每条记录包含工具、来源、原因码和原因。

| 原因码 | 含义 |
| --- | --- |
| permission_denied | 操作系统拒绝读取文件或遍历目录 |
| missing_source | 预期的索引文件、登记配置或指定目录已缺失 |
| unsupported | 已探测到工具但缺少适配器，或当前数据格式、远程配置尚不支持 |
| busy | 数据库被锁定或缺少安全读取 WAL 所需的共享内存 |
| invalid_source / read_error | 数据损坏、结构异常或其他读取错误 |
| empty | 已检查的数据源没有可归属的工作区记录 |

有结果且伴随异常时总体状态为 `partial`，具体原因保留在 `issues` 和 `doctor`。探测范围是已知 macOS 应用、命令、扩展及元数据位置。

## 本地索引和失效路径

```sh
mappo scan
mappo projects --indexed --status missing
mappo projects --indexed --historical
mappo link <旧项目ID> <新项目ID>
mappo inspect <旧项目ID> --indexed
mappo unlink <旧项目ID> <新项目ID>
mappo star <项目ID>
mappo tag <项目ID> 核心 前端
mappo hide <项目ID>
mappo projects --indexed --favorite --tag 核心
mappo projects --indexed --hidden
mappo unhide <项目ID>
```

索引默认保存在 `~/.local/state/mappo/index.sqlite`（如本机存在旧版 `~/.local/state/awh/index.sqlite` 会在首次运行时自动复制迁移），可用 `--index-file` 指定其他位置。索引按 `--agent` 和完整的 `--path` 参数组合保存，查询时带同一组扫描参数。两者组合时，列表包含该 Agent 的记录和指定目录的扫描结果。`--no-index` 允许单次扫描跳过保存。索引记录目录、活动时间和来源，默认文件权限为当前用户读写。

最新扫描仍能找到的项目标为 `observed`。同范围的后续扫描没有发现的项目保留为 `historical`，并保留最后一次观察时间和证据。扫描异常也可能导致项目进入历史视图，请结合该范围的 `doctor --indexed` 检查。路径状态取自最近一次扫描，重新运行 `scan` 可刷新。手动关联独立保存，`link` 可将迁移前后的路径标为相关项目，各自的路径、ID 和证据继续可追溯。

## macOS 权限

扫描以调用者身份读取当前账号可访问的 Agent 索引及显式指定的目录。常规运行无需 sudo、辅助功能权限或完全磁盘访问权限。受 macOS 隐私保护的目录（例如桌面、文稿、下载、iCloud Drive 或网络卷）可能要求运行 CLI 的终端或宿主应用获得对应访问权限。访问被拒绝时，扫描会跳过受限来源，继续处理其余可读数据。用 `mappo doctor` 查看实时受限来源，或用 `mappo doctor --indexed` 查看上次扫描的诊断。按实际需要在系统设置的「隐私与安全性 → 文件与文件夹」授予对应访问权限。[Apple 平台安全指南](https://support.apple.com/guide/security/controlling-app-access-to-files-secddd1d86a6/web)

`--path` 可重复传入，只遍历指定目录，识别 Git 与常见项目清单，跳过依赖、构建产物和递归符号链接。默认扫描不会递归搜索主目录。输出只包含项目和来源元数据；CodeBuddy 每份会话只检查首尾事件（两端各限 64 KiB）。历史条目和编辑器 History 索引均在本机解析，只输出目录、时间和来源。

运行脱敏样本测试可用 `python3 -B -m unittest -v`。

开发适配器时，在 `src/mappo/providers/registry.py` 登记已知安装位置和只读来源，并在 `src/mappo/providers/` 对应适配器模块中通过 `Inventory.add` 添加记录并保留来源（目录分层见 [docs/architecture.md](docs/architecture.md)）。用临时目录或脱敏样本验证缺失、无权限和格式变化。发行文件由 `scripts/build_release.py` 构建，可在源码目录外运行 `mappo --version` 和 `mappo scan` 验收。

## 本地 Web UI（`mappo web`）

```sh
mappo web
mappo web --port 4318
mappo web --no-open
mappo web --agent codex
```

`mappo web` 启动仅绑定 `127.0.0.1` 的本地服务并自动打开浏览器，按 `Ctrl+C` 停止。Web UI 与 CLI 共用扫描器、检索逻辑和同一份 SQLite 索引（`~/.local/state/mappo/index.sqlite`）。

- **三视图与分层筛选**：
  - **项目**：按时间分组（近 7 天 / 近 30 天 / 30 天以上沉睡）展示本地项目、收藏、远程工作区与待整理项，自动识别 Git 分支、远端仓库与同仓库多副本；
  - **Agent**：展示活跃的 Coding Agent、编辑器与编辑器扩展，以及折叠的无记录工具；
  - **整理（Hygiene）**：按需扫描依赖与构建产物（`node_modules`、`.venv`、`.next`、上下文感知的 `dist`/`build`/`target` 等）、聚合「同仓库多副本」与「临时沙箱」，执行清理前自动检查 Git 未提交/未推送改动与 `.env` 文件，所有清理均安全移入 macOS 废纸篓而非 `rm -rf`。
- **快速启动与桌面 Agent 打开**：仅对服务端实时确认存在的本地目录提供用编辑器（Cursor / CodeBuddy CN / VS Code / Trae）、桌面 Agent（Codex / Claude / WorkBuddy / Antigravity / DeepSeek Harness）、终端或访达打开，并支持打开 Git 远程仓库页；变更接口均校验本机 Host、Origin 与一次性会话令牌。
- **收藏、标签、隐藏与关联**：所有操作实时写入本地索引，与 `mappo star`/`tag`/`hide`/`link` 互通；隐藏支持底部撤销和「已隐藏」视图恢复。
- **快捷键与主题**：支持 `/` 或 `Cmd+K` 搜索、`↑`/`↓` 选择、`Enter` 看详情、`S` 收藏、`E` 用默认编辑器/Agent 打开、`T` 在终端中打开、`O` 在访达中打开、`R` 重新扫描、`Esc` 逐层关闭，自动适配浅色/深色与系统「减少动态效果」。

## 自定义本地工具配置（可选）

如果希望在本机额外识别未内置的私有或内部编辑器扩展/工具，可在 `~/.config/mappo/custom_tools.json`（或通过环境变量 `MAPPO_CUSTOM_TOOLS` 指定路径）添加配置：

```json
{
  "extensions": {
    "my-ext": {
      "name": "My Extension",
      "extension_id": "publisher.my-extension",
      "data_dir": ".my-extension"
    }
  },
  "products": {
    "my-agent": {
      "name": "My Agent",
      "data_dir": ".my-agent",
      "limit": "仅探测本地目录，暂未解析项目索引"
    }
  }
}
```

## 许可证

本项目采用 [MIT License](LICENSE) 开源。个人自用起家，按需维护，欢迎提交 Bug 修复与新工具适配器 PR。
