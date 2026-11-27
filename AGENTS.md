# AGENTS.md

在 `mappo` 仓库中工作的 Coding Agent 工程规范。目录结构与模块职责见 `docs/architecture.md`。

## 核心不变量（硬性约束）

1. **零外部依赖**
   - `src/mappo/` 下只允许使用 **Python 3.9+ 标准库**，禁止引入第三方 PyPI 依赖。
   - `apps/web/` 下为纯 HTML、CSS 与原生 JS，**无构建步骤、无打包器**。
   - 必须同时兼容源码直接运行（`./mappo`）与单文件 zipapp 分发（`dist/mappo.pyz`）。

2. **严格的单向分层依赖**
   - `core/` 与 `providers/` **严禁**导入 `host/` 或 `storage/`。
   - `providers/` 只能依赖 `core/` 与 `providers/registry.py`。
   - `sessions/` 保持只读、按需解析，**严禁将聊天正文持久化写入 `index.sqlite`**。
   - `apps/web/` 只能通过本地 HTTP JSON 接口与 `src/mappo/host/web_server.py` 通信。

3. **只读 WAL 安全 SQLite 与本地隐私边界**
   - 读取第三方 Agent 的 SQLite 数据库时，必须统一使用 `mappo.core.io.query()`（只读、WAL 安全，禁止在第三方应用目录留下 `-wal`/`-shm` 临时文件）。
   - 禁止发起任何外网请求或遥测上报。
   - Web 服务仅绑定 `127.0.0.1`；所有变更接口（`POST`/`PATCH`/`DELETE`）必须经过 `_check_mutation_guard()` 校验（`Host`、`Origin` 与单次会话 `X-Mappo-Token`）。

4. **只做安全清理（严禁 `rm -rf`）**
   - 所有清理删除动作必须通过严格路径校验（`validate_artifact_target` / `validate_project_trash_target`：拒绝软链接、主目录/系统路径及白名单外目录），并统一通过 `move_to_trash` 移入系统废纸篓。

5. **开源脱敏边界**
   - 严禁在代码、测试、文档、截图中提交公司内部工具名、内网域名、真实个人用户名或专有仓库名。
   - 私有/内部工具只能配置在用户本机的 `~/.config/mappo/custom_tools.json`（`MAPPO_CUSTOM_TOOLS`），不得写入 `src/mappo/providers/registry.py`。
   - 所有单元测试必须使用隔离临时目录与脱敏 fixture。

## 新增或修改代码规范

- **新增前端静态资源**（`apps/web/js/*.js`、`apps/web/css/*.css`、`apps/web/icons/*`）：必须在 `src/mappo/host/web_server.py` 注册路由，确保 `scripts/build_release.py` 将其打入 `mappo/_web_assets/`，并在 `tests/test_web.py` 中验证源码与 zipapp 双模式加载。
- **新增 Agent Provider**：在 `src/mappo/providers/registry.py` 注册元数据，在 `src/mappo/providers/` 实现只读发现逻辑，经 `src/mappo/providers/__init__.py` 导出并接入 `src/mappo/core/engine.py`，同时在 `tests/test_scanner.py` 补充临时目录 fixture 测试。
- **文档同步与语言约定**：本项目以**中文为主**（主文档为 `README.md`，英文版为 `README.en.md`）。新增或变更命令、参数、支持的工具时，需同步更新 `README.md`、`README.en.md` 与 `skills/mappo/SKILL.md`。

## 提交前验证命令

完成任意代码改动后执行（传 `-B` 避免生成 `.pyc`）：

```sh
# 1. 前端 JS 语法检查（改动 apps/web/ 时）
for f in apps/web/app.js apps/web/js/*.js; do node --check "$f" || exit 1; done

# 2. 全量单元测试（scanner、sessions、web、zipapp）
python3 -B -m unittest -v

# 3. 单文件 zipapp 构建验证（改动打包逻辑或静态资源时）
python3 -B scripts/build_release.py dist/mappo.pyz
```

## Git 约定

- 保持提交聚焦，使用常规前缀（`feat:`、`fix:`、`docs:`、`refactor:`、`test:`）。
- 不要提交 `dist/` 构建产物或本地 SQLite 状态文件。
