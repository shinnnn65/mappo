(() => {
  "use strict";

  const SESSION_CACHE_TTL_MS = 30 * 1000;
  const COVERAGE_LABELS = {
    full: { text: "完整对话", tone: "is-full" },
    summary_only: { text: "摘要", tone: "is-partial" },
    meta_and_diffs: { text: "元信息+改动", tone: "is-partial" },
    meta_only: { text: "仅元信息", tone: "is-partial" },
  };

  const sessionState = {
    byProjectId: new Map(), // projectId -> { status, sessions, error, fetchedAt }
    handoffByRef: new Map(), // ref -> { status, data, error }
    agentFilter: "all",
    expandedRef: null,
  };

  function invalidateCache(projectId = null) {
    if (projectId) {
      sessionState.byProjectId.delete(projectId);
    } else {
      sessionState.byProjectId.clear();
    }
    sessionState.handoffByRef.clear();
    sessionState.expandedRef = null;
  }

  function resetSelectionState() {
    sessionState.agentFilter = "all";
    sessionState.expandedRef = null;
  }

  function getProjectEntry(projectId) {
    return (
      sessionState.byProjectId.get(projectId) || {
        status: "idle",
        sessions: [],
        error: null,
        fetchedAt: 0,
      }
    );
  }

  function getCachedSessionCount(projectId) {
    const entry = sessionState.byProjectId.get(projectId);
    return entry && entry.status === "ready" ? entry.sessions.length : null;
  }

  async function ensureProjectSessions(project, ctx, { force = false } = {}) {
    if (!project || project.status !== "directory") return;
    const pid = project.id;
    const existing = sessionState.byProjectId.get(pid);
    const fresh =
      existing &&
      existing.status === "ready" &&
      Date.now() - existing.fetchedAt < SESSION_CACHE_TTL_MS;
    if (!force && (fresh || existing?.status === "loading")) {
      return;
    }

    sessionState.byProjectId.set(pid, {
      status: "loading",
      sessions: existing?.sessions || [],
      error: null,
      fetchedAt: 0,
    });
    ctx.onSessionsUpdated(pid);

    try {
      const res = await ctx.api(
        `/api/projects/${encodeURIComponent(pid)}/sessions?limit=30`
      );
      sessionState.byProjectId.set(pid, {
        status: "ready",
        sessions: Array.isArray(res.sessions) ? res.sessions : [],
        error: null,
        fetchedAt: Date.now(),
      });
    } catch (error) {
      sessionState.byProjectId.set(pid, {
        status: "error",
        sessions: [],
        error: error.message || "加载会话失败",
        fetchedAt: Date.now(),
      });
    }
    ctx.onSessionsUpdated(pid);
  }

  async function ensureHandoff(ref, ctx) {
    const cached = sessionState.handoffByRef.get(ref);
    if (cached && cached.status === "ready") {
      return cached.data;
    }
    sessionState.handoffByRef.set(ref, { status: "loading", data: null, error: null });
    try {
      const data = await ctx.api(
        `/api/sessions/handoff?ref=${encodeURIComponent(ref)}&turns=6`
      );
      sessionState.handoffByRef.set(ref, { status: "ready", data, error: null });
      return data;
    } catch (error) {
      sessionState.handoffByRef.set(ref, {
        status: "error",
        data: null,
        error: error.message || "生成交接包失败",
      });
      throw error;
    }
  }

  function renderPreviewHtml(ref, ctx) {
    const entry = sessionState.handoffByRef.get(ref);
    if (!entry || entry.status === "loading") {
      return `<div class="session-preview-box">
        <div class="session-preview-summary">正在按需只读解析会话内容…</div>
      </div>`;
    }
    if (entry.status === "error") {
      return `<div class="session-preview-box">
        <div class="session-preview-note">${ctx.escapeHtml(entry.error || "加载失败")}</div>
      </div>`;
    }
    const { handoff } = entry.data;
    const parts = [];
    if (handoff.limitations) {
      parts.push(
        `<div class="session-preview-note">${ctx.escapeHtml(handoff.limitations)}</div>`
      );
    }
    if (handoff.summary) {
      parts.push(`<div>
        <div class="session-preview-block-title">原生摘要</div>
        <div class="session-preview-summary">${ctx.escapeHtml(handoff.summary)}</div>
      </div>`);
    }
    const msgs = handoff.messages || [];
    if (msgs.length > 0) {
      const turnsHtml = msgs
        .slice(-4)
        .map((m) => {
          const isUser = m.role === "user";
          return `<div class="session-turn-item${isUser ? " is-user" : ""}">
            <span class="session-turn-role">${isUser ? "用户" : "助手"}</span>
            <div>${ctx.escapeHtml(m.text)}</div>
          </div>`;
        })
        .join("");
      parts.push(`<div>
        <div class="session-preview-block-title">最近对话（共 ${handoff.turns_total || msgs.length} 轮，预览最近 ${Math.min(4, msgs.length)} 条）</div>
        <div class="session-preview-turns">${turnsHtml}</div>
      </div>`);
    }
    const files = handoff.changed_files || [];
    if (files.length > 0) {
      const chips = files
        .slice(0, 10)
        .map(
          (f) =>
            `<span class="session-file-chip" title="${ctx.escapeHtml(f)}">${ctx.escapeHtml(
              ctx.shortenPath(f)
            )}</span>`
        )
        .join("");
      parts.push(`<div>
        <div class="session-preview-block-title">涉及改动文件（${files.length}）</div>
        <div class="session-preview-files">${chips}</div>
      </div>`);
    }
    if (parts.length === 0) {
      parts.push(
        `<div class="session-preview-summary">该会话暂无可预览的正文或文件改动。</div>`
      );
    }
    return `<div class="session-preview-box">${parts.join("")}</div>`;
  }

  function renderSessionCardHtml(session, ctx, { compact = false } = {}) {
    const cov = COVERAGE_LABELS[session.coverage] || {
      text: session.coverage || "可读",
      tone: "is-partial",
    };
    const expanded = !compact && sessionState.expandedRef === session.ref;
    const shortPrompt = `请通过 mappo 读取会话 ${session.ref} 的上下文并接着往下做`;
    return `<div class="session-card" data-session-ref="${ctx.escapeHtml(session.ref)}">
      <div class="session-card-row">
        <div class="session-card-main">
          <span class="session-card-icon">${ctx.renderAgentIconHtml(session.agent, "sm")}</span>
          <div class="session-card-titles">
            <div class="session-card-title" title="${ctx.escapeHtml(session.title)}">${ctx.escapeHtml(session.title)}</div>
            <div class="session-card-meta">
              <span class="session-ref-code">${ctx.escapeHtml(session.ref)}</span>
              <span title="${ctx.escapeHtml(
                ctx.formatExactTime(session.updated_at)
              )}">${ctx.escapeHtml(ctx.formatRelativeTime(session.updated_at))}</span>
              <span class="session-coverage-pill ${cov.tone}">${ctx.escapeHtml(cov.text)}</span>
            </div>
          </div>
        </div>
        <div class="session-card-actions">
          <button type="button" class="session-action-btn is-primary" data-session-action="copy-handoff" data-ref="${ctx.escapeHtml(
            session.ref
          )}" title="复制裁剪好的 Markdown 上下文（摘要 + 最近对话 + Git 状态），任意聊天窗口粘贴即续聊">
            <span class="icon-swap"><span class="icon-base">${ctx.ICONS.copy}</span><span class="icon-done">${ctx.ICONS.check}</span></span>
            <span>复制上下文</span>
          </button>
          <button type="button" class="session-action-btn" data-session-action="copy-ref" data-ref="${ctx.escapeHtml(
            session.ref
          )}" data-prompt="${ctx.escapeHtml(
      shortPrompt
    )}" title="只复制一句话指令，让已装 Mappo Skill 的 Agent 自己调用 mappo 拉取会话">
            <span class="icon-swap"><span class="icon-base">${ctx.ICONS.copy}</span><span class="icon-done">${ctx.ICONS.check}</span></span>
            <span>复制指令</span>
          </button>
          ${
            !compact
              ? `<button type="button" class="session-action-btn" data-session-action="toggle-preview" data-ref="${ctx.escapeHtml(
                  session.ref
                )}" aria-expanded="${expanded ? "true" : "false"}">
                  <span>${expanded ? "收起" : "预览"}</span>
                </button>`
              : ""
          }
        </div>
      </div>
      ${expanded ? renderPreviewHtml(session.ref, ctx) : ""}
    </div>`;
  }

  function renderOverviewCard(project, ctx) {
    if (!project || project.status !== "directory") return "";
    const entry = getProjectEntry(project.id);
    if (entry.status === "idle" || entry.status === "loading") {
      return `<div class="drawer-section">
        <div class="sessions-section-header">
          <h3 class="drawer-section-title">最近跨工具会话</h3>
        </div>
        <div class="sessions-empty-box">
          <span>正在按需读取 Codex / Antigravity / Cursor / CodeBuddy 会话…</span>
        </div>
      </div>`;
    }
    if (entry.status === "error") {
      return `<div class="drawer-section">
        <div class="sessions-section-header">
          <h3 class="drawer-section-title">最近跨工具会话</h3>
          <button type="button" class="btn btn-subtle" style="height:24px;font-size:11.5px" data-session-action="refresh">重试</button>
        </div>
        <div class="sessions-empty-box">
          <span>${ctx.escapeHtml(entry.error)}</span>
        </div>
      </div>`;
    }
    const items = entry.sessions || [];
    if (items.length === 0) {
      return `<div class="drawer-section">
        <div class="sessions-section-header">
          <h3 class="drawer-section-title">最近跨工具会话</h3>
        </div>
        <div class="sessions-empty-box">
          <span>暂未在 Codex、Antigravity、Cursor 或 CodeBuddy 中找到该目录的本地会话。</span>
        </div>
      </div>`;
    }
    const preview = items.slice(0, 3);
    const moreBtn =
      items.length > 3
        ? `<button type="button" class="btn btn-subtle" style="height:24px;font-size:11.5px" data-drawer-tab="sessions">查看全部 ${items.length} 条 →</button>`
        : `<button type="button" class="btn btn-subtle" style="height:24px;font-size:11.5px" data-drawer-tab="sessions">展开预览 →</button>`;
    return `<div class="drawer-section">
      <div class="sessions-section-header">
        <h3 class="drawer-section-title">最近跨工具会话（${items.length}）</h3>
        ${moreBtn}
      </div>
      <div class="sessions-list">
        ${preview.map((item) => renderSessionCardHtml(item, ctx, { compact: true })).join("")}
      </div>
    </div>`;
  }

  function renderSessionsTab(project, ctx) {
    if (!project || project.status !== "directory") {
      return `<div class="sessions-empty-box">
        <span>仅支持为本机可用目录读取跨工具会话记录。</span>
      </div>`;
    }
    const entry = getProjectEntry(project.id);
    if (entry.status === "idle" || entry.status === "loading") {
      return `<div class="sessions-empty-box">
        <span>正在按需读取本机跨工具会话…</span>
      </div>`;
    }
    if (entry.status === "error") {
      return `<div class="sessions-empty-box">
        <span>${ctx.escapeHtml(entry.error)}</span>
        <button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-session-action="refresh">重新读取</button>
      </div>`;
    }
    const all = entry.sessions || [];
    if (all.length === 0) {
      return `<div class="sessions-empty-box">
        <span>该目录下暂无 Codex / Antigravity / Cursor / CodeBuddy 本地会话记录。</span>
        <button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-session-action="refresh">刷新</button>
      </div>`;
    }

    const counts = new Map();
    for (const s of all) {
      counts.set(s.agent, (counts.get(s.agent) || 0) + 1);
    }
    if (
      sessionState.agentFilter !== "all" &&
      !counts.has(sessionState.agentFilter)
    ) {
      sessionState.agentFilter = "all";
    }
    const agentOrder = ["codex", "antigravity", "cursor", "codebuddy"].filter((a) =>
      counts.has(a)
    );
    const pillsHtml = [
      `<button type="button" class="session-filter-pill${
        sessionState.agentFilter === "all" ? " is-active" : ""
      }" data-session-action="filter-agent" data-agent="all">全部 ${all.length}</button>`,
      ...agentOrder.map(
        (agentId) => `<button type="button" class="session-filter-pill${
          sessionState.agentFilter === agentId ? " is-active" : ""
        }" data-session-action="filter-agent" data-agent="${ctx.escapeHtml(agentId)}">
          ${ctx.renderAgentIconHtml(agentId, "xs")}
          <span>${ctx.escapeHtml(ctx.agentLabel(agentId))} ${counts.get(agentId)}</span>
        </button>`
      ),
    ].join("");

    const filtered =
      sessionState.agentFilter === "all"
        ? all
        : all.filter((s) => s.agent === sessionState.agentFilter);

    return `
      <div class="sessions-filter-row">
        <div class="sessions-filter-pills">${pillsHtml}</div>
        <button type="button" class="btn btn-subtle" style="height:27px;font-size:12px" data-session-action="refresh">刷新会话</button>
      </div>
      <div class="sessions-hint-bar">
        按需只读解析，对话正文不入库。「复制上下文」直接粘贴即续聊；「复制指令」仅复制一句话，由已装 Mappo Skill 的 Agent 按需拉取。
      </div>
      <div class="sessions-list">
        ${filtered.map((item) => renderSessionCardHtml(item, ctx)).join("")}
      </div>
    `;
  }

  async function handleAction(btn, project, ctx) {
    const action = btn.dataset.sessionAction;
    if (!action || !project) return false;

    if (action === "refresh") {
      await ensureProjectSessions(project, ctx, { force: true });
      return true;
    }

    if (action === "filter-agent") {
      sessionState.agentFilter = btn.dataset.agent || "all";
      ctx.onSessionsUpdated(project.id);
      return true;
    }

    if (action === "copy-ref") {
      const prompt = btn.dataset.prompt || btn.dataset.ref || "";
      await ctx.copyText(prompt, btn, "已复制一句话指令，发给已装 Mappo Skill 的 Agent 即可自动拉取");
      return true;
    }

    if (action === "copy-handoff") {
      const ref = btn.dataset.ref;
      if (!ref) return true;
      btn.disabled = true;
      try {
        const data = await ensureHandoff(ref, ctx);
        await ctx.copyText(
          data.markdown,
          btn,
          `已复制 ${ref} 完整上下文（Markdown），粘贴即续聊`
        );
      } catch (error) {
        ctx.showToast(error.message || "生成交接包失败");
      } finally {
        btn.disabled = false;
      }
      return true;
    }

    if (action === "toggle-preview") {
      const ref = btn.dataset.ref;
      if (!ref) return true;
      if (sessionState.expandedRef === ref) {
        sessionState.expandedRef = null;
        ctx.onSessionsUpdated(project.id);
        return true;
      }
      sessionState.expandedRef = ref;
      ctx.onSessionsUpdated(project.id);
      try {
        await ensureHandoff(ref, ctx);
      } catch (_) {}
      ctx.onSessionsUpdated(project.id);
      return true;
    }

    return false;
  }

  window.MappoSessionsPanel = {
    ensureProjectSessions,
    getCachedSessionCount,
    handleAction,
    invalidateCache,
    renderOverviewCard,
    renderSessionsTab,
    resetSelectionState,
  };
})();
