const PAGE = document.body.dataset.page || "home";
const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_MCP_BASE_URL = "";
const SESSION_STORAGE_KEY = "sts_session_token";
const CONVERSATION_TOKEN_STORAGE_KEY = "sts_conversation_tokens_v1";

const refs = {
  authSlot: document.getElementById("auth-slot"),
  metricTotal: document.getElementById("metric-total"),
  metricTools: document.getElementById("metric-tools"),
  metricModalities: document.getElementById("metric-modalities"),
  signalStrip: document.getElementById("signal-strip"),
  homeFeed: document.getElementById("home-feed"),
  homeEntityList: document.getElementById("home-entity-list"),
  homePromptChips: document.getElementById("home-prompt-chips"),
  homeNoticing: document.getElementById("home-noticing"),
  homeTopics: document.getElementById("home-topics"),
  homeGuides: document.getElementById("home-guides"),
  homeQuestions: document.getElementById("home-questions"),
  composerForm: document.getElementById("composer-form"),
  composerText: document.getElementById("composer-text"),
  composerSeed: document.getElementById("composer-seed"),
  composerSubmit: document.getElementById("composer-submit"),
  composerAuthNote: document.getElementById("composer-auth-note"),
  conversationTitle: document.getElementById("conversation-title"),
  conversationMeta: document.getElementById("conversation-meta"),
  conversationThread: document.getElementById("conversation-thread"),
  conversationForm: document.getElementById("conversation-form"),
  conversationText: document.getElementById("conversation-text"),
  conversationSubmit: document.getElementById("conversation-submit"),
  conversationAuthNote: document.getElementById("conversation-auth-note"),
  conversationSidebar: document.getElementById("conversation-sidebar"),
  entitySearch: document.getElementById("entity-search"),
  entityList: document.getElementById("entity-list"),
  entityInspector: document.getElementById("entity-inspector"),
  mcpStatus: document.getElementById("mcp-status"),
  mcpTransport: document.getElementById("mcp-transport"),
  mcpEndpoint: document.getElementById("mcp-endpoint"),
  mcpOpenEndpoint: document.getElementById("mcp-open-endpoint"),
  mcpReadTools: document.getElementById("mcp-read-tools"),
  mcpWriteTools: document.getElementById("mcp-write-tools"),
  mcpResources: document.getElementById("mcp-resources"),
  mcpCommand: document.getElementById("mcp-command"),
  mcpInspectorCommand: document.getElementById("mcp-inspector-command"),
  postOpen: document.getElementById("post-open"),
  postSheet: document.getElementById("post-sheet"),
  postClose: document.getElementById("post-close"),
};

const state = {
  apiBaseUrl: readApiBaseUrl(),
  mcpBaseUrl: readMcpBaseUrl(),
  config: null,
  session: null,
  feed: null,
  mcpInfo: null,
  homeSubmitting: false,
  conversationSubmitting: false,
  conversation: null,
  entitySearchTimer: 0,
  entities: [],
  selectedEntityId: "",
  booted: false,
};

void init();

async function init() {
  await bootApp();
}

async function bootApp() {
  if (state.booted) return;
  state.booted = true;

  renderAuthSlot();

  const configPromise = fetchConfigSafe();
  const feedPromise = fetchFeedSafe();
  state.config = await configPromise;
  state.session = await fetchSessionSafe();
  renderAuthSlot();
  renderAuthNotes();

  state.feed = await feedPromise;
  syncMetrics(state.feed?.metrics);

  if (PAGE === "home") {
    wireHomePage();
    renderHome();
    return;
  }

  if (PAGE === "conversation") {
    wireConversationPage();
    await loadConversationPage();
    return;
  }

  if (PAGE === "wiki") {
    wireWikiPage();
    await loadWikiPage();
    return;
  }

  if (PAGE === "mcp") {
    await loadMcpPage();
    return;
  }

  if (PAGE === "feedback" || PAGE === "compat") {
    return;
  }
}

function wireHomePage() {
  refs.composerForm?.addEventListener("submit", handleComposerSubmit);
  refs.postOpen?.addEventListener("click", openPostSheet);
  refs.postClose?.addEventListener("click", closePostSheet);
  refs.postSheet?.addEventListener("click", (event) => {
    if (event.target.closest("[data-close-post]")) {
      closePostSheet();
    }
  });
}

function wireConversationPage() {
  refs.conversationForm?.addEventListener("submit", handleConversationSubmit);
  refs.conversationSidebar?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-manage-link]");
    if (!button) return;
    const conversationId = readQueryParam("conversation");
    const token = conversationId ? readConversationToken(conversationId) : "";
    if (!conversationId || !token) return;
    const manageLink = buildManageLink(conversationId, token);
    try {
      await navigator.clipboard.writeText(manageLink);
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = "Copy manage link";
      }, 1400);
    } catch (_error) {
      button.textContent = "Copy failed";
      window.setTimeout(() => {
        button.textContent = "Copy manage link";
      }, 1400);
    }
  });
}

function wireWikiPage() {
  refs.entitySearch?.addEventListener("input", () => {
    window.clearTimeout(state.entitySearchTimer);
    state.entitySearchTimer = window.setTimeout(() => {
      void loadEntityList(refs.entitySearch?.value || "");
    }, 220);
  });

  refs.entityList?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-entity-id]");
    if (!button) return;
    const entityId = button.getAttribute("data-entity-id") || "";
    if (!entityId) return;
    void selectEntity(entityId, true);
  });
}

