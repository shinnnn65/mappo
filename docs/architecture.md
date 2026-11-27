# 目录架构说明

本项目参考 `deepseek-harness` 的顶层 `apps/` 与核心分层思路，同时适配纯 Python 标准库与单文件 `dist/mappo.pyz` 分发形态。

## 顶层布局

```text
mappo/
├── mappo                       # 根目录可执行入口（保持 ./mappo 直接运行）
├── pyproject.toml              # Python 包配置、命令行入口与 ruff 规则
├── apps/
│   ├── cli/
│   │   └── main.py             # CLI 独立启动入口
│   └── web/                    # Web 前端应用（mappo web 托管的静态资源）
│       ├── index.html
│       ├── app.css
│       ├── app.js
│       ├── css/                # 拆分样式模块（如抽屉与会话面板 drawer.css）
│       ├── js/                 # 拆分前端模块（detail-drawer.js、sessions-panel.js）
│       └── icons/              # 品牌图标（mappo.svg）与各 Agent/编辑器图标
├── src/
│   └── mappo/
│       ├── __init__.py         # 版本常量 APP_VERSION
│       ├── __main__.py         # 支持 python3 -m mappo
│       ├── cli.py              # CLI 参数解析与命令分发
│       ├── core/               # 领域模型、只读 IO/SQLite 工具与扫描聚合引擎
│       ├── providers/          # 各 Agent、编辑器、扩展及文件系统只读适配器
│       ├── sessions/           # 按需只读跨 Agent 会话解析与上下文交接（不入库正文）
│       ├── storage/            # 每用户 SQLite 本地索引、手工关联与元数据
│       ├── query/              # 列表检索、时间解析与组合过滤
│       └── host/               # 本地 HTTP 服务、API 安全校验与前端资源加载
├── scripts/
│   └── build_release.py        # 构建单文件发行包 dist/mappo.pyz
├── tests/                      # 脱敏样本与 Web/打包单元测试
├── docs/                       # 架构与演进文档
└── dist/                       # 单文件发行产物
```

## 分层与依赖方向

| 层级 | 目录 | 职责 |
| --- | --- | --- |
| 应用壳 | `apps/cli/`、`apps/web/` | CLI 与浏览器前端入口。`apps/web/` 与 Python 核心解耦，后续可按需拆分前端模块或引入独立构建流程。 |
| 命令层 | `src/mappo/cli.py` | 解析子命令与过滤参数，调用核心、索引、查询与本地 HTTP 服务。 |
| 本地托管层 | `src/mappo/host/` | 绑定 `127.0.0.1` 提供只读与变更 API、Host/Origin/Token 校验，以及源码/zipapp 双模式静态资源加载。 |
| 存储与查询层 | `src/mappo/storage/`、`src/mappo/query/` | 维护 `~/.local/state/mappo/index.sqlite` 快照、历史项目、收藏/标签/隐藏状态，以及统一的列表过滤与排序逻辑。 |
| 核心与适配器层 | `src/mappo/core/`、`src/mappo/providers/`、`src/mappo/sessions/` | 负责路径规范化、诊断原因码分类、只读 JSON/SQLite 读取、按工具拆分的只读工作区发现适配器，以及按需读取的跨 Agent 会话与交接导出（会话正文不写入 `index.sqlite`）。 |

依赖保持单向流动。`apps/cli` 与 `cli` 依赖 `host`、`storage`、`query` 和 `core`，`core/engine` 调度 `providers`，各 `providers` 仅依赖 `core` 与 `providers/registry`，`apps/web` 通过本机 HTTP API 与 `host` 通信。

## 前端资源双模式加载

- **源码运行模式** `mappo.host.assets.load_asset` 直接读取仓库顶层 `apps/web/`，修改页面或样式后刷新浏览器即可生效，无需构建步骤。
- **单文件发行模式** `scripts/build_release.py` 将 `src/mappo/` 与 `apps/web/` 打包进 `dist/mappo.pyz`（资源位于归档内 `mappo/_web_assets/`），运行时通过 `pkgutil.get_data` 直接从归档内读取，复制到仓库外部目录仍可独立运行 `mappo web`。

## 新增 Agent 适配器方式

1. 在 `src/mappo/providers/registry.py` 的 `PRODUCTS`（以及需要时的 `EDITORS`、`EXTENSIONS` 或 `LIMITS`）登记工具标识与本地数据位置。
2. 在 `src/mappo/providers/` 新增或更新对应只读适配器模块，通过 `Inventory.add` 写入记录并保留来源与活动时间证据。
3. 在 `src/mappo/providers/__init__.py` 导出并在 `src/mappo/core/engine.py` 接入调度。
4. 在 `tests/test_scanner.py` 添加脱敏临时目录测试用例。
