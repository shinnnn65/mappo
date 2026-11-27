(() => {
  "use strict";

  function renderCompactOverview(project, ctx) {
    const canOpen = project.status === "directory";
    const statusMeta = ctx.STATUS_META[project.status] || {
      label: project.status,
      short: project.status,
      pill: "is-neutral",
    };
    const gInfo = ctx.gitInfo(project);
    const isRemote = project.status === "remote";
    const rInfo = isRemote ? ctx.remoteInfo(project) : null;

    let gitCardHtml = "";
    if (gInfo && gInfo.is_git) {
      const branchText = gInfo.branch
        ? gInfo.detached
          ? `${gInfo.branch} (HEAD)`
          : gInfo.branch
        : "未知";
      const remoteText = gInfo.remote_url ? gInfo.remote_url : "仅本地 Git 仓库";
      gitCardHtml = `<div class="overview-stat-card">
        <span class="overview-stat-label">Git 分支与远端</span>
        <div class="overview-stat-value">
          <span class="git-branch-pill" title="${ctx.escapeHtml(branchText)}">${ctx.escapeHtml(
            branchText
          )}</span>
          ${
            gInfo.remote_url
              ? `<button type="button" class="git-inline-copy" data-drawer-action="copy-text" data-text="${ctx.escapeHtml(
                  gInfo.remote_url
                )}" aria-label="复制远端地址" title="复制远端地址">
                  <span class="icon-swap"><span class="icon-base">${ctx.ICONS.copy}</span><span class="icon-done">${ctx.ICONS.check}</span></span>
                </button>`
              : ""
          }
        </div>
        <span class="overview-stat-sub" title="${ctx.escapeHtml(remoteText)}">${ctx.escapeHtml(
        remoteText
      )}</span>
      </div>`;
    } else if (isRemote && rInfo?.host) {
      gitCardHtml = `<div class="overview-stat-card">
        <span class="overview-stat-label">远程主机</span>
        <div class="overview-stat-value">${ctx.escapeHtml(rInfo.host)}</div>
        <span class="overview-stat-sub" title="${ctx.escapeHtml(
          rInfo.remote_path || ""
        )}">${ctx.escapeHtml(rInfo.remote_path || "")}</span>
      </div>`;
    } else {
      gitCardHtml = `<div class="overview-stat-card">
        <span class="overview-stat-label">版本控制</span>
        <div class="overview-stat-value">
          <span class="status-pill is-local-only">纯本地目录</span>
        </div>
        <span class="overview-stat-sub">未检测到 .git 仓库</span>
      </div>`;
    }

    const activityCardHtml = `<div class="overview-stat-card">
      <span class="overview-stat-label">最近活动</span>
      <div class="overview-stat-value">
        <span>${ctx.escapeHtml(ctx.formatRelativeTime(project.last_activity))}</span>
        <span class="status-pill ${statusMeta.pill}">${ctx.escapeHtml(
      statusMeta.short || "可用"
    )}</span>
      </div>
      <span class="overview-stat-sub">${ctx.escapeHtml(
        ctx.formatExactTime(project.last_activity)
      )}</span>
    </div>`;

    const dupGroup = ctx.state.duplicateGroupByProjectId.get(project.id);
    const dupCalloutHtml =
      dupGroup && dupGroup.count >= 2 && canOpen
        ? `<div class="drawer-inline-callout">
            <div class="drawer-inline-callout-text">
              <span class="drawer-inline-callout-title">本机另有 ${dupGroup.count - 1} 份同源副本</span>
              <span class="drawer-inline-callout-sub">${ctx.escapeHtml(dupGroup.name)} · 共 ${dupGroup.count} 个本地目录</span>
            </div>
            <button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-drawer-action="compare-duplicates" data-remote-key="${ctx.escapeHtml(
              dupGroup.remote_key
            )}">去对比</button>
          </div>`
        : "";

    const reclaimBytes = ctx.projectReclaimableBytes(project.id);
    const artifacts = ctx.projectArtifacts(project.id);
    const hygieneCalloutHtml =
      canOpen && reclaimBytes > 0
        ? `<div class="drawer-inline-callout">
            <div class="drawer-inline-callout-text">
              <span class="drawer-inline-callout-title">可安全瘦身 ${ctx.escapeHtml(
                ctx.formatBytes(reclaimBytes)
              )}</span>
              <span class="drawer-inline-callout-sub">${ctx.escapeHtml(
                artifacts
                  .slice(0, 3)
                  .map((a) => `${a.rel_path} (${ctx.formatBytes(a.bytes)})`)
                  .join("、")
              )}</span>
            </div>
            <button type="button" class="btn btn-secondary" style="height:28px;font-size:12px" data-drawer-action="slim-project">清理依赖</button>
          </div>`
        : "";

    const currentTags = project.tags || [];
    const currentTagSet = new Set(currentTags.map((t) => t.toLowerCase()));
    const suggestions = (ctx.state.data?.all_tags || [])
      .map((item) => item.tag)
      .filter((t) => !currentTagSet.has(t.toLowerCase()))
      .slice(0, 8);

    const tagsHtml = currentTags
      .map(
        (tag) => `<span class="tag-removable" data-tag-chip="${ctx.escapeHtml(tag)}">
          <span>#${ctx.escapeHtml(tag)}</span>
          <button type="button" class="tag-remove-btn" data-drawer-action="remove-tag" data-tag="${ctx.escapeHtml(
            tag
          )}" aria-label="移除标签 ${ctx.escapeHtml(tag)}">${ctx.ICONS.close}</button>
        </span>`
      )
      .join("");

    const suggestionsHtml = suggestions
      .map(
        (tag) =>
          `<button type="button" class="tag-suggest-btn" data-drawer-action="add-suggest-tag" data-tag="${ctx.escapeHtml(
            tag
          )}">+ ${ctx.escapeHtml(tag)}</button>`
      )
      .join("");

    const sessionsPreviewHtml = window.MappoSessionsPanel
      ? window.MappoSessionsPanel.renderOverviewCard(project, ctx.sessionsCtx)
      : "";

    return `
      ${ctx.contextCardHtml}
      <div class="overview-stat-grid">
        ${activityCardHtml}
        ${gitCardHtml}
      </div>
      ${hygieneCalloutHtml}
      ${dupCalloutHtml}
      ${sessionsPreviewHtml}
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
    `;
  }

  function renderDetailsTab(project, ctx) {
    const indexStateText =
      project.index_state === "historical"
        ? `历史记录（上次出现于 ${ctx.formatExactTime(project.last_seen)}）`
        : "最近一次扫描已确认";
    const gInfo = ctx.gitInfo(project);
    let parentRowHtml = "";
    if (gInfo?.parent_repo) {
      const parentProj = ctx.state.projectByPath.get(gInfo.parent_repo);
      const parentShort = ctx.shortenPath(gInfo.parent_repo);
      const valHtml = parentProj
        ? `<button type="button" class="git-parent-btn" data-drawer-action="jump-project" data-id="${ctx.escapeHtml(
            parentProj.id
          )}">${ctx.escapeHtml(parentShort)}</button>`
        : `<span class="git-parent-text">${ctx.escapeHtml(parentShort)}</span>`;
      parentRowHtml = `<div class="meta-row">
        <span class="meta-key">所属父仓库</span>
        <span class="meta-val">${valHtml}</span>
      </div>`;
    }

    return `
      <div class="drawer-section">
        <h3 class="drawer-section-title">发现记录（${ctx.evidenceCount}）</h3>
        <div class="evidence-list">${ctx.evidenceHtml}</div>
      </div>

      <div class="drawer-section">
        <h3 class="drawer-section-title">关联项目${
          ctx.relatedCount ? `（${ctx.relatedCount}）` : ""
        }</h3>
        ${ctx.relatedHtml}
        ${ctx.linkPickerHtml}
      </div>

      <div class="drawer-section">
        <h3 class="drawer-section-title">索引与来源元信息</h3>
        <div class="meta-grid">
          <div class="meta-row">
            <span class="meta-key">索引状态</span>
            <span class="meta-val">${ctx.escapeHtml(indexStateText)}</span>
          </div>
          ${parentRowHtml}
          ${
            project.activity_source
              ? `<div class="meta-row">
                  <span class="meta-key">时间依据</span>
                  <span class="meta-val" style="font-family:var(--font-mono);font-size:11px">${ctx.escapeHtml(
                    ctx.shortenPath(project.activity_source)
                  )}</span>
                </div>`
              : ""
          }
        </div>
      </div>
    `;
  }

  function renderHeaderActions(ctx) {
    const appLaunchers = ctx.appLaunchers || [];
    const utilLaunchers = ctx.utilLaunchers || [];
    const expanded = Boolean(ctx.state.drawerAppsExpanded);
    const maxVisible = 4;
    const visibleApps = appLaunchers.slice(0, maxVisible);
    const overflowCount = Math.max(0, appLaunchers.length - maxVisible);

    let appStackHtml = "";
    if (appLaunchers.length > 0) {
      const avatarsHtml = visibleApps
        .map((item, idx) => {
          const tip =
            item.opens_path === false
              ? `打开 ${item.label}（应用）`
              : `用 ${item.label} 打开`;
          return `<button type="button" class="drawer-app-avatar" style="z-index:${
            visibleApps.length - idx
          }" data-drawer-action="open" data-target="${ctx.escapeHtml(
            item.id
          )}" data-tooltip="${ctx.escapeHtml(tip)}" aria-label="${ctx.escapeHtml(tip)}">
            <span class="icon-swap"><span class="icon-base">${ctx.renderLauncherChipIcon(
              item.id
            )}</span><span class="icon-done">${ctx.ICONS.check}</span></span>
          </button>`;
        })
        .join("");

      const moreBtnHtml =
        overflowCount > 0 || expanded
          ? `<button type="button" class="drawer-app-more${
              expanded ? " is-open" : ""
            }" data-drawer-action="toggle-drawer-apps" aria-expanded="${
              expanded ? "true" : "false"
            }" title="${expanded ? "收起全部打开方式" : `展开全部 ${appLaunchers.length} 个工具`}">${
              expanded ? "收起" : `+${overflowCount}`
            }</button>`
          : "";

      appStackHtml = `<div class="drawer-app-stack" role="group" aria-label="其他编辑器与 Agent">${avatarsHtml}${moreBtnHtml}</div>`;
    }

    const expandedTrayHtml =
      expanded && appLaunchers.length > 0
        ? `<div class="drawer-app-expanded-tray" aria-label="全部编辑器与 Agent">
            ${appLaunchers
              .map((item) => {
                const tip =
                  item.opens_path === false
                    ? `打开 ${item.label} 应用（暂不支持直接传入目录）`
                    : `在 ${item.label} 中打开`;
                return `<button type="button" class="launch-chip" data-drawer-action="open" data-target="${ctx.escapeHtml(
                  item.id
                )}" title="${ctx.escapeHtml(tip)}">
                  <span class="icon-swap"><span class="icon-base">${ctx.renderLauncherChipIcon(
                    item.id
                  )}</span><span class="icon-done">${ctx.ICONS.check}</span></span>
                  <span>${ctx.escapeHtml(item.label)}</span>
                </button>`;
              })
              .join("")}
          </div>`
        : "";

    const utilGroupHtml =
      utilLaunchers.length > 0
        ? `<div class="drawer-util-group" role="group" aria-label="系统与仓库入口">
            ${utilLaunchers
              .map(
                (item) => `<button type="button" class="drawer-util-btn" data-drawer-action="open" data-target="${ctx.escapeHtml(
                  item.id
                )}" title="${ctx.escapeHtml(item.tip || item.label)}">
                  <span class="icon-swap"><span class="icon-base">${item.iconHtml}</span><span class="icon-done">${ctx.ICONS.check}</span></span>
                  <span>${ctx.escapeHtml(item.label)}</span>
                </button>`
              )
              .join("")}
          </div>`
        : "";

    return `
      <div class="drawer-header-actions">
        <div class="drawer-action-bar">
          <div class="drawer-app-group">
            ${ctx.primaryBtn}
            ${appStackHtml}
          </div>
          ${utilGroupHtml}
        </div>
        ${expandedTrayHtml}
      </div>
    `;
  }

  function renderProjectDrawer(project, ctx) {
    const canOpen = project.status === "directory";
    const isPromotedSandbox = project.asset_reason === "promoted_sandbox";
    const activeTab = ctx.state.drawerTab || "overview";
    const cachedSessions = window.MappoSessionsPanel
      ? window.MappoSessionsPanel.getCachedSessionCount(project.id)
      : null;

    let bodyHtml = "";
    if (activeTab === "sessions") {
      bodyHtml = window.MappoSessionsPanel
        ? window.MappoSessionsPanel.renderSessionsTab(project, ctx.sessionsCtx)
        : "";
    } else if (activeTab === "details") {
      bodyHtml = renderDetailsTab(project, ctx);
    } else {
      bodyHtml = renderCompactOverview(project, ctx);
    }

    const sessionBadge =
      cachedSessions !== null
        ? `<span class="drawer-tab-badge">${cachedSessions}</span>`
        : "";
    const detailCount = ctx.evidenceCount + ctx.relatedCount;
    const detailBadge =
      detailCount > 0
        ? `<span class="drawer-tab-badge">${detailCount}</span>`
        : "";

    return `
      <div class="drawer-header">
        <div class="drawer-title-row">
          <div class="drawer-title-cluster">
            <button type="button" class="star-btn${
              project.favorite ? " is-starred" : ""
            }" data-drawer-action="star" aria-label="${
      project.favorite ? "取消收藏" : "收藏项目"
    }" title="${project.favorite ? "取消收藏 (S)" : "收藏项目 (S)"}">
              ${project.favorite ? ctx.ICONS.starFilled : ctx.ICONS.starOutline}
            </button>
            <h2 class="drawer-title" title="${ctx.escapeHtml(ctx.name)}">${ctx.escapeHtml(
      ctx.name
    )}</h2>
          </div>
          <button type="button" class="icon-btn" data-drawer-action="close" aria-label="关闭详情">${
            ctx.ICONS.close
          }</button>
        </div>

        <div class="drawer-path-box">
          <span class="drawer-path-text" title="${ctx.escapeHtml(project.path)}">${ctx.escapeHtml(
      project.path
    )}</span>
          <button type="button" class="git-inline-copy" data-drawer-action="copy" aria-label="复制路径" title="复制完整路径">
            <span class="icon-swap"><span class="icon-base">${ctx.ICONS.copy}</span><span class="icon-done">${ctx.ICONS.check}</span></span>
          </button>
        </div>

        ${renderHeaderActions(ctx)}

        <nav class="drawer-tabs" role="tablist" aria-label="项目详情标签页">
          <button type="button" class="drawer-tab-btn${
            activeTab === "overview" ? " is-active" : ""
          }" role="tab" aria-selected="${activeTab === "overview"}" data-drawer-tab="overview">
            <span>概览</span>
          </button>
          ${
            canOpen
              ? `<button type="button" class="drawer-tab-btn${
                  activeTab === "sessions" ? " is-active" : ""
                }" role="tab" aria-selected="${activeTab === "sessions"}" data-drawer-tab="sessions">
                  <span>会话交接</span>
                  ${sessionBadge}
                </button>`
              : ""
          }
          <button type="button" class="drawer-tab-btn${
            activeTab === "details" ? " is-active" : ""
          }" role="tab" aria-selected="${activeTab === "details"}" data-drawer-tab="details">
            <span>来源与关联</span>
            ${detailBadge}
          </button>
        </nav>
      </div>

      <div class="drawer-body" id="drawer-body">
        ${bodyHtml}
      </div>

      <div class="drawer-footer">
        <span class="drawer-id-label">${ctx.escapeHtml(project.id)}</span>
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
            ${project.hidden ? ctx.ICONS.eye : ctx.ICONS.eyeOff}
            <span>${project.hidden ? "恢复显示" : "隐藏此项目"}</span>
          </button>
        </div>
      </div>
    `;
  }

  window.MappoDetailDrawer = {
    renderProjectDrawer,
  };
})();