function renderHome() {
  renderComplaintStream(Array.isArray(state.feed?.items) ? state.feed.items : []);
}

async function loadConversationPage() {
  const conversationId = readQueryParam("conversation");
  const queryToken = readQueryParam("token");
  if (conversationId && queryToken) {
    storeConversationToken(conversationId, queryToken);
    scrubConversationTokenFromUrl(conversationId);
  }

  if (!conversationId) {
    renderConversationUnavailable("No conversation link was provided.");
    return;
  }

  await fetchAndRenderConversation(conversationId);
}

async function loadWikiPage() {
  const query = readQueryParam("q");
  if (query && refs.entitySearch) {
    refs.entitySearch.value = query;
  }
  await loadEntityList(refs.entitySearch?.value || "");
}

async function loadMcpPage() {
  renderMcpPageLoading();
  if (!state.mcpBaseUrl) {
    renderMcpPageUnavailable("The MCP server endpoint is not configured yet.");
    return;
  }

  try {
    const [info, health] = await Promise.all([
      fetchAbsoluteJson(`${state.mcpBaseUrl}/info`),
      fetchAbsoluteJson(`${state.mcpBaseUrl}/healthz`),
    ]);
    state.mcpInfo = info;
    renderMcpPage(info, health);
  } catch (error) {
    renderMcpPageUnavailable(error.message || "The MCP server could not be reached.");
  }
}

async function fetchAndRenderConversation(conversationId) {
  renderConversationLoading();
  try {
    const conversation = await apiFetch(`/api/conversations/${encodeURIComponent(conversationId)}`, {
      headers: buildConversationHeaders(conversationId),
    });
    state.conversation = conversation;
    renderConversation(conversation);
  } catch (error) {
    renderConversationUnavailable(error.message || "Conversation unavailable.");
  }
}

async function loadEntityList(queryText = "") {
  renderEntityListLoading();
  try {
    const query = queryText.trim();
    const payload = await apiFetch(query ? `/api/entities?q=${encodeURIComponent(query)}` : "/api/entities");
    state.entities = Array.isArray(payload) ? payload : [];
    renderEntityList(state.entities);

    const requestedId = readQueryParam("entity");
    const firstId = requestedId || state.entities[0]?.id || "";
    if (firstId) {
      await selectEntity(firstId, false);
      return;
    }
    renderEntityInspectorEmpty();
  } catch (error) {
    renderEntityListError(error.message || "Could not load entities.");
  }
}

async function selectEntity(entityId, pushState) {
  state.selectedEntityId = entityId;
  renderEntityList(state.entities);
  if (pushState) {
    setQueryParam("entity", entityId);
  }

  try {
    const entity = await apiFetch(`/api/entities/${encodeURIComponent(entityId)}`);
    renderEntityInspector(entity);
  } catch (error) {
    renderEntityInspectorError(error.message || "Could not load entity.");
  }
}

async function handleComposerSubmit(event) {
  event.preventDefault();
  if (!refs.composerForm || state.homeSubmitting) return;

  if (!hasComposerContent(refs.composerForm, refs.composerText)) {
    renderInlineNotice(refs.composerAuthNote, "Type a message to start.");
    return;
  }

  state.homeSubmitting = true;
  setButtonBusy(refs.composerSubmit, true, "Posting...");
  renderInlineNotice(refs.composerAuthNote, "Posting your complaint publicly.");

  try {
    const post = await apiFetch("/api/posts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text: refs.composerText?.value || "",
      }),
    });
    refs.composerForm.reset();
    clearInlineNotice(refs.composerAuthNote);
    prependHomePost(post);
    closePostSheet();
  } catch (error) {
    renderInlineNotice(refs.composerAuthNote, error.message || "The complaint could not be posted.");
  } finally {
    state.homeSubmitting = false;
    setButtonBusy(refs.composerSubmit, false, "Post Complaint");
  }
}

async function handleConversationSubmit(event) {
  event.preventDefault();
  if (!refs.conversationForm || state.conversationSubmitting) return;

  const conversationId = readQueryParam("conversation");
  if (!conversationId) {
    renderInlineNotice(refs.conversationAuthNote, "Conversation id is missing.");
    return;
  }

  if (!hasComposerContent(refs.conversationForm, refs.conversationText)) {
    renderInlineNotice(refs.conversationAuthNote, "Type a follow-up before sending.");
    return;
  }

  state.conversationSubmitting = true;
  setButtonBusy(refs.conversationSubmit, true, "Sending...");
  renderInlineNotice(refs.conversationAuthNote, "Reading your follow-up, answering privately, and refreshing the public memory where needed.");

  try {
    const formData = new FormData(refs.conversationForm);
    const manageToken = readConversationToken(conversationId);
    if (manageToken) {
      formData.set("manageToken", manageToken);
    }

    const conversation = await apiFetch(`/api/conversations/${encodeURIComponent(conversationId)}/turns`, {
      method: "POST",
      body: formData,
    });
    if (conversation.manageToken) {
      storeConversationToken(conversation.id, conversation.manageToken);
    }
    refs.conversationForm.reset();
    clearInlineNotice(refs.conversationAuthNote);
    state.conversation = conversation;
    renderConversation(conversation);
  } catch (error) {
    renderInlineNotice(refs.conversationAuthNote, error.message || "The follow-up could not be processed.");
  } finally {
    state.conversationSubmitting = false;
    setButtonBusy(refs.conversationSubmit, false, "Send");
  }
}

