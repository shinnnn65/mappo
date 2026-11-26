(() => {
  "use strict";

  const TOKEN = document.querySelector('meta[name="mappo-token"]')?.content || "";
  const ACTIONABLE_CODES = new Set(["permission_denied", "busy", "invalid_source", "read_error"]);

  const STATUS_META = {
    directory: { label: "本地目录可用", short: "", pill: "is-ok" },
    remote: { label: "远程路径（SSH 或远程环境）", short: "远程", pill: "is-remote" },
    missing: { label: "原路径已不存在，可能已移动、重命名或删除", short: "路径缺失", pill: "is-missing" },
    inaccessible: { label: "当前账号缺少该目录的读取权限", short: "无权限", pill: "is-error" },
    "not-directory": { label: "路径当前指向文件，无法作为目录打开", short: "非目录", pill: "is-error" },
  };

  const AGENT_STATUS_META = {
    ok: { label: "正常", pill: "is-ok", desc: "已读取全部可用发现记录" },
    partial: { label: "部分缺失", pill: "is-partial", desc: "已读取部分发现记录，个别来源不可读或已缺失" },
    empty: { label: "暂无记录", pill: "is-neutral", desc: "已检查本机数据源，尚无归属该工具的发现记录" },
    unsupported: { label: "暂未支持", pill: "is-neutral", desc: "已探测到工具，当前版本尚无对应的发现适配器" },
    missing_source: { label: "未找到索引", pill: "is-neutral", desc: "预期的本地索引或配置尚未生成或已清理" },
    permission_denied: { label: "权限受限", pill: "is-error", desc: "系统拒绝读取，需在隐私与安全性中授权" },
    busy: { label: "文件占用中", pill: "is-missing", desc: "工具数据库正在写入锁定，稍后刷新重试" },
    invalid_source: { label: "读取异常", pill: "is-error", desc: "数据格式变化或文件损坏" },
    read_error: { label: "读取异常", pill: "is-error", desc: "读取本地数据源时出现错误" },
  };

  const KIND_LABEL = {
    native: "原生登记",
    inferred: "历史推导",
    filesystem: "目录扫描",
  };

  const GIT_KIND_META = {
    repo: { label: "Git 仓库", short: "Git", pill: "is-git" },
    subdir: { label: "Git 子目录", short: "Git 子目录", pill: "is-git" },
    worktree: { label: "Git Worktree", short: "工作树", pill: "is-git" },
    submodule: { label: "Git 子模块", short: "子模块", pill: "is-git" },
    none: { label: "纯本地目录", short: "纯本地", pill: "is-local-only" },
  };

  const DIAG_GUIDANCE = {
    permission_denied: "可在 macOS「系统设置 → 隐私与安全性 → 文件与文件夹」为运行 mappo 的终端授权后点击刷新。",
    busy: "对应工具正在写入本地数据库，等待片刻后点击右上角刷新即可重试。",
    invalid_source: "源文件可能已损坏或格式变更，不影响其他可读发现记录的展示。",
    read_error: "读取该文件失败，可检查文件权限或磁盘状态后重试。",
  };

  const ICONS = {
    starOutline: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linejoin="round"><path d="m10 2.7 2.2 4.5 5 .7-3.6 3.5.85 4.9L10 14l-4.45 2.3.85-4.9-3.6-3.5 5-.7L10 2.7Z"/></svg>',
    starFilled: '<svg viewBox="0 0 20 20" width="15" height="15" fill="currentColor" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"><path d="m10 2.7 2.2 4.5 5 .7-3.6 3.5.85 4.9L10 14l-4.45 2.3.85-4.9-3.6-3.5 5-.7L10 2.7Z"/></svg>',
    folder: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><path d="M2.8 6.2A1.7 1.7 0 0 1 4.5 4.5h3.3l1.6 1.8h6.1a1.7 1.7 0 0 1 1.7 1.7v6.3a1.7 1.7 0 0 1-1.7 1.7H4.5a1.7 1.7 0 0 1-1.7-1.7V6.2Z"/></svg>',
    copy: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="7" width="9.5" height="9.5" rx="2"/><path d="M4.8 13H4.5a1.5 1.5 0 0 1-1.5-1.5v-7A1.5 1.5 0 0 1 4.5 3h7A1.5 1.5 0 0 1 13 4.5v.3"/></svg>',
    check: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="m4.5 10.5 3.6 3.6 7.4-8"/></svg>',
    tag: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 9.8V4.8A1.3 1.3 0 0 1 4.8 3.5h5l6.6 6.6a1.3 1.3 0 0 1 0 1.8l-4.5 4.5a1.3 1.3 0 0 1-1.8 0L3.5 9.8Z"/><circle cx="7.2" cy="7.2" r="1" fill="currentColor" stroke="none"/></svg>',
    eyeOff: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l14 14M8.5 5.2A7 7 0 0 1 10 5c4.2 0 7.2 3.8 7.6 5-.2.6-.9 1.8-2.1 2.9M12.2 14.6A6.8 6.8 0 0 1 10 15c-4.2 0-7.2-3.8-7.6-5 .3-.8 1.4-2.4 3.2-3.6"/></svg>',
    eye: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><path d="M2.4 10S5.5 5 10 5s7.6 5 7.6 5-3.1 5-7.6 5-7.6-5-7.6-5Z"/><circle cx="10" cy="10" r="2.2"/></svg>',
    close: '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="m4 4 8 8M12 4l-8 8"/></svg>',
    chevron: '<svg class="disclosure-chevron" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="m6 3.5 4.5 4.5L6 12.5"/></svg>',
    sun: '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="10" cy="10" r="3.4"/><path d="M10 2.5v1.8M10 15.7v1.8M2.5 10h1.8M15.7 10h1.8M4.7 4.7l1.3 1.3M14 14l1.3 1.3M15.3 4.7 14 6M6 14l-1.3 1.3"/></svg>',
    moon: '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M15.9 12.6A6.5 6.5 0 0 1 7.4 4.1a6.6 6.6 0 1 0 8.5 8.5Z"/></svg>',
    autoTheme: '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="10" r="6.8"/><path d="M10 3.2v13.6A6.8 6.8 0 0 1 10 3.2Z" fill="currentColor" opacity="0.28"/></svg>',
    gitBranch: '<svg class="git-branch-icon" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="4.5" cy="3.5" r="1.75"/><circle cx="4.5" cy="12.5" r="1.75"/><circle cx="11.5" cy="5.5" r="1.75"/><path d="M4.5 5.25v5.5M11.5 7.25c0 2.4-2.2 3-7 3"/></svg>',
    terminal: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><rect x="2.8" y="3.8" width="14.4" height="12.4" rx="2.2"/><path d="m6.5 8 2.6 2.2-2.6 2.2M10.8 12.6h2.8"/></svg>',
    externalLink: '<svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4.2h4.8V9M15.6 4.4 9.2 10.8M14 11.4v3a1.6 1.6 0 0 1-1.6 1.6H5.6A1.6 1.6 0 0 1 4 14.4V7.6A1.6 1.6 0 0 1 5.6 6h3"/></svg>',
  };

  const AGENT_ICONS = {
    codex: { file: "codex.png" },
    cursor: { file: "cursor.png" },
    codebuddy: { file: "codebuddy.png" },
    workbuddy: { file: "workbuddy.png" },
    claude: { file: "claude.png" },
    vscode: { file: "vscode.png" },
    trae: { file: "trae.png" },
    dsh: { file: "dsh.png" },
    copilot: { file: "copilot.png" },
    antigravity: { file: "antigravity.svg", pad: true, bg: "#FFFFFF" },
    opencode: { file: "opencode.png" },
    gemini: { file: "gemini.svg", pad: true, bg: "#FFFFFF" },
    continue: { file: "continue.png", shape: "circle" },
    codegeex: { file: "codegeex.png" },
    pencil: { file: "pencil.png" },
    stagewise: { file: "stagewise.png", shape: "circle" },
    openclaw: { file: "openclaw.svg", pad: true, bg: "#FFFFFF" },
  };

  const FALLBACK_BRAND_COLORS = [
    "#3B82F6",
    "#6366F1",
    "#0EA5E9",
    "#10B981",
    "#F59E0B",
    "#EC4899",
    "#8B5CF6",
    "#14B8A6",
  ];

  function fallbackBrandColor(agentId) {
    let hash = 0;
    const str = String(agentId || "");
    for (let i = 0; i < str.length; i += 1) {
      hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
    }
    return FALLBACK_BRAND_COLORS[hash % FALLBACK_BRAND_COLORS.length];
  }

  function agentMonogram(agentId) {
    const name = agentDisplayName(agentId).trim();
    const words = name.split(/[\s_-]+/).filter(Boolean);
    if (words.length >= 2) {
      return (words[0][0] + words[1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase() || "?";
  }

  function renderAgentIconHtml(agentId, size = "sm") {
    const icon = AGENT_ICONS[agentId];
    if (icon) {
      const classes = ["agent-icon", `is-${size}`, "has-img"];
      if (icon.shape === "circle") classes.push("is-circle");
      if (icon.pad) classes.push("has-pad");
      const style = icon.bg ? ` style="background:${icon.bg}"` : "";
      return `<span class="${classes.join(" ")}"${style} aria-hidden="true"><img class="agent-icon-img" src="/assets/icons/${escapeHtml(
        icon.file
      )}" alt="" decoding="async" draggable="false"></span>`;
    }
    const style = `background:${fallbackBrandColor(agentId)};color:#FFFFFF`;
    return `<span class="agent-icon is-${size} is-fallback" style="${style}" aria-hidden="true"><span class="agent-icon-mono">${escapeHtml(
      agentMonogram(agentId)
    )}</span></span>`;
  }

  function agentTooltipText(agentId) {
    const name = agentDisplayName(agentId);
    const ext = isExtensionAgent(agentId);
    if (ext) {
      const hosts = extensionHosts(agentId)
        .map((h) => h.display_name)
        .filter(Boolean);
      return hosts.length > 0
        ? `${name} · 扩展 (${hosts.join("、")})`
        : `${name} · 编辑器扩展`;
    }
    return name;
  }

  function loadSavedLayoutMode() {
    try {
      const saved =
        localStorage.getItem("mappo-layout-mode") ||
        localStorage.getItem("awh-layout-mode");
      if (saved === "card" || saved === "list") return saved;
    } catch (_) {}
    return "card";
  }

  function saveLayoutMode(mode) {
    try {
      localStorage.setItem("mappo-layout-mode", mode);
    } catch (_) {}
  }

  const state = {
    loaded: false,
    scanning: false,
    data: null,
    projectById: new Map(),
    projectByPath: new Map(),
    workspaceById: new Map(),
    agentById: new Map(),
    agentNameById: new Map(),
    remoteGroupByKey: new Map(),
    view: "projects",
    layoutMode: loadSavedLayoutMode(),
    scopeFilter: "local",
    gitFilter: "",
    search: "",
    timeRange: "",
    sortBy: "recent",
    selectedAgent: null,
    selectedTag: null,
    selectedDuplicateKey: null,
    duplicateGroupByKey: new Map(),
    duplicateGroupByProjectId: new Map(),
    dormantGroupCollapsed: false,
    hygiene: null,
    hygieneScanning: false,
    organizeTab: "slim",
    organizeDormantDays: 7,
    selectedArtifacts: new Map(),
    trashModal: {
      open: false,
      mode: null,
      loading: false,
      items: [],
      projectId: null,
      gitCheck: null,
      submitting: false,
      confirmedCaution: false,
      error: null,
    },
    selectedProjectId: null,
    selectedRemoteGroupKey: null,
    focusedProjectId: null,
    lastTriggerEl: null,
    diagOpen: false,
    diagAgentFilter: null,
    inactiveAgentsOpen: false,
    sandboxExpanded: false,
    expandedAgentStacks: new Set(),
    linkPickerOpen: false,
    linkPickerQuery: "",
    restoredId: null,
    pendingHideTimers: new Map(),
    buttonTimers: new WeakMap(),
    lastCounts: {
      local: null,
      favorite: null,
      remote: null,
      attention: null,
      hidden: null,
    },
    popoverProjectId: null,
    toastHandle: null,
  };

  const el = {
    topbar: document.querySelector(".topbar"),
    appShell: document.getElementById("app-shell"),
    topProgress: document.getElementById("top-progress"),
    scopePill: document.getElementById("scope-pill"),
    viewSegmented: document.getElementById("view-segmented"),
    syncStatus: document.getElementById("sync-status"),
    syncLabel: document.getElementById("sync-label"),
    btnRefresh: document.getElementById("btn-refresh"),
    btnDiagnostics: document.getElementById("btn-diagnostics"),
    diagDot: document.getElementById("diag-dot"),
    btnTheme: document.getElementById("btn-theme"),
    themeIcon: document.getElementById("theme-icon"),
    viewProjects: document.getElementById("view-projects"),
    viewAgents: document.getElementById("view-agents"),
    viewOrganize: document.getElementById("view-organize"),
    organizeRoot: document.getElementById("organize-root"),
    tabBtnOrganize: document.getElementById("tab-btn-organize"),
    searchInput: document.getElementById("search-input"),
    searchClear: document.getElementById("search-clear"),
    searchKbd: document.getElementById("search-kbd"),
    scopeFilters: document.getElementById("scope-filters"),
    countLocal: document.getElementById("count-local"),
    countFavorite: document.getElementById("count-favorite"),
    countRemote: document.getElementById("count-remote"),
    countAttention: document.getElementById("count-attention"),
    btnAttentionScope: document.getElementById("btn-attention-scope"),
    countHidden: document.getElementById("count-hidden"),
    btnHiddenView: document.getElementById("btn-hidden-view"),
    gitFilterWrap: document.getElementById("git-filter-wrap"),
    gitFilter: document.getElementById("git-filter"),
    timeFilter: document.getElementById("time-filter"),
    sortSelect: document.getElementById("sort-select"),
    viewModeToggle: document.getElementById("view-mode-toggle"),
    chipsCollapse: document.getElementById("chips-collapse"),
    chipsBar: document.getElementById("active-chips-bar"),
    scopeContextBar: document.getElementById("scope-context-bar"),
    scopeContextText: document.getElementById("scope-context-text"),
    scopeContextMeta: document.getElementById("scope-context-meta"),
    btnScopeReset: document.getElementById("btn-scope-reset"),
    projectsContainer: document.getElementById("projects-container"),
    agentsSummary: document.getElementById("agents-summary"),
    agentsPrimarySection: document.getElementById("agents-primary-section"),
    agentsPrimaryMeta: document.getElementById("agents-primary-meta"),
    agentsPrimaryGrid: document.getElementById("agents-primary-grid"),
    agentsExtensionsSection: document.getElementById("agents-extensions-section"),
    agentsExtensionsMeta: document.getElementById("agents-extensions-meta"),
    agentsExtensionsGrid: document.getElementById("agents-extensions-grid"),
    agentsEmpty: document.getElementById("agents-empty"),
    agentsInactiveCard: document.getElementById("agents-inactive-card"),
    btnInactiveAgents: document.getElementById("btn-inactive-agents"),
    inactiveAgentsTitle: document.getElementById("inactive-agents-title"),
    inactiveAgentsMeta: document.getElementById("inactive-agents-meta"),
    inactiveAgentsPanel: document.getElementById("inactive-agents-panel"),
    agentsInactiveList: document.getElementById("agents-inactive-list"),
    drawerScrim: document.getElementById("drawer-scrim"),
    drawer: document.getElementById("detail-drawer"),
    drawerContent: document.getElementById("drawer-content"),
    tagPopover: document.getElementById("tag-popover"),
    diagScrim: document.getElementById("diag-scrim"),
    diagModal: document.getElementById("diag-modal"),
    diagSubtitle: document.getElementById("diag-modal-subtitle"),
    diagFilterBar: document.getElementById("diag-filter-bar"),
    diagBody: document.getElementById("diag-modal-body"),
    btnCloseDiag: document.getElementById("btn-close-diag"),
    trashScrim: document.getElementById("trash-scrim"),
    trashModal: document.getElementById("trash-modal"),
    trashTitle: document.getElementById("trash-modal-title"),
    trashSubtitle: document.getElementById("trash-modal-subtitle"),
    trashBody: document.getElementById("trash-modal-body"),
    trashFooter: document.getElementById("trash-modal-footer"),
    btnCloseTrash: document.getElementById("btn-close-trash"),
    toastHost: document.getElementById("toast-host"),
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function shortenPath(rawPath) {
    const home = state.data?.home_dir || "";
    if (home && rawPath.startsWith(home + "/")) {
      return "~" + rawPath.slice(home.length);
    }
    if (home && rawPath === home) return "~";
    return rawPath;
  }

  function formatDiagReason(reason, code) {
    if (!reason) return (AGENT_STATUS_META[code] || {}).desc || "";
    const text = String(reason);
    if (/\[Errno 2\]\s*No such file or directory/i.test(text)) {
      return "目标索引或配置文件已不存在（通常由历史记录清理或文件移动引起）";
    }
    if (/\[Errno 13\]\s*Permission denied/i.test(text)) {
      return "操作系统拒绝读取该文件或目录，需授予文件访问权限";
    }
    const home = state.data?.home_dir || "";
    return home ? text.split(home).join("~") : text;
  }

  function projectName(project) {
    if (project.names && project.names.length > 0 && project.names[0]) {
      return project.names[0];
    }
    const parts = (project.path || "").split("/").filter(Boolean);
    return parts[parts.length - 1] || project.path || project.id;
  }

  function agentDisplayName(agentId) {
    return state.agentNameById.get(agentId) || agentId;
  }

  const EDITOR_AGENTS = new Set(["cursor", "codebuddy", "trae", "vscode"]);
  const EXTENSION_AGENTS = new Set([
    "copilot",
    "stagewise",
    "continue",
    "codegeex",
    "pencil",
  ]);
  const CATEGORY_LABEL = {
    coding_agent: "Coding Agent",
    editor: "VS Code 系编辑器",
    extension: "编辑器扩展",
  };
  const HOST_EDITOR_NAMES = [
    ["/Application Support/Cursor/", "Cursor"],
    ["/Application Support/CodeBuddy CN/", "CodeBuddy CN"],
    ["/Application Support/Code/", "Visual Studio Code"],
    ["/Application Support/Trae/", "Trae"],
  ];

  function agentCategory(agentId) {
    const entry = state.agentById.get(agentId);
    if (entry && entry.category) return entry.category;
    if (EDITOR_AGENTS.has(agentId)) return "editor";
    if (EXTENSION_AGENTS.has(agentId)) return "extension";
    return "coding_agent";
  }

  function isExtensionAgent(agentId) {
    return agentCategory(agentId) === "extension";
  }

  function extensionHosts(agentId) {
    const entry = state.agentById.get(agentId);
    return Array.isArray(entry?.host_editors) ? entry.host_editors : [];
  }

  function detectHostEditor(sources) {
    for (const src of sources) {
      for (const [marker, label] of HOST_EDITOR_NAMES) {
        if (src.includes(marker)) return label;
      }
    }
    return null;
  }

  function describeDiscoveryRecord(record) {
    const agent = record.agent || "";
    const agentName = agentDisplayName(agent);
    const kind = record.kind || "";
    const kindLabel = KIND_LABEL[kind] || kind || "发现记录";
    const kindTone =
      kind === "native" ? "is-native" : kind === "filesystem" ? "is-filesystem" : "is-inferred";
    const sources = record.sources || [];
    const roots = record.roots || [];
    const resource = record.resource || "";
    const isMultiRoot = roots.length > 1;
    const isRemote = resource.startsWith("vscode-remote://");
    const isWorkspaceConfig =
      isMultiRoot ||
      /\.code-workspace$/i.test(resource) ||
      /\/Workspaces\/[^/]+\/workspace\.json$/i.test(resource);
    const hasSource = (frag) => sources.some((s) => s.includes(frag));

    if (agent === "filesystem" || kind === "filesystem") {
      const marker = sources[0] ? sources[0].split("/").pop() : "";
      return {
        nativeTitle: "目录扫描",
        nativeNameLabel: "目录名",
        hostSummary: marker ? `识别标记：${marker}` : "",
        kindLabel,
        kindTone,
      };
    }

    if (agent === "codex") {
      if (record.native_type === "chatgpt_project") {
        return {
          nativeTitle: "ChatGPT 项目镜像",
          nativeNameLabel: "原生项目名",
          hostSummary: "",
          kindLabel,
          kindTone,
        };
      }
      if (hasSource("#saved-workspace-roots")) {
        return {
          nativeTitle: "Codex 已保存目录",
          nativeNameLabel: "目录名",
          hostSummary: "",
          kindLabel,
          kindTone,
        };
      }
      if (kind === "native") {
        return {
          nativeTitle: "Codex 项目",
          nativeNameLabel: "原生项目名",
          hostSummary: "",
          kindLabel,
          kindTone,
        };
      }
      return {
        nativeTitle: "Codex 会话工作目录",
        nativeNameLabel: "目录名",
        hostSummary: "",
        kindLabel,
        kindTone,
      };
    }

    if (EDITOR_AGENTS.has(agent)) {
      if (kind === "native") {
        const unit = isMultiRoot
          ? "多根工作区"
          : isWorkspaceConfig
          ? isRemote
            ? "远程工作区"
            : "工作区"
          : isRemote
          ? "远程文件夹"
          : "文件夹";
        return {
          nativeTitle: `${agentName} ${unit}`,
          nativeNameLabel: isWorkspaceConfig ? "原生工作区名" : "文件夹名",
          hostSummary: "",
          kindLabel,
          kindTone,
        };
      }
      const isHistoryProject =
        hasSource("history.jsonl#project") &&
        !hasSource("#session.cwd") &&
        !hasSource("#first.cwd") &&
        !hasSource("#last.cwd");
      return {
        nativeTitle: `${agentName} ${isHistoryProject ? "历史项目" : "会话工作目录"}`,
        nativeNameLabel: "目录名",
        hostSummary: "",
        kindLabel,
        kindTone,
      };
    }

    if (hasSource("/User/workspaceStorage/") && hasSource("#")) {
      const hostName = detectHostEditor(sources);
      const hostUnit = isMultiRoot
        ? "多根工作区"
        : isWorkspaceConfig
        ? "工作区"
        : isRemote
        ? "远程文件夹"
        : "文件夹";
      return {
        nativeTitle: `${agentName} 扩展记录`,
        nativeNameLabel: isWorkspaceConfig ? "宿主工作区名" : "记录名称",
        hostSummary: hostName ? `来源编辑器：${hostName} · ${hostUnit}` : "",
        kindLabel,
        kindTone,
      };
    }

    if (agent === "claude") {
      return {
        nativeTitle: kind === "native" ? "Claude 项目" : "Claude 会话历史",
        nativeNameLabel: kind === "native" ? "原生项目名" : "目录名",
        hostSummary: "",
        kindLabel,
        kindTone,
      };
    }

    if (agent === "dsh" || agent === "workbuddy" || agent === "openclaw") {
      return {
        nativeTitle: kind === "native" ? `${agentName} 工作区` : `${agentName} 会话工作目录`,
        nativeNameLabel: kind === "native" ? "原生工作区名" : "目录名",
        hostSummary: "",
        kindLabel,
        kindTone,
      };
    }

    if (agent === "opencode" || agent === "gemini") {
      return {
        nativeTitle: `${agentName} 项目`,
        nativeNameLabel: "原生项目名",
        hostSummary: "",
        kindLabel,
        kindTone,
      };
    }

    if (agent === "antigravity") {
      if (kind === "native") {
        if (hasSource("#projectResources")) {
          return {
            nativeTitle: `${agentName} 项目`,
            nativeNameLabel: "原生项目名",
            hostSummary: "",
            kindLabel,
            kindTone,
          };
        }
        const unit = isMultiRoot
          ? "多根工作区"
          : isWorkspaceConfig
          ? "工作区"
          : "文件夹";
        return {
          nativeTitle: `Antigravity IDE ${unit}`,
          nativeNameLabel: isWorkspaceConfig ? "原生工作区名" : "文件夹名",
          hostSummary: "",
          kindLabel,
          kindTone,
        };
      }
      return {
        nativeTitle: `${agentName} 会话工作区`,
        nativeNameLabel: "目录名",
        hostSummary: "",
        kindLabel,
        kindTone,
      };
    }

    if (agent === "continue") {
      return {
        nativeTitle: `${agentName} 会话目录`,
        nativeNameLabel: "目录名",
        hostSummary: "",
        kindLabel,
        kindTone,
      };
    }

    return {
      nativeTitle: `${agentName} 发现记录`,
      nativeNameLabel: "记录名称",
      hostSummary: "",
      kindLabel,
      kindTone,
    };
  }

  function isAvailableStatus(status) {
    return status === "directory" || status === "remote";
  }

  function formatExactTime(iso) {
    if (!iso) return "暂无时间依据";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function formatRelativeTime(iso) {
    if (!iso) return "无时间记录";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    const now = Date.now();
    const diffSec = Math.floor((now - d.getTime()) / 1000);
    if (diffSec < 60) return "刚刚";
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin} 分钟前`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour} 小时前`;
    const pad = (n) => String(n).padStart(2, "0");
    const today = new Date();
    const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
    if (
      d.getFullYear() === yesterday.getFullYear() &&
      d.getMonth() === yesterday.getMonth() &&
      d.getDate() === yesterday.getDate()
    ) {
      return `昨天 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }
    if (d.getFullYear() === today.getFullYear()) {
      return `${d.getMonth() + 1} 月 ${d.getDate()} 日`;
    }
    return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月`;
  }

  function timeThresholdMs(range) {
    if (!range) return null;
    const hours = { "24h": 24, "7d": 24 * 7, "30d": 24 * 30 }[range];
    return hours ? Date.now() - hours * 3600 * 1000 : null;
  }

  async function api(url, options = {}) {
    const headers = Object.assign({}, options.headers || {});
    if (options.method && options.method !== "GET" && options.method !== "HEAD") {
      headers["X-Mappo-Token"] = TOKEN;
      if (options.body && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
      }
    }
    const res = await fetch(url, Object.assign({}, options, { headers }));
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(payload.error || `请求失败 (${res.status})`);
      err.code = payload.code || null;
      err.status = res.status;
      throw err;
    }
    return payload;
  }

  function formatBytes(bytes) {
    const num = Number(bytes) || 0;
    if (num <= 0) return "0 B";
    if (num < 1024) return `${num} B`;
    const kb = num / 1024;
    if (kb < 1024) return `${kb.toFixed(kb < 10 ? 1 : 0)} KB`;
    const mb = kb / 1024;
    if (mb < 1024) return `${mb.toFixed(mb < 10 ? 1 : 0)} MB`;
    const gb = mb / 1024;
    return `${gb.toFixed(gb < 10 ? 2 : 1)} GB`;
  }

  function daysSinceActivity(iso) {
    if (!iso) return null;
    const ms = Date.parse(iso);
    if (Number.isNaN(ms)) return null;
    return Math.max(0, Math.floor((Date.now() - ms) / (24 * 3600 * 1000)));
  }

  function isRecentlyActive(project, windowMs = 3600 * 1000) {
    if (!project?.last_activity) return false;
    const ms = Date.parse(project.last_activity);
    if (Number.isNaN(ms)) return false;
    return Date.now() - ms < windowMs;
  }

  function projectHygieneInfo(projectId) {
    return state.hygiene?.by_project?.[projectId] || null;
  }

  function projectReclaimableBytes(projectId) {
    return projectHygieneInfo(projectId)?.reclaimable_bytes || 0;
  }

  function projectArtifacts(projectId) {
    return projectHygieneInfo(projectId)?.artifacts || [];
  }

  function rebuildDuplicateLookups() {
    const groups = state.hygiene?.duplicate_groups || state.data?.duplicate_groups || [];
    state.duplicateGroupByKey = new Map();
    state.duplicateGroupByProjectId = new Map();
    for (const g of groups) {
      state.duplicateGroupByKey.set(g.remote_key, g);
      for (const pid of g.project_ids || []) {
        state.duplicateGroupByProjectId.set(pid, g);
      }
    }
    if (state.selectedDuplicateKey && !state.duplicateGroupByKey.has(state.selectedDuplicateKey)) {
      state.selectedDuplicateKey = null;
    }
  }

  function applyData(payload) {
    state.data = payload;
    state.loaded = true;
    state.projectById = new Map((payload.projects || []).map((p) => [p.id, p]));
    state.projectByPath = new Map((payload.projects || []).map((p) => [p.path, p]));
    state.workspaceById = new Map((payload.workspaces || []).map((w) => [w.id, w]));
    const visibleAgents = (payload.agents || []).filter((a) => a.status !== "unsupported");
    state.agentById = new Map(visibleAgents.map((a) => [a.agent, a]));
    state.agentNameById = new Map(visibleAgents.map((a) => [a.agent, a.display_name || a.agent]));
    if (payload.hygiene) {
      state.hygiene = payload.hygiene;
      state.hygieneScanning = Boolean(payload.hygiene.scanning);
      updateHygieneProgressUI();
      if (state.hygieneScanning) {
        scheduleHygienePoll();
      }
    }
    rebuildDuplicateLookups();
    updateScopePill();
    updateSyncStatus(payload.duration_ms);
    updateDiagnosticsIndicator();
    renderAll();
  }

  function updateScopePill() {
    const scope = state.data?.scope;
    if (!scope || (!scope.agent && (!scope.paths || scope.paths.length === 0))) {
      el.scopePill.hidden = true;
      return;
    }
    const parts = [];
    if (scope.agent) parts.push(agentDisplayName(scope.agent));
    if (scope.paths?.length) parts.push(`补扫 ${scope.paths.length} 目录`);
    el.scopePill.textContent = parts.join(" · ");
    el.scopePill.hidden = false;
  }

  function updateSyncStatus(durationMs) {
    el.syncStatus.classList.remove("is-scanning", "is-fresh");
    const iso = state.data?.indexed_at;
    if (!iso) {
      el.syncLabel.textContent = "尚未扫描";
      el.syncStatus.title = "";
      return;
    }
    if (typeof durationMs === "number") {
      const sec = (durationMs / 1000).toFixed(durationMs < 1000 ? 2 : 1);
      el.syncLabel.textContent = `刚刚更新 (${sec}s)`;
      void el.syncStatus.offsetWidth;
      el.syncStatus.classList.add("is-fresh");
    } else {
      el.syncLabel.textContent = `更新于 ${formatRelativeTime(iso)}`;
    }
    el.syncStatus.title = `上次索引时间：${formatExactTime(iso)}`;
  }

  function updateDiagnosticsIndicator() {
    const diags = state.data?.diagnostics || [];
    const actionable = diags.filter((d) => ACTIONABLE_CODES.has(d.code));
    if (actionable.length > 0) {
      el.diagDot.hidden = false;
      el.diagDot.classList.toggle(
        "is-critical",
        actionable.some((d) => d.code === "permission_denied")
      );
      el.btnDiagnostics.title = `扫描诊断（${actionable.length} 项建议处理，共 ${diags.length} 条）`;
    } else {
      el.diagDot.hidden = true;
      el.btnDiagnostics.title = `扫描诊断（${diags.length} 条常规说明）`;
    }
  }

  /* Theme Management */
  function getThemeMode() {
    return document.documentElement.dataset.themeMode || "auto";
  }

  function applyTheme(mode) {
    try {
      localStorage.setItem("mappo-theme", mode);
    } catch (_) {}
    const dark =
      mode === "dark" ||
      (mode === "auto" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    document.documentElement.dataset.themeMode = mode;
    const labels = { auto: "外观：跟随系统", light: "外观：浅色", dark: "外观：深色" };
    el.btnTheme.title = labels[mode] || "外观主题";
    el.btnTheme.setAttribute("aria-label", labels[mode] || "切换外观主题");
    el.themeIcon.innerHTML =
      mode === "light" ? ICONS.sun : mode === "dark" ? ICONS.moon : ICONS.autoTheme;
  }

  function cycleTheme() {
    const order = ["auto", "light", "dark"];
    const next = order[(order.indexOf(getThemeMode()) + 1) % order.length];
    applyTheme(next);
  }

  /* Segmented Control Sliding Pill */
  function positionSegmentedThumb(container) {
    const thumb = container.querySelector(".segmented-thumb");
    const active = container.querySelector(".segmented-btn.is-active");
    if (!thumb || !active) return;
    thumb.style.width = `${active.offsetWidth}px`;
    thumb.style.transform = `translate3d(${active.offsetLeft}px, 0, 0)`;
  }

  function switchView(nextView) {
    if (state.view === nextView) return;
    state.view = nextView;
    el.viewSegmented.querySelectorAll(".segmented-btn").forEach((btn) => {
      const active = btn.dataset.view === nextView;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    positionSegmentedThumb(el.viewSegmented);

    const showProjects = nextView === "projects";
    const showAgents = nextView === "agents";
    const showOrganize = nextView === "organize";
    el.viewProjects.hidden = !showProjects;
    el.viewAgents.hidden = !showAgents;
    if (el.viewOrganize) el.viewOrganize.hidden = !showOrganize;
    requestAnimationFrame(() => {
      el.viewProjects.classList.toggle("is-active", showProjects);
      el.viewAgents.classList.toggle("is-active", showAgents);
      if (el.viewOrganize) el.viewOrganize.classList.toggle("is-active", showOrganize);
    });
    if (!showProjects) {
      closeTagPopover();
    }
    if (showAgents) {
      renderAgentsView();
    } else if (showOrganize) {
      renderOrganizeView();
      if (!state.hygiene?.scanned && !state.hygieneScanning) {
        triggerHygieneScan();
      }
    } else {
      renderProjectsView();
    }
    updateHygieneProgressUI();
  }

  /* Filtering & Sorting */
  function assetKind(project) {
    return project.asset_kind || (project.status === "remote" ? "remote" : "project");
  }

  function isLocalProject(project) {
    return !project.hidden && assetKind(project) === "project" && project.status === "directory";
  }

  function isAttentionProject(project) {
    return !project.hidden && assetKind(project) === "project" && project.status !== "directory";
  }

  function isSandboxProject(project) {
    return !project.hidden && assetKind(project) === "sandbox";
  }

  function isRemoteProject(project) {
    return !project.hidden && assetKind(project) === "remote";
  }

  function gitInfo(project) {
    return project && project.git && typeof project.git === "object" ? project.git : null;
  }

  function formatGitRemoteShort(url) {
    if (!url) return "";
    let clean = String(url).trim().replace(/\/+$/, "").replace(/\.git$/i, "");
    const scp = clean.match(/^(?:[^@]+@)?([^:\/]+):(.+)$/);
    if (scp && !clean.includes("://")) {
      return `${scp[1]}/${scp[2].replace(/^\/+/, "")}`;
    }
    try {
      const parsed = new URL(clean);
      const host = parsed.hostname;
      const path = parsed.pathname.replace(/^\/+/, "");
      return host && path ? `${host}/${path}` : host || clean;
    } catch (_) {
      return clean.replace(/^https?:\/\//i, "");
    }
  }

  function matchesGitFilter(project) {
    if (!state.gitFilter || state.scopeFilter !== "local") return true;
    if (state.gitFilter === "duplicates") {
      return state.duplicateGroupByProjectId.has(project.id);
    }
    const info = gitInfo(project);
    if (state.gitFilter === "git") return Boolean(info && info.is_git);
    if (state.gitFilter === "local-only") return Boolean(info && !info.is_git);
    return true;
  }

  function remoteInfo(project) {
    if (project.remote) return project.remote;
    const raw = project.path || "";
    return {
      protocol: "remote",
      authority: "",
      host: "",
      remote_path: raw,
      group_key: raw,
      name: projectName(project),
    };
  }

  function formatRemoteProtocol(protocol) {
    const map = {
      "codebuddy-remote-ssh": "CodeBuddy SSH",
      "ssh-remote": "SSH Remote",
      "dev-container": "Dev Container",
      "attached-container": "Container",
      wsl: "WSL",
    };
    return map[protocol] || protocol || "远程";
  }

  function workspaceActivityForProject(ws, projectPath) {
    if (!ws) return "";
    if (projectPath && ws.activity_by_root && typeof ws.activity_by_root === "object") {
      const rootEntry = ws.activity_by_root[projectPath];
      if (rootEntry && rootEntry.last_activity) return rootEntry.last_activity;
    }
    return ws.last_activity || "";
  }

  function projectAgentActivityMap(project) {
    const map = new Map();
    if (!project) return map;
    const rows =
      project.workspaces && project.workspaces.length > 0
        ? project.workspaces.map((wid) => state.workspaceById.get(wid)).filter(Boolean)
        : project.historical_evidence || [];
    for (const ws of rows) {
      const agent = ws?.agent;
      if (!agent || agent === "filesystem") continue;
      const stamp = workspaceActivityForProject(ws, project.path);
      if (stamp && stamp > (map.get(agent) || "")) {
        map.set(agent, stamp);
      }
    }
    return map;
  }

  function sortAgentIds(ids, activityByAgent = null) {
    return [...(ids || [])].sort((a, b) => {
      if (state.selectedAgent) {
        if (a === state.selectedAgent) return -1;
        if (b === state.selectedAgent) return 1;
      }
      const aExt = isExtensionAgent(a) ? 1 : 0;
      const bExt = isExtensionAgent(b) ? 1 : 0;
      if (aExt !== bExt) return aExt - bExt;
      if (activityByAgent && activityByAgent.size > 0) {
        const ta = activityByAgent.get(a) || "";
        const tb = activityByAgent.get(b) || "";
        if (ta !== tb) {
          if (!ta) return 1;
          if (!tb) return -1;
          return ta < tb ? 1 : -1;
        }
      }
      return 0;
    });
  }

  function groupRemoteProjects(rows) {
    const map = new Map();
    for (const p of rows) {
      const info = remoteInfo(p);
      const key = info.group_key || p.path;
      let group = map.get(key);
      if (!group) {
        group = {
          groupKey: key,
          remotePath: info.remote_path || key,
          name: info.name || projectName(p),
          items: [],
          hostSet: new Set(),
          agentSet: new Set(),
          agentActivity: new Map(),
          tagSet: new Set(),
          favorite: false,
          last_activity: null,
        };
        map.set(key, group);
      }
      group.items.push(p);
      if (info.host) group.hostSet.add(info.host);
      const itemActivity = projectAgentActivityMap(p);
      for (const a of p.agents || []) {
        group.agentSet.add(a);
        const stamp = itemActivity.get(a) || p.last_activity || "";
        if (stamp && stamp > (group.agentActivity.get(a) || "")) {
          group.agentActivity.set(a, stamp);
        }
      }
      for (const t of p.tags || []) group.tagSet.add(t);
      if (p.favorite) group.favorite = true;
      if (p.last_activity && (!group.last_activity || p.last_activity > group.last_activity)) {
        group.last_activity = p.last_activity;
      }
    }
    const groups = Array.from(map.values()).map((g) => {
      g.items.sort(compareRecent);
      return {
        groupKey: g.groupKey,
        remotePath: g.remotePath,
        name: g.name,
        items: g.items,
        hosts: Array.from(g.hostSet).sort(),
        agents: sortAgentIds(Array.from(g.agentSet), g.agentActivity),
        tags: Array.from(g.tagSet),
        favorite: g.favorite,
        last_activity: g.last_activity,
        primaryId: g.items[0].id,
      };
    });
    if (state.sortBy === "name") {
      groups.sort(
        (a, b) =>
          a.name.toLowerCase().localeCompare(b.name.toLowerCase(), "zh-CN") ||
          a.remotePath.localeCompare(b.remotePath)
      );
    } else if (state.sortBy === "agents") {
      groups.sort((a, b) => {
        const diff = b.agents.length - a.agents.length;
        if (diff !== 0) return diff;
        return compareRecent(
          { last_activity: a.last_activity, path: a.remotePath },
          { last_activity: b.last_activity, path: b.remotePath }
        );
      });
    } else {
      groups.sort((a, b) => {
        if (a.last_activity && b.last_activity && a.last_activity !== b.last_activity) {
          return a.last_activity < b.last_activity ? 1 : -1;
        }
        if (a.last_activity && !b.last_activity) return -1;
        if (!a.last_activity && b.last_activity) return 1;
        const hostDiff = (b.hosts.length || b.items.length) - (a.hosts.length || a.items.length);
        if (hostDiff !== 0) return hostDiff;
        return compareRecent(
          { last_activity: a.last_activity, path: a.remotePath },
          { last_activity: b.last_activity, path: b.remotePath }
        );
      });
    }
    return groups;
  }

  function matchesQuery(project, q) {
    if (!q) return true;
    const nameHit = (project.names || []).some((n) => n && n.toLowerCase().includes(q));
    if (nameHit) return true;
    if ((project.path || "").toLowerCase().includes(q)) return true;
    if (shortenPath(project.path || "").toLowerCase().includes(q)) return true;
    if (project.remote) {
      if ((project.remote.host || "").toLowerCase().includes(q)) return true;
      if ((project.remote.remote_path || "").toLowerCase().includes(q)) return true;
    }
    if (project.git) {
      if ((project.git.branch || "").toLowerCase().includes(q)) return true;
      if ((project.git.remote_url || "").toLowerCase().includes(q)) return true;
      if ((project.git.parent_repo || "").toLowerCase().includes(q)) return true;
    }
    if (
      (project.agents || []).some(
        (a) => a.toLowerCase().includes(q) || agentDisplayName(a).toLowerCase().includes(q)
      )
    ) {
      return true;
    }
    if ((project.tags || []).some((t) => t.toLowerCase().includes(q))) return true;
    return false;
  }

  function matchesNonScopeFilters(project, q, minTime) {
    if (state.selectedAgent && !(project.agents || []).includes(state.selectedAgent)) {
      return false;
    }
    if (
      state.selectedTag &&
      !(project.tags || []).some((t) => t.toLowerCase() === state.selectedTag.toLowerCase())
    ) {
      return false;
    }
    if (state.selectedDuplicateKey) {
      const grp = state.duplicateGroupByProjectId.get(project.id);
      if (!grp || grp.remote_key !== state.selectedDuplicateKey) return false;
    }
    if (state.timeRange === "dormant30") {
      if (project.last_activity) {
        const ts = Date.parse(project.last_activity);
        if (!Number.isNaN(ts) && Date.now() - ts < 30 * 24 * 3600 * 1000) return false;
      }
    } else if (minTime !== null) {
      if (!project.last_activity) return false;
      const ts = Date.parse(project.last_activity);
      if (Number.isNaN(ts) || ts < minTime) return false;
    }
    return matchesQuery(project, q);
  }

  function compareRecent(a, b) {
    if (a.last_activity && b.last_activity) {
      if (a.last_activity !== b.last_activity) {
        return a.last_activity < b.last_activity ? 1 : -1;
      }
    } else if (a.last_activity) {
      return -1;
    } else if (b.last_activity) {
      return 1;
    }
    return a.path.localeCompare(b.path);
  }

  function sortProjects(rows) {
    const copy = rows.slice();
    if (state.sortBy === "name") {
      copy.sort((a, b) => {
        const na = projectName(a).toLowerCase();
        const nb = projectName(b).toLowerCase();
        return na.localeCompare(nb, "zh-CN") || a.path.localeCompare(b.path);
      });
    } else if (state.sortBy === "agents") {
      copy.sort((a, b) => {
        const diff = (b.agents?.length || 0) - (a.agents?.length || 0);
        if (diff !== 0) return diff;
        return compareRecent(a, b);
      });
    } else if (state.sortBy === "reclaimable") {
      copy.sort((a, b) => {
        const diff = projectReclaimableBytes(b.id) - projectReclaimableBytes(a.id);
        if (diff !== 0) return diff;
        return compareRecent(a, b);
      });
    } else {
      copy.sort(compareRecent);
    }
    return copy;
  }

  function setCountWithTick(node, key, value) {
    const prev = state.lastCounts[key];
    node.textContent = String(value);
    if (prev !== null && prev !== value) {
      node.classList.remove("is-tick");
      void node.offsetWidth;
      node.classList.add("is-tick");
    }
    state.lastCounts[key] = value;
  }

  function computeFilteredState() {
    const projects = state.data?.projects || [];
    const q = state.search.trim().toLowerCase();
    const minTime = timeThresholdMs(state.timeRange);

    let localTotal = 0;
    let localGitTotal = 0;
    let localPlainTotal = 0;
    let favoriteTotal = 0;
    let attentionTotal = 0;
    let sandboxTotal = 0;
    let hiddenTotal = 0;
    const allRemoteVisible = [];

    for (const p of projects) {
      if (p.hidden) {
        hiddenTotal += 1;
        continue;
      }
      if (p.favorite) favoriteTotal += 1;
      const kind = assetKind(p);
      if (kind === "remote") {
        allRemoteVisible.push(p);
      } else if (kind === "sandbox") {
        sandboxTotal += 1;
      } else if (p.status === "directory") {
        localTotal += 1;
        const g = gitInfo(p);
        if (g && g.is_git) localGitTotal += 1;
        else if (g) localPlainTotal += 1;
      } else {
        attentionTotal += 1;
      }
    }

    const allRemoteGroups = groupRemoteProjects(allRemoteVisible);
    state.remoteGroupByKey = new Map(allRemoteGroups.map((g) => [g.groupKey, g]));
    const remoteTotal = allRemoteGroups.length;

    if (state.scopeFilter === "hidden" && hiddenTotal === 0) {
      state.scopeFilter = "local";
    }

    const matchedBase = projects.filter((p) => matchesNonScopeFilters(p, q, minTime));
    const hasNarrowing = Boolean(q || state.selectedAgent || state.selectedTag);

    let visible = [];
    let sandboxVisible = [];
    let remoteGroups = [];
    let remoteMatchedHostCount = 0;
    const penetration = { local: 0, remote: 0, attention: 0, sandbox: 0, hidden: 0 };

    if (state.scopeFilter === "hidden") {
      visible = sortProjects(matchedBase.filter((p) => p.hidden));
    } else if (state.scopeFilter === "favorite") {
      visible = sortProjects(matchedBase.filter((p) => !p.hidden && p.favorite));
    } else if (state.scopeFilter === "remote") {
      const matchedRemotes = matchedBase.filter(isRemoteProject);
      remoteGroups = groupRemoteProjects(matchedRemotes);
      remoteMatchedHostCount = new Set(
        matchedRemotes.map((p) => remoteInfo(p).host).filter(Boolean)
      ).size;
    } else if (state.scopeFilter === "attention") {
      visible = sortProjects(matchedBase.filter(isAttentionProject));
    } else {
      visible = sortProjects(matchedBase.filter((p) => isLocalProject(p) && matchesGitFilter(p)));
      sandboxVisible = sortProjects(
        matchedBase.filter((p) => isSandboxProject(p) && matchesGitFilter(p))
      );
    }

    if (hasNarrowing) {
      if (state.scopeFilter !== "local") {
        penetration.local = matchedBase.filter(isLocalProject).length;
        penetration.sandbox = matchedBase.filter(isSandboxProject).length;
      }
      if (state.scopeFilter !== "remote") {
        penetration.remote = groupRemoteProjects(matchedBase.filter(isRemoteProject)).length;
      }
      if (state.scopeFilter !== "attention") {
        penetration.attention = matchedBase.filter(isAttentionProject).length;
      }
      if (state.scopeFilter !== "hidden") {
        penetration.hidden = matchedBase.filter((p) => p.hidden).length;
      }
    }

    return {
      counts: {
        local: localTotal,
        localGit: localGitTotal,
        localPlain: localPlainTotal,
        favorite: favoriteTotal,
        remote: remoteTotal,
        attention: attentionTotal,
        sandbox: sandboxTotal,
        hidden: hiddenTotal,
      },
      visible,
      sandboxVisible,
      remoteGroups,
      remoteMatchedHostCount,
      penetration,
    };
  }

  function renderToolbarMeta(counts) {
    setCountWithTick(el.countLocal, "local", counts.local);
    setCountWithTick(el.countFavorite, "favorite", counts.favorite);
    setCountWithTick(el.countRemote, "remote", counts.remote);
    setCountWithTick(el.countAttention, "attention", counts.attention);
    setCountWithTick(el.countHidden, "hidden", counts.hidden);

    el.scopeFilters.querySelectorAll(".filter-pill").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.scope === state.scopeFilter);
    });

    if (el.btnAttentionScope) {
      el.btnAttentionScope.classList.toggle("has-attention", counts.attention > 0);
    }

    el.btnHiddenView.hidden = counts.hidden === 0;
    el.btnHiddenView.classList.toggle("is-active", state.scopeFilter === "hidden");

    if (el.gitFilterWrap && el.gitFilter) {
      const showGitFilter = state.scopeFilter === "local";
      el.gitFilterWrap.hidden = !showGitFilter;
      const dupCount = state.duplicateGroupByProjectId.size;
      const opts = el.gitFilter.options;
      if (opts.length >= 4) {
        opts[0].textContent = "全部类型";
        opts[1].textContent = `Git 仓库 (${counts.localGit})`;
        opts[2].textContent = `纯本地 (${counts.localPlain})`;
        opts[3].textContent = dupCount > 0 ? `多副本仓库 (${dupCount})` : "多副本仓库";
      }
      el.gitFilter.value = state.gitFilter;
    }

    if (el.viewModeToggle) {
      el.viewModeToggle.querySelectorAll(".view-mode-btn").forEach((btn) => {
        const active = btn.dataset.layout === state.layoutMode;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }

    const allTags = (state.data?.all_tags || []).filter((t) =>
      state.scopeFilter === "hidden" ? t.total > 0 : t.count > 0
    );
    const showChipsBar = Boolean(
      state.selectedAgent || state.selectedDuplicateKey || allTags.length > 0
    );
    el.chipsCollapse.classList.toggle("is-open", showChipsBar);

    const parts = [];
    if (state.selectedAgent) {
      const chipPrefix = isExtensionAgent(state.selectedAgent) ? "编辑器扩展" : "Agent";
      parts.push(
        `<button type="button" class="filter-chip is-agent-chip" data-action="clear-agent">${renderAgentIconHtml(
          state.selectedAgent,
          "xs"
        )}<span>${chipPrefix}：${escapeHtml(agentDisplayName(state.selectedAgent))}</span>${
          ICONS.close
        }</button>`
      );
    }
    if (state.selectedDuplicateKey) {
      const grp = state.duplicateGroupByKey.get(state.selectedDuplicateKey);
      const label = grp ? `${grp.name}（${grp.count} 份副本）` : "同源副本";
      parts.push(
        `<button type="button" class="filter-chip is-active" data-action="clear-duplicate"><span>同仓库：${escapeHtml(
          label
        )}</span>${ICONS.close}</button>`
      );
    }
    for (const item of allTags) {
      const active =
        state.selectedTag && state.selectedTag.toLowerCase() === item.tag.toLowerCase();
      const count = state.scopeFilter === "hidden" ? item.total : item.count;
      parts.push(
        `<button type="button" class="filter-chip${
          active ? " is-active" : ""
        }" data-action="toggle-tag" data-tag="${escapeHtml(item.tag)}"># ${escapeHtml(
          item.tag
        )} <span class="pill-count">${count}</span></button>`
      );
    }
    el.chipsBar.innerHTML = parts.join("");
  }

  function renderRowStatusBadges(project) {
    const pills = [];
    const kind = assetKind(project);
    const meta = STATUS_META[project.status];
    if (meta && meta.short) {
      pills.push(
        `<span class="status-pill ${meta.pill}" title="${escapeHtml(meta.label)}">${escapeHtml(
          meta.short
        )}</span>`
      );
    }
    if (kind === "sandbox") {
      const label = project.asset_reason === "active_worktree" ? "工作树" : "临时沙盒";
      const title =
        project.asset_reason === "active_worktree"
          ? "Git Worktree 衍生目录"
          : "由 Agent 自动创建的临时目录";
      pills.push(
        `<span class="status-pill is-sandbox" title="${escapeHtml(title)}">${escapeHtml(
          label
        )}</span>`
      );
    }
    const g = gitInfo(project);
    if (kind === "project" && project.status === "directory" && g) {
      if (g.kind === "subdir") {
        pills.push(
          `<span class="status-pill is-git" title="位于上级 Git 仓库：${escapeHtml(
            shortenPath(g.parent_repo || "")
          )}">Git 子目录</span>`
        );
      } else if (g.kind === "submodule") {
        pills.push(
          `<span class="status-pill is-git" title="Git 子模块">子模块</span>`
        );
      }
    }
    if (project.index_state === "historical") {
      pills.push(
        `<span class="status-pill is-historical" title="最近一次扫描未再发现，保留历史证据">历史</span>`
      );
    }
    const dupGroup = state.duplicateGroupByProjectId.get(project.id);
    if (dupGroup && dupGroup.count >= 2 && project.status === "directory") {
      pills.push(
        `<button type="button" class="dup-pill" data-action="filter-duplicate" data-remote-key="${escapeHtml(
          dupGroup.remote_key
        )}" title="同一 Git 仓库本机共有 ${dupGroup.count} 份目录，点击筛选对比">${dupGroup.count} 份副本</button>`
      );
    }
    const reclaimBytes = projectReclaimableBytes(project.id);
    if (state.hygiene?.scanned && reclaimBytes >= 200 * 1024 * 1024) {
      pills.push(
        `<button type="button" class="reclaim-pill" data-action="quick-slim-project" data-id="${escapeHtml(
          project.id
        )}" title="包含可安全重建的依赖/构建产物，点击清理">可清 ${escapeHtml(
          formatBytes(reclaimBytes)
        )}</button>`
      );
    }
    return pills.join("");
  }

  function renderAgentBadgesHtml(agentList) {
    const agents = sortAgentIds(agentList);
    return agents
      .map((a) => {
        const ext = isExtensionAgent(a);
        const tip = agentTooltipText(a);
        return `<span class="agent-badge has-icon${ext ? " is-extension" : ""}" title="${escapeHtml(
          tip
        )}">${renderAgentIconHtml(a, "xs")}<span>${escapeHtml(agentDisplayName(a))}</span></span>`;
      })
      .join("");
  }

  function renderAgentStackHtml(agentList, stackKey, options = {}) {
    const includeCollapse = options.includeCollapse !== false;
    const agents = sortAgentIds(agentList, options.activityByAgent || null);
    if (agents.length === 0) return "";

    if (agents.length === 1) {
      const a = agents[0];
      const ext = isExtensionAgent(a);
      const tip = agentTooltipText(a);
      return `<span class="agent-single-pill${ext ? " is-extension" : ""}" title="${escapeHtml(
        tip
      )}">${renderAgentIconHtml(a, "xs")}<span>${escapeHtml(agentDisplayName(a))}</span></span>`;
    }

    const isExpanded = state.expandedAgentStacks.has(stackKey);
    if (isExpanded) {
      const pills = agents
        .map((a) => {
          const ext = isExtensionAgent(a);
          const tip = `${agentTooltipText(a)} · 点击筛选`;
          return `<button type="button" class="agent-pill${
            ext ? " is-extension" : ""
          }" data-action="filter-agent-inline" data-agent="${escapeHtml(a)}" title="${escapeHtml(
            tip
          )}">${renderAgentIconHtml(a, "xs")}<span>${escapeHtml(
            agentDisplayName(a)
          )}</span></button>`;
        })
        .join("");
      const collapseBtnHtml = includeCollapse
        ? `<button type="button" class="agent-stack-collapse" data-action="toggle-agent-stack" data-stack-key="${escapeHtml(
            stackKey
          )}" aria-label="收起工具列表" title="收起头像列表">收起</button>`
        : "";
      return `<div class="agent-stack is-expanded" data-stack-key="${escapeHtml(stackKey)}">
        ${pills}
        ${collapseBtnHtml}
      </div>`;
    }

    const maxShown = 5;
    const shown = agents.slice(0, maxShown);
    const extra = agents.length - shown.length;
    const avatars = shown
      .map((a, idx) => {
        const tip = agentTooltipText(a);
        const isCircle = AGENT_ICONS[a]?.shape === "circle";
        return `<span class="agent-avatar${
          isCircle ? " is-circle" : ""
        }" style="z-index:${maxShown - idx}" data-tooltip="${escapeHtml(tip)}">${renderAgentIconHtml(
          a,
          "sm"
        )}</span>`;
      })
      .join("");
    const moreHtml =
      extra > 0
        ? `<span class="agent-avatar is-more" style="z-index:${maxShown + 1}" data-tooltip="另有 ${extra} 个工具，点击展开">+${extra}</span>`
        : "";

    return `<button type="button" class="agent-stack" data-action="toggle-agent-stack" data-stack-key="${escapeHtml(
      stackKey
    )}" aria-expanded="false" aria-label="展开查看全部 ${
      agents.length
    } 个工具" title="点击展开全部 ${agents.length} 个工具">${avatars}${moreHtml}</button>`;
  }

  function renderGitMetaBlockHtml(project) {
    const isRemote = project.status === "remote";
    if (isRemote) {
      const rInfo = remoteInfo(project);
      const host = rInfo?.host || formatRemoteProtocol(rInfo?.protocol);
      return `<div class="git-summary is-remote-meta">
        <span class="git-remote-short" title="${escapeHtml(host)}">${escapeHtml(host)}</span>
      </div>`;
    }

    const g = gitInfo(project);
    if (g && g.is_git) {
      const branchText = g.branch
        ? g.detached
          ? `HEAD@${g.branch}`
          : g.branch
        : "无分支";
      const branchTitle = g.detached
        ? `游离 HEAD：${g.branch || ""}`
        : `当前分支：${g.branch || "无"}`;
      const remoteShort = formatGitRemoteShort(g.remote_url);
      const remoteHtml = remoteShort
        ? `<span class="git-remote-short" title="${escapeHtml(g.remote_url)}">${escapeHtml(
            remoteShort
          )}</span>`
        : `<span class="git-remote-short is-empty">仅本地 Git 仓库</span>`;
      return `<div class="git-summary">
        <span class="git-branch-chip" title="${escapeHtml(branchTitle)}">${ICONS.gitBranch}<span>${escapeHtml(
        branchText
      )}</span></span>
        ${remoteHtml}
      </div>`;
    }

    if (g && !g.is_git) {
      return `<div class="git-summary is-plain">
        <span class="status-pill is-local-only" title="当前目录及上级目录未检测到 .git 仓库">纯本地目录</span>
      </div>`;
    }

    if (isAttentionProject(project)) {
      const meta = STATUS_META[project.status];
      return `<div class="git-summary is-attention-meta">
        <span class="git-remote-short is-empty">${escapeHtml(meta?.label || "需要确认")}</span>
      </div>`;
    }

    return "";
  }

  function availableLaunchers() {
    return (state.data?.launchers || []).filter((item) => item && item.available);
  }

  function launcherById(targetId) {
    return (state.data?.launchers || []).find((item) => item.id === targetId) || null;
  }

  function isAppLauncher(item) {
    return item && (item.kind === "editor" || item.kind === "coding_agent");
  }

  function preferredLauncherForProject(project) {
    const apps = availableLaunchers().filter(
      (item) => isAppLauncher(item) && item.opens_path !== false
    );
    if (apps.length === 0) return null;
    const appMap = new Map(apps.map((item) => [item.id, item]));
    const activity = projectAgentActivityMap(project);
    let bestId = null;
    let bestStamp = "";
    for (const [agentId, stamp] of activity.entries()) {
      if (!appMap.has(agentId)) continue;
      if (!bestId || stamp > bestStamp) {
        bestId = agentId;
        bestStamp = stamp;
      }
    }
    if (bestId) return appMap.get(bestId);
    for (const agentId of sortAgentIds(project.agents || [], activity)) {
      if (appMap.has(agentId)) return appMap.get(agentId);
    }
    return null;
  }

  function renderLauncherChipIcon(targetId) {
    if (AGENT_ICONS[targetId]) return renderAgentIconHtml(targetId, "xs");
    if (targetId === "terminal") return ICONS.terminal;
    if (targetId === "remote") return ICONS.externalLink;
    return ICONS.folder;
  }

  function buildQuickOpenButtonsHtml(project) {
    const preferredLauncher = preferredLauncherForProject(project);
    const terminalLauncher = launcherById("terminal");
    const buttons = [];
    if (preferredLauncher) {
      buttons.push(
        `<button type="button" class="row-action-btn is-primary-action is-editor-launch" data-action="open" data-target="${escapeHtml(
          preferredLauncher.id
        )}" data-id="${escapeHtml(project.id)}" aria-label="用 ${escapeHtml(
          preferredLauncher.label
        )} 打开" title="用 ${escapeHtml(preferredLauncher.label)} 打开 (E)">
          <span class="icon-swap"><span class="icon-base">${renderAgentIconHtml(
            preferredLauncher.id,
            "xs"
          )}</span><span class="icon-done">${ICONS.check}</span></span>
        </button>`
      );
    }
    if (terminalLauncher && terminalLauncher.available) {
      buttons.push(
        `<button type="button" class="row-action-btn" data-action="open" data-target="terminal" data-id="${escapeHtml(
          project.id
        )}" aria-label="在${escapeHtml(terminalLauncher.label)}中打开" title="在${escapeHtml(
          terminalLauncher.label
        )}中打开 (T)">
          <span class="icon-swap"><span class="icon-base">${ICONS.terminal}</span><span class="icon-done">${ICONS.check}</span></span>
        </button>`
      );
    }
    buttons.push(
      `<button type="button" class="row-action-btn${
        preferredLauncher ? "" : " is-primary-action"
      }" data-action="open" data-target="finder" data-id="${escapeHtml(
        project.id
      )}" aria-label="在访达中打开" title="在访达中打开 (O)">
        <span class="icon-swap"><span class="icon-base">${ICONS.folder}</span><span class="icon-done">${ICONS.check}</span></span>
      </button>`
    );
    return buttons.join("");
  }

  function buildProjectRowActionsHtml(project, isRemote, canOpen, isAttention, isSandbox) {
    if (isAttention) {
      return `
        <button type="button" class="row-text-action" data-action="resolve-link" data-id="${escapeHtml(
          project.id
        )}" title="关联到迁移后的现有项目">关联新路径</button>
        <button type="button" class="row-text-action is-danger" data-action="dismiss-missing" data-id="${escapeHtml(
          project.id
        )}" title="确认已删除并从待整理移除">移除</button>
      `;
    }
    if (isSandbox) {
      return `
        <button type="button" class="row-text-action" data-action="promote" data-id="${escapeHtml(
          project.id
        )}" title="提升为正式本地项目">设为项目</button>
        ${canOpen ? buildQuickOpenButtonsHtml(project) : ""}
        <button type="button" class="row-action-btn" data-action="copy" data-id="${escapeHtml(
          project.id
        )}" aria-label="复制路径" title="复制完整路径">
          <span class="icon-swap"><span class="icon-base">${ICONS.copy}</span><span class="icon-done">${ICONS.check}</span></span>
        </button>
        <button type="button" class="row-action-btn" data-action="hide" data-id="${escapeHtml(
          project.id
        )}" aria-label="隐藏此项目" title="隐藏此项目">${ICONS.eyeOff}</button>
      `;
    }
    const openBtns = canOpen ? buildQuickOpenButtonsHtml(project) : "";
    const hideAction = project.hidden
      ? `<button type="button" class="row-action-btn" data-action="unhide" data-id="${escapeHtml(
          project.id
        )}" aria-label="恢复显示" title="恢复显示">${ICONS.eye}</button>`
      : `<button type="button" class="row-action-btn" data-action="hide" data-id="${escapeHtml(
          project.id
        )}" aria-label="隐藏此项目" title="隐藏此项目">${ICONS.eyeOff}</button>`;
    return `
      ${openBtns}
      <button type="button" class="row-action-btn" data-action="copy" data-id="${escapeHtml(
        project.id
      )}" aria-label="复制路径" title="${isRemote ? "复制远程地址" : "复制完整路径"}">
        <span class="icon-swap"><span class="icon-base">${ICONS.copy}</span><span class="icon-done">${ICONS.check}</span></span>
      </button>
      <button type="button" class="row-action-btn" data-action="popover-tag" data-id="${escapeHtml(
        project.id
      )}" aria-label="管理标签" title="管理标签">${ICONS.tag}</button>
      ${hideAction}
    `;
  }

  function renderProjectRowHtml(project) {
    const name = projectName(project);
    const isRemote = project.status === "remote";
    const rInfo = isRemote ? remoteInfo(project) : null;
    const shortPath = isRemote ? rInfo.remote_path : shortenPath(project.path);
    const isSelected = state.selectedProjectId === project.id;
    const isMuted = !isAvailableStatus(project.status) || project.hidden;
    const isRestored = state.restoredId === project.id;
    const canOpen = project.status === "directory";
    const isAttention = isAttentionProject(project);
    const isSandbox = isSandboxProject(project);

    const agentActivity = projectAgentActivityMap(project);
    const agentBadgesHtml = renderAgentStackHtml(project.agents || [], `p:${project.id}`, {
      activityByAgent: agentActivity,
    });
    const gitBlockHtml = renderGitMetaBlockHtml(project);

    const tagsHtml = (project.tags || [])
      .slice(0, 4)
      .map(
        (tag) =>
          `<button type="button" class="tag-pill" data-action="filter-tag" data-tag="${escapeHtml(
            tag
          )}" title="按标签「${escapeHtml(tag)}」筛选">#${escapeHtml(tag)}</button>`
      )
      .join("");

    const rowActionsHtml = buildProjectRowActionsHtml(
      project,
      isRemote,
      canOpen,
      isAttention,
      isSandbox
    );

    return `
      <div class="project-row-wrap${isRestored ? " is-entering" : ""}" data-row-wrap="${escapeHtml(
      project.id
    )}">
        <div class="project-row-clip">
          <div class="project-row is-list-row${isSelected ? " is-selected" : ""}${
      isMuted ? " is-muted" : ""
    }${isRestored ? " is-restored" : ""}" data-project-id="${escapeHtml(
      project.id
    )}" tabindex="0" role="button" aria-pressed="${isSelected ? "true" : "false"}">
            <button type="button" class="star-btn${
              project.favorite ? " is-starred" : ""
            }" data-action="star" data-id="${escapeHtml(
      project.id
    )}" aria-label="${project.favorite ? "取消收藏" : "收藏项目"}" title="${
      project.favorite ? "取消收藏 (S)" : "收藏项目 (S)"
    }">
              ${project.favorite ? ICONS.starFilled : ICONS.starOutline}
            </button>
            <div class="project-col-identity">
              <div class="project-line-1">
                <span class="project-name">${escapeHtml(name)}</span>
                ${renderRowStatusBadges(project)}
                ${tagsHtml ? `<span class="row-tags">${tagsHtml}</span>` : ""}
              </div>
              <div class="project-line-2">
                <span class="project-path" title="${escapeHtml(project.path)}">${escapeHtml(
      shortPath
    )}</span>
              </div>
            </div>
            <div class="project-col-git">${gitBlockHtml}</div>
            <div class="project-col-agents">
              ${agentBadgesHtml}
            </div>
            <div class="project-col-trailing">
              <span class="project-time" title="${escapeHtml(
                formatExactTime(project.last_activity)
              )}">${escapeHtml(formatRelativeTime(project.last_activity))}</span>
              <span class="row-actions${isAttention ? " is-always-visible" : ""}">
                ${rowActionsHtml}
              </span>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderProjectCardHtml(project) {
    const name = projectName(project);
    const isRemote = project.status === "remote";
    const rInfo = isRemote ? remoteInfo(project) : null;
    const shortPath = isRemote ? rInfo.remote_path : shortenPath(project.path);
    const isSelected = state.selectedProjectId === project.id;
    const isMuted = !isAvailableStatus(project.status) || project.hidden;
    const isRestored = state.restoredId === project.id;
    const canOpen = project.status === "directory";
    const isAttention = isAttentionProject(project);
    const isSandbox = isSandboxProject(project);

    const stackKey = `p:${project.id}`;
    const agents = project.agents || [];
    const agentActivity = projectAgentActivityMap(project);
    const isStackExpanded = agents.length > 1 && state.expandedAgentStacks.has(stackKey);
    const agentBadgesHtml = renderAgentStackHtml(agents, stackKey, {
      includeCollapse: false,
      activityByAgent: agentActivity,
    });
    const gitBlockHtml = renderGitMetaBlockHtml(project);

    const tagsHtml = (project.tags || [])
      .slice(0, 3)
      .map(
        (tag) =>
          `<button type="button" class="tag-pill" data-action="filter-tag" data-tag="${escapeHtml(
            tag
          )}" title="按标签「${escapeHtml(tag)}」筛选">#${escapeHtml(tag)}</button>`
      )
      .join("");

    const rowActionsHtml = buildProjectRowActionsHtml(
      project,
      isRemote,
      canOpen,
      isAttention,
      isSandbox
    );

    return `
      <div class="project-row-wrap is-card-wrap${isRestored ? " is-entering" : ""}" data-row-wrap="${escapeHtml(
      project.id
    )}">
        <div class="project-row is-card${isSelected ? " is-selected" : ""}${
      isMuted ? " is-muted" : ""
    }${isRestored ? " is-restored" : ""}" data-project-id="${escapeHtml(
      project.id
    )}" tabindex="0" role="button" aria-pressed="${isSelected ? "true" : "false"}">
          <div class="card-header">
            <button type="button" class="star-btn${
              project.favorite ? " is-starred" : ""
            }" data-action="star" data-id="${escapeHtml(
      project.id
    )}" aria-label="${project.favorite ? "取消收藏" : "收藏项目"}" title="${
      project.favorite ? "取消收藏 (S)" : "收藏项目 (S)"
    }">
              ${project.favorite ? ICONS.starFilled : ICONS.starOutline}
            </button>
            <div class="card-title-group">
              <span class="project-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
              ${renderRowStatusBadges(project)}
            </div>
            <span class="project-time" title="${escapeHtml(
              formatExactTime(project.last_activity)
            )}">${escapeHtml(formatRelativeTime(project.last_activity))}</span>
          </div>
          <div class="card-path-line">
            <span class="project-path" title="${escapeHtml(project.path)}">${escapeHtml(
      shortPath
    )}</span>
          </div>
          ${gitBlockHtml ? `<div class="card-git-line">${gitBlockHtml}</div>` : ""}
          <div class="card-footer${isStackExpanded ? " is-expanded-stack" : ""}">
            <div class="card-meta-left">
              ${agentBadgesHtml}
              ${tagsHtml ? `<span class="row-tags">${tagsHtml}</span>` : ""}
            </div>
            ${
              isStackExpanded
                ? `<div class="card-footer-bar">
                    <button type="button" class="agent-stack-collapse" data-action="toggle-agent-stack" data-stack-key="${escapeHtml(
                      stackKey
                    )}" aria-label="收起工具列表" title="收起头像列表">收起</button>
                    <span class="row-actions${isAttention ? " is-always-visible" : ""}">
                      ${rowActionsHtml}
                    </span>
                  </div>`
                : `<span class="row-actions${isAttention ? " is-always-visible" : ""}">
                    ${rowActionsHtml}
                  </span>`
            }
          </div>
        </div>
      </div>
    `;
  }

  function renderRemoteGroupRowHtml(group) {
    if (group.items.length === 1) {
      return renderProjectRowHtml(group.items[0]);
    }
    const isSelected = state.selectedRemoteGroupKey === group.groupKey;
    const hostCount = group.hosts.length || group.items.length;
    const hostBadge = `${hostCount} 台主机`;
    const hostPreview =
      group.hosts.length > 0
        ? group.hosts.length > 1
          ? `${group.hosts[0]} 等 ${group.hosts.length} 台`
          : group.hosts[0]
        : `${group.items.length} 条远端记录`;
    const agentBadgesHtml = renderAgentStackHtml(group.agents, `rg:${group.groupKey}`);
    const tagsHtml = group.tags
      .slice(0, 3)
      .map(
        (tag) =>
          `<button type="button" class="tag-pill" data-action="filter-tag" data-tag="${escapeHtml(
            tag
          )}" title="按标签「${escapeHtml(tag)}」筛选">#${escapeHtml(tag)}</button>`
      )
      .join("");

    return `
      <div class="project-row-wrap">
        <div class="project-row-clip">
          <div class="project-row is-list-row${isSelected ? " is-selected" : ""}" data-remote-group="${escapeHtml(
      group.groupKey
    )}" tabindex="0" role="button" aria-pressed="${isSelected ? "true" : "false"}">
            <button type="button" class="star-btn${
              group.favorite ? " is-starred" : ""
            }" data-action="star" data-id="${escapeHtml(
      group.primaryId
    )}" aria-label="${group.favorite ? "取消收藏" : "收藏项目"}" title="${
      group.favorite ? "取消收藏" : "收藏该项目"
    }">
              ${group.favorite ? ICONS.starFilled : ICONS.starOutline}
            </button>
            <div class="project-col-identity">
              <div class="project-line-1">
                <span class="project-name">${escapeHtml(group.name)}</span>
                <span class="status-pill is-remote" title="已按远端路径聚合多台主机记录">${escapeHtml(
                  hostBadge
                )}</span>
                ${tagsHtml ? `<span class="row-tags">${tagsHtml}</span>` : ""}
              </div>
              <div class="project-line-2">
                <span class="project-path" title="${escapeHtml(group.remotePath)}">${escapeHtml(
      group.remotePath
    )}</span>
              </div>
            </div>
            <div class="project-col-git">
              <div class="git-summary is-remote-meta">
                <span class="remote-hosts-summary">${escapeHtml(hostPreview)}</span>
              </div>
            </div>
            <div class="project-col-agents">
              ${agentBadgesHtml}
            </div>
            <div class="project-col-trailing">
              <span class="project-time" title="${escapeHtml(
                formatExactTime(group.last_activity)
              )}">${escapeHtml(formatRelativeTime(group.last_activity))}</span>
              <span class="row-actions">
                <button type="button" class="row-action-btn" data-action="copy-text" data-text="${escapeHtml(
                  group.remotePath
                )}" aria-label="复制远端路径" title="复制远端路径">
                  <span class="icon-swap"><span class="icon-base">${ICONS.copy}</span><span class="icon-done">${ICONS.check}</span></span>
                </button>
              </span>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderRemoteGroupCardHtml(group) {
    if (group.items.length === 1) {
      return renderProjectCardHtml(group.items[0]);
    }
    const isSelected = state.selectedRemoteGroupKey === group.groupKey;
    const hostCount = group.hosts.length || group.items.length;
    const hostBadge = `${hostCount} 台主机`;
    const hostPreview =
      group.hosts.length > 0
        ? group.hosts.length > 1
          ? `${group.hosts[0]} 等 ${group.hosts.length} 台`
          : group.hosts[0]
        : `${group.items.length} 条远端记录`;
    const stackKey = `rg:${group.groupKey}`;
    const agents = group.agents || [];
    const isStackExpanded = agents.length > 1 && state.expandedAgentStacks.has(stackKey);
    const agentBadgesHtml = renderAgentStackHtml(agents, stackKey, {
      includeCollapse: false,
    });
    const tagsHtml = group.tags
      .slice(0, 3)
      .map(
        (tag) =>
          `<button type="button" class="tag-pill" data-action="filter-tag" data-tag="${escapeHtml(
            tag
          )}" title="按标签「${escapeHtml(tag)}」筛选">#${escapeHtml(tag)}</button>`
      )
      .join("");

    return `
      <div class="project-row-wrap is-card-wrap">
        <div class="project-row is-card${isSelected ? " is-selected" : ""}" data-remote-group="${escapeHtml(
      group.groupKey
    )}" tabindex="0" role="button" aria-pressed="${isSelected ? "true" : "false"}">
          <div class="card-header">
            <button type="button" class="star-btn${
              group.favorite ? " is-starred" : ""
            }" data-action="star" data-id="${escapeHtml(
      group.primaryId
    )}" aria-label="${group.favorite ? "取消收藏" : "收藏项目"}" title="${
      group.favorite ? "取消收藏" : "收藏该项目"
    }">
              ${group.favorite ? ICONS.starFilled : ICONS.starOutline}
            </button>
            <div class="card-title-group">
              <span class="project-name" title="${escapeHtml(group.name)}">${escapeHtml(group.name)}</span>
              <span class="status-pill is-remote" title="已按远端路径聚合多台主机记录">${escapeHtml(
                hostBadge
              )}</span>
            </div>
            <span class="project-time" title="${escapeHtml(
              formatExactTime(group.last_activity)
            )}">${escapeHtml(formatRelativeTime(group.last_activity))}</span>
          </div>
          <div class="card-path-line">
            <span class="project-path" title="${escapeHtml(group.remotePath)}">${escapeHtml(
      group.remotePath
    )}</span>
          </div>
          <div class="card-git-line">
            <div class="git-summary is-remote-meta">
              <span class="remote-hosts-summary" title="${escapeHtml(hostPreview)}">${escapeHtml(
      hostPreview
    )}</span>
            </div>
          </div>
          <div class="card-footer${isStackExpanded ? " is-expanded-stack" : ""}">
            <div class="card-meta-left">
              ${agentBadgesHtml}
              ${tagsHtml ? `<span class="row-tags">${tagsHtml}</span>` : ""}
            </div>
            ${
              isStackExpanded
                ? `<div class="card-footer-bar">
                    <button type="button" class="agent-stack-collapse" data-action="toggle-agent-stack" data-stack-key="${escapeHtml(
                      stackKey
                    )}" aria-label="收起工具列表" title="收起头像列表">收起</button>
                    <span class="row-actions">
                      <button type="button" class="row-action-btn" data-action="copy-text" data-text="${escapeHtml(
                        group.remotePath
                      )}" aria-label="复制远端路径" title="复制远端路径">
                        <span class="icon-swap"><span class="icon-base">${ICONS.copy}</span><span class="icon-done">${ICONS.check}</span></span>
                      </button>
                    </span>
                  </div>`
                : `<span class="row-actions">
                    <button type="button" class="row-action-btn" data-action="copy-text" data-text="${escapeHtml(
                      group.remotePath
                    )}" aria-label="复制远端路径" title="复制远端路径">
                      <span class="icon-swap"><span class="icon-base">${ICONS.copy}</span><span class="icon-done">${ICONS.check}</span></span>
                    </button>
                  </span>`
            }
          </div>
        </div>
      </div>
    `;
  }

  function renderSkeleton() {
    if (state.layoutMode === "card") {
      const cards = Array.from({ length: 8 }, (_, idx) => {
        const w1 = 42 + ((idx * 13) % 28);
        const w2 = 64 + ((idx * 17) % 26);
        return `<div class="skeleton-card">
          <div class="skeleton-line" style="width:${w1}%"></div>
          <div class="skeleton-line" style="width:${w2}%;height:10px;opacity:0.7"></div>
          <div class="skeleton-line" style="width:52%;height:10px;opacity:0.5"></div>
        </div>`;
      }).join("");
      el.projectsContainer.innerHTML = `<div class="projects-grid">${cards}</div>`;
      return;
    }
    const rows = Array.from({ length: 6 }, (_, idx) => {
      const w1 = 28 + ((idx * 13) % 24);
      const w2 = 46 + ((idx * 17) % 30);
      return `<div class="skeleton-row">
        <div class="skeleton-dot"></div>
        <div class="skeleton-col">
          <div class="skeleton-line" style="width:${w1}%"></div>
          <div class="skeleton-line" style="width:${w2}%;height:10px;opacity:0.7"></div>
        </div>
      </div>`;
    }).join("");
    el.projectsContainer.innerHTML = `<div class="list-card">${rows}</div>`;
  }

  function renderPenetrationEntries(penetration) {
    const entries = [];
    if (penetration.local > 0) {
      entries.push({
        scope: "local",
        desc: `本地项目中 ${penetration.local} 条`,
        btnLabel: "查看本地项目",
      });
    }
    if (penetration.remote > 0) {
      entries.push({
        scope: "remote",
        desc: `远程项目中 ${penetration.remote} 条`,
        btnLabel: "查看远程",
      });
    }
    if (penetration.attention > 0) {
      entries.push({
        scope: "attention",
        desc: `待整理中 ${penetration.attention} 条`,
        btnLabel: "查看待整理",
      });
    }
    if (penetration.sandbox > 0) {
      entries.push({
        scope: "sandbox",
        desc: `临时沙盒中 ${penetration.sandbox} 条`,
        btnLabel: "查看临时沙盒",
      });
    }
    if (penetration.hidden > 0) {
      entries.push({
        scope: "hidden",
        desc: `已隐藏中 ${penetration.hidden} 条`,
        btnLabel: "查看已隐藏",
      });
    }
    return entries;
  }

  function renderScopeContextBar(counts, visibleCount, remoteMatchedHostCount, sandboxMatchedCount = 0) {
    if (!el.scopeContextBar) return;
    const activeGitFilter = state.scopeFilter === "local" ? state.gitFilter : "";
    const hasFilter = Boolean(
      state.search.trim() ||
        state.selectedAgent ||
        state.selectedTag ||
        state.timeRange ||
        activeGitFilter
    );
    let text = "";
    let meta = "";

    if (state.scopeFilter === "attention") {
      text = "以下路径原位于常用项目目录但当前已不存在，可关联到迁移后的新目录，或确认已删除后移出列表。";
      meta = hasFilter ? `命中 ${visibleCount} 项` : `共 ${counts.attention} 项待确认`;
    } else if (state.scopeFilter === "remote") {
      text = "按远端路径聚合多台开发主机记录，点击条目可查看全部关联主机与 SSH 地址。";
      meta =
        remoteMatchedHostCount > 0
          ? `${visibleCount} 个远程项目 · 覆盖 ${remoteMatchedHostCount} 台主机`
          : `${visibleCount} 个远程项目`;
    } else if (state.scopeFilter === "hidden") {
      text = "已隐藏或已确认移除的记录保存在此，随时可以恢复显示。";
      meta = `共 ${visibleCount} 项`;
    } else if (hasFilter) {
      const label =
        state.scopeFilter === "favorite"
          ? "收藏项目"
          : activeGitFilter === "git"
          ? " Git 项目"
          : activeGitFilter === "local-only"
          ? "纯本地目录"
          : "本地项目";
      if (state.scopeFilter === "local" && visibleCount === 0 && sandboxMatchedCount > 0) {
        text = `本地项目中无匹配，已在下方展开 ${sandboxMatchedCount} 个临时沙盒`;
      } else {
        text = `筛选命中 ${visibleCount} 个${label}`;
        if (state.scopeFilter === "local" && sandboxMatchedCount > 0) {
          meta = `临时沙盒另命中 ${sandboxMatchedCount} 个`;
        }
      }
    }

    if (!text) {
      el.scopeContextBar.hidden = true;
      return;
    }
    el.scopeContextBar.hidden = false;
    el.scopeContextText.textContent = text;
    el.scopeContextMeta.textContent = meta;
    if (el.btnScopeReset) {
      el.btnScopeReset.hidden = !hasFilter;
    }
  }

  function renderSandboxSectionHtml(
    sandboxItems,
    totalCount,
    hasFilter,
    isExpanded,
    { autoExpanded = false } = {}
  ) {
    if (!sandboxItems || sandboxItems.length === 0) return "";
    const isCardMode = state.layoutMode === "card";
    const countBadge = hasFilter
      ? `${sandboxItems.length} / ${totalCount}`
      : String(totalCount);
    const hintText = hasFilter
      ? "匹配当前筛选条件的会话沙盒与 Git Worktree"
      : "Agent 自动创建的会话沙盒与 Git Worktree，可展开查看或设为正式项目";
    const bodyHtml = isExpanded
      ? isCardMode
        ? `<div class="projects-grid">${sandboxItems.map(renderProjectCardHtml).join("")}</div>`
        : `<div class="list-card">${sandboxItems.map(renderProjectRowHtml).join("")}</div>`
      : "";

    const headerHtml = autoExpanded
      ? `<div class="sandbox-disclosure-trigger is-static">
          <span class="sandbox-disclosure-left">
            <span class="sandbox-disclosure-title">临时沙盒</span>
            <span class="sandbox-disclosure-count">${escapeHtml(countBadge)}</span>
            <span class="sandbox-disclosure-hint">${escapeHtml(hintText)}</span>
          </span>
          <span class="sandbox-disclosure-action is-muted">已自动展开</span>
        </div>`
      : `<button type="button" class="sandbox-disclosure-trigger" data-action="toggle-sandbox" aria-expanded="${
          isExpanded ? "true" : "false"
        }">
          <span class="sandbox-disclosure-left">
            ${ICONS.chevron}
            <span class="sandbox-disclosure-title">临时沙盒</span>
            <span class="sandbox-disclosure-count">${escapeHtml(countBadge)}</span>
            <span class="sandbox-disclosure-hint">${escapeHtml(hintText)}</span>
          </span>
          <span class="sandbox-disclosure-action">${isExpanded ? "收起" : "展开"}</span>
        </button>`;

    return `
      <section class="sandbox-disclosure${isExpanded ? " is-open" : ""}" id="sandbox-disclosure" aria-label="临时沙盒">
        ${headerHtml}
        <div class="sandbox-disclosure-panel${isExpanded ? " is-open" : ""}">
          <div class="sandbox-disclosure-inner">
            <div class="sandbox-disclosure-body">${bodyHtml}</div>
          </div>
        </div>
      </section>
    `;
  }

  function renderGroupedProjectsHtml(items, isCardMode) {
    const startOfToday = new Date();
    startOfToday.setHours(0, 0, 0, 0);
    const todayMs = startOfToday.getTime();
    const nowMs = Date.now();
    const day7Ms = nowMs - 7 * 24 * 3600 * 1000;
    const day30Ms = nowMs - 30 * 24 * 3600 * 1000;

    const buckets = [
      { key: "today", title: "今天", items: [] },
      { key: "week", title: "近 7 天", items: [] },
      { key: "month", title: "近 30 天", items: [] },
      { key: "dormant", title: "30 天以上未动（沉睡）", items: [], collapsible: true },
    ];

    for (const p of items) {
      const ts = p.last_activity ? Date.parse(p.last_activity) : NaN;
      if (!Number.isNaN(ts) && ts >= todayMs) {
        buckets[0].items.push(p);
      } else if (!Number.isNaN(ts) && ts >= day7Ms) {
        buckets[1].items.push(p);
      } else if (!Number.isNaN(ts) && ts >= day30Ms) {
        buckets[2].items.push(p);
      } else {
        buckets[3].items.push(p);
      }
    }

    const nonEmpty = buckets.filter((b) => b.items.length > 0);
    const renderItems = (list) =>
      isCardMode
        ? `<div class="projects-grid">${list.map(renderProjectCardHtml).join("")}</div>`
        : `<div class="list-card">${list.map(renderProjectRowHtml).join("")}</div>`;

    if (nonEmpty.length <= 1 && !(nonEmpty[0]?.key === "dormant")) {
      return renderItems(items);
    }

    return nonEmpty
      .map((bucket) => {
        const isDormant = bucket.key === "dormant";
        const collapsed = isDormant && state.dormantGroupCollapsed;
        const actionsHtml = isDormant
          ? `<div class="time-group-actions">
              <button type="button" class="time-group-toggle" data-action="open-organize-slim">去空间瘦身</button>
              <button type="button" class="time-group-toggle" data-action="toggle-dormant-group">${
                collapsed ? "展开" : "收起"
              }</button>
            </div>`
          : "";
        return `<section class="time-group-section" data-time-group="${bucket.key}">
          <div class="time-group-header">
            <div class="time-group-left">
              <h2 class="time-group-title">${bucket.title}</h2>
              <span class="time-group-count">${bucket.items.length}</span>
            </div>
            ${actionsHtml}
          </div>
          ${collapsed ? "" : renderItems(bucket.items)}
        </section>`;
      })
      .join("");
  }

  function renderProjectsView() {
    if (!state.loaded) {
      renderSkeleton();
      return;
    }
    const { counts, visible, sandboxVisible, remoteGroups, remoteMatchedHostCount, penetration } =
      computeFilteredState();
    renderToolbarMeta(counts);

    const isRemoteScope = state.scopeFilter === "remote";
    const isLocalScope = state.scopeFilter === "local";
    const displayCount = isRemoteScope ? remoteGroups.length : visible.length;
    const hasFilter = Boolean(
      state.search.trim() ||
        state.selectedAgent ||
        state.selectedTag ||
        state.timeRange ||
        (isLocalScope && state.gitFilter)
    );
    renderScopeContextBar(
      counts,
      displayCount,
      remoteMatchedHostCount,
      isLocalScope ? sandboxVisible.length : 0
    );
    const penEntries = renderPenetrationEntries(penetration);

    if (isLocalScope && displayCount === 0 && sandboxVisible.length > 0) {
      const sandboxHtml = renderSandboxSectionHtml(
        sandboxVisible,
        counts.sandbox,
        hasFilter,
        true,
        { autoExpanded: true }
      );
      let penHtml = "";
      if (penEntries.length > 0) {
        const detail = penEntries.map((item) => item.desc).join("、");
        const btns = penEntries
          .map(
            (item) =>
              `<button type="button" class="btn-inline-link" data-action="switch-scope" data-scope="${escapeHtml(
                item.scope
              )}">${escapeHtml(item.btnLabel)}</button>`
          )
          .join("");
        penHtml = `<div class="penetration-banner"><span>另有匹配：${detail}</span><span>${btns}</span></div>`;
      }
      el.projectsContainer.innerHTML = sandboxHtml + penHtml;
      return;
    }

    if (displayCount === 0) {
      const q = state.search.trim();
      let title = "没有匹配的项目";
      let desc = "试试调整搜索关键词、时间范围或筛选条件";
      const actions = [];

      if (penEntries.length > 0) {
        title = q
          ? `当前范围中未找到「${escapeHtml(q)}」`
          : "当前范围中没有符合条件的项目";
        desc = `其他范围有匹配：${penEntries.map((item) => item.desc).join("、")}`;
        penEntries.slice(0, 3).forEach((item, idx) => {
          actions.push(
            `<button type="button" class="btn ${
              idx === 0 ? "btn-primary" : "btn-secondary"
            }" data-action="switch-scope" data-scope="${escapeHtml(item.scope)}">${escapeHtml(
              item.btnLabel
            )}</button>`
          );
        });
      } else if (
        state.scopeFilter === "favorite" &&
        !q &&
        !state.selectedAgent &&
        !state.selectedTag
      ) {
        title = "还没有收藏的项目";
        desc = "点击任意项目左侧的星标，将常用项目固定在这里";
        actions.push(
          `<button type="button" class="btn btn-secondary" data-action="switch-scope" data-scope="local">浏览本地项目</button>`
        );
      } else if (
        state.scopeFilter === "attention" &&
        !q &&
        !state.selectedAgent &&
        !state.selectedTag
      ) {
        title = "全部路径状态正常";
        desc = "当前没有需要确认迁移或清理的缺失项目";
        actions.push(
          `<button type="button" class="btn btn-secondary" data-action="switch-scope" data-scope="local">返回本地项目</button>`
        );
      } else if (
        state.scopeFilter === "remote" &&
        !q &&
        !state.selectedAgent &&
        !state.selectedTag
      ) {
        title = "暂无远程开发项目";
        desc = "使用 SSH Remote 或容器连接远端目录后，将自动按远端路径聚合在此";
      } else if (state.scopeFilter === "hidden") {
        title = "当前没有隐藏的项目";
        desc = "隐藏后的项目会收纳于此，随时可以恢复";
    } else if (
      q ||
      state.selectedAgent ||
      state.selectedTag ||
      state.timeRange ||
      (state.scopeFilter === "local" && state.gitFilter)
    ) {
        title = q ? `没有找到与「${escapeHtml(q)}」匹配的项目` : "当前筛选条件下没有项目";
        desc = "试试更短的路径片段、项目名，或切换至「全部时间」";
        actions.push(
          `<button type="button" class="btn btn-secondary" data-action="reset-filters">清空筛选</button>`
        );
      }

      el.projectsContainer.innerHTML = `
        <div class="empty-state">
          <p class="empty-title">${title}</p>
          <p class="empty-desc">${desc}</p>
          ${actions.length ? `<div class="empty-actions">${actions.join("")}</div>` : ""}
        </div>
      `;
      return;
    }

    const isCardMode = state.layoutMode === "card";
    const useTimeGroups =
      !isRemoteScope &&
      state.sortBy === "recent" &&
      !state.selectedDuplicateKey &&
      state.timeRange !== "dormant30" &&
      (state.scopeFilter === "local" || state.scopeFilter === "favorite");
    let html = isRemoteScope
      ? isCardMode
        ? `<div class="projects-grid">${remoteGroups.map(renderRemoteGroupCardHtml).join("")}</div>`
        : `<div class="list-card">${remoteGroups.map(renderRemoteGroupRowHtml).join("")}</div>`
      : useTimeGroups
      ? renderGroupedProjectsHtml(visible, isCardMode)
      : isCardMode
      ? `<div class="projects-grid">${visible.map(renderProjectCardHtml).join("")}</div>`
      : `<div class="list-card">${visible.map(renderProjectRowHtml).join("")}</div>`;

    if (isLocalScope && sandboxVisible.length > 0) {
      html += renderSandboxSectionHtml(
        sandboxVisible,
        counts.sandbox,
        hasFilter,
        state.sandboxExpanded
      );
    }

    if (penEntries.length > 0) {
      const detail = penEntries.map((item) => item.desc).join("、");
      const btns = penEntries
        .map(
          (item) =>
            `<button type="button" class="btn-inline-link" data-action="switch-scope" data-scope="${escapeHtml(
              item.scope
            )}">${escapeHtml(item.btnLabel)}</button>`
        )
        .join("");
      html += `<div class="penetration-banner">
        <span>另有匹配：${detail}</span>
        <span>${btns}</span>
      </div>`;
    }

    el.projectsContainer.innerHTML = html;
    if (state.restoredId) {
      const rid = state.restoredId;
      setTimeout(() => {
        if (state.restoredId === rid) state.restoredId = null;
      }, 650);
    }
  }

  /* Agents View */
  function renderAgentCardHtml(a, projStats) {
    const actionableIssues = (a.issues || []).filter((code) => ACTIONABLE_CODES.has(code));
    const effectiveStatus =
      a.status === "partial" && actionableIssues.length === 0 ? "ok" : a.status;
    const st = AGENT_STATUS_META[effectiveStatus] || {
      label: effectiveStatus,
      pill: "is-neutral",
    };
    const stats = projStats.get(a.agent) || {
      local: 0,
      remote: 0,
      sandbox: 0,
      attention: 0,
      latest: null,
    };
    const presence = a.installed?.length ? "已安装" : "仅保留本地数据";
    const cat = agentCategory(a.agent);
    const isExt = cat === "extension";
    const hosts = isExt ? a.host_editors || [] : [];
    const issueLink =
      actionableIssues.length > 0
        ? `<button type="button" class="agent-diag-link" data-action="agent-diag" data-agent="${escapeHtml(
            a.agent
          )}">查看 ${actionableIssues.length} 项异常</button>`
        : `<span>${presence}</span>`;

    let primaryNum = stats.local;
    let primaryLabel = "个本地项目";
    const extraMetricParts = [];
    if (stats.local > 0) {
      if (stats.remote > 0) extraMetricParts.push(`${stats.remote} 远程`);
      if (stats.sandbox > 0) extraMetricParts.push(`${stats.sandbox} 沙盒`);
    } else if (stats.remote > 0) {
      primaryNum = stats.remote;
      primaryLabel = "个远程项目";
      if (stats.sandbox > 0) extraMetricParts.push(`${stats.sandbox} 沙盒`);
    } else if (stats.sandbox > 0) {
      primaryNum = stats.sandbox;
      primaryLabel = "个临时沙盒";
    } else if (stats.attention > 0) {
      primaryNum = stats.attention;
      primaryLabel = "项待整理";
    }

    let subMetaHtml = "";
    if (isExt) {
      if (hosts.length > 0) {
        const hostPills = hosts
          .map((h) => {
            const hostLabel = h.display_name || agentDisplayName(h.agent);
            const hostTitle =
              h.records > 0
                ? `${hostLabel}：${h.records} 条发现记录`
                : h.installed
                ? `已安装于 ${hostLabel}`
                : `本地数据位于 ${hostLabel}`;
            return `<span class="agent-host-pill" title="${escapeHtml(
              hostTitle
            )}">${renderAgentIconHtml(h.agent, "xxs")}<span>${escapeHtml(hostLabel)}</span></span>`;
          })
          .join("");
        subMetaHtml = `<div class="agent-card-hosts"><span class="agent-hosts-label">来源</span>${hostPills}</div>`;
      } else {
        subMetaHtml = `<div class="agent-card-meta"><span class="agent-kind-tag">编辑器扩展</span></div>`;
      }
    } else {
      subMetaHtml = `<div class="agent-card-meta"><span class="agent-kind-tag">${escapeHtml(
        CATEGORY_LABEL[cat] || "Agent"
      )}</span></div>`;
    }

    return `<div class="agent-card${isExt ? " is-extension" : ""}" role="button" tabindex="0" data-action="filter-agent" data-agent="${escapeHtml(
      a.agent
    )}">
      <div class="agent-card-top">
        <span class="agent-card-identity">
          ${renderAgentIconHtml(a.agent, "md")}
          <span class="agent-card-name">${escapeHtml(a.display_name || a.agent)}</span>
        </span>
        <span class="status-pill ${st.pill}" title="${escapeHtml(st.desc || "")}">${escapeHtml(
      st.label
    )}</span>
      </div>
      ${subMetaHtml}
      <div class="agent-card-metrics">
        <div>
          <span class="agent-metric-num">${primaryNum}</span>
          <span class="agent-metric-label">${primaryLabel}</span>
        </div>
        ${
          extraMetricParts.length > 0
            ? `<div class="agent-metric-label">${escapeHtml(extraMetricParts.join(" · "))}</div>`
            : ""
        }
      </div>
      <div class="agent-card-foot">
        <span title="${escapeHtml(formatExactTime(stats.latest))}">${
      stats.latest ? `最近 ${formatRelativeTime(stats.latest)}` : "暂无活动时间"
    }</span>
        ${issueLink}
      </div>
    </div>`;
  }

  function computeAgentProjectStats() {
    const projects = state.data?.projects || [];
    const projStats = new Map();
    for (const p of projects) {
      if (p.hidden) continue;
      const kind = assetKind(p);
      const rKey = kind === "remote" ? remoteInfo(p).group_key : null;
      for (const a of p.agents || []) {
        let entry = projStats.get(a);
        if (!entry) {
          entry = {
            local: 0,
            remoteKeys: new Set(),
            remote: 0,
            sandbox: 0,
            attention: 0,
            latest: null,
          };
          projStats.set(a, entry);
        }
        if (kind === "remote") {
          entry.remoteKeys.add(rKey);
          entry.remote = entry.remoteKeys.size;
        } else if (kind === "sandbox") {
          entry.sandbox += 1;
        } else if (p.status === "directory") {
          entry.local += 1;
        } else {
          entry.attention += 1;
        }
        if (p.last_activity && (!entry.latest || p.last_activity > entry.latest)) {
          entry.latest = p.last_activity;
        }
      }
    }
    return projStats;
  }

  function renderAgentsView() {
    if (!state.loaded) return;
    const agents = (state.data.agents || []).filter((a) => a.status !== "unsupported");
    const diags = state.data.diagnostics || [];
    const projStats = computeAgentProjectStats();

    const diagReasonByAgent = new Map();
    for (const d of diags) {
      if (!diagReasonByAgent.has(d.agent)) {
        diagReasonByAgent.set(d.agent, d.reason);
      }
    }

    const activeAgents = agents
      .filter((a) => {
        const st = projStats.get(a.agent);
        return (
          a.records > 0 &&
          (!st || st.local + st.remote + st.sandbox + st.attention > 0)
        );
      })
      .sort((a, b) => {
        const sa = projStats.get(a.agent) || { local: 0, remote: 0, sandbox: 0 };
        const sb = projStats.get(b.agent) || { local: 0, remote: 0, sandbox: 0 };
        return (
          sb.local - sa.local ||
          sb.remote - sa.remote ||
          sb.sandbox - sa.sandbox ||
          b.records - a.records
        );
      });
    const activePrimary = activeAgents.filter((a) => !isExtensionAgent(a.agent));
    const activeExtensions = activeAgents.filter((a) => isExtensionAgent(a.agent));
    const activeSet = new Set(activeAgents.map((a) => a.agent));
    const inactiveAgents = agents.filter((a) => !activeSet.has(a.agent));

    const summaryParts = [];
    if (activePrimary.length > 0) summaryParts.push(`${activePrimary.length} 个 Agent`);
    if (activeExtensions.length > 0) summaryParts.push(`${activeExtensions.length} 个编辑器扩展`);
    el.agentsSummary.textContent =
      summaryParts.length > 0
        ? `${summaryParts.join("、")}正在管理本机项目，点击任意卡片按工具筛选`
        : "暂未发现带有项目路径记录的 Agent 或编辑器扩展";

    if (activePrimary.length > 0) {
      el.agentsPrimarySection.hidden = false;
      const codingCount = activePrimary.filter((a) => agentCategory(a.agent) === "coding_agent").length;
      const editorCount = activePrimary.filter((a) => agentCategory(a.agent) === "editor").length;
      const primaryMetaParts = [];
      if (codingCount > 0) primaryMetaParts.push(`${codingCount} 个 Coding Agent`);
      if (editorCount > 0) primaryMetaParts.push(`${editorCount} 个 VS Code 系编辑器`);
      el.agentsPrimaryMeta.textContent = primaryMetaParts.join(" · ");
      el.agentsPrimaryGrid.innerHTML = activePrimary
        .map((a) => renderAgentCardHtml(a, projStats))
        .join("");
    } else {
      el.agentsPrimarySection.hidden = true;
      el.agentsPrimaryGrid.innerHTML = "";
    }

    if (activeExtensions.length > 0) {
      el.agentsExtensionsSection.hidden = false;
      el.agentsExtensionsMeta.textContent = `${activeExtensions.length} 个 · 按宿主编辑器工作区记录归属`;
      el.agentsExtensionsGrid.innerHTML = activeExtensions
        .map((a) => renderAgentCardHtml(a, projStats))
        .join("");
    } else {
      el.agentsExtensionsSection.hidden = true;
      el.agentsExtensionsGrid.innerHTML = "";
    }

    if (activeAgents.length === 0) {
      el.agentsEmpty.hidden = false;
      el.agentsEmpty.innerHTML = `<div class="empty-state">
        <p class="empty-title">暂无活跃的 Agent 或编辑器扩展</p>
        <p class="empty-desc">已支持的本机工具目前没有可归属的发现记录，点击右上角刷新可重新扫描。</p>
      </div>`;
    } else {
      el.agentsEmpty.hidden = true;
      el.agentsEmpty.innerHTML = "";
    }

    if (inactiveAgents.length === 0) {
      el.agentsInactiveCard.hidden = true;
      return;
    }
    el.agentsInactiveCard.hidden = false;
    el.inactiveAgentsTitle.textContent = `暂无发现记录的工具（${inactiveAgents.length}）`;
    const inactivePrimaryCount = inactiveAgents.filter((a) => !isExtensionAgent(a.agent)).length;
    const inactiveExtCount = inactiveAgents.length - inactivePrimaryCount;
    const metaParts = [];
    if (inactivePrimaryCount > 0) metaParts.push(`${inactivePrimaryCount} 个 Agent`);
    if (inactiveExtCount > 0) metaParts.push(`${inactiveExtCount} 个编辑器扩展`);
    el.inactiveAgentsMeta.textContent = metaParts.join(" · ");

    const sortedInactive = [...inactiveAgents].sort((a, b) => {
      const aExt = isExtensionAgent(a.agent) ? 1 : 0;
      const bExt = isExtensionAgent(b.agent) ? 1 : 0;
      return aExt - bExt;
    });

    el.agentsInactiveList.innerHTML = sortedInactive
      .map((a) => {
        const st = AGENT_STATUS_META[a.status] || { label: a.status, pill: "is-neutral" };
        const reason = formatDiagReason(diagReasonByAgent.get(a.agent), a.status);
        const cat = agentCategory(a.agent);
        const catLabel = CATEGORY_LABEL[cat] || "Agent";
        const hostNames =
          cat === "extension"
            ? (a.host_editors || []).map((h) => h.display_name || agentDisplayName(h.agent)).filter(Boolean)
            : [];
        const installTag = a.installed?.length ? "已安装" : "仅数据遗留";
        const detailBits = [catLabel];
        if (hostNames.length > 0) detailBits.push(`来源 ${hostNames.join(" / ")}`);
        detailBits.push(installTag);
        return `<div class="inactive-agent-row">
          <div class="inactive-agent-left">
            <span class="inactive-agent-name">${renderAgentIconHtml(a.agent, "xs")}<span>${escapeHtml(
              a.display_name || a.agent
            )}</span> <span class="disclosure-meta">· ${escapeHtml(detailBits.join(" · "))}</span></span>
            <span class="inactive-agent-reason">${escapeHtml(reason)}</span>
          </div>
          <span class="status-pill ${st.pill}">${escapeHtml(st.label)}</span>
        </div>`;
      })
      .join("");
  }

  /* Detail Drawer */
  function openDrawer(projectId, triggerEl = null, { openLinkPicker = false } = {}) {
    const project = state.projectById.get(projectId);
    if (!project) return;
    const wasOpen = Boolean(state.selectedProjectId || state.selectedRemoteGroupKey);
    const changed = state.selectedProjectId !== projectId;
    state.selectedProjectId = projectId;
    state.selectedRemoteGroupKey = null;
    state.focusedProjectId = projectId;
    state.linkPickerOpen = Boolean(openLinkPicker);
    state.linkPickerQuery = "";
    if (triggerEl) state.lastTriggerEl = triggerEl;

    renderDrawerContent(project, wasOpen && changed);
    document.body.classList.add("drawer-open");
    el.drawer.inert = false;
    el.drawer.classList.add("is-open");
    el.drawer.setAttribute("aria-hidden", "false");
    el.drawerScrim.classList.add("is-open");

    el.projectsContainer.querySelectorAll(".project-row.is-selected").forEach((row) => {
      row.classList.remove("is-selected");
      row.setAttribute("aria-pressed", "false");
    });
    const activeRow = el.projectsContainer.querySelector(
      `.project-row[data-project-id="${CSS.escape(projectId)}"]`
    );
    if (activeRow) {
      activeRow.classList.add("is-selected");
      activeRow.setAttribute("aria-pressed", "true");
    }
    if (openLinkPicker) {
      setTimeout(() => document.getElementById("link-picker-input")?.focus(), 40);
    }
  }

  function openRemoteGroupDrawer(groupKey, triggerEl = null) {
    const group = state.remoteGroupByKey.get(groupKey);
    if (!group) return;
    if (group.items.length === 1) {
      openDrawer(group.items[0].id, triggerEl);
      return;
    }
    const wasOpen = Boolean(state.selectedProjectId || state.selectedRemoteGroupKey);
    const changed = state.selectedRemoteGroupKey !== groupKey;
    state.selectedProjectId = null;
    state.selectedRemoteGroupKey = groupKey;
    state.linkPickerOpen = false;
    if (triggerEl) state.lastTriggerEl = triggerEl;

    renderRemoteGroupDrawer(group, wasOpen && changed);
    document.body.classList.add("drawer-open");
    el.drawer.inert = false;
    el.drawer.classList.add("is-open");
    el.drawer.setAttribute("aria-hidden", "false");
    el.drawerScrim.classList.add("is-open");

    el.projectsContainer.querySelectorAll(".project-row.is-selected").forEach((row) => {
      row.classList.remove("is-selected");
      row.setAttribute("aria-pressed", "false");
    });
    const activeRow = el.projectsContainer.querySelector(
      `.project-row[data-remote-group="${CSS.escape(groupKey)}"]`
    );
    if (activeRow) {
      activeRow.classList.add("is-selected");
      activeRow.setAttribute("aria-pressed", "true");
    }
  }

  function closeDrawer() {
    if (!state.selectedProjectId && !state.selectedRemoteGroupKey) return;
    state.selectedProjectId = null;
    state.selectedRemoteGroupKey = null;
    state.linkPickerOpen = false;
    document.body.classList.remove("drawer-open");
    el.drawer.classList.remove("is-open");
    el.drawer.setAttribute("aria-hidden", "true");
    el.drawer.inert = true;
    el.drawerScrim.classList.remove("is-open");
    el.projectsContainer.querySelectorAll(".project-row.is-selected").forEach((row) => {
      row.classList.remove("is-selected");
      row.setAttribute("aria-pressed", "false");
    });
    if (state.lastTriggerEl && document.contains(state.lastTriggerEl)) {
      state.lastTriggerEl.focus({ preventScroll: true });
    }
  }

  function renderRemoteGroupDrawer(group, animateSwap = false) {
    const hostCount = group.hosts.length || group.items.length;
    const hostsHtml = group.items
      .map((item, idx) => {
        const info = remoteInfo(item);
        const protoLabel = formatRemoteProtocol(info.protocol);
        const evRows =
          item.workspaces && item.workspaces.length > 0
            ? item.workspaces.map((id) => state.workspaceById.get(id)).filter(Boolean)
            : item.historical_evidence || [];
        const panelId = `remote-host-ev-${idx}`;
        return `<div class="remote-host-card">
          <div class="remote-host-top">
            <span class="remote-host-name">${escapeHtml(info.host || item.path)}</span>
            <span class="evidence-time" title="${escapeHtml(
              formatExactTime(item.last_activity)
            )}">${escapeHtml(formatRelativeTime(item.last_activity))}</span>
          </div>
          <div class="remote-host-meta">
            <span class="status-pill is-remote">${escapeHtml(protoLabel)}</span>
            <span class="agent-badges">${renderAgentBadgesHtml(item.agents || [])}</span>
          </div>
          <div class="remote-host-actions">
            <button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-drawer-action="copy-text" data-text="${escapeHtml(
              item.path
            )}">
              <span class="icon-swap"><span class="icon-base">${ICONS.copy}</span><span class="icon-done">${ICONS.check}</span></span>
              <span>复制远程地址</span>
            </button>
            <button type="button" class="btn btn-subtle" style="height:28px;font-size:12px" data-drawer-action="jump-project" data-id="${escapeHtml(
              item.id
            )}">查看单条详情</button>
            ${
              evRows.length > 0
                ? `<button type="button" class="mini-disclosure-btn" style="margin-left:auto" data-toggle-panel="${panelId}" aria-expanded="false">
                    ${ICONS.chevron}<span>${evRows.length} 条记录</span>
                  </button>`
                : ""
            }
          </div>
          ${
            evRows.length > 0
              ? `<div class="disclosure-panel" id="${panelId}">
                  <div class="disclosure-panel-inner">
                    <div class="raw-evidence-box">${evRows
                      .map((w) => {
                        const desc = describeDiscoveryRecord(w);
                        return `<div>${escapeHtml(desc.nativeTitle)}（${escapeHtml(
                          desc.kindLabel
                        )}）</div>`;
                      })
                      .join("")}</div>
                  </div>
                </div>`
              : ""
          }
        </div>`;
      })
      .join("");

    el.drawerContent.innerHTML = `
      <div class="drawer-header">
        <div class="drawer-title-row">
          <button type="button" class="star-btn${
            group.favorite ? " is-starred" : ""
          }" data-drawer-action="star-target" data-id="${escapeHtml(
      group.primaryId
    )}" aria-label="${group.favorite ? "取消收藏" : "收藏项目"}" title="${
      group.favorite ? "取消收藏" : "收藏项目"
    }">
            ${group.favorite ? ICONS.starFilled : ICONS.starOutline}
          </button>
          <h2 class="drawer-title" title="${escapeHtml(group.name)}">${escapeHtml(group.name)}</h2>
          <button type="button" class="icon-btn" data-drawer-action="close" aria-label="关闭详情">${
            ICONS.close
          }</button>
        </div>
        <div class="drawer-path-box">
          <span class="drawer-path-text">${escapeHtml(group.remotePath)}</span>
        </div>
        <div class="drawer-primary-actions">
          <button type="button" class="btn btn-primary" data-drawer-action="copy-text" data-text="${escapeHtml(
            group.remotePath
          )}">
            <span class="icon-swap"><span class="icon-base">${ICONS.copy}</span><span class="icon-done">${ICONS.check}</span></span>
            <span>复制远端路径</span>
          </button>
        </div>
      </div>
      <div class="drawer-body" id="drawer-body">
        <div class="drawer-section">
          <h3 class="drawer-section-title">远程聚合概览</h3>
          <div class="meta-grid">
            <div class="meta-row">
              <span class="meta-key">类型</span>
              <span class="meta-val"><span class="status-pill is-remote">远程工作区</span></span>
            </div>
            <div class="meta-row">
              <span class="meta-key">关联主机</span>
              <span class="meta-val">${hostCount} 台主机（${group.items.length} 条记录）</span>
            </div>
            <div class="meta-row">
              <span class="meta-key">涉及工具</span>
              <span class="meta-val"><span class="agent-badges">${renderAgentBadgesHtml(
                group.agents
              )}</span></span>
            </div>
            <div class="meta-row">
              <span class="meta-key">最近活动</span>
              <span class="meta-val">${escapeHtml(
                formatExactTime(group.last_activity)
              )}</span>
            </div>
          </div>
        </div>

        <div class="drawer-section">
          <h3 class="drawer-section-title">关联主机（${group.items.length}）</h3>
          <div class="remote-host-list">${hostsHtml}</div>
        </div>
      </div>
      <div class="drawer-footer">
        <span class="drawer-id-label">按远端路径聚合</span>
      </div>
    `;

    if (animateSwap) {
      el.drawerContent.classList.remove("is-swapping");
      void el.drawerContent.offsetWidth;
      el.drawerContent.classList.add("is-swapping");
    }
    const body = document.getElementById("drawer-body");
    if (body) body.scrollTop = 0;
  }

  function renderDrawerContent(project, animateSwap = false) {
    const renderGitSectionHtml = (info) => {
      if (!info) return "";
      const kindMeta = GIT_KIND_META[info.kind] || {
        label: info.is_git ? "Git 仓库" : "纯本地目录",
        pill: info.is_git ? "is-git" : "is-local-only",
      };
      if (!info.is_git) {
        return `
          <div class="drawer-section">
            <h3 class="drawer-section-title">版本控制</h3>
            <div class="meta-grid">
              <div class="meta-row">
                <span class="meta-key">仓库类型</span>
                <span class="meta-val"><span class="status-pill is-local-only">纯本地目录</span></span>
              </div>
              <div class="meta-row">
                <span class="meta-key">说明</span>
                <span class="meta-val">当前目录及上级目录未检测到 .git 仓库</span>
              </div>
            </div>
          </div>
        `;
      }
      const branchText = info.branch
        ? info.detached
          ? `${info.branch}（游离 HEAD）`
          : info.branch
        : "未知";
      const remoteRowHtml = info.remote_url
        ? `<div class="meta-row">
            <span class="meta-key">远端地址${
              info.remote_name && info.remote_name !== "origin"
                ? `（${escapeHtml(info.remote_name)}）`
                : ""
            }</span>
            <span class="meta-val">
              <span class="git-remote-wrap">
                <span class="git-remote-url" title="${escapeHtml(info.remote_url)}">${escapeHtml(
            info.remote_url
          )}</span>
                <button type="button" class="git-inline-copy" data-drawer-action="copy-text" data-text="${escapeHtml(
                  info.remote_url
                )}" aria-label="复制远端地址" title="复制远端地址">
                  <span class="icon-swap"><span class="icon-base">${ICONS.copy}</span><span class="icon-done">${ICONS.check}</span></span>
                </button>
              </span>
            </span>
          </div>`
        : `<div class="meta-row">
            <span class="meta-key">远端地址</span>
            <span class="meta-val">仅本地 Git 仓库（未配置 remote）</span>
          </div>`;
      let parentRowHtml = "";
      if (info.parent_repo) {
        const parentProj = state.projectByPath.get(info.parent_repo);
        const parentShort = shortenPath(info.parent_repo);
        const parentValHtml = parentProj
          ? `<button type="button" class="git-parent-btn" data-drawer-action="jump-project" data-id="${escapeHtml(
              parentProj.id
            )}" title="跳转到父仓库详情：${escapeHtml(info.parent_repo)}">${escapeHtml(
              parentShort
            )}</button>`
          : `<span class="git-parent-text" title="${escapeHtml(info.parent_repo)}">${escapeHtml(
              parentShort
            )}</span>`;
        parentRowHtml = `<div class="meta-row">
          <span class="meta-key">所属父仓库</span>
          <span class="meta-val">${parentValHtml}</span>
        </div>`;
      }
      return `
        <div class="drawer-section">
          <h3 class="drawer-section-title">Git 仓库</h3>
          <div class="meta-grid">
            <div class="meta-row">
              <span class="meta-key">仓库形态</span>
              <span class="meta-val"><span class="status-pill ${kindMeta.pill}">${escapeHtml(
        kindMeta.label
      )}</span></span>
            </div>
            <div class="meta-row">
              <span class="meta-key">当前分支</span>
              <span class="meta-val"><span class="git-branch-pill" title="${escapeHtml(
                branchText
              )}">${escapeHtml(branchText)}</span></span>
            </div>
            ${remoteRowHtml}
            ${parentRowHtml}
          </div>
        </div>
      `;
    };
    const name = projectName(project);
    const statusMeta = STATUS_META[project.status] || {
      label: project.status,
      short: project.status,
      pill: "is-neutral",
    };
    const canOpen = project.status === "directory";
    const isAttention = isAttentionProject(project);
    const agentActivity = projectAgentActivityMap(project);
    const preferredLauncher = canOpen ? preferredLauncherForProject(project) : null;
    const primaryTarget = preferredLauncher ? preferredLauncher.id : "finder";
    const primaryBtn = canOpen
      ? `<button type="button" class="btn btn-primary" data-drawer-action="open" data-target="${escapeHtml(
          primaryTarget
        )}">
          <span class="icon-swap"><span class="icon-base">${renderLauncherChipIcon(
            primaryTarget
          )}</span><span class="icon-done">${ICONS.check}</span></span>
          <span>${
            preferredLauncher ? `用 ${escapeHtml(preferredLauncher.label)} 打开` : "在访达中打开"
          }</span>
        </button>`
      : `<button type="button" class="btn ${isAttention ? "btn-secondary" : "btn-primary"}" data-drawer-action="copy">
          <span class="icon-swap"><span class="icon-base">${ICONS.copy}</span><span class="icon-done">${ICONS.check}</span></span>
          <span>${project.status === "remote" ? "复制远程地址" : "复制原路径"}</span>
        </button>`;

    const secondaryCopyBtn = canOpen
      ? `<button type="button" class="btn btn-secondary" data-drawer-action="copy" title="复制完整路径">
          <span class="icon-swap"><span class="icon-base">${ICONS.copy}</span><span class="icon-done">${ICONS.check}</span></span>
          <span>复制路径</span>
        </button>`
      : "";

    const drawerLaunchChips = [];
    if (canOpen) {
      const projAgents = new Set(project.agents || []);
      const launchers = availableLaunchers()
        .filter(
          (item) =>
            item.id !== primaryTarget &&
            (item.opens_path !== false || projAgents.has(item.id))
        )
        .sort((a, b) => {
          const rank = (item) => {
            if (isAppLauncher(item) && projAgents.has(item.id)) return 0;
            if (item.kind === "editor") return 1;
            if (item.kind === "coding_agent") return 2;
            if (item.kind === "terminal") return 3;
            if (item.kind === "finder") return 4;
            return 9;
          };
          const ra = rank(a);
          const rb = rank(b);
          if (ra !== rb) return ra - rb;
          if (ra === 0) {
            const ta = agentActivity.get(a.id) || "";
            const tb = agentActivity.get(b.id) || "";
            if (ta !== tb) {
              if (!ta) return 1;
              if (!tb) return -1;
              return ta < tb ? 1 : -1;
            }
          }
          return 0;
        });
      for (const item of launchers) {
        const tip =
          item.opens_path === false
            ? `打开 ${item.label} 应用（暂不支持直接传入目录）`
            : `在 ${item.label} 中打开`;
        drawerLaunchChips.push(
          `<button type="button" class="launch-chip" data-drawer-action="open" data-target="${escapeHtml(
            item.id
          )}" title="${escapeHtml(tip)}">
            <span class="icon-swap"><span class="icon-base">${renderLauncherChipIcon(
              item.id
            )}</span><span class="icon-done">${ICONS.check}</span></span>
            <span>${escapeHtml(item.label)}</span>
          </button>`
        );
      }
      if (project.git?.web_url) {
        drawerLaunchChips.push(
          `<button type="button" class="launch-chip" data-drawer-action="open" data-target="remote" title="在浏览器打开 Git 仓库 (${escapeHtml(
            project.git.web_url
          )})">
            <span class="icon-swap"><span class="icon-base">${ICONS.externalLink}</span><span class="icon-done">${ICONS.check}</span></span>
            <span>Git 仓库</span>
          </button>`
        );
      }
    }
    const drawerLaunchStripHtml =
      drawerLaunchChips.length > 0
        ? `<div class="drawer-launch-strip" aria-label="其他打开方式">${drawerLaunchChips.join("")}</div>`
        : "";

    const currentTags = project.tags || [];
    const currentTagSet = new Set(currentTags.map((t) => t.toLowerCase()));
    const suggestions = (state.data?.all_tags || [])
      .map((item) => item.tag)
      .filter((t) => !currentTagSet.has(t.toLowerCase()))
      .slice(0, 8);

    const tagsHtml = currentTags
      .map(
        (tag) => `<span class="tag-removable" data-tag-chip="${escapeHtml(tag)}">
          <span>#${escapeHtml(tag)}</span>
          <button type="button" class="tag-remove-btn" data-drawer-action="remove-tag" data-tag="${escapeHtml(
            tag
          )}" aria-label="移除标签 ${escapeHtml(tag)}">${ICONS.close}</button>
        </span>`
      )
      .join("");

    const suggestionsHtml = suggestions
      .map(
        (tag) =>
          `<button type="button" class="tag-suggest-btn" data-drawer-action="add-suggest-tag" data-tag="${escapeHtml(
            tag
          )}">+ ${escapeHtml(tag)}</button>`
      )
      .join("");

    const rawEvidenceRows =
      project.workspaces && project.workspaces.length > 0
        ? project.workspaces.map((id) => state.workspaceById.get(id)).filter(Boolean)
        : project.historical_evidence || [];
    const evidenceRows = [...rawEvidenceRows].sort((a, b) => {
      const aExt = isExtensionAgent(a.agent) ? 1 : 0;
      const bExt = isExtensionAgent(b.agent) ? 1 : 0;
      if (aExt !== bExt) return aExt - bExt;
      const ta = workspaceActivityForProject(a, project.path);
      const tb = workspaceActivityForProject(b, project.path);
      if (ta !== tb) {
        if (!ta) return 1;
        if (!tb) return -1;
        return ta < tb ? 1 : -1;
      }
      return 0;
    });

    const evidenceHtml =
      evidenceRows.length > 0
        ? evidenceRows
            .map((w, idx) => {
              const info = describeDiscoveryRecord(w);
              const roots = w.roots || [];
              const multiRootHtml =
                roots.length > 1
                  ? `<div class="evidence-roots">
                      <div class="evidence-roots-label">包含 ${roots.length} 个项目路径</div>
                      ${roots
                        .map((r) => {
                          if (r === project.path) {
                            return `<div class="evidence-root is-current">${escapeHtml(
                              shortenPath(r)
                            )}（当前）</div>`;
                          }
                          const sibling = state.projectByPath.get(r);
                          if (sibling) {
                            return `<button type="button" class="evidence-root-btn" data-drawer-action="jump-project" data-id="${escapeHtml(
                              sibling.id
                            )}" title="查看该项目详情">${escapeHtml(shortenPath(r))}</button>`;
                          }
                          return `<div class="evidence-root">${escapeHtml(shortenPath(r))}</div>`;
                        })
                        .join("")}
                    </div>`
                  : "";

              const rawItems = [];
              if (w.native_id) rawItems.push(`原生 ID：${w.native_id}`);
              if (w.desktop_ids?.length) rawItems.push(`桌面 ID：${w.desktop_ids.join(", ")}`);
              if (w.chatgpt_project_id) rawItems.push(`ChatGPT ID：${w.chatgpt_project_id}`);
              for (const src of w.sources || []) {
                rawItems.push(shortenPath(src));
              }
              const rawId = `raw-ev-${idx}`;
              return `<div class="evidence-card">
                <div class="evidence-top">
                  <span class="evidence-agent">
                    ${renderAgentIconHtml(w.agent, "xs")}
                    <span>${escapeHtml(info.nativeTitle)}</span>
                    <span class="evidence-kind ${info.kindTone}">${escapeHtml(info.kindLabel)}</span>
                  </span>
                  <span class="evidence-time" title="${escapeHtml(
                    formatExactTime(w.last_activity)
                  )}">${escapeHtml(formatRelativeTime(w.last_activity))}</span>
                </div>
                ${
                  info.hostSummary
                    ? `<div class="evidence-meta-line">${escapeHtml(info.hostSummary)}</div>`
                    : ""
                }
                ${
                  w.name && w.name !== name
                    ? `<div class="evidence-meta-line">${escapeHtml(info.nativeNameLabel)}：${escapeHtml(
                        w.name
                      )}</div>`
                    : ""
                }
                ${multiRootHtml}
                ${
                  rawItems.length
                    ? `<button type="button" class="mini-disclosure-btn" data-toggle-panel="${rawId}" aria-expanded="false">
                        ${ICONS.chevron}<span>查看原始来源与标识</span>
                      </button>
                      <div class="disclosure-panel" id="${rawId}">
                        <div class="disclosure-panel-inner">
                          <div class="raw-evidence-box">${rawItems
                            .map((line) => `<div>${escapeHtml(line)}</div>`)
                            .join("")}</div>
                        </div>
                      </div>`
                    : ""
                }
              </div>`;
            })
            .join("")
        : `<div class="inactive-agent-reason">暂无可展开的发现记录明细。</div>`;

    const relatedIds = project.related_projects || [];
    const relatedHtml = relatedIds
      .map((rid) => {
        const target = state.projectById.get(rid);
        const tName = target ? projectName(target) : rid;
        const tPath = target ? shortenPath(target.path) : "索引外项目";
        return `<div class="related-item">
          <button type="button" class="related-jump" data-drawer-action="jump-project" data-id="${escapeHtml(
            rid
          )}">
            <span class="related-name">${escapeHtml(tName)}</span>
            <span class="related-path">${escapeHtml(tPath)}</span>
          </button>
          <button type="button" class="icon-btn" data-drawer-action="unlink" data-id="${escapeHtml(
            rid
          )}" aria-label="解除关联" title="解除关联">${ICONS.close}</button>
        </div>`;
      })
      .join("");

    const linkPickerHtml = state.linkPickerOpen
      ? renderLinkPickerHtml(project)
      : `<button type="button" class="btn btn-subtle" data-drawer-action="open-link-picker">关联迁移前后的其他路径</button>`;

    const indexStateText =
      project.index_state === "historical"
        ? `历史记录（上次出现于 ${formatExactTime(project.last_seen)}）`
        : "最近一次扫描已确认";

    const isSandbox = isSandboxProject(project);
    const isPromotedSandbox = project.asset_reason === "promoted_sandbox";
    const isRemote = project.status === "remote";
    const rInfo = isRemote ? remoteInfo(project) : null;
    const gInfo = gitInfo(project);
    const gitSectionHtml = renderGitSectionHtml(gInfo);
    const dupGroup = state.duplicateGroupByProjectId.get(project.id);
    const drawerDupCalloutHtml =
      dupGroup && dupGroup.count >= 2 && canOpen
        ? `<div class="drawer-inline-callout">
            <div class="drawer-inline-callout-text">
              <span class="drawer-inline-callout-title">本机另有 ${dupGroup.count - 1} 份同源副本</span>
              <span class="drawer-inline-callout-sub">${escapeHtml(dupGroup.name)} · 共 ${dupGroup.count} 个本地目录</span>
            </div>
            <button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-drawer-action="compare-duplicates" data-remote-key="${escapeHtml(
              dupGroup.remote_key
            )}">去对比</button>
          </div>`
        : "";
    const reclaimBytes = projectReclaimableBytes(project.id);
    const artifacts = projectArtifacts(project.id);
    const drawerHygieneCalloutHtml =
      canOpen && reclaimBytes > 0
        ? `<div class="drawer-inline-callout">
            <div class="drawer-inline-callout-text">
              <span class="drawer-inline-callout-title">可安全瘦身 ${escapeHtml(formatBytes(reclaimBytes))}</span>
              <span class="drawer-inline-callout-sub">${escapeHtml(
                artifacts
                  .slice(0, 3)
                  .map((a) => `${a.rel_path} (${formatBytes(a.bytes)})`)
                  .join("、")
              )}</span>
            </div>
            <button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-drawer-action="slim-project">清理依赖</button>
          </div>`
        : "";

    let contextCardHtml = "";
    if (isAttention) {
      const titleText =
        project.status === "missing"
          ? "原路径已不存在，请确认处理方式"
          : project.status === "inaccessible"
          ? "当前无权限访问该目录"
          : "原路径已不再是目录";
      contextCardHtml = `
        <div class="drawer-action-card is-attention">
          <div class="drawer-action-title">${escapeHtml(titleText)}</div>
          <div class="drawer-action-desc">若目录已迁移或重命名，可关联到新项目以保留跨工具历史；若确认不再需要，可直接移出待整理。</div>
          <div class="drawer-action-row">
            <button type="button" class="btn btn-primary" style="height:32px" data-drawer-action="open-link-picker">关联到现有项目</button>
            <button type="button" class="btn btn-secondary" style="height:32px" data-drawer-action="dismiss-missing">确认已删除并移除</button>
          </div>
        </div>
      `;
    } else if (isSandbox) {
      const sandboxTitle =
        project.asset_reason === "active_worktree"
          ? "Git Worktree 分支目录"
          : "Agent 自动创建的临时沙盒目录";
      contextCardHtml = `
        <div class="drawer-action-card is-sandbox">
          <div class="drawer-action-title">${escapeHtml(sandboxTitle)}</div>
          <div class="drawer-action-desc">默认收纳在「临时沙盒」以保持主列表整洁。如果这是你的长期项目，可以一键提升到「本地项目」。</div>
          <div class="drawer-action-row">
            <button type="button" class="btn btn-primary" style="height:32px" data-drawer-action="promote">提升为正式项目</button>
          </div>
        </div>
      `;
    }

    el.drawerContent.innerHTML = `
      <div class="drawer-header">
        <div class="drawer-title-row">
          <button type="button" class="star-btn${
            project.favorite ? " is-starred" : ""
          }" data-drawer-action="star" aria-label="${
      project.favorite ? "取消收藏" : "收藏项目"
    }" title="${project.favorite ? "取消收藏 (S)" : "收藏项目 (S)"}">
            ${project.favorite ? ICONS.starFilled : ICONS.starOutline}
          </button>
          <h2 class="drawer-title" title="${escapeHtml(name)}">${escapeHtml(name)}</h2>
          <button type="button" class="icon-btn" data-drawer-action="close" aria-label="关闭详情">${
            ICONS.close
          }</button>
        </div>
        <div class="drawer-path-box">
          <span class="drawer-path-text">${escapeHtml(project.path)}</span>
        </div>
        <div class="drawer-primary-actions">
          ${primaryBtn}
          ${secondaryCopyBtn}
        </div>
        ${drawerLaunchStripHtml}
      </div>
      <div class="drawer-body" id="drawer-body">
        ${contextCardHtml}
        <div class="drawer-section">
          <h3 class="drawer-section-title">状态与最近活动</h3>
          <div class="meta-grid">
            <div class="meta-row">
              <span class="meta-key">目录状态</span>
              <span class="meta-val"><span class="status-pill ${statusMeta.pill}">${escapeHtml(
      statusMeta.short || "可用"
    )}</span></span>
            </div>
            ${
              isRemote && rInfo?.host
                ? `<div class="meta-row">
                    <span class="meta-key">远程主机</span>
                    <span class="meta-val">${escapeHtml(rInfo.host)}</span>
                  </div>
                  <div class="meta-row">
                    <span class="meta-key">远端路径</span>
                    <span class="meta-val">${escapeHtml(rInfo.remote_path)}</span>
                  </div>`
                : `<div class="meta-row">
                    <span class="meta-key">说明</span>
                    <span class="meta-val">${escapeHtml(statusMeta.label)}</span>
                  </div>`
            }
            <div class="meta-row">
              <span class="meta-key">索引状态</span>
              <span class="meta-val">${escapeHtml(indexStateText)}</span>
            </div>
            <div class="meta-row">
              <span class="meta-key">最近活动</span>
              <span class="meta-val">${escapeHtml(
                formatExactTime(project.last_activity)
              )}</span>
            </div>
            ${
              project.activity_source
                ? `<button type="button" class="mini-disclosure-btn" data-toggle-panel="drawer-activity-src" aria-expanded="false">
                    ${ICONS.chevron}<span>查看时间依据</span>
                  </button>
                  <div class="disclosure-panel" id="drawer-activity-src">
                    <div class="disclosure-panel-inner">
                      <div class="raw-evidence-box">${escapeHtml(
                        shortenPath(project.activity_source)
                      )}</div>
                    </div>
                  </div>`
                : ""
            }
          </div>
          ${drawerHygieneCalloutHtml}
        </div>

        ${gitSectionHtml}
        ${drawerDupCalloutHtml}

        <div class="drawer-section">
          <h3 class="drawer-section-title">标签</h3>
          ${tagsHtml ? `<div class="tag-list">${tagsHtml}</div>` : ""}
          <form class="tag-input-row" id="drawer-tag-form">
            <input type="text" id="drawer-tag-input" class="text-input" maxlength="32" placeholder="输入新标签并回车，如 核心项目" autocomplete="off">
            <button type="submit" class="btn btn-secondary" style="height:32px">添加</button>
          </form>
          <div class="inline-error" id="drawer-tag-error" hidden></div>
          ${suggestionsHtml ? `<div class="tag-suggestions">${suggestionsHtml}</div>` : ""}
        </div>

        <div class="drawer-section">
          <h3 class="drawer-section-title">发现记录（${evidenceRows.length}）</h3>
          <div class="evidence-list">${evidenceHtml}</div>
        </div>

        <div class="drawer-section">
          <h3 class="drawer-section-title">关联项目${
            relatedIds.length ? `（${relatedIds.length}）` : ""
          }</h3>
          ${relatedHtml}
          ${linkPickerHtml}
        </div>
      </div>
      <div class="drawer-footer">
        <span class="drawer-id-label">${escapeHtml(project.id)}</span>
        <div style="display:flex;align-items:center;gap:6px">
          ${
            canOpen
              ? `<button type="button" class="btn btn-subtle" data-drawer-action="trash-project" title="检查 Git 状态后移入废纸篓">移入废纸篓</button>`
              : ""
          }
          ${
            isPromotedSandbox
              ? `<button type="button" class="btn btn-subtle" data-drawer-action="demote">移回临时沙盒</button>`
              : ""
          }
          <button type="button" class="btn btn-subtle" data-drawer-action="${
            project.hidden ? "unhide" : "hide"
          }">
            ${project.hidden ? ICONS.eye : ICONS.eyeOff}
            <span>${project.hidden ? "恢复显示" : "隐藏此项目"}</span>
          </button>
        </div>
      </div>
    `;

    if (animateSwap) {
      el.drawerContent.classList.remove("is-swapping");
      void el.drawerContent.offsetWidth;
      el.drawerContent.classList.add("is-swapping");
    }
    const body = document.getElementById("drawer-body");
    if (body) body.scrollTop = 0;
  }

  function getLinkCandidates(project) {
    const excluded = new Set([project.id, ...(project.related_projects || [])]);
    const q = state.linkPickerQuery.trim().toLowerCase();
    const matches = (state.data?.projects || []).filter(
      (p) => !excluded.has(p.id) && !p.hidden && (!q || matchesQuery(p, q))
    );
    matches.sort((a, b) => {
      const aLocal = isLocalProject(a) ? 0 : 1;
      const bLocal = isLocalProject(b) ? 0 : 1;
      if (aLocal !== bLocal) return aLocal - bLocal;
      return compareRecent(a, b);
    });
    return matches.slice(0, 8);
  }

  function renderLinkPickerHtml(project) {
    const candidates = getLinkCandidates(project);

    return `<div class="evidence-card">
      <div class="tag-input-row">
        <input type="search" id="link-picker-input" class="text-input" value="${escapeHtml(
          state.linkPickerQuery
        )}" placeholder="搜索要关联的项目名或路径" autocomplete="off">
        <button type="button" class="btn btn-subtle" style="height:32px" data-drawer-action="close-link-picker">取消</button>
      </div>
      <div class="link-picker-results" id="link-picker-results">
        ${
          candidates.length
            ? candidates
                .map(
                  (c) => `<button type="button" class="link-candidate-btn" data-drawer-action="add-link" data-id="${escapeHtml(
                    c.id
                  )}">
                    <span class="related-name">${escapeHtml(projectName(c))}</span>
                    <span class="related-path">${escapeHtml(shortenPath(c.path))}</span>
                  </button>`
                )
                .join("")
            : `<div class="inactive-agent-reason">没有找到可关联的其他项目</div>`
        }
      </div>
    </div>`;
  }

  /* Anchored Tag Popover */
  function openTagPopover(projectId, anchorEl) {
    const project = state.projectById.get(projectId);
    if (!project) return;
    if (state.popoverProjectId === projectId && !el.tagPopover.hidden) {
      closeTagPopover();
      return;
    }
    state.popoverProjectId = projectId;
    renderTagPopover(project);
    el.tagPopover.hidden = false;

    const rect = anchorEl.getBoundingClientRect();
    const popRect = el.tagPopover.getBoundingClientRect();
    const left = Math.max(
      12,
      Math.min(rect.right - popRect.width, window.innerWidth - popRect.width - 12)
    );
    const belowTop = rect.bottom + 6;
    const top =
      belowTop + popRect.height <= window.innerHeight - 12
        ? belowTop
        : Math.max(12, rect.top - popRect.height - 6);
    el.tagPopover.style.left = `${left}px`;
    el.tagPopover.style.top = `${top}px`;
    const input = el.tagPopover.querySelector("input");
    if (input) input.focus();
  }

  function renderTagPopover(project) {
    const current = project.tags || [];
    const curSet = new Set(current.map((t) => t.toLowerCase()));
    const suggestions = (state.data?.all_tags || [])
      .map((item) => item.tag)
      .filter((t) => !curSet.has(t.toLowerCase()))
      .slice(0, 8);

    el.tagPopover.innerHTML = `
      <div class="popover-title">为「${escapeHtml(projectName(project))}」管理标签</div>
      ${
        current.length
          ? `<div class="tag-list">${current
              .map(
                (tag) => `<span class="tag-removable">
                  <span>#${escapeHtml(tag)}</span>
                  <button type="button" class="tag-remove-btn" data-pop-action="remove-tag" data-tag="${escapeHtml(
                    tag
                  )}" aria-label="移除标签">${ICONS.close}</button>
                </span>`
              )
              .join("")}</div>`
          : ""
      }
      <form class="tag-input-row" id="popover-tag-form">
        <input type="text" class="text-input" maxlength="32" placeholder="输入标签后回车" autocomplete="off">
        <button type="submit" class="btn btn-primary" style="height:32px;padding:0 10px">添加</button>
      </form>
      <div class="inline-error" id="popover-tag-error" hidden></div>
      ${
        suggestions.length
          ? `<div class="tag-suggestions">${suggestions
              .map(
                (tag) =>
                  `<button type="button" class="tag-suggest-btn" data-pop-action="add-tag" data-tag="${escapeHtml(
                    tag
                  )}">+ ${escapeHtml(tag)}</button>`
              )
              .join("")}</div>`
          : ""
      }
    `;
  }

  function closeTagPopover() {
    state.popoverProjectId = null;
    el.tagPopover.hidden = true;
  }

  /* Diagnostics Modal */
  function openDiagnosticsModal(agentFilter = null) {
    state.diagOpen = true;
    state.diagAgentFilter = agentFilter;
    closeTagPopover();
    renderDiagnosticsModal();
    if (el.topbar) el.topbar.inert = true;
    if (el.appShell) el.appShell.inert = true;
    el.drawer.inert = true;
    el.diagModal.inert = false;
    el.diagScrim.classList.add("is-open");
    el.diagModal.classList.add("is-open");
    el.diagModal.setAttribute("aria-hidden", "false");
    el.btnCloseDiag.focus();
  }

  function closeDiagnosticsModal() {
    if (!state.diagOpen) return;
    state.diagOpen = false;
    el.diagScrim.classList.remove("is-open");
    el.diagModal.classList.remove("is-open");
    el.diagModal.setAttribute("aria-hidden", "true");
    el.diagModal.inert = true;
    if (el.topbar) el.topbar.inert = false;
    if (el.appShell) el.appShell.inert = false;
    el.drawer.inert = !(state.selectedProjectId || state.selectedRemoteGroupKey);
    el.btnDiagnostics.focus();
  }

  function renderDiagnosticsModal() {
    const allDiags = state.data?.diagnostics || [];
    const diags = state.diagAgentFilter
      ? allDiags.filter((d) => d.agent === state.diagAgentFilter)
      : allDiags;
    const actionable = diags.filter((d) => ACTIONABLE_CODES.has(d.code));
    const info = diags.filter((d) => !ACTIONABLE_CODES.has(d.code));

    el.diagSubtitle.textContent = `${actionable.length} 项建议处理 · ${info.length} 项常规说明`;
    if (state.diagAgentFilter) {
      el.diagFilterBar.hidden = false;
      el.diagFilterBar.innerHTML = `<span class="filter-chip is-agent-chip">仅查看：${escapeHtml(
        agentDisplayName(state.diagAgentFilter)
      )}</span>
      <button type="button" class="btn-inline-link" id="btn-diag-show-all">查看全部诊断</button>`;
    } else {
      el.diagFilterBar.hidden = true;
    }

    let html = "";
    if (actionable.length === 0) {
      html += `<div class="diag-ok-banner">当前没有阻塞读取的权限或异常错误，所有可访问数据源均已正常读取。</div>`;
    } else {
      html += `<div>
        <h3 class="diag-tier-title">需要处理（${actionable.length}）</h3>
        <div class="diag-group-card">
          ${actionable
            .map((d) => {
              const st = AGENT_STATUS_META[d.code] || { label: d.code, pill: "is-error" };
              const guide = DIAG_GUIDANCE[d.code] || "";
              return `<div class="diag-item">
                <div class="diag-item-top">
                  <strong>${escapeHtml(agentDisplayName(d.agent))}</strong>
                  <span class="status-pill ${st.pill}">${escapeHtml(st.label)}</span>
                </div>
                <div class="diag-item-source">${escapeHtml(shortenPath(d.source))}</div>
                <div class="diag-item-reason">${escapeHtml(formatDiagReason(d.reason, d.code))}</div>
                ${guide ? `<div class="diag-guidance">${escapeHtml(guide)}</div>` : ""}
              </div>`;
            })
            .join("")}
        </div>
      </div>`;
    }

    if (info.length > 0) {
      const byAgent = new Map();
      for (const item of info) {
        const list = byAgent.get(item.agent) || [];
        list.push(item);
        byAgent.set(item.agent, list);
      }
      const groupsHtml = Array.from(byAgent.entries())
        .map(([agentId, items], idx) => {
          const panelId = `diag-info-${idx}`;
          const expanded = Boolean(state.diagAgentFilter) || items.length <= 2;
          const codes = Array.from(
            new Set(items.map((i) => (AGENT_STATUS_META[i.code] || { label: i.code }).label))
          ).join(" / ");
          return `<div class="diag-group-card">
            <button type="button" class="disclosure-trigger" data-toggle-panel="${panelId}" aria-expanded="${
            expanded ? "true" : "false"
          }">
              <span class="disclosure-left">
                ${ICONS.chevron}
                <span>${escapeHtml(agentDisplayName(agentId))}</span>
              </span>
              <span class="disclosure-meta">${escapeHtml(codes)} · ${items.length} 条</span>
            </button>
            <div class="disclosure-panel${expanded ? " is-open" : ""}" id="${panelId}">
              <div class="disclosure-panel-inner">
                ${items
                  .map((d) => {
                    const st = AGENT_STATUS_META[d.code] || { label: d.code, pill: "is-neutral" };
                    return `<div class="diag-item">
                      <div class="diag-item-top">
                        <span class="diag-item-source">${escapeHtml(shortenPath(d.source))}</span>
                        <span class="status-pill ${st.pill}">${escapeHtml(st.label)}</span>
                      </div>
                      <div class="diag-item-reason">${escapeHtml(formatDiagReason(d.reason, d.code))}</div>
                    </div>`;
                  })
                  .join("")}
              </div>
            </div>
          </div>`;
        })
        .join("");
      html += `<div>
        <h3 class="diag-tier-title">常规说明（${info.length} · 本机常见状态，不影响正常使用）</h3>
        ${groupsHtml}
      </div>`;
    }

    el.diagBody.innerHTML = html;
  }

  /* Toast System with Pause-on-Hover */
  function dismissToast() {
    if (!state.toastHandle) return;
    const handle = state.toastHandle;
    state.toastHandle = null;
    clearTimeout(handle.timer);
    handle.node.classList.remove("is-open");
    handle.node.classList.add("is-leaving");
    setTimeout(() => handle.node.remove(), 200);
  }

  function showToast(message, { sub = "", actionLabel = "", onAction = null, duration = 4200 } = {}) {
    dismissToast();
    const node = document.createElement("div");
    node.className = "toast";
    node.innerHTML = `
      <div class="toast-text">
        <span>${escapeHtml(message)}</span>
        ${sub ? `<span class="toast-sub">${escapeHtml(sub)}</span>` : ""}
      </div>
      ${actionLabel ? `<button type="button" class="toast-action">${escapeHtml(actionLabel)}</button>` : ""}
      <div class="toast-timer"></div>
    `;
    el.toastHost.appendChild(node);

    const timerBar = node.querySelector(".toast-timer");
    let remaining = duration;
    let startedAt = Date.now();
    const handle = { node, timer: null };
    state.toastHandle = handle;

    const startCountdown = () => {
      startedAt = Date.now();
      if (timerBar) {
        timerBar.style.transition = `transform ${remaining}ms linear`;
        requestAnimationFrame(() => {
          timerBar.style.transform = "scaleX(0)";
        });
      }
      handle.timer = setTimeout(dismissToast, remaining);
    };

    const pauseCountdown = () => {
      clearTimeout(handle.timer);
      const elapsed = Date.now() - startedAt;
      remaining = Math.max(400, remaining - elapsed);
      if (timerBar) {
        const ratio = remaining / duration;
        timerBar.style.transition = "none";
        timerBar.style.transform = `scaleX(${ratio})`;
      }
    };

    node.addEventListener("mouseenter", pauseCountdown);
    node.addEventListener("mouseleave", startCountdown);

    const actionBtn = node.querySelector(".toast-action");
    if (actionBtn && onAction) {
      actionBtn.addEventListener("click", () => {
        dismissToast();
        onAction();
      });
    }

    requestAnimationFrame(() => {
      node.classList.add("is-open");
      startCountdown();
    });
  }

  /* Micro-feedback Helpers */
  function flashButtonDone(btn) {
    if (!btn) return;
    const existing = state.buttonTimers.get(btn);
    if (existing) clearTimeout(existing);
    btn.classList.add("is-done");
    const timer = setTimeout(() => {
      btn.classList.remove("is-done");
      state.buttonTimers.delete(btn);
    }, 1400);
    state.buttonTimers.set(btn, timer);
  }

  function shakeElement(node) {
    if (!node) return;
    node.classList.remove("is-shaking");
    void node.offsetWidth;
    node.classList.add("is-shaking");
  }

  /* Mutations */
  async function toggleStar(projectId, btnEl = null) {
    const project = state.projectById.get(projectId);
    if (!project) return;
    const next = !project.favorite;
    project.favorite = next;

    const updateStarButton = (btn) => {
      if (!btn) return;
      btn.classList.toggle("is-starred", next);
      btn.innerHTML = next ? ICONS.starFilled : ICONS.starOutline;
      btn.setAttribute("aria-label", next ? "取消收藏" : "收藏项目");
      btn.classList.remove("is-pop-on", "is-pop-off");
      void btn.offsetWidth;
      btn.classList.add(next ? "is-pop-on" : "is-pop-off");
    };

    updateStarButton(btnEl);
    const rowStar = el.projectsContainer.querySelector(
      `.star-btn[data-id="${CSS.escape(projectId)}"]`
    );
    if (rowStar && rowStar !== btnEl) updateStarButton(rowStar);
    const drawerStar =
      state.selectedProjectId === projectId
        ? el.drawerContent.querySelector('[data-drawer-action="star"]')
        : null;
    if (drawerStar && drawerStar !== btnEl) updateStarButton(drawerStar);

    const { counts } = computeFilteredState();
    renderToolbarMeta(counts);
    if (state.scopeFilter === "favorite" && !next) {
      renderProjectsView();
    }

    try {
      const res = await api(`/api/projects/${encodeURIComponent(projectId)}/meta`, {
        method: "PATCH",
        body: JSON.stringify({ favorite: next }),
      });
      project.favorite = res.favorite;
      state.data.all_tags = res.all_tags;
    } catch (err) {
      project.favorite = !next;
      renderAll();
      shakeElement(btnEl);
      showToast("更新收藏失败", { sub: err.message });
    }
  }

  async function setProjectHidden(projectId, hidden, { fromUndo = false, reason = "hide" } = {}) {
    const project = state.projectById.get(projectId);
    if (!project) return;
    const name = projectName(project);

    const pending = state.pendingHideTimers.get(projectId);
    if (pending) {
      clearTimeout(pending);
      state.pendingHideTimers.delete(projectId);
    }

    const wrap = el.projectsContainer.querySelector(
      `.project-row-wrap[data-row-wrap="${CSS.escape(projectId)}"]`
    );
    const willRemoveFromCurrentView =
      (hidden && state.scopeFilter !== "hidden") ||
      (!hidden && state.scopeFilter === "hidden");

    project.hidden = hidden;
    if (!hidden && fromUndo) {
      state.restoredId = projectId;
    }

    if (wrap && willRemoveFromCurrentView) {
      wrap.classList.add("is-collapsing");
      const timer = setTimeout(() => {
        state.pendingHideTimers.delete(projectId);
        renderProjectsView();
      }, 190);
      state.pendingHideTimers.set(projectId, timer);
      const { counts } = computeFilteredState();
      renderToolbarMeta(counts);
    } else {
      renderProjectsView();
    }

    if (state.selectedProjectId === projectId) {
      renderDrawerContent(project, false);
    }

    try {
      const res = await api(`/api/projects/${encodeURIComponent(projectId)}/meta`, {
        method: "PATCH",
        body: JSON.stringify({ hidden }),
      });
      project.hidden = res.hidden;
      state.data.all_tags = res.all_tags;
      const { counts } = computeFilteredState();
      renderToolbarMeta(counts);

      if (hidden) {
        const msg =
          reason === "dismiss" ? `已从待整理移除「${name}」` : `已隐藏「${name}」`;
        showToast(msg, {
          actionLabel: "撤销",
          duration: 5000,
          onAction: () => setProjectHidden(projectId, false, { fromUndo: true, reason }),
        });
      } else {
        showToast(`已恢复显示「${name}」`, { duration: 2500 });
      }
    } catch (err) {
      project.hidden = !hidden;
      renderAll();
      showToast(hidden ? "隐藏失败" : "恢复失败", { sub: err.message });
    }
  }

  async function setProjectPromoted(projectId, promoted) {
    const project = state.projectById.get(projectId);
    if (!project) return;
    const name = projectName(project);
    const prevPromoted = Boolean(project.promoted);
    const prevKind = project.asset_kind;
    const prevReason = project.asset_reason;

    project.promoted = promoted;
    project.asset_kind = promoted ? "project" : "sandbox";
    project.asset_reason = promoted ? "promoted_sandbox" : "agent_sandbox";
    renderAll();
    if (state.selectedProjectId === projectId) {
      renderDrawerContent(project, false);
    }

    try {
      const res = await api(`/api/projects/${encodeURIComponent(projectId)}/meta`, {
        method: "PATCH",
        body: JSON.stringify({ promoted }),
      });
      project.promoted = Boolean(res.promoted);
      if (res.asset_kind) project.asset_kind = res.asset_kind;
      if (res.asset_reason) project.asset_reason = res.asset_reason;
      state.data.all_tags = res.all_tags;
      renderAll();
      if (state.selectedProjectId === projectId) {
        renderDrawerContent(project, false);
      }
      showToast(
        promoted ? `已将「${name}」提升为正式项目` : `已将「${name}」移回临时沙盒`,
        {
          actionLabel: "撤销",
          duration: 4500,
          onAction: () => setProjectPromoted(projectId, !promoted),
        }
      );
    } catch (err) {
      project.promoted = prevPromoted;
      project.asset_kind = prevKind;
      project.asset_reason = prevReason;
      renderAll();
      if (state.selectedProjectId === projectId) {
        renderDrawerContent(project, false);
      }
      showToast(promoted ? "提升失败" : "移回失败", { sub: err.message });
    }
  }

  async function resolveMissingByLink(missingId, targetId) {
    const missingProj = state.projectById.get(missingId);
    const targetProj = state.projectById.get(targetId);
    if (!missingProj || !targetProj) return;
    try {
      const res = await api("/api/links", {
        method: "POST",
        body: JSON.stringify({ first: missingId, second: targetId }),
      });
      for (const [pid, related] of Object.entries(res.related || {})) {
        const target = state.projectById.get(pid);
        if (target) {
          if (related.length > 0) target.related_projects = related;
          else delete target.related_projects;
        }
      }
      const metaRes = await api(`/api/projects/${encodeURIComponent(missingId)}/meta`, {
        method: "PATCH",
        body: JSON.stringify({ hidden: true }),
      });
      missingProj.hidden = Boolean(metaRes.hidden);
      state.data.all_tags = metaRes.all_tags;
      state.linkPickerOpen = false;
      state.linkPickerQuery = "";
      renderAll();
      openDrawer(targetId);
      showToast(`已关联至「${projectName(targetProj)}」，原缺失记录已移出待整理`, {
        actionLabel: "撤销",
        duration: 5000,
        onAction: async () => {
          await changeLink(missingId, targetId, true);
          await setProjectHidden(missingId, false, { fromUndo: true });
        },
      });
    } catch (err) {
      showToast("关联新路径失败", { sub: err.message });
    }
  }

  async function mutateTags(projectId, payload, errorEl = null) {
    const project = state.projectById.get(projectId);
    if (!project) return false;
    if (errorEl) errorEl.hidden = true;
    try {
      const res = await api(`/api/projects/${encodeURIComponent(projectId)}/meta`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      project.tags = res.tags;
      state.data.all_tags = res.all_tags;
      if (
        state.selectedTag &&
        !(res.all_tags || []).some(
          (item) => item.tag.toLowerCase() === state.selectedTag.toLowerCase()
        )
      ) {
        state.selectedTag = null;
      }
      renderProjectsView();
      if (state.selectedProjectId === projectId) {
        renderDrawerContent(project, false);
      }
      if (state.popoverProjectId === projectId && !el.tagPopover.hidden) {
        renderTagPopover(project);
      }
      return true;
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message;
        errorEl.hidden = false;
        shakeElement(errorEl.previousElementSibling);
      } else {
        showToast("更新标签失败", { sub: err.message });
      }
      return false;
    }
  }

  async function openProjectTarget(projectId, target = "finder", btnEl = null) {
    const project = state.projectById.get(projectId);
    if (!project) return;
    const resolvedTarget = target || "finder";
    try {
      const res = await api(`/api/projects/${encodeURIComponent(projectId)}/open`, {
        method: "POST",
        body: JSON.stringify({ target: resolvedTarget }),
      });
      flashButtonDone(btnEl);
      if (res && res.opens_path === false) {
        showToast(`已打开 ${res.label || resolvedTarget}`, {
          sub: "该应用暂不支持直接传入目录路径，可按需复制路径",
          duration: 3200,
        });
      }
    } catch (err) {
      shakeElement(btnEl);
      if (err.code && STATUS_META[err.code]) {
        project.status = err.code;
        renderAll();
      }
      showToast(err.message || "无法打开该项目", {
        actionLabel: "复制路径",
        onAction: () => copyPath(project.path),
      });
    }
  }

  async function copyPath(path, btnEl = null) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(path);
      } else {
        const ta = document.createElement("textarea");
        ta.value = path;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      flashButtonDone(btnEl);
      if (!btnEl) {
        showToast("已复制完整路径", { duration: 2200 });
      }
    } catch (_) {
      shakeElement(btnEl);
      showToast("复制失败，请手动选中路径复制");
    }
  }

  async function changeLink(firstId, secondId, remove) {
    try {
      const res = await api("/api/links", {
        method: remove ? "DELETE" : "POST",
        body: JSON.stringify({ first: firstId, second: secondId }),
      });
      for (const [pid, related] of Object.entries(res.related || {})) {
        const target = state.projectById.get(pid);
        if (target) {
          if (related.length > 0) target.related_projects = related;
          else delete target.related_projects;
        }
      }
      state.linkPickerOpen = false;
      state.linkPickerQuery = "";
      const current = state.projectById.get(state.selectedProjectId);
      if (current) renderDrawerContent(current, false);
      if (remove) {
        const canUndo =
          state.projectById.has(firstId) && state.projectById.has(secondId);
        showToast(
          "已解除项目关联",
          canUndo
            ? {
                actionLabel: "撤销",
                onAction: () => changeLink(firstId, secondId, false),
              }
            : { duration: 2500 }
        );
      } else {
        showToast("已关联项目", { duration: 2200 });
      }
    } catch (err) {
      showToast(remove ? "解除关联失败" : "关联失败", { sub: err.message });
    }
  }

  async function triggerRescan() {
    if (state.scanning) return;
    state.scanning = true;
    el.btnRefresh.classList.add("is-spinning");
    el.btnRefresh.setAttribute("aria-busy", "true");
    el.syncStatus.classList.remove("is-fresh");
    el.syncStatus.classList.add("is-scanning");
    el.syncLabel.textContent = "扫描中…";
    el.topProgress.classList.remove("is-finishing");
    el.topProgress.classList.add("is-loading");

    const scrollY = window.scrollY;
    try {
      const payload = await api("/api/scan", { method: "POST" });
      el.topProgress.classList.remove("is-loading");
      el.topProgress.classList.add("is-finishing");
      applyData(payload);
      window.scrollTo({ top: scrollY, behavior: "instant" });
      if (state.selectedProjectId) {
        const updated = state.projectById.get(state.selectedProjectId);
        if (updated) renderDrawerContent(updated, false);
      } else if (state.selectedRemoteGroupKey) {
        const updatedGroup = state.remoteGroupByKey.get(state.selectedRemoteGroupKey);
        if (updatedGroup) renderRemoteGroupDrawer(updatedGroup, false);
        else closeDrawer();
      }
    } catch (err) {
      el.topProgress.classList.remove("is-loading", "is-finishing");
      updateSyncStatus();
      shakeElement(el.btnRefresh);
      showToast("重新扫描未能完成，仍保留上次索引结果", {
        sub: err.message,
        actionLabel: "重试",
        onAction: triggerRescan,
      });
    } finally {
      state.scanning = false;
      el.btnRefresh.classList.remove("is-spinning");
      el.btnRefresh.removeAttribute("aria-busy");
    }
  }

  /* ========================================================================
     Organize / Hygiene View & Safe Trash Confirmation Modal
     ======================================================================== */

  function syncDefaultSelectedArtifacts() {
    state.selectedArtifacts = new Map();
    if (!state.hygiene?.scanned) return;
    const minDays = state.organizeDormantDays;
    for (const [pid, info] of Object.entries(state.hygiene.by_project || {})) {
      const p = state.projectById.get(pid);
      if (!p || p.hidden || p.status !== "directory") continue;
      if (!info.artifacts || info.artifacts.length === 0) continue;
      if (isRecentlyActive(p)) continue;
      const days = daysSinceActivity(p.last_activity);
      if (minDays > 0 && days !== null && days < minDays) continue;
      state.selectedArtifacts.set(pid, new Set(info.artifacts.map((a) => a.path)));
    }
  }

  let hygienePollTimer = null;

  function updateHygieneProgressUI({ finished = false } = {}) {
    if (el.tabBtnOrganize) {
      const wasScanning = el.tabBtnOrganize.classList.contains("is-scanning");
      el.tabBtnOrganize.classList.toggle("is-scanning", state.hygieneScanning);
      if (wasScanning !== state.hygieneScanning) {
        requestAnimationFrame(() => positionSegmentedThumb(el.viewSegmented));
      }
    }
    // Do not interfere while full agent rescan owns the top bar
    if (state.scanning) return;
    if (state.hygieneScanning && state.view === "organize") {
      const prog = state.hygiene?.progress;
      el.topProgress.classList.remove("is-finishing");
      if (prog && prog.total > 0) {
        const ratio = Math.max(0.05, Math.min(0.98, prog.done / prog.total));
        el.topProgress.style.setProperty("--progress", String(ratio));
        el.topProgress.classList.remove("is-loading");
        el.topProgress.classList.add("is-determinate");
      } else {
        el.topProgress.classList.remove("is-determinate");
        el.topProgress.classList.add("is-loading");
      }
    } else if (finished && state.view === "organize") {
      el.topProgress.style.setProperty("--progress", "1");
      el.topProgress.classList.remove("is-loading", "is-determinate");
      el.topProgress.classList.add("is-finishing");
    } else {
      el.topProgress.classList.remove("is-loading", "is-determinate", "is-finishing");
    }
  }

  function scheduleHygienePoll() {
    clearTimeout(hygienePollTimer);
    hygienePollTimer = setTimeout(async () => {
      try {
        const res = await api("/api/hygiene");
        state.hygiene = res;
        state.hygieneScanning = Boolean(res.scanning);
        rebuildDuplicateLookups();
        if (state.hygieneScanning) {
          updateHygieneProgressUI();
          if (state.view === "organize") renderOrganizeView();
          scheduleHygienePoll();
        } else {
          updateHygieneProgressUI({ finished: true });
          syncDefaultSelectedArtifacts();
          renderAll();
        }
      } catch (_) {
        state.hygieneScanning = false;
        updateHygieneProgressUI();
        if (state.view === "organize") renderOrganizeView();
      }
    }, 800);
  }

  async function triggerHygieneScan() {
    if (state.hygieneScanning) return;
    state.hygieneScanning = true;
    updateHygieneProgressUI();
    renderOrganizeView();
    try {
      const res = await api("/api/hygiene/scan", {
        method: "POST",
        body: JSON.stringify({ background: true }),
      });
      state.hygiene = res;
      state.hygieneScanning = Boolean(res.scanning);
      rebuildDuplicateLookups();
      if (state.hygieneScanning) {
        updateHygieneProgressUI();
        renderOrganizeView();
        scheduleHygienePoll();
      } else {
        updateHygieneProgressUI({ finished: true });
        syncDefaultSelectedArtifacts();
        renderAll();
      }
    } catch (err) {
      state.hygieneScanning = false;
      updateHygieneProgressUI();
      showToast("空间体检失败", { sub: err.message });
      renderOrganizeView();
    }
  }

  function getSlimCandidates() {
    if (!state.hygiene?.by_project) return [];
    const minDays = state.organizeDormantDays;
    const rows = [];
    for (const [pid, info] of Object.entries(state.hygiene.by_project || {})) {
      const p = state.projectById.get(pid);
      if (!p || p.hidden || p.status !== "directory") continue;
      if (!info.reclaimable_bytes || !info.artifacts?.length) continue;
      const days = daysSinceActivity(p.last_activity);
      const activeNow = isRecentlyActive(p);
      if (minDays > 0 && !activeNow && days !== null && days < minDays) continue;
      rows.push({
        project: p,
        bytes: info.reclaimable_bytes,
        artifacts: info.artifacts,
        days,
        activeNow,
      });
    }
    rows.sort((a, b) => {
      if (a.activeNow !== b.activeNow) return a.activeNow ? 1 : -1;
      return b.bytes - a.bytes || compareRecent(a.project, b.project);
    });
    return rows;
  }

  function computeSelectedArtifactsStats(candidates) {
    let totalBytes = 0;
    let dirCount = 0;
    let projectCount = 0;
    const items = [];
    for (const row of candidates) {
      const sel = state.selectedArtifacts.get(row.project.id);
      if (!sel || sel.size === 0) continue;
      const matched = row.artifacts.filter((a) => sel.has(a.path));
      if (matched.length === 0) continue;
      projectCount += 1;
      dirCount += matched.length;
      for (const a of matched) totalBytes += a.bytes;
      items.push({
        project_id: row.project.id,
        project_name: projectName(row.project),
        paths: matched.map((a) => a.path),
        artifacts: matched,
      });
    }
    return { totalBytes, dirCount, projectCount, items };
  }

  function renderOrganizeSlimHtml() {
    const partialCount = Object.keys(state.hygiene?.by_project || {}).length;
    if (state.hygieneScanning && partialCount === 0) {
      const prog = state.hygiene?.progress;
      const progText = prog && prog.total > 0 ? `（${prog.done} / ${prog.total}）` : "";
      return `<div class="empty-state">
        <p class="empty-title">正在统计本机可重建依赖与构建产物${progText}…</p>
        <p class="empty-desc">仅扫描 node_modules、.venv、dist、target 等可 100% 重建目录，结果会实时更新，不会改动任何文件</p>
      </div>`;
    }
    if (!state.hygiene?.scanned && !state.hygieneScanning) {
      return `<div class="empty-state">
        <p class="empty-title">尚未运行空间体检</p>
        <p class="empty-desc">扫描各项目内的依赖与构建缓存体积，一键移入废纸篓释放磁盘空间</p>
        <div class="empty-actions">
          <button type="button" class="btn btn-primary" data-org-action="rescan-hygiene">开始空间体检</button>
        </div>
      </div>`;
    }

    const candidates = getSlimCandidates();
    const selStats = computeSelectedArtifactsStats(candidates);
    const dormantOptions = [
      { value: 0, label: "全部沉睡" },
      { value: 7, label: "> 7 天未动" },
      { value: 30, label: "> 30 天未动" },
      { value: 90, label: "> 90 天未动" },
    ];
    const toolbarRight = `
      <label class="select-wrap" aria-label="沉睡时间门槛">
        <select class="compact-select" id="org-dormant-select">
          ${dormantOptions
            .map(
              (o) =>
                `<option value="${o.value}"${
                  state.organizeDormantDays === o.value ? " selected" : ""
                }>${o.label}</option>`
            )
            .join("")}
        </select>
      </label>
      ${
        candidates.length > 0
          ? `<button type="button" class="btn btn-secondary" style="height:30px;font-size:12px" data-org-action="${
              selStats.dirCount > 0 ? "clear-all-artifacts" : "select-all-artifacts"
            }">${selStats.dirCount > 0 ? "取消全选" : "全选可瘦身"}</button>`
          : ""
      }
    `;

    if (candidates.length === 0) {
      return `
        <div class="organize-toolbar">
          <span class="organize-scan-meta">仅统计 node_modules、.venv、dist、target、.next 等可 100% 重建产物</span>
          <div class="organize-toolbar-right">${toolbarRight}</div>
        </div>
        <div class="empty-state">
          <p class="empty-title">当前条件下没有可瘦身的依赖目录</p>
          <p class="empty-desc">可以调低沉睡天数门槛（如切换为「全部沉睡」）查看所有含依赖产物的项目</p>
        </div>
      `;
    }

    const rowsHtml = candidates
      .map((row) => {
        const p = row.project;
        const pid = p.id;
        const selSet = state.selectedArtifacts.get(pid) || new Set();
        const checked = selSet.size > 0;
        const topAgent = (p.agents || [])[0];
        const dormantText = row.activeNow
          ? "活跃中（1 小时内使用过，默认保护）"
          : row.days === null
          ? "缺少活动时间"
          : row.days === 0
          ? "今天活跃"
          : `沉睡 ${row.days} 天`;
        const chipsHtml = row.artifacts
          .map((art) => {
            const isSel = selSet.has(art.path);
            return `<button type="button" class="artifact-chip${
              isSel ? " is-selected" : ""
            }" data-org-action="toggle-artifact" data-id="${escapeHtml(
              pid
            )}" data-path="${escapeHtml(art.path)}" title="点击勾选或取消 ${escapeHtml(
              art.rel_path
            )}"><span>${escapeHtml(art.rel_path)}</span><span class="artifact-chip-size">${escapeHtml(
              formatBytes(art.bytes)
            )}</span></button>`;
          })
          .join("");
        return `<div class="hygiene-row${row.activeNow ? " is-active-protected" : ""}">
          <div class="hygiene-row-left">
            <input type="checkbox" class="hygiene-checkbox" data-org-action="toggle-project-artifacts" data-id="${escapeHtml(
              pid
            )}"${checked ? " checked" : ""} aria-label="选择 ${escapeHtml(projectName(p))}">
            <div class="hygiene-row-body">
              <div class="hygiene-row-title-line">
                <button type="button" class="hygiene-row-name" data-org-action="open-drawer" data-id="${escapeHtml(
                  pid
                )}">${escapeHtml(projectName(p))}</button>
                ${
                  p.asset_kind === "sandbox"
                    ? `<span class="status-pill is-sandbox">临时沙盒</span>`
                    : ""
                }
                ${
                  row.activeNow
                    ? `<span class="status-pill is-ok">活跃中</span>`
                    : ""
                }
              </div>
              <div class="hygiene-row-path" title="${escapeHtml(p.path)}">${escapeHtml(
          shortenPath(p.path)
        )}</div>
              <div class="hygiene-artifacts-row">${chipsHtml}</div>
              <div class="hygiene-meta-line">
                <span>${escapeHtml(dormantText)}</span>
                ${
                  topAgent
                    ? `<span>·</span><span style="display:inline-flex;align-items:center;gap:4px">${renderAgentIconHtml(
                        topAgent,
                        "xxs"
                      )}<span>${escapeHtml(agentDisplayName(topAgent))}</span></span>`
                    : ""
                }
              </div>
            </div>
          </div>
          <div class="hygiene-row-right">
            <span class="hygiene-size-total">${escapeHtml(formatBytes(row.bytes))}</span>
            <button type="button" class="btn btn-secondary" style="height:30px;font-size:12px" data-org-action="slim-single" data-id="${escapeHtml(
              pid
            )}">瘦身</button>
          </div>
        </div>`;
      })
      .join("");

    const batchBarHtml =
      selStats.dirCount > 0
        ? `<div class="organize-batch-bar" role="region" aria-label="批量瘦身操作栏">
            <div class="organize-batch-summary">
              <span>已选 ${selStats.projectCount} 个项目（${selStats.dirCount} 个依赖目录）· 预计释放 ${escapeHtml(
                formatBytes(selStats.totalBytes)
              )}</span>
              <span class="organize-batch-sub">仅清理可重建依赖产物，源码、.git 与 .env 均保留不动</span>
            </div>
            <div class="organize-batch-actions">
              <button type="button" class="btn btn-secondary" style="height:32px" data-org-action="clear-all-artifacts">取消</button>
              <button type="button" class="btn btn-primary" style="height:32px" data-org-action="trash-selected-artifacts">移入废纸篓</button>
            </div>
          </div>`
        : "";

    return `
      <div class="organize-toolbar">
        <span class="organize-scan-meta">共 ${candidates.length} 个项目含可重建产物，默认保护 1 小时内活跃项目</span>
        <div class="organize-toolbar-right">${toolbarRight}</div>
      </div>
      <div class="hygiene-list">${rowsHtml}</div>
      ${batchBarHtml}
    `;
  }

  function renderOrganizeDuplicatesHtml() {
    const groups = state.hygiene?.duplicate_groups || state.data?.duplicate_groups || [];
    if (groups.length === 0) {
      return `<div class="empty-state">
        <p class="empty-title">本机没有重复克隆的 Git 仓库</p>
        <p class="empty-desc">同一 Git 远端地址在本机存在 2 份及以上目录（含 Worktree）时，会自动归组展示在这里</p>
      </div>`;
    }
    const cardsHtml = groups
      .map((grp) => {
        const copies = (grp.project_ids || [])
          .map((pid) => state.projectById.get(pid))
          .filter((p) => p && !p.hidden && p.status === "directory");
        if (copies.length < 2) return "";
        const rowsHtml = copies
          .map((p, idx) => {
            const g = gitInfo(p);
            const branch = g?.branch ? (g.detached ? `HEAD@${g.branch}` : g.branch) : "无分支";
            const isWt = g?.kind === "worktree" || p.asset_reason === "active_worktree";
            const reclaim = projectReclaimableBytes(p.id);
            const topAgent = (p.agents || [])[0];
            return `<div class="dup-copy-row">
              <div class="dup-copy-info">
                <div class="dup-copy-top">
                  ${idx === 0 ? `<span class="status-pill is-ok">最近活跃</span>` : ""}
                  <span class="status-pill ${isWt ? "is-sandbox" : "is-git"}">${
              isWt ? "Worktree" : "主仓库"
            }</span>
                  <span class="git-branch-chip">${ICONS.gitBranch}<span>${escapeHtml(branch)}</span></span>
                  ${
                    reclaim > 0
                      ? `<span class="reclaim-pill" data-org-action="slim-single" data-id="${escapeHtml(
                          p.id
                        )}">依赖 ${escapeHtml(formatBytes(reclaim))}</span>`
                      : ""
                  }
                </div>
                <div class="hygiene-row-path" title="${escapeHtml(p.path)}">${escapeHtml(
              shortenPath(p.path)
            )}</div>
                <div class="hygiene-meta-line">
                  <span>最近活动：${escapeHtml(formatRelativeTime(p.last_activity))}</span>
                  ${
                    topAgent
                      ? `<span>·</span><span style="display:inline-flex;align-items:center;gap:4px">${renderAgentIconHtml(
                          topAgent,
                          "xxs"
                        )}<span>${escapeHtml(agentDisplayName(topAgent))}</span></span>`
                      : ""
                  }
                </div>
              </div>
              <div class="dup-copy-actions">
                <button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-org-action="open-drawer" data-id="${escapeHtml(
                  p.id
                )}">详情</button>
                <button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-org-action="open-finder" data-id="${escapeHtml(
                  p.id
                )}">访达</button>
                ${
                  reclaim > 0
                    ? `<button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-org-action="slim-single" data-id="${escapeHtml(
                        p.id
                      )}">清依赖</button>`
                    : ""
                }
                <button type="button" class="btn btn-subtle" style="height:28px;font-size:12px" data-org-action="trash-project" data-id="${escapeHtml(
                  p.id
                )}">移入废纸篓</button>
              </div>
            </div>`;
          })
          .join("");
        const groupReclaim = copies.reduce((sum, p) => sum + projectReclaimableBytes(p.id), 0);
        return `<div class="dup-group-card" data-dup-group="${escapeHtml(grp.remote_key)}">
          <div class="dup-group-header">
            <div class="dup-group-title-wrap">
              <span class="dup-group-name">${escapeHtml(grp.name)}</span>
              <span class="dup-group-remote">${escapeHtml(
                formatGitRemoteShort(grp.remote_url) || grp.remote_key
              )}</span>
            </div>
            <span class="dup-group-meta">共 ${copies.length} 份本地目录${
          groupReclaim > 0 ? ` · 含可清依赖 ${escapeHtml(formatBytes(groupReclaim))}` : ""
        }</span>
          </div>
          ${rowsHtml}
        </div>`;
      })
      .filter(Boolean)
      .join("");

    return `<div class="dup-groups-stack">${cardsHtml}</div>`;
  }

  function renderOrganizeSandboxesHtml() {
    const sandboxes = (state.data?.projects || [])
      .filter((p) => !p.hidden && p.status === "directory" && assetKind(p) === "sandbox")
      .sort((a, b) => {
        const diff = projectReclaimableBytes(b.id) - projectReclaimableBytes(a.id);
        if (diff !== 0) return diff;
        return compareRecent(b, a);
      });
    if (sandboxes.length === 0) {
      return `<div class="empty-state">
        <p class="empty-title">当前没有临时沙箱或衍生 Worktree</p>
        <p class="empty-desc">Agent 自动创建的会话沙箱和 Git Worktree 会归类在这里便于集中整理</p>
      </div>`;
    }
    const rowsHtml = sandboxes
      .map((p) => {
        const g = gitInfo(p);
        const days = daysSinceActivity(p.last_activity);
        const reclaim = projectReclaimableBytes(p.id);
        const topAgent = (p.agents || [])[0];
        const isWt = p.asset_reason === "active_worktree" || g?.kind === "worktree";
        const dormantLabel =
          days === null ? "无时间记录" : days === 0 ? "今天活跃" : `沉睡 ${days} 天`;
        return `<div class="hygiene-row">
          <div class="hygiene-row-body">
            <div class="hygiene-row-title-line">
              <button type="button" class="hygiene-row-name" data-org-action="open-drawer" data-id="${escapeHtml(
                p.id
              )}">${escapeHtml(projectName(p))}</button>
              <span class="status-pill is-sandbox">${isWt ? "Worktree" : "临时沙箱"}</span>
              ${
                g?.branch
                  ? `<span class="git-branch-chip">${ICONS.gitBranch}<span>${escapeHtml(
                      g.branch
                    )}</span></span>`
                  : ""
              }
              ${
                reclaim > 0
                  ? `<span class="reclaim-pill" data-org-action="slim-single" data-id="${escapeHtml(
                      p.id
                    )}">依赖 ${escapeHtml(formatBytes(reclaim))}</span>`
                  : ""
              }
            </div>
            <div class="hygiene-row-path" title="${escapeHtml(p.path)}">${escapeHtml(
          shortenPath(p.path)
        )}</div>
            <div class="hygiene-meta-line">
              <span>${escapeHtml(dormantLabel)}</span>
              ${
                topAgent
                  ? `<span>·</span><span style="display:inline-flex;align-items:center;gap:4px">${renderAgentIconHtml(
                      topAgent,
                      "xxs"
                    )}<span>${escapeHtml(agentDisplayName(topAgent))}</span></span>`
                  : ""
              }
            </div>
          </div>
          <div class="dup-copy-actions">
            <button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-org-action="open-finder" data-id="${escapeHtml(
              p.id
            )}">访达</button>
            <button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-org-action="promote-sandbox" data-id="${escapeHtml(
              p.id
            )}">转为正式项目</button>
            ${
              reclaim > 0
                ? `<button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-org-action="slim-single" data-id="${escapeHtml(
                    p.id
                  )}">清依赖</button>`
                : ""
            }
            <button type="button" class="btn btn-subtle" style="height:28px;font-size:12px" data-org-action="trash-project" data-id="${escapeHtml(
              p.id
            )}">移入废纸篓</button>
          </div>
        </div>`;
      })
      .join("");
    return `<div class="hygiene-list">${rowsHtml}</div>`;
  }

  function renderOrganizeView() {
    if (!el.organizeRoot || !state.loaded) return;
    const h = state.hygiene;
    const summary = h?.summary || {};
    const scanned = Boolean(h?.scanned);
    const dupGroups = h?.duplicate_groups || state.data?.duplicate_groups || [];
    const sandboxCount = (state.data?.projects || []).filter(
      (p) => !p.hidden && p.status === "directory" && assetKind(p) === "sandbox"
    ).length;

    const prog = h?.progress;
    const kpiReclaimVal = state.hygieneScanning
      ? summary.total_reclaimable_bytes > 0
        ? formatBytes(summary.total_reclaimable_bytes)
        : "扫描中…"
      : scanned
      ? formatBytes(summary.total_reclaimable_bytes || 0)
      : "点击体检";
    const kpiReclaimSub = state.hygieneScanning
      ? prog && prog.total > 0
        ? `实时体检中 ${prog.done} / ${prog.total} 个目录…`
        : "正在并发统计依赖占用空间…"
      : scanned
      ? `${summary.reclaimable_project_count || 0} 个目录含可重建依赖（不动源码）`
      : "统计 node_modules、.venv、dist、target 等";

    const kpiDupVal = `${dupGroups.length} 组`;
    const kpiDupSub =
      dupGroups.length > 0
        ? `共 ${dupGroups.reduce((s, g) => s + (g.count || 0), 0)} 个同源本地目录 / Worktree`
        : "未发现同仓库多份克隆";

    const kpiSandboxVal = `${sandboxCount} 个`;
    const kpiSandboxSub =
      scanned && summary.dormant_sandbox_count > 0
        ? `其中 ${summary.dormant_sandbox_count} 个已沉睡超 14 天`
        : "Codex / WorkBuddy / Cursor 衍生目录";

    const scanMeta = state.hygieneScanning
      ? "正在扫描依赖体积…"
      : scanned && h.scanned_at
      ? `上次体检：${formatRelativeTime(h.scanned_at)}${
          typeof h.duration_ms === "number" ? `（${(h.duration_ms / 1000).toFixed(1)}s）` : ""
        }`
      : "尚未扫描磁盘依赖体积";

    const kpiPct =
      state.hygieneScanning && prog && prog.total > 0
        ? Math.max(4, Math.min(100, Math.round((prog.done / prog.total) * 100)))
        : 0;
    const kpiProgressHtml = state.hygieneScanning
      ? `<div class="kpi-progress-track" aria-hidden="true"><div class="kpi-progress-fill" style="width:${
          kpiPct || 15
        }%"></div></div>`
      : "";

    let bodyHtml = "";
    let subbarRightHtml = "";
    if (state.organizeTab === "duplicates") {
      bodyHtml = renderOrganizeDuplicatesHtml();
    } else if (state.organizeTab === "sandboxes") {
      bodyHtml = renderOrganizeSandboxesHtml();
    } else {
      bodyHtml = renderOrganizeSlimHtml();
    }

    el.organizeRoot.innerHTML = `
      <div class="organize-wrap">
        <div class="organize-header">
          <div>
            <h1 class="section-title">空间瘦身与副本整理</h1>
            <p class="section-subtitle">所有清理动作均移入 macOS 废纸篓（可在访达还原），删除整个目录前会自动做一次 Git 安全兜底检查</p>
          </div>
          <div class="organize-header-actions">
            <span class="organize-scan-meta">${escapeHtml(scanMeta)}</span>
            <button type="button" class="btn btn-primary" data-org-action="rescan-hygiene"${
              state.hygieneScanning ? " disabled" : ""
            }>${
              state.hygieneScanning
                ? `<span class="btn-spinner" aria-hidden="true"></span><span>体检中${
                    prog && prog.total > 0 ? ` ${prog.done}/${prog.total}` : "…"
                  }</span>`
                : scanned
                ? "重新体检"
                : "开始空间体检"
            }</button>
          </div>
        </div>

        <div class="organize-kpi-grid">
          <button type="button" class="organize-kpi-card${
            state.organizeTab === "slim" ? " is-active" : ""
          }" data-org-tab="slim">
            <span class="organize-kpi-label">可瘦身依赖空间</span>
            <span class="organize-kpi-value">${escapeHtml(kpiReclaimVal)}</span>
            <span class="organize-kpi-sub">${escapeHtml(kpiReclaimSub)}</span>
            ${kpiProgressHtml}
          </button>
          <button type="button" class="organize-kpi-card${
            state.organizeTab === "duplicates" ? " is-active" : ""
          }" data-org-tab="duplicates">
            <span class="organize-kpi-label">同仓库多副本</span>
            <span class="organize-kpi-value">${escapeHtml(kpiDupVal)}</span>
            <span class="organize-kpi-sub">${escapeHtml(kpiDupSub)}</span>
          </button>
          <button type="button" class="organize-kpi-card${
            state.organizeTab === "sandboxes" ? " is-active" : ""
          }" data-org-tab="sandboxes">
            <span class="organize-kpi-label">临时沙箱</span>
            <span class="organize-kpi-value">${escapeHtml(kpiSandboxVal)}</span>
            <span class="organize-kpi-sub">${escapeHtml(kpiSandboxSub)}</span>
          </button>
        </div>

        <div class="organize-subbar">
          <div class="pill-group" role="tablist" aria-label="整理子视图">
            <button type="button" class="filter-pill${
              state.organizeTab === "slim" ? " is-active" : ""
            }" data-org-tab="slim"><span>空间瘦身</span></button>
            <button type="button" class="filter-pill${
              state.organizeTab === "duplicates" ? " is-active" : ""
            }" data-org-tab="duplicates"><span>同仓库多副本</span><span class="pill-count">${
              dupGroups.length
            }</span></button>
            <button type="button" class="filter-pill${
              state.organizeTab === "sandboxes" ? " is-active" : ""
            }" data-org-tab="sandboxes"><span>临时沙箱</span><span class="pill-count">${
              sandboxCount
            }</span></button>
          </div>
          ${subbarRightHtml}
        </div>

        ${bodyHtml}
      </div>
    `;
  }

  function showTrashModal() {
    state.trashModal.open = true;
    el.trashScrim.classList.add("is-open");
    el.trashModal.classList.add("is-open");
    el.trashModal.setAttribute("aria-hidden", "false");
    el.trashModal.removeAttribute("inert");
    renderTrashModal();
  }

  function closeTrashModal() {
    state.trashModal.open = false;
    state.trashModal.submitting = false;
    el.trashScrim.classList.remove("is-open");
    el.trashModal.classList.remove("is-open");
    el.trashModal.setAttribute("aria-hidden", "true");
    el.trashModal.setAttribute("inert", "");
  }

  function openArtifactsTrashModal(items) {
    if (!items || items.length === 0) return;
    state.trashModal = {
      open: true,
      mode: "artifacts",
      loading: false,
      items,
      projectId: null,
      gitCheck: null,
      submitting: false,
      confirmedCaution: true,
      error: null,
    };
    showTrashModal();
  }

  async function openProjectTrashModal(projectId) {
    const project = state.projectById.get(projectId);
    if (!project) return;
    state.trashModal = {
      open: true,
      mode: "project",
      loading: true,
      items: [],
      projectId,
      gitCheck: null,
      submitting: false,
      confirmedCaution: false,
      error: null,
    };
    showTrashModal();
    try {
      const check = await api("/api/hygiene/git-check", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId }),
      });
      if (!state.trashModal.open || state.trashModal.projectId !== projectId) return;
      state.trashModal.loading = false;
      state.trashModal.gitCheck = check;
      state.trashModal.confirmedCaution = Boolean(check.safe_to_trash);
      renderTrashModal();
    } catch (err) {
      if (!state.trashModal.open || state.trashModal.projectId !== projectId) return;
      state.trashModal.loading = false;
      state.trashModal.error = err.message || "安全检查失败";
      renderTrashModal();
    }
  }

  function renderTrashModal() {
    const m = state.trashModal;
    if (!m.open) return;

    if (m.mode === "artifacts") {
      const flat = [];
      let totalBytes = 0;
      for (const item of m.items) {
        for (const art of item.artifacts || []) {
          flat.push({
            projectName: item.project_name,
            path: art.path,
            relPath: art.rel_path,
            bytes: art.bytes,
          });
          totalBytes += art.bytes || 0;
        }
      }
      el.trashTitle.textContent = "确认清理依赖产物";
      el.trashSubtitle.textContent = `共 ${flat.length} 个可重建目录 · 预计释放 ${formatBytes(totalBytes)}`;
      el.trashBody.innerHTML = `
        <div class="trash-safety-box is-safe">
          <div class="trash-safety-title">仅清理可重建依赖与构建产物</div>
          <div>项目源码、<code>.git</code> 历史与 <code>.env</code> 配置文件均保留不动；产物将移入 macOS 废纸篓，随时可在访达还原。</div>
        </div>
        <div class="trash-target-list">
          ${flat
            .map(
              (f) => `<div class="trash-target-item">
                <span class="trash-target-path" title="${escapeHtml(f.path)}">${escapeHtml(
                shortenPath(f.path)
              )}</span>
                <span class="trash-target-size">${escapeHtml(formatBytes(f.bytes))}</span>
              </div>`
            )
            .join("")}
        </div>
      `;
      el.trashFooter.innerHTML = `
        <button type="button" class="btn btn-secondary" data-trash-action="cancel"${
          m.submitting ? " disabled" : ""
        }>取消</button>
        <button type="button" class="btn btn-primary" data-trash-action="confirm"${
          m.submitting ? " disabled" : ""
        }>${m.submitting ? "正在移入废纸篓…" : `移入废纸篓（释放 ${escapeHtml(formatBytes(totalBytes))}）`}</button>
      `;
      return;
    }

    const project = state.projectById.get(m.projectId);
    const pName = project ? projectName(project) : m.projectId;
    el.trashTitle.textContent = `移入废纸篓：${pName}`;
    el.trashSubtitle.textContent = project ? shortenPath(project.path) : "";

    if (m.loading) {
      el.trashBody.innerHTML = `<div class="empty-state" style="padding:28px 12px">
        <p class="empty-title">正在进行删前 Git 安全兜底检查…</p>
        <p class="empty-desc">检查未提交改动、未推送提交与本地 .env 配置</p>
      </div>`;
      el.trashFooter.innerHTML = `<button type="button" class="btn btn-secondary" data-trash-action="cancel">取消</button>`;
      return;
    }

    if (m.error) {
      el.trashBody.innerHTML = `<div class="trash-safety-box is-local">
        <div class="trash-safety-title">无法完成安全检查</div>
        <div>${escapeHtml(m.error)}</div>
      </div>`;
      el.trashFooter.innerHTML = `<button type="button" class="btn btn-secondary" data-trash-action="cancel">关闭</button>`;
      return;
    }

    const chk = m.gitCheck;
    const isSafe = Boolean(chk?.safe_to_trash);
    const boxClass = isSafe ? "is-safe" : chk?.level === "local_only" ? "is-local" : "is-caution";
    const titleText = isSafe
      ? "已同步远端，可放心移入废纸篓"
      : chk?.level === "local_only"
      ? "注意：该目录无 Git 版本保护"
      : "注意：检测到本地未保存资产";
    const warningsHtml =
      chk?.warnings?.length > 0
        ? `<ul class="trash-warning-list">${chk.warnings
            .map((w) => `<li>${escapeHtml(w)}</li>`)
            .join("")}</ul>`
        : "<div>工作区干净且已推送至远端，无未应用 stash 或额外 .env 文件。</div>";

    const cautionCheckHtml = isSafe
      ? ""
      : `<label class="trash-confirm-check">
          <input type="checkbox" id="trash-caution-checkbox"${m.confirmedCaution ? " checked" : ""}>
          <span>我已了解上述风险，仍要将整个目录移入废纸篓</span>
        </label>`;

    el.trashBody.innerHTML = `
      <div class="trash-safety-box ${boxClass}">
        <div class="trash-safety-title">${escapeHtml(titleText)}</div>
        ${warningsHtml}
      </div>
      <div class="drawer-path-box" style="margin:0">
        <span class="drawer-path-text">${escapeHtml(project?.path || "")}</span>
      </div>
      ${cautionCheckHtml}
    `;

    const fallbackSlimBtn =
      chk?.reclaimable_bytes > 0
        ? `<button type="button" class="btn btn-secondary" data-trash-action="switch-to-slim"${
            m.submitting ? " disabled" : ""
          }>改走仅清依赖（${escapeHtml(formatBytes(chk.reclaimable_bytes))}）</button>`
        : "";
    const confirmDisabled = m.submitting || (!isSafe && !m.confirmedCaution);
    el.trashFooter.innerHTML = `
      ${fallbackSlimBtn}
      <button type="button" class="btn btn-secondary" data-trash-action="cancel"${
        m.submitting ? " disabled" : ""
      }>取消</button>
      <button type="button" class="btn btn-danger" data-trash-action="confirm"${
        confirmDisabled ? " disabled" : ""
      }>${m.submitting ? "正在移入废纸篓…" : "移入废纸篓"}</button>
    `;
  }

  async function confirmTrashModal() {
    const m = state.trashModal;
    if (!m.open || m.submitting) return;
    m.submitting = true;
    renderTrashModal();
    try {
      if (m.mode === "artifacts") {
        const res = await api("/api/hygiene/trash", {
          method: "POST",
          body: JSON.stringify({
            mode: "artifacts",
            items: m.items.map((item) => ({
              project_id: item.project_id,
              paths: item.paths,
            })),
          }),
        });
        if (res.hygiene) {
          state.hygiene = res.hygiene;
          rebuildDuplicateLookups();
          syncDefaultSelectedArtifacts();
        }
        closeTrashModal();
        renderAll();
        if (state.selectedProjectId) renderDetailDrawer(state.selectedProjectId, { animateSwap: false });
        showToast(`已释放 ${formatBytes(res.freed_bytes || 0)}`, {
          sub: "已移入 macOS 废纸篓，可在访达中还原",
          duration: 3800,
        });
      } else if (m.mode === "project") {
        const pid = m.projectId;
        const res = await api("/api/hygiene/trash", {
          method: "POST",
          body: JSON.stringify({ mode: "project", project_id: pid }),
        });
        const proj = state.projectById.get(pid);
        if (proj) proj.status = res.status || "missing";
        if (res.hygiene) {
          state.hygiene = res.hygiene;
          rebuildDuplicateLookups();
          syncDefaultSelectedArtifacts();
        }
        closeTrashModal();
        if (state.selectedProjectId === pid) closeDrawer();
        renderAll();
        showToast("已将目录移入废纸篓", {
          sub: "可在访达废纸篓中还原；下次扫描会自动更新索引",
          duration: 4000,
        });
      }
    } catch (err) {
      m.submitting = false;
      renderTrashModal();
      showToast("移入废纸篓失败", { sub: err.message });
    }
  }

  function renderAll() {
    renderProjectsView();
    if (state.view === "agents") {
      renderAgentsView();
    } else if (state.view === "organize") {
      renderOrganizeView();
    }
    if (state.diagOpen) {
      renderDiagnosticsModal();
    }
  }

  function resetFilters() {
    state.search = "";
    state.gitFilter = "";
    state.timeRange = "";
    state.selectedAgent = null;
    state.selectedTag = null;
    state.selectedDuplicateKey = null;
    el.searchInput.value = "";
    el.searchClear.hidden = true;
    el.searchKbd.hidden = false;
    if (el.gitFilter) el.gitFilter.value = "";
    el.timeFilter.value = "";
    renderProjectsView();
  }

  /* Event Bindings */
  let searchTimer = null;
  el.searchInput.addEventListener("input", () => {
    const val = el.searchInput.value;
    el.searchClear.hidden = !val;
    el.searchKbd.hidden = Boolean(val);
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.search = val;
      renderProjectsView();
    }, 45);
  });

  el.searchClear.addEventListener("click", () => {
    state.search = "";
    el.searchInput.value = "";
    el.searchClear.hidden = true;
    el.searchKbd.hidden = false;
    renderProjectsView();
    el.searchInput.focus();
  });

  el.viewSegmented.addEventListener("click", (e) => {
    const btn = e.target.closest(".segmented-btn");
    if (btn) switchView(btn.dataset.view);
  });

  el.scopeFilters.addEventListener("click", (e) => {
    const btn = e.target.closest(".filter-pill");
    if (!btn) return;
    state.scopeFilter = btn.dataset.scope;
    renderProjectsView();
  });

  el.btnHiddenView.addEventListener("click", () => {
    state.scopeFilter = state.scopeFilter === "hidden" ? "local" : "hidden";
    renderProjectsView();
  });

  if (el.btnScopeReset) {
    el.btnScopeReset.addEventListener("click", resetFilters);
  }

  if (el.gitFilter) {
    el.gitFilter.addEventListener("change", () => {
      state.gitFilter = el.gitFilter.value;
      renderProjectsView();
    });
  }

  el.timeFilter.addEventListener("change", () => {
    state.timeRange = el.timeFilter.value;
    renderProjectsView();
  });

  el.sortSelect.addEventListener("change", () => {
    state.sortBy = el.sortSelect.value;
    if (state.sortBy === "reclaimable" && !state.hygiene?.scanned && !state.hygieneScanning) {
      triggerHygieneScan();
    }
    renderProjectsView();
  });

  if (el.viewModeToggle) {
    el.viewModeToggle.addEventListener("click", (e) => {
      const btn = e.target.closest(".view-mode-btn[data-layout]");
      if (!btn) return;
      const next = btn.dataset.layout;
      if (next !== "card" && next !== "list") return;
      if (state.layoutMode === next) return;
      state.layoutMode = next;
      saveLayoutMode(next);
      renderProjectsView();
    });
  }

  el.chipsBar.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;
    if (action === "clear-agent") {
      state.selectedAgent = null;
      renderProjectsView();
    } else if (action === "clear-duplicate") {
      state.selectedDuplicateKey = null;
      renderProjectsView();
    } else if (action === "toggle-tag") {
      const tag = btn.dataset.tag;
      state.selectedTag =
        state.selectedTag && state.selectedTag.toLowerCase() === tag.toLowerCase() ? null : tag;
      renderProjectsView();
    } else if (action === "reset-filters") {
      resetFilters();
    }
  });

  el.projectsContainer.addEventListener("click", (e) => {
    const actionBtn = e.target.closest("[data-action]");
    if (actionBtn) {
      e.stopPropagation();
      const action = actionBtn.dataset.action;
      const pid = actionBtn.dataset.id;
      if (action === "star") toggleStar(pid, actionBtn);
      else if (action === "open") openProjectTarget(pid, actionBtn.dataset.target || "finder", actionBtn);
      else if (action === "copy") {
        const p = state.projectById.get(pid);
        if (p) copyPath(p.path, actionBtn);
      } else if (action === "copy-text") {
        copyPath(actionBtn.dataset.text || "", actionBtn);
      } else if (action === "popover-tag") openTagPopover(pid, actionBtn);
      else if (action === "hide") setProjectHidden(pid, true);
      else if (action === "unhide") setProjectHidden(pid, false);
      else if (action === "dismiss-missing") {
        setProjectHidden(pid, true, { reason: "dismiss" });
      } else if (action === "resolve-link") {
        closeTagPopover();
        openDrawer(pid, actionBtn, { openLinkPicker: true });
      } else if (action === "promote") {
        setProjectPromoted(pid, true);
      } else if (action === "filter-tag") {
        const tag = actionBtn.dataset.tag;
        state.selectedTag =
          state.selectedTag && state.selectedTag.toLowerCase() === tag.toLowerCase() ? null : tag;
        renderProjectsView();
      } else if (action === "switch-scope") {
        const targetScope = actionBtn.dataset.scope || "local";
        if (targetScope === "sandbox") {
          state.scopeFilter = "local";
          state.sandboxExpanded = true;
          renderProjectsView();
          requestAnimationFrame(() => {
            document
              .getElementById("sandbox-disclosure")
              ?.scrollIntoView({ behavior: "smooth", block: "start" });
          });
        } else {
          state.scopeFilter = targetScope;
          renderProjectsView();
        }
      } else if (action === "toggle-sandbox") {
        state.sandboxExpanded = !state.sandboxExpanded;
        renderProjectsView();
      } else if (action === "toggle-agent-stack") {
        const key = actionBtn.dataset.stackKey;
        if (key) {
          if (state.expandedAgentStacks.has(key)) {
            state.expandedAgentStacks.delete(key);
          } else {
            state.expandedAgentStacks.add(key);
          }
          renderProjectsView();
        }
      } else if (action === "filter-agent-inline") {
        const agentId = actionBtn.dataset.agent;
        if (agentId) {
          state.selectedAgent = state.selectedAgent === agentId ? null : agentId;
          renderProjectsView();
        }
      } else if (action === "filter-duplicate") {
        const key = actionBtn.dataset.remoteKey;
        if (key) {
          state.selectedDuplicateKey = state.selectedDuplicateKey === key ? null : key;
          state.scopeFilter = "local";
          renderProjectsView();
        }
      } else if (action === "toggle-dormant-group") {
        state.dormantGroupCollapsed = !state.dormantGroupCollapsed;
        renderProjectsView();
      } else if (action === "open-organize-slim") {
        state.organizeTab = "slim";
        switchView("organize");
      } else if (action === "quick-slim-project") {
        const p = state.projectById.get(pid);
        const arts = projectArtifacts(pid);
        if (p && arts.length > 0) {
          openArtifactsTrashModal([
            {
              project_id: pid,
              project_name: projectName(p),
              paths: arts.map((a) => a.path),
              artifacts: arts,
            },
          ]);
        }
      } else if (action === "reset-filters") {
        resetFilters();
      }
      return;
    }
    const row = e.target.closest(".project-row");
    if (row) {
      closeTagPopover();
      if (row.dataset.remoteGroup) {
        openRemoteGroupDrawer(row.dataset.remoteGroup, row);
      } else if (row.dataset.projectId) {
        openDrawer(row.dataset.projectId, row);
      }
    }
  });

  el.projectsContainer.addEventListener("keydown", (e) => {
    const row = e.target.closest(".project-row");
    if (!row || e.target !== row) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (row.dataset.remoteGroup) {
        openRemoteGroupDrawer(row.dataset.remoteGroup, row);
      } else if (row.dataset.projectId) {
        openDrawer(row.dataset.projectId, row);
      }
    }
  });

  function selectAgentAndJump(agentId) {
    state.selectedAgent = agentId;
    const stats = computeAgentProjectStats().get(agentId);
    if (stats) {
      if (stats.local > 0) {
        state.scopeFilter = "local";
        state.sandboxExpanded = false;
      } else if (stats.remote > 0) {
        state.scopeFilter = "remote";
      } else if (stats.sandbox > 0) {
        state.scopeFilter = "local";
        state.sandboxExpanded = true;
      } else if (stats.attention > 0) {
        state.scopeFilter = "attention";
      } else {
        state.scopeFilter = "local";
      }
    }
    switchView("projects");
  }

  el.viewAgents.addEventListener("click", (e) => {
    const diagBtn = e.target.closest('[data-action="agent-diag"]');
    if (diagBtn) {
      e.stopPropagation();
      openDiagnosticsModal(diagBtn.dataset.agent);
      return;
    }
    const card = e.target.closest('[data-action="filter-agent"]');
    if (card) {
      selectAgentAndJump(card.dataset.agent);
    }
  });

  el.viewAgents.addEventListener("keydown", (e) => {
    const card = e.target.closest('[data-action="filter-agent"]');
    if (card && e.target === card && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      selectAgentAndJump(card.dataset.agent);
    }
  });

  el.btnInactiveAgents.addEventListener("click", () => {
    state.inactiveAgentsOpen = !state.inactiveAgentsOpen;
    el.btnInactiveAgents.setAttribute("aria-expanded", String(state.inactiveAgentsOpen));
    el.inactiveAgentsPanel.classList.toggle("is-open", state.inactiveAgentsOpen);
  });

  el.drawerContent.addEventListener("click", (e) => {
    const toggleBtn = e.target.closest("[data-toggle-panel]");
    if (toggleBtn) {
      const panel = document.getElementById(toggleBtn.dataset.togglePanel);
      if (panel) {
        const open = !panel.classList.contains("is-open");
        panel.classList.toggle("is-open", open);
        toggleBtn.setAttribute("aria-expanded", String(open));
      }
      return;
    }
    const btn = e.target.closest("[data-drawer-action]");
    if (!btn) return;
    const action = btn.dataset.drawerAction;
    if (action === "close") {
      closeDrawer();
      return;
    }
    if (action === "copy-text") {
      copyPath(btn.dataset.text || "", btn);
      return;
    }
    if (action === "star-target") {
      toggleStar(btn.dataset.id, btn);
      return;
    }
    if (action === "jump-project") {
      openDrawer(btn.dataset.id);
      return;
    }
    if (!state.selectedProjectId) return;
    const pid = state.selectedProjectId;
    const project = state.projectById.get(pid);
    if (!project) return;
    if (action === "star") toggleStar(pid, btn);
    else if (action === "open") openProjectTarget(pid, btn.dataset.target || "finder", btn);
    else if (action === "copy") copyPath(project.path, btn);
    else if (action === "hide") setProjectHidden(pid, true);
    else if (action === "unhide") setProjectHidden(pid, false);
    else if (action === "dismiss-missing") {
      setProjectHidden(pid, true, { reason: "dismiss" });
    } else if (action === "promote") {
      setProjectPromoted(pid, true);
    } else if (action === "demote") {
      setProjectPromoted(pid, false);
    } else if (action === "compare-duplicates") {
      const key = btn.dataset.remoteKey;
      state.organizeTab = "duplicates";
      closeDrawer();
      switchView("organize");
      if (key) {
        requestAnimationFrame(() => {
          el.organizeRoot
            ?.querySelector(`[data-dup-group="${CSS.escape(key)}"]`)
            ?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      }
    } else if (action === "slim-project") {
      const arts = projectArtifacts(pid);
      if (arts.length > 0) {
        openArtifactsTrashModal([
          {
            project_id: pid,
            project_name: projectName(project),
            paths: arts.map((a) => a.path),
            artifacts: arts,
          },
        ]);
      }
    } else if (action === "trash-project") {
      openProjectTrashModal(pid);
    }
    else if (action === "remove-tag") {
      const chip = btn.closest("[data-tag-chip]");
      if (chip) chip.classList.add("is-leaving");
      setTimeout(() => mutateTags(pid, { remove_tags: [btn.dataset.tag] }), 120);
    } else if (action === "add-suggest-tag") {
      mutateTags(pid, { add_tags: [btn.dataset.tag] });
    } else if (action === "unlink") {
      changeLink(pid, btn.dataset.id, true);
    } else if (action === "open-link-picker") {
      state.linkPickerOpen = true;
      renderDrawerContent(project, false);
      document.getElementById("link-picker-input")?.focus();
    } else if (action === "close-link-picker") {
      state.linkPickerOpen = false;
      state.linkPickerQuery = "";
      renderDrawerContent(project, false);
    } else if (action === "add-link") {
      if (isAttentionProject(project)) {
        resolveMissingByLink(pid, btn.dataset.id);
      } else {
        changeLink(pid, btn.dataset.id, false);
      }
    }
  });

  el.drawerContent.addEventListener("input", (e) => {
    if (e.target.id === "link-picker-input" && state.selectedProjectId) {
      state.linkPickerQuery = e.target.value;
      const project = state.projectById.get(state.selectedProjectId);
      const results = document.getElementById("link-picker-results");
      if (project && results) {
        const candidates = getLinkCandidates(project);
        results.innerHTML = candidates.length
          ? candidates
              .map(
                (c) => `<button type="button" class="link-candidate-btn" data-drawer-action="add-link" data-id="${escapeHtml(
                  c.id
                )}">
                  <span class="related-name">${escapeHtml(projectName(c))}</span>
                  <span class="related-path">${escapeHtml(shortenPath(c.path))}</span>
                </button>`
              )
              .join("")
          : `<div class="inactive-agent-reason">没有找到可关联的其他项目</div>`;
      }
    }
  });

  el.drawerContent.addEventListener("submit", async (e) => {
    if (e.target.id !== "drawer-tag-form" || !state.selectedProjectId) return;
    e.preventDefault();
    const input = document.getElementById("drawer-tag-input");
    const errBox = document.getElementById("drawer-tag-error");
    const value = (input?.value || "").trim();
    if (!value) {
      if (errBox) {
        errBox.textContent = "请输入标签名称";
        errBox.hidden = false;
      }
      shakeElement(e.target);
      return;
    }
    const ok = await mutateTags(state.selectedProjectId, { add_tags: [value] }, errBox);
    if (ok) {
      document.getElementById("drawer-tag-input")?.focus();
    }
  });

  el.tagPopover.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-pop-action]");
    if (!btn || !state.popoverProjectId) return;
    const action = btn.dataset.popAction;
    if (action === "remove-tag") {
      mutateTags(state.popoverProjectId, { remove_tags: [btn.dataset.tag] });
    } else if (action === "add-tag") {
      mutateTags(state.popoverProjectId, { add_tags: [btn.dataset.tag] });
    }
  });

  el.tagPopover.addEventListener("submit", async (e) => {
    if (e.target.id !== "popover-tag-form" || !state.popoverProjectId) return;
    e.preventDefault();
    const input = el.tagPopover.querySelector("input");
    const errBox = document.getElementById("popover-tag-error");
    const value = (input?.value || "").trim();
    if (!value) {
      if (errBox) {
        errBox.textContent = "请输入标签名称";
        errBox.hidden = false;
      }
      shakeElement(e.target);
      return;
    }
    await mutateTags(state.popoverProjectId, { add_tags: [value] }, errBox);
  });

  document.addEventListener("click", (e) => {
    if (!el.tagPopover.hidden && !el.tagPopover.contains(e.target)) {
      closeTagPopover();
    }
  });

  el.drawerScrim.addEventListener("click", closeDrawer);
  el.btnRefresh.addEventListener("click", triggerRescan);
  el.btnDiagnostics.addEventListener("click", () => openDiagnosticsModal(null));
  el.btnCloseDiag.addEventListener("click", closeDiagnosticsModal);
  el.diagScrim.addEventListener("click", closeDiagnosticsModal);
  el.btnTheme.addEventListener("click", cycleTheme);

  if (el.organizeRoot) {
    el.organizeRoot.addEventListener("click", (e) => {
      const tabBtn = e.target.closest("[data-org-tab]");
      if (tabBtn) {
        state.organizeTab = tabBtn.dataset.orgTab;
        renderOrganizeView();
        return;
      }
      const actionEl = e.target.closest("[data-org-action]");
      if (!actionEl) return;
      const action = actionEl.dataset.orgAction;
      const pid = actionEl.dataset.id;
      if (action === "rescan-hygiene") {
        triggerHygieneScan();
      } else if (action === "open-drawer" && pid) {
        openDrawer(pid, actionEl);
      } else if (action === "open-finder" && pid) {
        openProjectTarget(pid, "finder", actionEl);
      } else if (action === "promote-sandbox" && pid) {
        setProjectPromoted(pid, true);
      } else if (action === "toggle-artifact" && pid) {
        const path = actionEl.dataset.path;
        let sel = state.selectedArtifacts.get(pid);
        if (!sel) {
          sel = new Set();
          state.selectedArtifacts.set(pid, sel);
        }
        if (sel.has(path)) sel.delete(path);
        else sel.add(path);
        if (sel.size === 0) state.selectedArtifacts.delete(pid);
        renderOrganizeView();
      } else if (action === "toggle-project-artifacts" && pid) {
        const arts = projectArtifacts(pid);
        if (actionEl.checked) {
          state.selectedArtifacts.set(pid, new Set(arts.map((a) => a.path)));
        } else {
          state.selectedArtifacts.delete(pid);
        }
        renderOrganizeView();
      } else if (action === "select-all-artifacts") {
        const candidates = getSlimCandidates();
        for (const row of candidates) {
          if (row.activeNow) continue;
          state.selectedArtifacts.set(
            row.project.id,
            new Set(row.artifacts.map((a) => a.path))
          );
        }
        renderOrganizeView();
      } else if (action === "clear-all-artifacts") {
        state.selectedArtifacts.clear();
        renderOrganizeView();
      } else if (action === "slim-single" && pid) {
        const p = state.projectById.get(pid);
        const arts = projectArtifacts(pid);
        if (p && arts.length > 0) {
          openArtifactsTrashModal([
            {
              project_id: pid,
              project_name: projectName(p),
              paths: arts.map((a) => a.path),
              artifacts: arts,
            },
          ]);
        }
      } else if (action === "trash-selected-artifacts") {
        const stats = computeSelectedArtifactsStats(getSlimCandidates());
        if (stats.items.length > 0) {
          openArtifactsTrashModal(stats.items);
        }
      } else if (action === "trash-project" && pid) {
        openProjectTrashModal(pid);
      }
    });

    el.organizeRoot.addEventListener("change", (e) => {
      if (e.target.id === "org-dormant-select") {
        state.organizeDormantDays = Number(e.target.value) || 0;
        syncDefaultSelectedArtifacts();
        renderOrganizeView();
      }
    });
  }

  if (el.btnCloseTrash) {
    el.btnCloseTrash.addEventListener("click", closeTrashModal);
  }
  if (el.trashScrim) {
    el.trashScrim.addEventListener("click", closeTrashModal);
  }
  if (el.trashBody) {
    el.trashBody.addEventListener("change", (e) => {
      if (e.target.id === "trash-caution-checkbox") {
        state.trashModal.confirmedCaution = Boolean(e.target.checked);
        renderTrashModal();
      }
    });
  }
  if (el.trashFooter) {
    el.trashFooter.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-trash-action]");
      if (!btn) return;
      const act = btn.dataset.trashAction;
      if (act === "cancel") {
        closeTrashModal();
      } else if (act === "confirm") {
        confirmTrashModal();
      } else if (act === "switch-to-slim") {
        const m = state.trashModal;
        const p = state.projectById.get(m.projectId);
        const arts = m.gitCheck?.artifacts || [];
        if (p && arts.length > 0) {
          openArtifactsTrashModal([
            {
              project_id: m.projectId,
              project_name: projectName(p),
              paths: arts.map((a) => a.path),
              artifacts: arts,
            },
          ]);
        }
      }
    });
  }

  el.diagFilterBar.addEventListener("click", (e) => {
    if (e.target.id === "btn-diag-show-all") {
      state.diagAgentFilter = null;
      renderDiagnosticsModal();
    }
  });

  el.diagBody.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-toggle-panel]");
    if (!btn) return;
    const panel = document.getElementById(btn.dataset.togglePanel);
    if (panel) {
      const open = !panel.classList.contains("is-open");
      panel.classList.toggle("is-open", open);
      btn.setAttribute("aria-expanded", String(open));
    }
  });

  /* Global Keyboard Shortcuts */
  document.addEventListener("keydown", (e) => {
    const tag = document.activeElement?.tagName;
    const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    const hasMod = e.metaKey || e.ctrlKey || e.altKey;

    if (!state.diagOpen && (e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (state.view !== "projects") switchView("projects");
      el.searchInput.focus();
      el.searchInput.select();
      return;
    }

    if (e.key === "Escape") {
      if (!el.tagPopover.hidden) {
        closeTagPopover();
      } else if (state.trashModal.open) {
        closeTrashModal();
      } else if (state.diagOpen) {
        closeDiagnosticsModal();
      } else if (state.selectedProjectId || state.selectedRemoteGroupKey) {
        closeDrawer();
      } else if (state.search) {
        state.search = "";
        el.searchInput.value = "";
        el.searchClear.hidden = true;
        el.searchKbd.hidden = false;
        renderProjectsView();
      }
      return;
    }

    if (typing || state.diagOpen || state.trashModal.open) return;

    if (e.key === "/") {
      e.preventDefault();
      if (state.view !== "projects") switchView("projects");
      el.searchInput.focus();
      return;
    }

    const lower = e.key.toLowerCase();
    if (lower === "r" && !hasMod) {
      e.preventDefault();
      triggerRescan();
      return;
    }

    if (state.view === "projects") {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const rows = Array.from(el.projectsContainer.querySelectorAll(".project-row"));
        if (rows.length === 0) return;
        e.preventDefault();
        const curIdx = rows.findIndex(
          (r) => r.dataset.projectId === (state.selectedProjectId || state.focusedProjectId)
        );
        const delta = e.key === "ArrowDown" ? 1 : -1;
        const nextIdx =
          curIdx === -1
            ? delta > 0
              ? 0
              : rows.length - 1
            : Math.max(0, Math.min(rows.length - 1, curIdx + delta));
        const nextRow = rows[nextIdx];
        state.focusedProjectId = nextRow.dataset.projectId;
        nextRow.focus({ preventScroll: true });
        nextRow.scrollIntoView({ block: "nearest", behavior: "smooth" });
        if (state.selectedProjectId) {
          openDrawer(nextRow.dataset.projectId, nextRow);
        }
        return;
      }

      const activeId =
        state.selectedProjectId ||
        document.activeElement?.closest?.(".project-row")?.dataset?.projectId;
      if (!activeId || hasMod) return;
      if (lower === "s") {
        e.preventDefault();
        toggleStar(activeId);
      } else if (lower === "o") {
        const p = state.projectById.get(activeId);
        if (p && p.status === "directory") {
          e.preventDefault();
          openProjectTarget(activeId, "finder");
        }
      } else if (lower === "e") {
        const p = state.projectById.get(activeId);
        if (p && p.status === "directory") {
          const preferred =
            preferredLauncherForProject(p) ||
            availableLaunchers().find(
              (item) => isAppLauncher(item) && item.opens_path !== false
            );
          if (preferred) {
            e.preventDefault();
            openProjectTarget(activeId, preferred.id);
          }
        }
      } else if (lower === "t") {
        const p = state.projectById.get(activeId);
        const term = launcherById("terminal");
        if (p && p.status === "directory" && term && term.available) {
          e.preventDefault();
          openProjectTarget(activeId, "terminal");
        }
      }
    }
  });

  /* System Theme Watcher & Segmented ResizeObserver */
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (getThemeMode() === "auto") applyTheme("auto");
  });

  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(() => positionSegmentedThumb(el.viewSegmented));
    ro.observe(el.viewSegmented);
  }
  window.addEventListener("resize", () => {
    positionSegmentedThumb(el.viewSegmented);
    closeTagPopover();
  });

  /* Boot */
  applyTheme(getThemeMode());
  positionSegmentedThumb(el.viewSegmented);
  renderSkeleton();

  (async function init() {
    try {
      const payload = await api("/api/state");
      applyData(payload);
      positionSegmentedThumb(el.viewSegmented);
    } catch (err) {
      el.projectsContainer.innerHTML = `<div class="empty-state">
        <p class="empty-title">无法加载本机项目索引</p>
        <p class="empty-desc">${escapeHtml(err.message)}</p>
        <div class="empty-actions">
          <button type="button" class="btn btn-primary" onclick="location.reload()">重试</button>
        </div>
      </div>`;
    }
  })();
})();