function seedComposerExample() {
  setComposerPrompt(
    "People keep saying Claude Code is great for long coding sessions, but I keep hearing mixed things about reliability versus Cursor. What are people actually agreeing on, and what still seems disputed? https://www.anthropic.com/claude-code"
  );
}

function setComposerPrompt(prompt) {
  if (refs.composerText) {
    refs.composerText.value = String(prompt || "").trim();
  }
  refs.composerText?.focus();
}

function openPostSheet() {
  if (!refs.postSheet) return;
  refs.postSheet.hidden = false;
  document.body.classList.add("is-post-sheet-open");
  window.setTimeout(() => {
    refs.composerText?.focus();
  }, 40);
}

function closePostSheet() {
  if (!refs.postSheet) return;
  refs.postSheet.hidden = true;
  document.body.classList.remove("is-post-sheet-open");
  refs.postOpen?.focus();
}

function renderAuthSlot() {
  if (!refs.authSlot) return;

  const user = state.session?.authenticated ? state.session.user : null;
  if (user) {
    refs.authSlot.innerHTML = `
      <div class="auth-user">
        ${renderUserAvatar(user)}
        <div class="auth-user-copy">
          <strong>${escapeHtml(user.publicHandle || user.name || "Signed in")}</strong>
          <span>Authenticated</span>
        </div>
      </div>
    `;
    return;
  }

  const label = state.config?.authEnabled
    ? "Anonymous posting live. Accounts remain optional."
    : "Anonymous posting live.";
  refs.authSlot.innerHTML = `<div class="auth-status-pill">${escapeHtml(label)}</div>`;
}

function renderAuthNotes() {
  const note = "Anonymous. Public. Text only. Vent freely.";
  renderInlineNotice(refs.composerAuthNote, note, true);
  renderInlineNotice(refs.conversationAuthNote, note, true);
}

function renderSignalStrip(items) {
  if (!refs.signalStrip) return;
  const topItems = items.slice(0, 3);
  if (!topItems.length) {
    refs.signalStrip.innerHTML = `
      <article class="signal-strip-card">
        <span class="panel-kicker">People Are Saying</span>
        <p>The site is ready for the next AI question, complaint, or useful link.</p>
      </article>
    `;
    return;
  }

  refs.signalStrip.innerHTML = topItems
    .map(
      (item) => `
        <article class="signal-strip-card">
          <span class="panel-kicker">${escapeHtml(formatKind(item.kind))}</span>
          <p>${escapeHtml(item.title || item.summary || "Fresh signal")}</p>
        </article>
      `
    )
    .join("");
}

function renderHomeFeed(items) {
  if (!refs.homeFeed) return;
  if (!items.length) {
    refs.homeFeed.innerHTML = renderStateCard("No public takeaways yet", "The first good submission will start shaping what the site summarizes publicly.");
    return;
  }
  refs.homeFeed.innerHTML = items.map(renderFeedCard).join("");
}

function renderFeaturedEntities(entities) {
  if (!refs.homeEntityList) return;
  if (!entities.length) {
    refs.homeEntityList.innerHTML = renderStateCard("No tracked topics yet", "Topics will appear here as people keep bringing up the same tools, models, and workflows.");
    return;
  }
  refs.homeEntityList.innerHTML = entities.map(renderFeaturedEntityCard).join("");
}

function renderArtifactGrid(target, items, emptyTitle, emptyBody, renderItem) {
  if (!target) return;
  if (!items.length) {
    target.innerHTML = renderStateCard(emptyTitle, emptyBody);
    return;
  }
  target.innerHTML = items.map(renderItem).join("");
}

function renderComplaintStream(items) {
  if (!refs.homeFeed) return;
  if (!items.length) {
    refs.homeFeed.innerHTML = renderStateCard("No complaints yet", "Nothing has been posted yet. Be the first to vent about AI.");
    return;
  }
  refs.homeFeed.innerHTML = items.map(renderComplaintCard).join("");
}

function renderComplaintCard(item) {
  const meta = [
    item.anonymousHandle || "anon-user",
    item.createdAt ? formatDate(item.createdAt) : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return `
    <article class="complaint-card">
      <div class="complaint-meta">${escapeHtml(meta)}</div>
      <p class="complaint-body">${escapeHtml(item.text || item.summary || "")}</p>
    </article>
  `;
}

function prependHomePost(post) {
  const existing = Array.isArray(state.feed?.items) ? state.feed.items : [];
  state.feed = {
    ...(state.feed || {}),
    items: [post, ...existing].slice(0, 48),
  };
  renderHome();
}

function buildHomeCollections(feed) {
  const items = Array.isArray(feed?.items) ? feed.items : [];
  const featuredEntities = Array.isArray(feed?.featuredEntities) ? feed.featuredEntities : [];
  const seeing = items.filter((item) => item.kind === "cluster" || item.kind === "claim");
  const guides = items.filter((item) => item.kind === "guide");
  const questions = items.filter((item) => item.kind === "question");
  const entities = featuredEntities.length ? featuredEntities : items.filter((item) => item.kind === "entity");

  return {
    noticing: seeing.slice(0, 6),
    topics: entities.slice(0, 6),
    guides: guides.slice(0, 4),
    questions: questions.slice(0, 4),
  };
}

function renderFeedCard(item) {
  const href = item.entityId ? `./wiki.html?entity=${encodeURIComponent(item.entityId)}` : "";
  const summary = String(item.summary || "").trim();
  const compactContext = summary && summary.length <= 56 && summary !== item.title;
  const meta = [
    item.supportCount ? `${item.supportCount} signal${item.supportCount === 1 ? "" : "s"}` : "",
    item.updatedAt ? formatDate(item.updatedAt) : "",
  ]
    .filter(Boolean)
    .join(" · ");

  const body = `
    <span class="panel-kicker">${escapeHtml(formatKind(item.kind))}</span>
    <h3 class="ticket-title">${escapeHtml(item.title || "Untitled signal")}</h3>
    ${compactContext ? `<p class="feed-card-context">${escapeHtml(summary)}</p>` : ""}
    ${summary && !compactContext ? `<p class="feed-card-summary">${escapeHtml(summary)}</p>` : '<p class="feed-card-summary">Fresh public memory pulled from recent submissions and sources.</p>'}
    ${meta ? `<div class="feed-card-meta">${escapeHtml(meta)}</div>` : ""}
  `;

  if (href) {
    return `<a class="preview-card feed-card" href="${href}">${body}</a>`;
  }
  return `<article class="preview-card feed-card">${body}</article>`;
}

function renderFeaturedEntityCard(entity) {
  const stats = entityStats(entity);
  return `
    <a class="preview-card entity-card" href="./wiki.html?entity=${encodeURIComponent(entity.entityId || entity.id)}">
      <span class="panel-kicker">Topic Page</span>
      <h3 class="ticket-title">${escapeHtml(entity.title || entity.canonicalName || "Unnamed entity")}</h3>
      <p>${escapeHtml(entity.summary || "Freshly tracked topic")}</p>
      <div class="ticket-meta">
        <span class="meta-pill">${stats.sourceCount} sources</span>
        <span class="meta-pill">${stats.claimCount} claims</span>
        <span class="meta-pill">${stats.guideCount} guides</span>
      </div>
    </a>
  `;
}

function renderConversationLoading() {
  if (refs.conversationThread) {
    refs.conversationThread.innerHTML = renderStateCard("Loading your thread", "Pulling the private conversation and the latest AI answer.");
  }
  if (refs.conversationSidebar) {
    refs.conversationSidebar.innerHTML = renderSidebarStack([
      renderSidebarBlock("Status", `<p>Conversation state is loading.</p>`),
    ]);
  }
}

function renderConversationUnavailable(message) {
  if (refs.conversationTitle) {
    refs.conversationTitle.textContent = "Conversation unavailable";
  }
  if (refs.conversationMeta) {
    refs.conversationMeta.textContent = message;
  }
  if (refs.conversationThread) {
    refs.conversationThread.innerHTML = renderStateCard("Conversation unavailable", message);
  }
  if (refs.conversationSidebar) {
    refs.conversationSidebar.innerHTML = renderSidebarStack([
      renderSidebarBlock(
        "Access",
        `<p>${escapeHtml(message)}</p><p>Start on the home page to open a new thread, or use the private manage link for an existing one.</p>`
      ),
    ]);
  }
}

function renderConversation(conversation) {
  if (refs.conversationTitle) {
    refs.conversationTitle.textContent = conversation.title || "Your private thread";
  }
  if (refs.conversationMeta) {
    const parts = [
      "Private thread",
      conversation.anonymousHandle ? `started by ${conversation.anonymousHandle}` : "",
      conversation.updatedAt ? `updated ${formatDate(conversation.updatedAt)}` : "",
    ].filter(Boolean);
    refs.conversationMeta.textContent = parts.join(" · ");
  }
  if (refs.conversationThread) {
    refs.conversationThread.innerHTML = (conversation.messages || []).length
      ? conversation.messages.map(renderMessageCard).join("")
      : renderStateCard("No messages yet", "The thread exists, but no messages were returned.");
  }
  if (refs.conversationSidebar) {
    refs.conversationSidebar.innerHTML = renderConversationSidebar(conversation);
  }
}

function renderMessageCard(message) {
  const roleLabel = message.role === "assistant" ? "AI Answer" : "You";
  const meta = [formatDate(message.createdAt), roleLabel].filter(Boolean).join(" · ");
  const citations = Array.isArray(message.citations) && message.citations.length
    ? `
      <div class="message-section">
        <span class="panel-kicker">Grounding</span>
        <div class="citation-list">
          ${message.citations.map(renderCitation).join("")}
        </div>
      </div>
    `
    : "";
  const graphUpdates = Array.isArray(message.graphUpdates) && message.graphUpdates.length
    ? `
      <div class="message-section">
        <span class="panel-kicker">Public Memory</span>
        <div class="message-chip-list">
          ${message.graphUpdates.map(renderGraphUpdateChip).join("")}
        </div>
      </div>
    `
    : "";

  return `
    <article class="message-card ${message.role === "assistant" ? "is-assistant" : "is-user"}">
      <div class="message-topline">
        <span class="panel-kicker">${escapeHtml(roleLabel)}</span>
        <span class="message-meta">${escapeHtml(meta)}</span>
      </div>
      <div class="message-body">${renderRichText(message.text || "")}</div>
      ${citations}
      ${graphUpdates}
    </article>
  `;
}

function renderConversationSidebar(conversation) {
  const latestAssistant = [...(conversation.messages || [])]
    .reverse()
    .find((message) => message.role === "assistant");
  const manageToken = readConversationToken(conversation.id);
  const blocks = [
    renderSidebarBlock(
      "Thread",
      `
        <p>${escapeHtml(conversation.title || "Your private thread")}</p>
        <div class="sidebar-list">
          <span class="meta-pill">Created ${escapeHtml(formatDate(conversation.createdAt))}</span>
          <span class="meta-pill">Updated ${escapeHtml(formatDate(conversation.updatedAt))}</span>
          ${conversation.anonymousHandle ? `<span class="meta-pill">${escapeHtml(conversation.anonymousHandle)}</span>` : ""}
        </div>
      `
    ),
  ];

  if (manageToken) {
    blocks.push(
      renderSidebarBlock(
        "Manage Link",
        `
          <p>Use this private link to reopen the conversation anonymously from another device.</p>
          <div class="sidebar-action-row">
            <button class="button ghost" type="button" data-copy-manage-link>Copy manage link</button>
          </div>
        `
      )
    );
  }

  if (latestAssistant?.graphUpdates?.length) {
    blocks.push(
      renderSidebarBlock(
        "Public Memory Changes",
        `<div class="sidebar-list">${latestAssistant.graphUpdates.map(renderGraphUpdateChip).join("")}</div>`
      )
    );
  }

  if (latestAssistant?.citations?.length) {
    blocks.push(
      renderSidebarBlock(
        "Why It Answered That",
        `<div class="citation-list">${latestAssistant.citations.map(renderCitation).join("")}</div>`
      )
    );
  }

  if (!latestAssistant) {
    blocks.push(
      renderSidebarBlock(
        "Answer Details",
        `<p>The AI has not replied yet. Once it does, the supporting sources and any public memory changes will appear here.</p>`
      )
    );
  }

  return renderSidebarStack(blocks);
}

function renderEntityListLoading() {
  if (!refs.entityList) return;
  refs.entityList.innerHTML = renderStateCard("Loading topics", "Reading the latest public memory for tools, models, and workflows.");
}

function renderEntityListError(message) {
  if (refs.entityList) {
    refs.entityList.innerHTML = renderStateCard("Topics unavailable", message);
  }
  renderEntityInspectorError(message);
}

function renderEntityList(entities) {
  if (!refs.entityList) return;
  if (!entities.length) {
    refs.entityList.innerHTML = renderStateCard("No topics found", "Try a broader search or add new source material from the home composer.");
    return;
  }

  refs.entityList.innerHTML = entities
    .map((entity) => {
      const stats = entityStats(entity);
      const selectedClass = entity.id === state.selectedEntityId ? " is-selected" : "";
      return `
        <button class="ticket-card${selectedClass}" type="button" data-entity-id="${escapeHtml(entity.id)}">
          <div class="ticket-topline">
            <span class="panel-kicker">${escapeHtml(entity.entityType || "topic")}</span>
            ${entity.vendor ? `<span class="meta-pill">${escapeHtml(entity.vendor)}</span>` : ""}
          </div>
          <h3 class="ticket-title">${escapeHtml(entity.canonicalName || "Unnamed topic")}</h3>
          <p>${escapeHtml(entity.summary || entity.description || "No summary yet.")}</p>
          <div class="ticket-card-footer">
            <div class="ticket-meta">
              <span class="meta-pill">${stats.sourceCount} sources</span>
              <span class="meta-pill">${stats.claimCount} claims</span>
              <span class="meta-pill">${stats.guideCount} guides</span>
              <span class="meta-pill">${stats.questionCount} questions</span>
            </div>
          </div>
        </button>
      `;
    })
    .join("");
}

function renderEntityInspectorEmpty() {
  if (!refs.entityInspector) return;
  refs.entityInspector.innerHTML = `
    <div class="empty-state">
      <h3>Select a topic</h3>
      <p>Open any topic to see what the public memory currently says, what guides exist, and where questions remain open.</p>
    </div>
  `;
}

function renderEntityInspectorError(message) {
  if (!refs.entityInspector) return;
  refs.entityInspector.innerHTML = renderStateCard("Topic unavailable", message);
}

function renderEntityInspector(entity) {
  if (!refs.entityInspector) return;
  const stats = entityStats(entity);
  refs.entityInspector.innerHTML = `
    <div class="inspector-body">
      <div class="inspector-block">
        <span class="panel-kicker">${escapeHtml(entity.entityType || "topic")}</span>
        <h3>${escapeHtml(entity.canonicalName || "Unnamed topic")}</h3>
        <p>${escapeHtml(entity.summary || entity.description || "No description yet.")}</p>
        <div class="inspector-meta">
          ${entity.vendor ? `<span class="inspector-chip">${escapeHtml(entity.vendor)}</span>` : ""}
          <span class="inspector-chip">${stats.sourceCount} sources</span>
          <span class="inspector-chip">${stats.claimCount} claims</span>
          <span class="inspector-chip">${stats.guideCount} guides</span>
          <span class="inspector-chip">${stats.questionCount} questions</span>
        </div>
        <div class="link-list">
          ${renderEntityLink(entity.sourceLinks?.officialUrl, "Official site")}
          ${renderEntityLink(entity.sourceLinks?.webSearchUrl, "Web search")}
          ${renderEntityLink(entity.sourceLinks?.redditSearchUrl, "Reddit search")}
        </div>
      </div>

      ${renderChipSection("Good For", entity.goodFor)}
      ${renderChipSection("Bad At", entity.badAt)}
      ${renderChipSection("Used For", entity.usedFor)}
      ${renderClaimSection("Claims", entity.claims || [])}
      ${renderGuideSection("Guides", entity.guides || [])}
      ${renderQuestionSection("Questions", entity.questions || [])}
      ${renderRelatedEntitiesSection(entity.relatedEntities || [])}
    </div>
  `;
}

function renderChipSection(title, items) {
  if (!items || !items.length) return "";
  return `
    <div class="inspector-block">
      <h4>${escapeHtml(title)}</h4>
      <div class="chip-list">
        ${items.map((item) => `<span class="list-chip">${escapeHtml(item)}</span>`).join("")}
      </div>
    </div>
  `;
}

function renderClaimSection(title, claims) {
  if (!claims.length) return "";
  return `
    <div class="inspector-block">
      <h4>${escapeHtml(title)}</h4>
      <div class="entity-section-list">
        ${claims
          .map(
            (claim) => `
              <article class="entity-section-card">
                <div class="ticket-meta">
                  <span class="meta-pill">${escapeHtml(formatClaimType(claim.claimType))}</span>
                  <span class="meta-pill">${claim.supportCount || 0} signal${claim.supportCount === 1 ? "" : "s"}</span>
                  ${claim.stance ? `<span class="meta-pill">${escapeHtml(claim.stance)}</span>` : ""}
                </div>
                <p>${escapeHtml(claim.claimText || "")}</p>
              </article>
            `
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderGuideSection(title, guides) {
  if (!guides.length) return "";
  return `
    <div class="inspector-block">
      <h4>${escapeHtml(title)}</h4>
      <div class="entity-section-list">
        ${guides
          .map(
            (guide) => `
              <article class="entity-section-card">
                <strong>${escapeHtml(guide.title || "Untitled guide")}</strong>
                <p>${escapeHtml(guide.summary || "")}</p>
                ${guide.steps?.length ? `<div class="chip-list">${guide.steps.map((step) => `<span class="list-chip">${escapeHtml(step)}</span>`).join("")}</div>` : ""}
              </article>
            `
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderQuestionSection(title, questions) {
  if (!questions.length) return "";
  return `
    <div class="inspector-block">
      <h4>${escapeHtml(title)}</h4>
      <div class="entity-section-list">
        ${questions
          .map(
            (question) => `
              <article class="entity-section-card">
                <div class="ticket-meta">
                  <span class="meta-pill">${escapeHtml(question.status || "open")}</span>
                  <span class="meta-pill">${question.sourceIds?.length || 0} source${question.sourceIds?.length === 1 ? "" : "s"}</span>
                </div>
                <p>${escapeHtml(question.questionText || "")}</p>
              </article>
            `
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderRelatedEntitiesSection(entities) {
  if (!entities.length) return "";
  return `
    <div class="inspector-block">
      <h4>Related Entities</h4>
      <div class="entity-section-list">
        ${entities
          .map(
            (entity) => `
              <a class="entity-ticket-button" href="./wiki.html?entity=${encodeURIComponent(entity.id)}">
                <strong>${escapeHtml(entity.canonicalName || "Unnamed entity")}</strong>
                <span>${escapeHtml(entity.summary || entity.description || "")}</span>
              </a>
            `
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderCitation(citation) {
  const label = citation.label || citation.url || "Untitled source";
  const summary = citation.summary ? `<span>${escapeHtml(citation.summary)}</span>` : "";
  if (citation.url) {
    return `
      <a class="citation-card" href="${escapeHtml(citation.url)}" target="_blank" rel="noreferrer">
        <strong>${escapeHtml(label)}</strong>
        ${summary}
      </a>
    `;
  }
  return `
    <div class="citation-card">
      <strong>${escapeHtml(label)}</strong>
      ${summary}
    </div>
  `;
}

function renderGraphUpdateChip(update) {
  return `
    <div class="message-chip">
      <strong>${escapeHtml(formatKind(update.kind || "signal"))}</strong>
      <span>${escapeHtml(update.title || update.summary || "Updated")}</span>
    </div>
  `;
}

function renderSidebarStack(blocks) {
  return `<div class="sidebar-stack">${blocks.join("")}</div>`;
}

function renderSidebarBlock(title, body) {
  return `
    <section class="sidebar-block">
      <span class="panel-kicker">${escapeHtml(title)}</span>
      ${body}
    </section>
  `;
}

function renderEntityLink(url, label) {
  if (!url) return "";
  return `<a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
}

function renderInlineNotice(target, message, isPassive = false) {
  if (!target) return;
  target.innerHTML = `
    <div class="auth-note-card${isPassive ? "" : " is-attention"}">
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

function clearInlineNotice(target) {
  if (!target) return;
  target.innerHTML = "";
}

function renderStateCard(title, body) {
  return `
    <article class="ticket-card state-card">
      <span class="panel-kicker">Status</span>
      <h3 class="ticket-title">${escapeHtml(title)}</h3>
      <p>${escapeHtml(body)}</p>
    </article>
  `;
}

function renderMcpPageLoading() {
  if (refs.mcpStatus) {
    refs.mcpStatus.textContent = "Checking";
  }
  if (refs.mcpTransport) {
    refs.mcpTransport.textContent = "streamable-http";
  }
  if (refs.mcpEndpoint) {
    refs.mcpEndpoint.textContent = state.mcpBaseUrl ? `${state.mcpBaseUrl}/mcp` : "Not configured";
  }
  if (refs.mcpOpenEndpoint) {
    refs.mcpOpenEndpoint.href = state.mcpBaseUrl ? `${state.mcpBaseUrl}/mcp` : "#";
  }
  if (refs.mcpReadTools) {
    refs.mcpReadTools.innerHTML = renderStateCard("Loading tools", "Reading the live MCP tool catalog.");
  }
  if (refs.mcpWriteTools) {
    refs.mcpWriteTools.innerHTML = renderStateCard("Loading access", "Checking which write flows are exposed to agents.");
  }
  if (refs.mcpResources) {
    refs.mcpResources.innerHTML = renderStateCard("Loading resources", "Looking up the published MCP resources.");
  }
  if (refs.mcpCommand) {
    refs.mcpCommand.textContent = state.mcpBaseUrl
      ? `claude mcp add --transport http stop-the-slop ${state.mcpBaseUrl}/mcp`
      : "Endpoint not configured";
  }
  if (refs.mcpInspectorCommand) {
    refs.mcpInspectorCommand.textContent = "npx -y @modelcontextprotocol/inspector";
  }
}

function renderMcpPageUnavailable(message) {
  if (refs.mcpStatus) {
    refs.mcpStatus.textContent = "Unavailable";
  }
  if (refs.mcpOpenEndpoint) {
    refs.mcpOpenEndpoint.href = "#";
  }
  const card = renderStateCard("MCP server unavailable", message);
  if (refs.mcpReadTools) {
    refs.mcpReadTools.innerHTML = card;
  }
  if (refs.mcpWriteTools) {
    refs.mcpWriteTools.innerHTML = card;
  }
  if (refs.mcpResources) {
    refs.mcpResources.innerHTML = card;
  }
}

function renderMcpPage(info, health) {
  const endpoint = info?.mcpEndpoint || (state.mcpBaseUrl ? `${state.mcpBaseUrl}/mcp` : "");
  if (refs.mcpStatus) {
    refs.mcpStatus.textContent = health?.ok ? "Live" : "Degraded";
  }
  if (refs.mcpTransport) {
    refs.mcpTransport.textContent = info?.transport || "streamable-http";
  }
  if (refs.mcpEndpoint) {
    refs.mcpEndpoint.textContent = endpoint || "Unavailable";
  }
  if (refs.mcpOpenEndpoint) {
    refs.mcpOpenEndpoint.href = endpoint || "#";
  }
  if (refs.mcpCommand) {
    refs.mcpCommand.textContent = endpoint
      ? `claude mcp add --transport http stop-the-slop ${endpoint}`
      : "Endpoint unavailable";
  }
  if (refs.mcpInspectorCommand) {
    refs.mcpInspectorCommand.textContent = endpoint
      ? `Connect the inspector to ${endpoint}`
      : "Endpoint unavailable";
  }

  const tools = Array.isArray(info?.toolCatalog) ? info.toolCatalog : [];
  if (refs.mcpReadTools) {
    refs.mcpReadTools.innerHTML = renderMcpToolCards(tools.filter((tool) => String(tool.access || "").startsWith("read")));
  }
  if (refs.mcpWriteTools) {
    refs.mcpWriteTools.innerHTML = renderMcpToolCards(tools.filter((tool) => !String(tool.access || "").startsWith("read")));
  }
  if (refs.mcpResources) {
    refs.mcpResources.innerHTML = renderMcpResourceCards(Array.isArray(info?.resourceCatalog) ? info.resourceCatalog : []);
  }
}

function renderMcpToolCards(items) {
  if (!items.length) {
    return renderStateCard("No tools published", "The server is up, but it did not return any tool metadata.");
  }
  return items
    .map(
      (item) => `
        <article class="mcp-tool-card">
          <div class="ticket-topline">
            <strong>${escapeHtml(item.name || "Unnamed tool")}</strong>
            <span class="meta-pill">${escapeHtml(item.access || "read")}</span>
          </div>
          <p>${escapeHtml(item.description || "No description provided.")}</p>
        </article>
      `
    )
    .join("");
}

function renderMcpResourceCards(items) {
  if (!items.length) {
    return renderStateCard("No resources published", "This MCP server is currently tool-first.");
  }
  return items
    .map(
      (item) => `
        <article class="mcp-tool-card">
          <strong>${escapeHtml(item.uri || "Unnamed resource")}</strong>
          <p>${escapeHtml(item.description || "No description provided.")}</p>
        </article>
      `
    )
    .join("");
}

function syncMetrics(metrics) {
  if (!metrics) return;
  if (refs.metricTotal) {
    refs.metricTotal.textContent = formatNumber(metrics.sourceCount || 0);
  }
  if (refs.metricTools) {
    refs.metricTools.textContent = formatNumber(metrics.entityCount || 0);
  }
  if (refs.metricModalities) {
    refs.metricModalities.textContent = formatNumber(metrics.claimCount || 0);
  }
}

async function fetchConfigSafe() {
  try {
    return await apiFetch("/api/config");
  } catch (_error) {
    return {
      aiConfigured: false,
      authEnabled: false,
      anonymousPosting: true,
      acceptedUploads: [],
    };
  }
}

async function fetchSessionSafe() {
  try {
    return await apiFetch("/api/auth/session");
  } catch (_error) {
    return { authenticated: false, authEnabled: false, user: null };
  }
}

async function fetchFeedSafe() {
  try {
    return await apiFetch("/api/feed");
  } catch (_error) {
    return { metrics: null, items: [], featuredEntities: [] };
  }
}

async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const sessionToken = readStoredSessionToken();
  if (sessionToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${sessionToken}`);
  }

  const response = await fetch(`${state.apiBaseUrl}${path}`, {
    ...options,
    headers,
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const detail = payload?.detail || `Request failed with ${response.status}`;
    throw new Error(detail);
  }
  return payload;
}

async function fetchAbsoluteJson(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const detail = payload?.detail || `Request failed with ${response.status}`;
    throw new Error(detail);
  }
  return payload;
}

function buildConversationHeaders(conversationId) {
  const headers = {};
  const manageToken = readConversationToken(conversationId);
  if (manageToken) {
    headers["X-Conversation-Token"] = manageToken;
  }
  return headers;
}

function readApiBaseUrl() {
  if (typeof window.STS_API_BASE === "string" && window.STS_API_BASE.trim()) {
    return window.STS_API_BASE.trim().replace(/\/$/, "");
  }
  return DEFAULT_API_BASE_URL;
}

function readMcpBaseUrl() {
  if (typeof window.STS_MCP_BASE === "string" && window.STS_MCP_BASE.trim()) {
    return window.STS_MCP_BASE.trim().replace(/\/$/, "");
  }
  return DEFAULT_MCP_BASE_URL;
}

function readStoredSessionToken() {
  try {
    return window.localStorage.getItem(SESSION_STORAGE_KEY) || "";
  } catch (_error) {
    return "";
  }
}

function readConversationTokens() {
  try {
    return JSON.parse(window.localStorage.getItem(CONVERSATION_TOKEN_STORAGE_KEY) || "{}");
  } catch (_error) {
    return {};
  }
}

function readConversationToken(conversationId) {
  if (!conversationId) return "";
  const tokens = readConversationTokens();
  return typeof tokens[conversationId] === "string" ? tokens[conversationId] : "";
}

function storeConversationToken(conversationId, token) {
  if (!conversationId || !token) return;
  const tokens = readConversationTokens();
  tokens[conversationId] = token;
  try {
    window.localStorage.setItem(CONVERSATION_TOKEN_STORAGE_KEY, JSON.stringify(tokens));
  } catch (_error) {
    // Ignore local storage failures and rely on query token fallback.
  }
}

function scrubConversationTokenFromUrl(conversationId) {
  const url = new URL(window.location.href);
  url.searchParams.set("conversation", conversationId);
  url.searchParams.delete("token");
  window.history.replaceState({}, "", url.toString());
}

function buildConversationHref(conversationId, token = "") {
  const url = new URL("./board.html", window.location.href);
  url.searchParams.set("conversation", conversationId);
  if (token) {
    url.searchParams.set("token", token);
  }
  return url.toString();
}

function buildManageLink(conversationId, token) {
  const url = new URL("./board.html", window.location.href);
  url.searchParams.set("conversation", conversationId);
  url.searchParams.set("token", token);
  return url.toString();
}

function readQueryParam(name) {
  return new URL(window.location.href).searchParams.get(name) || "";
}

function setQueryParam(name, value) {
  const url = new URL(window.location.href);
  if (value) {
    url.searchParams.set(name, value);
  } else {
    url.searchParams.delete(name);
  }
  window.history.replaceState({}, "", url.toString());
}

function hasComposerContent(form, textField) {
  if (!form) return false;
  const text = textField?.value?.trim() || "";
  return Boolean(text);
}

function setButtonBusy(button, isBusy, label) {
  if (!button) return;
  button.disabled = isBusy;
  button.textContent = label;
}

function entityStats(entity) {
  const stats = entity.stats || {};
  if ("sourceCount" in stats || "claimCount" in stats) {
    return {
      sourceCount: Number(stats.sourceCount || 0),
      claimCount: Number(stats.claimCount || 0),
      guideCount: Number(stats.guideCount || 0),
      questionCount: Number(stats.questionCount || 0),
    };
  }
  return {
    sourceCount: Number(entity.supportCount || 0),
    claimCount: Number(entity.claimCount || 0),
    guideCount: Number(entity.guideCount || 0),
    questionCount: Number(entity.questionCount || 0),
  };
}

function formatKind(kind) {
  switch (kind) {
    case "post":
      return "Complaint";
    case "claim":
      return "Takeaway";
    case "guide":
      return "Guide";
    case "question":
      return "Question";
    case "cluster":
      return "Hot Topic";
    case "entity":
      return "Topic Page";
    case "source":
      return "Source";
    case "graph":
      return "Site Memory";
    case "web":
      return "Web";
    default:
      return "Signal";
  }
}

function formatClaimType(type) {
  return String(type || "observation")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(Number(value || 0));
}

function renderRichText(value) {
  return escapeHtml(value)
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br />")
    .replace(/^/, "<p>")
    .replace(/$/, "</p>");
}

function renderUserAvatar(user) {
  if (user.pictureUrl) {
    return `<img class="auth-avatar" src="${escapeHtml(user.pictureUrl)}" alt="${escapeHtml(user.publicHandle || "User")}" />`;
  }
  const fallback = initials(user.publicHandle || user.name || "AI");
  return `<span class="auth-avatar auth-avatar-fallback">${escapeHtml(fallback)}</span>`;
}

function initials(value) {
  return String(value || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("") || "AI";
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
