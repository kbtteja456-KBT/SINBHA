// ========================================================
// SINBHA - Client Script (Conversational Memory & Tasks Gate)
// ========================================================

document.addEventListener("DOMContentLoaded", () => {
  // Dynamic Viewport & Keyboard Adaptation (Mobile & Capacitor)
  function syncViewportMetrics() {
    const vv = window.visualViewport;
    const viewportHeight = vv ? vv.height : window.innerHeight;
    const keyboardHeight = Math.max(0, window.innerHeight - viewportHeight);
    document.documentElement.style.setProperty("--app-viewport-height", `${viewportHeight}px`);
    document.documentElement.style.setProperty("--keyboard-height", `${keyboardHeight}px`);
  }

  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", syncViewportMetrics);
    window.visualViewport.addEventListener("scroll", syncViewportMetrics);
  }
  window.addEventListener("resize", syncViewportMetrics);
  window.addEventListener("orientationchange", () => setTimeout(syncViewportMetrics, 150));
  syncViewportMetrics();

  document.addEventListener("focusin", (e) => {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA")) {
      const parentModal = e.target.closest(".settings-modal-card, .confirm-modal-card, .side-drawer");
      if (parentModal) {
        setTimeout(() => {
          e.target.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }, 220);
      }
    }
  });

  const messageInput = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");
  const chatMessages = document.getElementById("chatMessages");
  const scrollAnchor = document.getElementById("scrollAnchor");

  // Header controls
  const tasksBtn = document.getElementById("tasksBtn");
  const taskCountBadge = document.getElementById("taskCountBadge");
  const stopBtn = document.getElementById("stopBtn");
  const stopBanner = document.getElementById("stopBanner");
  const bannerResumeBtn = document.getElementById("bannerResumeBtn");
  const statusDot = document.getElementById("statusDot");

  // Developer mode elements
  const devMemoryBtn = document.getElementById("devMemoryBtn");
  const devFactBadge = document.getElementById("devFactBadge");
  const devFactsCountLabel = document.getElementById("devFactsCountLabel");
  const devMemoryDrawer = document.getElementById("devMemoryDrawer");
  const closeDevMemoryBtn = document.getElementById("closeDevMemoryBtn");
  const devRefreshBtn = document.getElementById("devRefreshBtn");
  const devFactsList = document.getElementById("devFactsList");
  const devAuditLogList = document.getElementById("devAuditLogList");

  // Tasks Drawer elements (Step 6)
  const taskDrawer = document.getElementById("taskDrawer");
  const closeTaskBtn = document.getElementById("closeTaskBtn");
  const drawerOverlay = document.getElementById("drawerOverlay");
  const emptyTaskState = document.getElementById("emptyTaskState");
  const taskListContainer = document.getElementById("taskListContainer");
  const pendingTaskList = document.getElementById("pendingTaskList");
  const pendingCountBadgeDrawer = document.getElementById("pendingCountBadgeDrawer");
  const completedTasksAccordion = document.getElementById("completedTasksAccordion");
  const completedTaskList = document.getElementById("completedTaskList");
  const completedCountBadge = document.getElementById("completedCountBadge");

  // Task Delete Modal elements (Step 6)
  const taskDeleteModal = document.getElementById("taskDeleteModal");
  const taskDeleteModalMessage = document.getElementById("taskDeleteModalMessage");
  const cancelTaskDeleteBtn = document.getElementById("cancelTaskDeleteBtn");
  const confirmTaskDeleteBtn = document.getElementById("confirmTaskDeleteBtn");
  let taskToDeleteId = null;

  // Settings & Purge elements
  const openSettingsBtn = document.getElementById("openSettingsBtn");
  const settingsModal = document.getElementById("settingsModal");
  const closeSettingsBtn = document.getElementById("closeSettingsBtn");
  const openPurgeConfirmBtn = document.getElementById("openPurgeConfirmBtn");
  const purgeConfirmModal = document.getElementById("purgeConfirmModal");
  const cancelPurgeBtn = document.getElementById("cancelPurgeBtn");
  const confirmPurgeBtn = document.getElementById("confirmPurgeBtn");

  // Private Inbox elements (Step D2)
  const inboxBtn = document.getElementById("inboxBtn");
  const inboxModal = document.getElementById("inboxModal");
  const closeInboxBtn = document.getElementById("closeInboxBtn");
  const refreshInboxBtn = document.getElementById("refreshInboxBtn");
  const clearInboxBtn = document.getElementById("clearInboxBtn");
  const inboxList = document.getElementById("inboxList");
  const inboxCountBadge = document.getElementById("inboxCountBadge");

  // Bird Reminder & Settings elements (Step 6B)
  const birdReminderContainer = document.getElementById("birdReminderContainer");
  const birdFlightWrapper = document.getElementById("birdFlightWrapper");
  const birdActor = document.getElementById("birdActor");
  const birdNoteTitle = document.getElementById("birdNoteTitle");
  const birdNoteDue = document.getElementById("birdNoteDue");
  const birdActionPopup = document.getElementById("birdActionPopup");
  const birdClosePopupBtn = document.getElementById("birdClosePopupBtn");
  const birdPopupTaskTitle = document.getElementById("birdPopupTaskTitle");
  const birdPopupTaskDue = document.getElementById("birdPopupTaskDue");
  const birdDoneBtn = document.getElementById("birdDoneBtn");
  const birdSnoozeDropdownBtn = document.getElementById("birdSnoozeDropdownBtn");
  const birdSnoozeMenu = document.getElementById("birdSnoozeMenu");
  const birdSnoozeMinsInput = document.getElementById("birdSnoozeMinsInput");
  const birdSnoozeSubmitBtn = document.getElementById("birdSnoozeSubmitBtn");
  const birdChatBtn = document.getElementById("birdChatBtn");

  const persistenceSelect = document.getElementById("persistenceSelect");
  const aiProviderSelect = document.getElementById("aiProviderSelect");
  const countrySelect = document.getElementById("countrySelect");
  const timezoneSelect = document.getElementById("timezoneSelect");
  const quietHoursToggle = document.getElementById("quietHoursToggle");
  const quietTimePickerRow = document.getElementById("quietTimePickerRow");
  const quietStartInput = document.getElementById("quietStartInput");
  const quietEndInput = document.getElementById("quietEndInput");
  const dndToggle = document.getElementById("dndToggle");
  const startWithWindowsToggle = document.getElementById("startWithWindowsToggle");
  const webSearchToggle = document.getElementById("webSearchToggle");

  // Step 9 Auth Elements
  const authScreen = document.getElementById("authScreen");
  const appContainer = document.getElementById("appContainer");
  const tabLoginBtn = document.getElementById("tabLoginBtn");
  const tabSignupBtn = document.getElementById("tabSignupBtn");
  const authAlert = document.getElementById("authAlert");
  const loginForm = document.getElementById("loginForm");
  const signupForm = document.getElementById("signupForm");
  const loginEmail = document.getElementById("loginEmail");
  const loginPassword = document.getElementById("loginPassword");
  const signupEmail = document.getElementById("signupEmail");
  const signupPassword = document.getElementById("signupPassword");
  const signupAgeCheck = document.getElementById("signupAgeCheck");
  const signupTermsCheck = document.getElementById("signupTermsCheck");
  const userHeaderPill = document.getElementById("userHeaderPill");
  const headerUserEmail = document.getElementById("headerUserEmail");
  const headerLogoutBtn = document.getElementById("headerLogoutBtn");

  // Terms & Privacy Modals
  const openTermsLink = document.getElementById("openTermsLink");
  const openPrivacyLink = document.getElementById("openPrivacyLink");
  const termsModal = document.getElementById("termsModal");
  const closeTermsBtn = document.getElementById("closeTermsBtn");
  const confirmTermsCloseBtn = document.getElementById("confirmTermsCloseBtn");
  const privacyModal = document.getElementById("privacyModal");
  const closePrivacyBtn = document.getElementById("closePrivacyBtn");
  const confirmPrivacyCloseBtn = document.getElementById("confirmPrivacyCloseBtn");

  // Delete Account Confirmation Modal
  const openDeleteAccountConfirmBtn = document.getElementById("openDeleteAccountConfirmBtn");
  const deleteAccountConfirmModal = document.getElementById("deleteAccountConfirmModal");
  const cancelDeleteAccountBtn = document.getElementById("cancelDeleteAccountBtn");
  const confirmDeleteAccountBtn = document.getElementById("confirmDeleteAccountBtn");

  // Toast notification
  const toast = document.getElementById("toast");

  // Global state
  let currentUser = null;
  let isDevMode = false;

  // Global Dev Trace History (Step C2.5 Item 7)
  const devTracesHistory = [];
  function recordDevTrace(trace) {
    if (!trace) return;
    devTracesHistory.unshift({
      timestamp: new Date().toLocaleTimeString(),
      ...trace
    });
    if (devTracesHistory.length > 20) devTracesHistory.pop();
    renderDevTraces();
  }

  function renderDevTraces() {
    const list = document.getElementById("devTracePanelList");
    if (!list) return;
    if (devTracesHistory.length === 0) {
      list.innerHTML = '<div style="color: #6b7280; font-style: italic; padding: 6px;">No traces yet. Chat with SINBHA to inspect model output, tool calls, and latencies.</div>';
      return;
    }
    list.innerHTML = devTracesHistory.map((t, idx) => {
      const toolCount = t.tool_calls ? t.tool_calls.length : 0;
      const statusColor = t.error ? "#ef4444" : "#10b981";
      return `
        <div style="background: #fff; border: 1px solid #fbcfe8; border-radius: 6px; padding: 8px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <strong style="color: #831843;">[#${devTracesHistory.length - idx}] ${escapeHtml(t.provider || 'AI')} / ${escapeHtml(t.model || 'model')}</strong>
            <span style="font-size: 0.7rem; color: ${statusColor}; font-weight: 700;">${t.error ? escapeHtml(t.error) : 'SUCCESS'} (${t.elapsed_ms || 0}ms)</span>
          </div>
          <div style="font-size: 0.72rem; color: #6b7280;">Tools: ${toolCount} executed &bull; Time: ${escapeHtml(t.timestamp)}</div>
          ${toolCount > 0 ? `<pre style="margin: 4px 0 0 0; background: #fdf2f8; padding: 4px; border-radius: 4px; overflow-x: auto; font-size: 0.68rem; color: #4b5563;">${escapeHtml(JSON.stringify(t.tool_calls, null, 2))}</pre>` : ''}
        </div>
      `;
    }).join("");
  }

  let activeReminderTask = null;
  let activeReminderId = null;
  let remindersPaused = false;
  let birdFlightTimer = null;

  // Format time helper
  function formatTime(dateStr) {
    const d = dateStr ? new Date(dateStr) : new Date();
    return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  // Auto-scroll chat to latest message
  function scrollToBottom() {
    scrollAnchor.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  // Show a brief toast notification
  function showToast(message, duration = 3000) {
    toast.textContent = message;
    toast.classList.add("show");
    setTimeout(() => {
      toast.classList.remove("show");
    }, duration);
  }

  function escapeHtml(string) {
    const div = document.createElement("div");
    div.innerText = string;
    return div.innerHTML;
  }

  // Enable/disable send button based on text
  messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 140) + "px";
    sendBtn.disabled = messageInput.value.trim().length === 0;
  });

  // Handle Enter key (Shift+Enter for newline)
  messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled) {
        sendMessage();
      }
    }
  });

  // Add a user bubble to chat
  function appendUserMessage(text, timeStr = null) {
    const group = document.createElement("div");
    group.className = "message-group user-group";
    group.innerHTML = `
      <div class="message-bubble user-bubble">
        <p>${escapeHtml(text)}</p>
        <span class="message-time">${formatTime(timeStr)}</span>
      </div>
    `;
    chatMessages.appendChild(group);
    scrollToBottom();
  }

  // Helper to format full date, time, and timezone on all task cards (Requirement 2)
  function formatFullTaskDateTime(dueDate, dueTime, dueDatetimeUtc) {
    if (!dueDate) return `<span class="task-card-due no-date">📅 No due date</span>`;
    const userTz = Intl.DateTimeFormat().resolvedOptions().timeZone || "Local";

    if (dueDatetimeUtc) {
      try {
        const dt = new Date(dueDatetimeUtc);
        if (!isNaN(dt.getTime())) {
          const formatted = dt.toLocaleString(undefined, {
            weekday: 'short',
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            timeZoneName: 'short'
          });
          return `<span class="task-card-due">📅 Due: ${escapeHtml(formatted)}</span>`;
        }
      } catch (_) {}
    }

    if (dueTime) {
      try {
        const partsD = dueDate.split('-').map(Number);
        const partsT = dueTime.split(':').map(Number);
        const dt = new Date(partsD[0], partsD[1] - 1, partsD[2], partsT[0], partsT[1]);
        const formatted = dt.toLocaleString(undefined, {
          weekday: 'short',
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: 'numeric',
          minute: '2-digit'
        });
        return `<span class="task-card-due">📅 Due: ${escapeHtml(formatted)} (${escapeHtml(userTz)})</span>`;
      } catch (_) {
        return `<span class="task-card-due">📅 Due: ${escapeHtml(dueDate)} at ${escapeHtml(dueTime)} (${escapeHtml(userTz)})</span>`;
      }
    }

    try {
      const partsD = dueDate.split('-').map(Number);
      const dt = new Date(partsD[0], partsD[1] - 1, partsD[2]);
      const formatted = dt.toLocaleString(undefined, {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
      return `<span class="task-card-due">📅 Due: ${escapeHtml(formatted)} (${escapeHtml(userTz)})</span>`;
    } catch (_) {
      return `<span class="task-card-due">📅 Due: ${escapeHtml(dueDate)} (${escapeHtml(userTz)})</span>`;
    }
  }

  // Add an AI bubble to chat (with optional proposal action card, web search sources, and action receipts)
  function appendAiMessage(text, timeStr = null, proposal = null, webSearch = null, trace = null, actionReceipt = null) {
    const group = document.createElement("div");
    group.className = "message-group ai-group";
    
    // Step M1+M2 Item 4: App-built action receipt
    let receiptHtml = "";
    let displayText = text;
    let proposalHtml = "";

    if (actionReceipt && actionReceipt.tool) {
      const st = String(actionReceipt.status || "unconfirmed").toLowerCase();
      const isSuccess = st === "succeeded";
      const isNeedsTap = st === "needs_tap";
      const isNotInstalled = st === "not_installed";
      const isUnverified = st === "sent_not_verified" || st === "unconfirmed";
      
      const badgeBg = isSuccess ? "#dcfce7" : (isNeedsTap ? "#fef3c7" : (isNotInstalled ? "#f3e8ff" : "#fee2e2"));
      const badgeColor = isSuccess ? "#15803d" : (isNeedsTap ? "#b45309" : (isNotInstalled ? "#7e22ce" : "#b91c1c"));
      const badgeLabel = isSuccess ? "✓ Succeeded" : (isNeedsTap ? "👆 Needs Tap" : (isNotInstalled ? "❓ Not Installed" : (isUnverified ? "⚠️ Sent (Not Verified)" : "✕ Failed")));
      
      const routeName = escapeHtml(actionReceipt.route || "direct");
      const devName = escapeHtml(actionReceipt.device || "Companion Device");
      const evidence = escapeHtml(actionReceipt.evidence || (isSuccess ? "Verified via window/process check" : "Awaiting verification"));
      const timeElapsed = actionReceipt.elapsed_ms ? `${actionReceipt.elapsed_ms}ms` : "";

      receiptHtml = `
        <div class="action-receipt-card" style="margin-top: 8px; background: #fff; border: 1.5px solid ${badgeColor}; border-radius: 8px; padding: 10px; font-size: 0.8rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-weight: 700; color: #1f2937;">Action Receipt: <span style="font-family: ui-monospace, monospace; color: #be185d;">${escapeHtml(actionReceipt.tool)}</span></span>
            <span style="background: ${badgeBg}; color: ${badgeColor}; font-weight: 700; font-size: 0.72rem; padding: 2px 8px; border-radius: 10px;">${badgeLabel}</span>
          </div>
          <div style="color: #4b5563; line-height: 1.4; font-size: 0.76rem;">
            <div><strong>Device:</strong> ${devName}</div>
            <div><strong>Route:</strong> <span style="font-family: ui-monospace, monospace; color: #2563eb;">${routeName}</span></div>
            <div><strong>Evidence:</strong> ${evidence}</div>
            ${timeElapsed ? `<div><strong>Duration:</strong> ${timeElapsed}</div>` : ''}
          </div>
        </div>
      `;

      // If AI text contradicts receipt (e.g. AI says "Settings is open" when receipt status is not succeeded), suppress AI text
      if (!isSuccess && displayText) {
        const lower = displayText.toLowerCase();
        if (lower.includes("is open") || lower.includes("opened ") || lower.includes("have opened")) {
          displayText = isNeedsTap 
            ? "Your phone requires a tap to open this app from the background. Check your notification shade"
            : (isNotInstalled ? displayText : "The command was transmitted, but device launch could not be confirmed.");
        }
      }
    }
    if (proposal) {
      if (proposal.type === "task_proposal") {
        // Step 5 & 6B: Task proposal card with suggested reminders & Confirm / Cancel gate
        let remindersHtml = "";
        if (proposal.due_date) {
          const suggested = proposal.suggested_reminders || [];
          remindersHtml = `
            <div class="task-proposal-reminders">
              <div class="task-reminders-title">
                <span>🔔</span>
                <span>Suggested Reminders:</span>
              </div>
              <div class="task-reminders-list">
                ${suggested.map(r => `
                  <label class="task-reminder-item">
                    <input type="checkbox" class="task-rem-checkbox" data-id="${escapeHtml(r.id)}" data-label="${escapeHtml(r.label)}" data-time="${escapeHtml(r.time || r.trigger_at || '')}" ${r.default !== false ? 'checked' : ''}>
                    <span>${escapeHtml(r.label)}</span>
                  </label>
                `).join('')}
              </div>
              <div class="task-reminder-custom-row">
                <button type="button" class="task-quick-10m-chip" title="Remind in 10 minutes">+ 10 min</button>
                <span style="color: #9ca3af; font-size: 0.76rem;">or custom time:</span>
                <input type="time" class="task-custom-time-input" title="Set specific reminder time">
              </div>
            </div>
          `;
        }

        const dueFormatted = proposal.display_due 
          ? `<span class="task-proposal-due-badge">📅 ${escapeHtml(proposal.display_due)}</span>`
          : (proposal.due_date 
              ? formatFullTaskDateTime(proposal.due_date, proposal.due_time, proposal.due_datetime_utc)
              : `<span style="color: #6b7280; font-size: 0.82rem;">No deadline</span>`);

        const ambiguityHtml = (proposal.ambiguous_options && proposal.ambiguous_options.length > 0)
          ? `
            <div class="task-proposal-ambiguity-box" style="margin: 8px 0; padding: 10px; background: rgba(236, 72, 153, 0.08); border-radius: 8px; border: 1.5px dashed rgba(236, 72, 153, 0.4);">
              <div style="font-size: 0.78rem; font-weight: 700; color: #be123c; margin-bottom: 6px;">Which time did you mean?</div>
              <div style="display: flex; gap: 8px;">
                ${proposal.ambiguous_options.map((opt, idx) => `
                  <button type="button" class="task-ambiguity-choice-btn ${idx === 1 ? 'selected' : ''}" data-time="${escapeHtml(opt.time)}" data-display="${escapeHtml(opt.display)}" style="flex: 1; padding: 7px 10px; border-radius: 6px; font-size: 0.82rem; font-weight: 700; cursor: pointer; border: 1.5px solid #ec4899; background: ${idx === 1 ? '#be123c' : '#fff'}; color: ${idx === 1 ? '#fff' : '#be123c'}; transition: all 0.15s ease;">
                    ${escapeHtml(opt.label)}
                  </button>
                `).join('')}
              </div>
            </div>
          `
          : "";

        proposalHtml = `
          <div class="task-proposal-card" id="task-prop-${proposal.id}">
            <div class="task-proposal-header">
              <span>📋</span>
              <span>Task Proposal</span>
            </div>
            <div class="task-proposal-body">
              <div class="task-proposal-title-row">
                <span>📌</span>
                <span>${escapeHtml(proposal.title)}</span>
              </div>
              <div class="task-proposal-due-row">
                ${dueFormatted}
              </div>
              ${ambiguityHtml}
              ${remindersHtml}
              ${proposal.notes ? `<div class="task-proposal-notes-row">📝 ${escapeHtml(proposal.notes)}</div>` : ''}
            </div>
            <div class="task-proposal-actions">
              <button class="task-confirm-btn" data-id="${proposal.id}">✓ Confirm & Save Task</button>
              <button class="task-cancel-btn" data-id="${proposal.id}">✕ Cancel</button>
            </div>
          </div>
        `;
      } else if (proposal.type === "task_complete") {
        // Step 6: Task completion confirmation card
        proposalHtml = `
          <div class="task-action-card" id="task-action-${proposal.task_id}">
            <div class="task-action-header">
              <span>🎉</span>
              <span>Task Completion</span>
            </div>
            <div class="task-action-title">
              ${escapeHtml(proposal.prompt || `Mark '${proposal.task_title}' as done?`)}
            </div>
            <div class="task-action-actions">
              <button class="task-action-confirm-btn" data-id="${proposal.task_id}">✓ Yes, mark done</button>
              <button class="task-action-cancel-btn" data-id="${proposal.task_id}">✕ Keep pending</button>
            </div>
          </div>
        `;
      } else if (proposal.type === "task_delete") {
        // Step 6: Task deletion confirmation card
        proposalHtml = `
          <div class="task-action-card" id="task-action-${proposal.task_id}">
            <div class="task-action-header">
              <span>🗑️</span>
              <span>Delete Task</span>
            </div>
            <div class="task-action-title">
              ${escapeHtml(proposal.prompt || `Delete '${proposal.task_title}'?`)}
            </div>
            <div class="task-action-actions">
              <button class="task-action-delete-btn" data-id="${proposal.task_id}">✓ Yes, delete</button>
              <button class="task-action-cancel-btn" data-id="${proposal.task_id}">✕ Cancel</button>
            </div>
          </div>
        `;
      } else if (proposal.type === "confirm_forget") {
        // Memory forget confirmation card
        proposalHtml = `
          <div class="proposal-card" id="proposal-${proposal.fact_id}">
            <div class="proposal-card-header">
              <span>⚠️</span>
              <span>${escapeHtml(proposal.prompt || "Confirm deletion")}</span>
            </div>
            <div class="proposal-card-fact">${escapeHtml(proposal.fact_text)}</div>
            <div class="proposal-card-actions">
              <button class="proposal-confirm-btn" data-action="confirm" data-id="${proposal.fact_id}">✓ Yes, forget it</button>
              <button class="proposal-cancel-btn" data-action="cancel" data-id="${proposal.fact_id}">✕ Keep it</button>
            </div>
          </div>
        `;
      } else if (proposal.type && proposal.type.startsWith("confirm_")) {
        // Step C2.12 Item 6: Structured Safety Confirmation Card
        const title = proposal.action_title || proposal.prompt || "Action Confirmation";
        const msg = proposal.message || "";
        const warning = proposal.warning ? `<div style="color: #ea580c; font-size: 0.85rem; margin-top: 6px;">⚠️ ${escapeHtml(proposal.warning)}</div>` : "";
        proposalHtml = `
          <div class="task-action-card" id="safety-card-${Math.random().toString(36).substring(7)}" style="background: #fffaf5; border: 1.5px solid #fed7aa; border-radius: 12px; padding: 14px; margin-top: 10px;">
            <div class="task-action-header" style="display:flex;align-items:center;gap:6px; font-weight:600; color: #9a3412;">
              <span>🛡️</span>
              <span>${escapeHtml(title)}</span>
            </div>
            <div class="task-action-prompt" style="margin-top:6px; color: #431407; font-size: 0.92rem;">
              ${escapeHtml(msg)}
              ${warning}
            </div>
            <div class="task-action-actions" style="margin-top:12px; display: flex; gap: 8px;">
              <button class="generic-confirm-btn primary-btn" style="padding:7px 16px; border-radius:8px; font-weight:600; font-size:0.88rem; cursor:pointer;">✓ Yes, proceed</button>
              <button class="generic-cancel-btn secondary-btn" style="padding:7px 16px; border-radius:8px; font-size:0.88rem; cursor:pointer;">✕ Cancel</button>
            </div>
          </div>
        `;
      }
    }

    let webSearchHtml = "";
    if (webSearch && webSearch.searched) {
      let sourcesHtml = "";
      if (webSearch.sources && webSearch.sources.length > 0) {
        sourcesHtml = `
          <div class="web-search-sources">
            ${webSearch.sources.map(s => {
              const safeDomain = escapeHtml(s.domain || "web");
              const safeDate = escapeHtml(s.date || "");
              const safeUrl = escapeHtml(s.url || "#");
              const safeTitle = escapeHtml(s.title || s.domain || "Source");
              return `
                <a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="web-source-chip" title="${safeTitle}">
                  <span class="source-icon">🔗</span>
                  <span class="source-domain">${safeDomain}</span>
                  ${safeDate ? `<span class="source-date">• ${safeDate}</span>` : ''}
                </a>
              `;
            }).join('')}
          </div>
        `;
      }
      webSearchHtml = `
        <div class="web-search-badge-container">
          <span class="web-search-badge">🌐 Searched the web${webSearch.cached ? ' (cached)' : ''}</span>
          ${sourcesHtml}
        </div>
      `;
    }

    group.innerHTML = `
      <div class="message-avatar"><img src="elephant_logo.png" alt="SINBHA" style="width: 24px; height: 24px; border-radius: 50%;"></div>
      <div class="message-bubble ai-bubble">
        <p>${escapeHtml(displayText)}</p>
        ${receiptHtml}
        ${webSearchHtml}
        ${proposalHtml}
        ${isDevMode && trace && (trace.provider || trace.tool_calls?.length > 0) ? `
          <details class="dev-trace-inline" style="margin-top: 6px; font-size: 0.74rem; background: #fdf2f8; border: 1px dashed #f472b6; border-radius: 6px; padding: 4px 8px;">
            <summary style="cursor: pointer; font-weight: 700; color: #9d174d;">🔍 Dev Trace (${trace.elapsed_ms || 0}ms &bull; ${escapeHtml(trace.provider || 'ai')}/${escapeHtml(trace.model || 'model')})</summary>
            <pre style="margin: 4px 0 0 0; white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 0.72rem; color: #374151;">${escapeHtml(JSON.stringify(trace, null, 2))}</pre>
          </details>
        ` : ''}
        <span class="message-time">${formatTime(timeStr)}</span>
      </div>
    `;
    chatMessages.appendChild(group);

    // Attach event listeners to task proposal buttons (Step 5 & 6B)
    if (proposal && proposal.type === "task_proposal") {
      const card = group.querySelector(".task-proposal-card");
      if (card) {
        card.querySelectorAll(".task-ambiguity-choice-btn").forEach(btn => {
          btn.addEventListener("click", () => {
            card.querySelectorAll(".task-ambiguity-choice-btn").forEach(b => {
              b.classList.remove("selected");
              b.style.background = "#fff";
              b.style.color = "#be123c";
            });
            btn.classList.add("selected");
            btn.style.background = "#be123c";
            btn.style.color = "#fff";
            card.dataset.chosenTime = btn.dataset.time;
            const dueRow = card.querySelector(".task-proposal-due-row");
            if (dueRow && btn.dataset.display) {
              dueRow.innerHTML = `<span class="task-proposal-due-badge">📅 ${escapeHtml(btn.dataset.display)}</span>`;
            }
          });
        });

        const quickChip = card.querySelector(".task-quick-10m-chip");
        if (quickChip) {
          quickChip.addEventListener("click", () => {
            quickChip.classList.toggle("active");
          });
        }

        const confirmBtn = card.querySelector(".task-confirm-btn");
        const cancelBtn = card.querySelector(".task-cancel-btn");
        if (confirmBtn && cancelBtn) {
          confirmBtn.addEventListener("click", async () => {
            confirmBtn.disabled = true;
            cancelBtn.disabled = true;
            await handleTaskConfirm(proposal.id, card);
          });

          cancelBtn.addEventListener("click", async () => {
            confirmBtn.disabled = true;
            cancelBtn.disabled = true;
            await handleTaskCancel(proposal.id, card);
          });
        }
      }
    }

    // Attach event listeners to task complete / delete action buttons (Step 6)
    if (proposal && (proposal.type === "task_complete" || proposal.type === "task_delete")) {
      const card = group.querySelector(".task-action-card");
      const confirmBtn = group.querySelector(".task-action-confirm-btn, .task-action-delete-btn");
      const cancelBtn = group.querySelector(".task-action-cancel-btn");

      if (confirmBtn && cancelBtn) {
        confirmBtn.addEventListener("click", async () => {
          confirmBtn.disabled = true;
          cancelBtn.disabled = true;
          await handleTaskActionCardConfirmation("confirm", proposal.type, card);
        });

        cancelBtn.addEventListener("click", async () => {
          confirmBtn.disabled = true;
          cancelBtn.disabled = true;
          await handleTaskActionCardConfirmation("cancel", proposal.type, card);
        });
      }
    }

    // Attach event listeners to memory forget buttons
    if (proposal && proposal.type === "confirm_forget") {
      const card = group.querySelector(".proposal-card");
      const confirmBtn = group.querySelector(".proposal-confirm-btn");
      const cancelBtn = group.querySelector(".proposal-cancel-btn");

      if (confirmBtn && cancelBtn) {
        confirmBtn.addEventListener("click", async () => {
          confirmBtn.disabled = true;
          cancelBtn.disabled = true;
          await handleMemoryActionConfirmation("confirm", card);
        });

        cancelBtn.addEventListener("click", async () => {
          confirmBtn.disabled = true;
          cancelBtn.disabled = true;
          await handleMemoryActionConfirmation("cancel", card);
        });
      }
    }

    // Attach event listeners to generic safety confirmation cards (Step C2.12)
    if (proposal && proposal.type && proposal.type.startsWith("confirm_") && proposal.type !== "confirm_forget") {
      const card = group.querySelector(".task-action-card");
      const confirmBtn = group.querySelector(".generic-confirm-btn");
      const cancelBtn = group.querySelector(".generic-cancel-btn");

      if (confirmBtn && cancelBtn) {
        confirmBtn.addEventListener("click", () => {
          confirmBtn.disabled = true;
          cancelBtn.disabled = true;
          const actionsDiv = card.querySelector(".task-action-actions");
          if (actionsDiv) actionsDiv.innerHTML = `<div class="task-proposal-resolved confirmed" style="color:#16a34a; font-weight:600; font-size:0.88rem;">✓ Confirmed</div>`;
          const input = document.getElementById("messageInput");
          if (input) {
            input.value = "yes, proceed";
            const form = document.getElementById("chatForm");
            if (form) form.dispatchEvent(new Event("submit"));
          }
        });

        cancelBtn.addEventListener("click", () => {
          confirmBtn.disabled = true;
          cancelBtn.disabled = true;
          const actionsDiv = card.querySelector(".task-action-actions");
          if (actionsDiv) actionsDiv.innerHTML = `<div class="task-proposal-resolved cancelled" style="color:#dc2626; font-size:0.88rem;">✕ Cancelled</div>`;
        });
      }
    }

    scrollToBottom();
  }

  // Handle confirming a proposed task (Step 5 & 6B with chosen reminders)
  async function handleTaskConfirm(proposalId, cardElement) {
    try {
      const chosenReminders = [];
      if (cardElement) {
        cardElement.querySelectorAll(".task-rem-checkbox:checked").forEach(cb => {
          chosenReminders.push({
            id: cb.dataset.id || ("rem_" + Date.now() + "_" + Math.random().toString(36).substr(2, 4)),
            label: cb.dataset.label || "Reminder",
            time: cb.dataset.time || cb.dataset.trigger || "",
            type: "relative"
          });
        });

        const chip10m = cardElement.querySelector(".task-quick-10m-chip.active");
        if (chip10m) {
          const d10 = new Date(Date.now() + 10 * 60000);
          const yyyy = d10.getFullYear();
          const mm = String(d10.getMonth() + 1).padStart(2, '0');
          const dd = String(d10.getDate()).padStart(2, '0');
          const hh = String(d10.getHours()).padStart(2, '0');
          const min = String(d10.getMinutes()).padStart(2, '0');
          chosenReminders.push({
            id: "rem_10m_" + Date.now(),
            label: "10 minutes from now",
            time: `${yyyy}-${mm}-${dd} ${hh}:${min}`,
            type: "manual"
          });
        }

        const customTimeInput = cardElement.querySelector(".task-custom-time-input");
        if (customTimeInput && customTimeInput.value) {
          const parts = customTimeInput.value.split(":");
          const hh = parts[0].padStart(2, '0');
          const min = parts[1].padStart(2, '0');
          const targetDate = new Date();
          targetDate.setHours(parseInt(hh, 10), parseInt(min, 10), 0, 0);
          if (targetDate.getTime() <= Date.now()) {
            targetDate.setDate(targetDate.getDate() + 1);
          }
          const yyyy = targetDate.getFullYear();
          const mm = String(targetDate.getMonth() + 1).padStart(2, '0');
          const dd = String(targetDate.getDate()).padStart(2, '0');
          chosenReminders.push({
            id: "rem_custom_" + Date.now(),
            label: `At ${customTimeInput.value}`,
            time: `${yyyy}-${mm}-${dd} ${hh}:${min}`,
            type: "manual"
          });
        }
      }

      const chosenTime = cardElement ? cardElement.dataset.chosenTime : undefined;
      const res = await fetch("/api/tasks/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          proposal_id: proposalId,
          reminders: chosenReminders,
          chosen_time: chosenTime
        })
      });
      const data = await res.json();
      
      if (data.success) {
        if (cardElement) {
          const actionsDiv = cardElement.querySelector(".task-proposal-actions");
          if (actionsDiv) {
            actionsDiv.outerHTML = `<div class="task-proposal-resolved confirmed">✓ Confirmed & saved to your tasks</div>`;
          }
        }
        if (data.reply) {
          appendAiMessage(data.reply);
        }
        showToast("Task saved to your list!");
        loadTasks();
        if (isDevMode) loadDevData();
      } else {
        showToast(data.reply || "Could not confirm task");
        if (cardElement) {
          const actionsDiv = cardElement.querySelector(".task-proposal-actions");
          if (actionsDiv) {
            actionsDiv.outerHTML = `<div class="task-proposal-resolved expired">⚠️ ${escapeHtml(data.reply || "Expired")}</div>`;
          }
        }
      }
    } catch (e) {
      console.error("Task confirmation failed", e);
    }
  }

  // Handle cancelling a proposed task (Step 5)
  async function handleTaskCancel(proposalId, cardElement) {
    try {
      const res = await fetch("/api/tasks/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposal_id: proposalId })
      });
      const data = await res.json();
      
      if (cardElement) {
        const actionsDiv = cardElement.querySelector(".task-proposal-actions");
        if (actionsDiv) {
          actionsDiv.outerHTML = `<div class="task-proposal-resolved cancelled">✕ Proposal cancelled</div>`;
        }
      }
      if (data.reply) {
        appendAiMessage(data.reply);
      }
      showToast("Task proposal dropped");
      if (isDevMode) loadDevData();
    } catch (e) {
      console.error("Task cancel failed", e);
    }
  }

  // Handle clicking Confirm / Cancel on memory deletion cards
  async function handleMemoryActionConfirmation(action, cardElement) {
    try {
      const res = await fetch("/api/confirm-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action })
      });
      const data = await res.json();
      
      if (cardElement) {
        cardElement.style.opacity = "0.6";
        cardElement.innerHTML = `<small style="font-weight: 600; color: ${action === "confirm" ? "#dc2626" : "#4b5563"};">${action === "confirm" ? "✓ Confirmed & deleted" : "✕ Kept in memory"}</small>`;
      }

      if (data.reply) {
        appendAiMessage(data.reply);
      }

      if (isDevMode) {
        loadDevData();
      }
    } catch (e) {
      console.error("Memory confirmation failed", e);
    }
  }

  // Handle clicking Confirm / Cancel on task action cards (complete or delete) (Step 6)
  async function handleTaskActionCardConfirmation(action, type, cardElement) {
    try {
      const res = await fetch("/api/confirm-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action })
      });
      const data = await res.json();
      
      if (cardElement) {
        const actionsDiv = cardElement.querySelector(".task-action-actions");
        if (actionsDiv) {
          if (action === "confirm") {
            const label = type === "task_complete" ? "✓ Marked as completed" : "✓ Task deleted";
            actionsDiv.outerHTML = `<div class="task-proposal-resolved confirmed">${label}</div>`;
          } else {
            const label = type === "task_complete" ? "✕ Kept pending" : "✕ Kept in tasks";
            actionsDiv.outerHTML = `<div class="task-proposal-resolved cancelled">${label}</div>`;
          }
        }
      }

      if (data.reply) {
        appendAiMessage(data.reply);
      }

      loadTasks();
      if (isDevMode) loadDevData();
    } catch (e) {
      console.error("Task action card confirmation failed", e);
    }
  }

  // Add a system notice (e.g. STOP command)
  function appendSystemNotice(text) {
    const notice = document.createElement("div");
    notice.className = "system-bubble";
    notice.innerHTML = `
      <div>${escapeHtml(text)}</div>
      <div class="system-bubble-actions">
        <button class="resume-btn inline-resume-btn">Resume Chat</button>
      </div>
    `;
    chatMessages.appendChild(notice);
    
    const inlineResume = notice.querySelector(".inline-resume-btn");
    if (inlineResume) {
      inlineResume.addEventListener("click", resumeChat);
    }
    scrollToBottom();
  }

  // Update STOP state UI
  function setStopUiState(isStopped) {
    if (isStopped) {
      stopBanner.style.display = "block";
      statusDot.classList.add("stopped");
      statusDot.title = "Emergency Stopped";
    } else {
      stopBanner.style.display = "none";
      statusDot.classList.remove("stopped");
      statusDot.title = "Online";
    }
  }

  // Load chat history on startup
  async function loadChatHistory() {
    try {
      const res = await fetch("/api/messages");
      if (res.status === 401) {
        showAuthScreen();
        return;
      }
      if (!res.ok) return;
      const data = await res.json();
      
      chatMessages.innerHTML = "";
      setStopUiState(data.emergency_stopped);

      if (!data.messages || data.messages.length === 0) {
        appendAiMessage("Hey there! I'm SINBHA I'm here to listen, support you, and keep your days calm and organized. How are you feeling right now?");
      } else {
        data.messages.forEach(msg => {
          if (msg.role === "user") {
            appendUserMessage(msg.content, msg.timestamp);
          } else if (msg.role === "assistant") {
            appendAiMessage(msg.content, msg.timestamp);
          }
        });
      }
      scrollToBottom();
    } catch (e) {
      console.error("Failed to load chat history:", e);
    }
  }

  // Load Tasks into Tasks Drawer (Step 6: Interactive)
  async function loadTasks() {
    try {
      const res = await fetch("/api/tasks");
      if (res.status === 401) {
        showAuthScreen();
        return;
      }
      if (!res.ok) return;
      const data = await res.json();
      const tasks = data.tasks || [];
      const pendingCount = typeof data.pending_count === "number" ? data.pending_count : tasks.filter(t => t.status === "pending").length;

      // Update header badge (pending tasks only)
      taskCountBadge.textContent = pendingCount;
      if (pendingCountBadgeDrawer) {
        pendingCountBadgeDrawer.textContent = `${pendingCount} pending`;
      }

      renderTasks(tasks);
    } catch (e) {
      console.error("Failed to load tasks:", e);
    }
  }

  function renderTasks(tasks) {
    if (!tasks || tasks.length === 0) {
      emptyTaskState.style.display = "block";
      taskListContainer.style.display = "none";
      return;
    }

    emptyTaskState.style.display = "none";
    taskListContainer.style.display = "block";

    const pendingTasks = tasks.filter(t => t.status === "pending");
    const completedTasks = tasks.filter(t => t.status === "completed");

    // Render pending tasks list
    pendingTaskList.innerHTML = "";
    if (pendingTasks.length === 0) {
      pendingTaskList.innerHTML = `<li style="font-size: 0.84rem; color: #9ca3af; text-align: center; padding: 14px 0;">All caught up! No pending tasks</li>`;
    } else {
      pendingTasks.forEach(t => {
        const li = document.createElement("li");
        li.className = `task-card-item ${t.is_overdue ? "overdue" : ""}`;
        li.dataset.id = t.id;

        li.innerHTML = `
          <div class="task-card-main">
            <label class="task-checkbox-container" title="Mark as done">
              <input type="checkbox" class="task-checkbox" data-id="${t.id}" />
              <span class="custom-checkmark"></span>
            </label>
            <div class="task-card-info">
              <div class="task-card-title-row">
                <span class="task-card-title">${escapeHtml(t.title)}</span>
                ${t.is_overdue ? `<span class="task-overdue-badge">⚠️ Overdue</span>` : ""}
              </div>
              <div class="task-card-meta">
                ${formatFullTaskDateTime(t.due_date, t.due_time, t.due_datetime_utc)}
                ${(t.reminders && t.reminders.length > 0) ? `<span style="font-size: 0.72rem; color: #db2777; background: #fff0f3; padding: 1px 6px; border-radius: 4px; font-weight: 600;">🔔 ${t.reminders.length} reminder${t.reminders.length > 1 ? 's' : ''}</span>` : ''}
                ${t.notes ? `<span class="task-card-notes">📝 ${escapeHtml(t.notes)}</span>` : ""}
              </div>
            </div>
            <button class="task-delete-btn" data-id="${t.id}" title="Delete task">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </div>
        `;

        // Checkbox event listener (toggle to completed with friendly micro-animation)
        const chk = li.querySelector(".task-checkbox");
        chk.addEventListener("change", () => {
          li.classList.add("completing");
          setTimeout(async () => {
            await updateTaskStatus(t.id, "completed");
            showToast("Great job! Task marked as done!");
          }, 240);
        });

        // Delete button listener
        const delBtn = li.querySelector(".task-delete-btn");
        delBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          openTaskDeleteModal(t.id, t.title);
        });

        pendingTaskList.appendChild(li);
      });
    }

    // Render completed tasks in collapsible section
    completedTaskList.innerHTML = "";
    if (completedTasks.length > 0) {
      completedTasksAccordion.style.display = "block";
      completedCountBadge.textContent = completedTasks.length;

      completedTasks.forEach(t => {
        const li = document.createElement("li");
        li.className = "task-card-item completed";
        li.dataset.id = t.id;

        li.innerHTML = `
          <div class="task-card-main">
            <label class="task-checkbox-container" title="Uncheck to reopen task">
              <input type="checkbox" class="task-checkbox" data-id="${t.id}" checked />
              <span class="custom-checkmark"></span>
            </label>
            <div class="task-card-info">
              <div class="task-card-title-row">
                <span class="task-card-title">${escapeHtml(t.title)}</span>
              </div>
              <div class="task-card-meta">
                ${formatFullTaskDateTime(t.due_date, t.due_time, t.due_datetime_utc)}
                ${t.notes ? `<span class="task-card-notes">📝 ${escapeHtml(t.notes)}</span>` : ""}
              </div>
            </div>
            <button class="task-delete-btn" data-id="${t.id}" title="Delete task">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </div>
        `;

        // Checkbox event listener (unchecking brings back to pending)
        const chk = li.querySelector(".task-checkbox");
        chk.addEventListener("change", async () => {
          await updateTaskStatus(t.id, "pending");
          showToast("Task brought back to pending");
        });

        // Delete button
        const delBtn = li.querySelector(".task-delete-btn");
        delBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          openTaskDeleteModal(t.id, t.title);
        });

        completedTaskList.appendChild(li);
      });
    } else {
      completedTasksAccordion.style.display = "none";
      completedCountBadge.textContent = "0";
    }
  }

  // Update task status via PATCH endpoint (Step 6)
  async function updateTaskStatus(taskId, status) {
    try {
      const res = await fetch(`/api/tasks/${taskId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: status })
      });
      if (res.ok) {
        await loadTasks();
        if (isDevMode) loadDevData();
      }
    } catch (e) {
      console.error("Failed to update task status:", e);
    }
  }

  // Open Task Delete Confirmation Modal (Step 6)
  function openTaskDeleteModal(taskId, taskTitle) {
    taskToDeleteId = taskId;
    if (taskDeleteModalMessage) {
      taskDeleteModalMessage.textContent = `Are you sure you want to delete '${taskTitle}'? This will remove it permanently.`;
    }
    if (taskDeleteModal) {
      taskDeleteModal.style.display = "flex";
    }
  }

  // Fetch App Info and Check DEV_MODE
  async function checkAppInfo() {
    try {
      const res = await fetch("/api/info");
      if (!res.ok) return;
      const data = await res.json();
      
      isDevMode = Boolean(data.dev_mode);
      if (isDevMode) {
        devMemoryBtn.style.display = "inline-flex";
        loadDevData();
      } else {
        devMemoryBtn.style.display = "none";
        devMemoryDrawer.style.display = "none";
      }
    } catch (e) {
      console.error("Info check error:", e);
    }
  }

  // Developer Mode: Load facts and audit logs
  async function loadDevData() {
    if (!isDevMode) return;
    try {
      const res = await fetch("/api/dev/facts");
      if (!res.ok) return;
      const data = await res.json();
      const facts = data.facts || [];
      const auditLogs = data.audit_logs || [];

      devFactBadge.textContent = facts.length;
      devFactsCountLabel.textContent = facts.length;

      renderDevFacts(facts);
      renderDevAuditLogs(auditLogs);
    } catch (e) {
      console.error("Dev data load failed:", e);
    }
  }

  function renderDevFacts(facts) {
    if (!facts || facts.length === 0) {
      devFactsList.innerHTML = `<div style="font-size: 0.82rem; color: #9ca3af; padding: 12px; text-align: center;">No SQLite facts stored yet.</div>`;
      return;
    }

    devFactsList.innerHTML = "";
    facts.forEach(f => {
      const item = document.createElement("div");
      item.className = "dev-fact-item";
      item.innerHTML = `
        <span class="dev-fact-id">#${f.id}</span>
        <span class="dev-fact-text">${escapeHtml(f.fact)}</span>
        <button class="dev-fact-delete" data-id="${f.id}" title="Delete fact directly (Dev mode)">🗑️</button>
      `;

      item.querySelector(".dev-fact-delete").addEventListener("click", async () => {
        if (confirm(`Dev Mode: Delete fact #${f.id}: "${f.fact}"?`)) {
          await fetch(`/api/facts/${f.id}`, { method: "DELETE" });
          loadDevData();
          showToast(`Deleted fact #${f.id}`);
        }
      });

      devFactsList.appendChild(item);
    });
  }

  function renderDevAuditLogs(logs) {
    if (!logs || logs.length === 0) {
      devAuditLogList.innerHTML = `<div style="font-size: 0.8rem; color: #9ca3af;">No audit records.</div>`;
      return;
    }

    devAuditLogList.innerHTML = "";
    logs.slice(0, 15).forEach(l => {
      const item = document.createElement("div");
      item.className = "dev-audit-item";
      item.innerHTML = `
        <div>
          <span class="dev-audit-action ${l.action}">${escapeHtml(l.action)}</span>
          <span class="dev-audit-details">${escapeHtml(l.details)}</span>
        </div>
        <span class="dev-audit-time">${escapeHtml(l.timestamp || "")}</span>
      `;
      devAuditLogList.appendChild(item);
    });
  }

  // Send message function
  async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text) return;

    messageInput.value = "";
    messageInput.style.height = "auto";
    sendBtn.disabled = true;

    appendUserMessage(text);

    // If user sent STOP in chat
    if (text.toUpperCase() === "STOP") {
      setStopUiState(true);
      triggerEmergencyStop();
      return;
    } else {
      setStopUiState(false);
    }

    const isSearchQuery = /https?:\/\/|\b(search|look up|price|cost|how much|latest|news|weather|who won)\b/i.test(text);
    const indicatorGroup = document.createElement("div");
    indicatorGroup.className = "message-group ai-group searching-indicator-group";
    indicatorGroup.innerHTML = `
      <div class="message-avatar"><img src="elephant_logo.png" alt="SINBHA" style="width: 24px; height: 24px; border-radius: 50%;"></div>
      <div class="searching-indicator-bubble">
        <span class="searching-indicator-spinner"></span>
        <span>${isSearchQuery ? "Searching the web…" : "Thinking…"}</span>
      </div>
    `;
    chatMessages.appendChild(indicatorGroup);
    scrollToBottom();

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          tz_offset_minutes: new Date().getTimezoneOffset(),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
        })
      });

      indicatorGroup.remove();

      if (response.status === 401) {
        showToast("Your session has expired. Please log in.");
        showAuthScreen();
        return;
      }

      if (!response.ok) {
        throw new Error("Server responded with error");
      }

      const data = await response.json();
      appendAiMessage(data.reply, null, data.proposal, data.web_search, data.trace, data.action_receipt);
      if (data.trace) {
        recordDevTrace(data.trace);
      }

      if (data.stopped) {
        setStopUiState(true);
      }

      if (data.task_confirmed || data.task_action_performed || (data.reply && data.reply.includes("Saved! I've added"))) {
        loadTasks();
        if (window.Capacitor?.Plugins?.SinbhaNative) {
          try {
            window.Capacitor.Plugins.SinbhaNative.syncReminders();
          } catch (e) {}
        }
        if (data.task_action_performed) {
          showToast("Tasks updated!");
        } else {
          showToast("Task saved to your list!");
        }
      }

      // If facts or proposals were updated, reload dev data in background
      if (isDevMode && (data.new_facts?.length > 0 || data.updated_fact || data.action_performed || data.proposal || data.task_confirmed || data.task_cancelled || data.task_action_performed)) {
        loadDevData();
      }
    } catch (err) {
      indicatorGroup.remove();
      appendAiMessage("I had a little hiccup connecting right now. Don't worry, please check if the server is still running on your computer");
      console.error(err);
    }
  }

  sendBtn.addEventListener("click", sendMessage);

  // Emergency STOP button functionality (Requirement 6: Hides bird & pauses reminders)
  async function triggerEmergencyStop() {
    setStopUiState(true);
    remindersPaused = true;
    hideBird();
    showToast("🛑 Emergency STOP activated", 3500);
    appendSystemNotice("🛑 Emergency STOP triggered. All processing and reminders paused.");

    // Requirement 6 & 7: cancel any pending proposal cards visibly on screen
    document.querySelectorAll(".task-proposal-actions, .task-action-actions, .proposal-card-actions").forEach(el => {
      el.innerHTML = `<div class="task-proposal-resolved cancelled">🛑 Cancelled due to STOP</div>`;
    });

    try {
      await fetch("/api/stop", { method: "POST" });
      if (isDevMode) loadDevData();
    } catch (e) {
      console.error("Stop call failed", e);
    }
  }

  stopBtn.addEventListener("click", triggerEmergencyStop);

  // Resume Chat functionality
  async function resumeChat() {
    try {
      await fetch("/api/resume", { method: "POST" });
      setStopUiState(false);
      remindersPaused = false;
      showToast("Welcome back! Chat and reminders resumed.");
      // Check for any pending reminders right after resuming
      checkDueReminders();
    } catch (e) {
      console.error("Resume failed", e);
    }
  }

  bannerResumeBtn.addEventListener("click", resumeChat);

  // Task Delete Modal Handlers (Step 6)
  if (cancelTaskDeleteBtn) {
    cancelTaskDeleteBtn.addEventListener("click", () => {
      if (taskDeleteModal) taskDeleteModal.style.display = "none";
      taskToDeleteId = null;
    });
  }

  if (confirmTaskDeleteBtn) {
    confirmTaskDeleteBtn.addEventListener("click", async () => {
      if (!taskToDeleteId) return;
      try {
        confirmTaskDeleteBtn.disabled = true;
        confirmTaskDeleteBtn.textContent = "Deleting...";

        const res = await fetch(`/api/tasks/${taskToDeleteId}`, {
          method: "DELETE"
        });

        if (res.ok) {
          if (taskDeleteModal) taskDeleteModal.style.display = "none";
          showToast("🗑️ Task removed");
          await loadTasks();
          if (isDevMode) loadDevData();
        } else {
          showToast("Could not delete task");
        }
      } catch (e) {
        console.error("Failed to delete task:", e);
        showToast("Error deleting task");
      } finally {
        confirmTaskDeleteBtn.disabled = false;
        confirmTaskDeleteBtn.textContent = "Yes, Delete";
        taskToDeleteId = null;
      }
    });
  }

  if (taskDeleteModal) {
    taskDeleteModal.addEventListener("click", (e) => {
      if (e.target === taskDeleteModal) {
        taskDeleteModal.style.display = "none";
        taskToDeleteId = null;
      }
    });
  }

  // Settings & Purge handling
  openSettingsBtn.addEventListener("click", () => {
    syncViewportMetrics();
    settingsModal.style.display = "flex";
    const modalBody = settingsModal.querySelector(".settings-modal-body");
    if (modalBody) modalBody.scrollTop = 0;
  });

  closeSettingsBtn.addEventListener("click", () => {
    settingsModal.style.display = "none";
  });

  openPurgeConfirmBtn.addEventListener("click", () => {
    syncViewportMetrics();
    purgeConfirmModal.style.display = "flex";
  });

  cancelPurgeBtn.addEventListener("click", () => {
    purgeConfirmModal.style.display = "none";
  });

  // Confirm Purge All Data
  confirmPurgeBtn.addEventListener("click", async () => {
    try {
      confirmPurgeBtn.disabled = true;
      confirmPurgeBtn.textContent = "Clearing...";

      const res = await fetch("/api/purge", { method: "POST" });
      if (res.ok) {
        purgeConfirmModal.style.display = "none";
        settingsModal.style.display = "none";
        chatMessages.innerHTML = "";
        appendAiMessage("All past conversations and memory have been wiped cleanly. We have a fresh, blank canvas together");
        showToast("🧹 All data wiped cleanly");

        loadTasks();
        if (isDevMode) {
          loadDevData();
        }
      }
    } catch (e) {
      showToast("Error wiping data");
    } finally {
      confirmPurgeBtn.disabled = false;
      confirmPurgeBtn.textContent = "Yes, Delete Everything";
    }
  });

  // Close modals when clicking outside card
  settingsModal.addEventListener("click", (e) => {
    if (e.target === settingsModal) {
      settingsModal.style.display = "none";
    }
  });

  purgeConfirmModal.addEventListener("click", (e) => {
    if (e.target === purgeConfirmModal) {
      purgeConfirmModal.style.display = "none";
    }
  });

  // Step D2: Private Inbox Logic
  async function loadInboxNotifications() {
    if (!inboxList) return;
    try {
      const res = await fetch("/api/devices/notifications");
      if (res.ok) {
        const data = await res.json();
        const notifs = data.notifications || [];
        if (inboxCountBadge) {
          if (notifs.length > 0) {
            inboxCountBadge.textContent = notifs.length;
            inboxCountBadge.style.display = "inline-flex";
          } else {
            inboxCountBadge.style.display = "none";
          }
        }

        if (notifs.length === 0) {
          inboxList.innerHTML = `<div style="text-align: center; color: #9ca3af; font-size: 0.85rem; padding: 30px 0;">No alerts in your private inbox.</div>`;
          return;
        }

        inboxList.innerHTML = "";
        notifs.forEach(n => {
          const item = document.createElement("div");
          item.style.cssText = "background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; gap: 4px;";
          
          const timeStr = n.timestamp ? new Date(n.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "";
          
          item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 0.72rem; font-weight: 700; color: #6366f1; text-transform: uppercase; background: #e0e7ff; padding: 2px 6px; border-radius: 4px;">${escapeHtml(n.app || 'App')}</span>
              <span style="font-size: 0.72rem; color: #94a3b8;">${timeStr}</span>
            </div>
            <div style="font-size: 0.82rem; font-weight: 600; color: #1e293b;">${escapeHtml(n.title || '')}</div>
            <div style="font-size: 0.78rem; color: #475569; line-height: 1.4;">${escapeHtml(n.text || '')}</div>
            <div style="display: flex; justify-content: flex-end; margin-top: 4px;">
              <button type="button" class="draft-reply-btn" style="background: transparent; border: 1px solid #cbd5e1; border-radius: 6px; padding: 3px 8px; font-size: 0.72rem; color: #4338ca; cursor: pointer; font-weight: 600;">💬 Draft Reply</button>
            </div>
          `;

          const replyBtn = item.querySelector(".draft-reply-btn");
          if (replyBtn) {
            replyBtn.addEventListener("click", () => {
              if (inboxModal) inboxModal.style.display = "none";
              const sender = n.title || "contact";
              messageInput.value = `Draft a reply to ${sender} saying `;
              messageInput.focus();
              autoResizeTextarea();
            });
          }

          inboxList.appendChild(item);
        });
      }
    } catch (e) {
      console.warn("Could not load inbox notifications:", e);
    }
  }

  if (inboxBtn) {
    inboxBtn.addEventListener("click", () => {
      syncViewportMetrics();
      if (inboxModal) inboxModal.style.display = "flex";
      loadInboxNotifications();
    });
  }

  if (closeInboxBtn) {
    closeInboxBtn.addEventListener("click", () => {
      if (inboxModal) inboxModal.style.display = "none";
    });
  }

  if (refreshInboxBtn) {
    refreshInboxBtn.addEventListener("click", loadInboxNotifications);
  }

  if (clearInboxBtn) {
    clearInboxBtn.addEventListener("click", async () => {
      try {
        await fetch("/api/devices/notifications", { method: "DELETE" });
        loadInboxNotifications();
        showToast("🧹 Inbox cleared");
      } catch (e) {
        showToast("Failed to clear inbox");
      }
    });
  }

  if (inboxModal) {
    inboxModal.addEventListener("click", (e) => {
      if (e.target === inboxModal) {
        inboxModal.style.display = "none";
      }
    });
  }

  // Drawer toggles
  function openTaskDrawer() {
    syncViewportMetrics();
    closeDrawers();
    taskDrawer.classList.add("open");
    drawerOverlay.classList.add("active");
    taskDrawer.setAttribute("aria-hidden", "false");
    const drawerContent = taskDrawer.querySelector(".drawer-content");
    if (drawerContent) drawerContent.scrollTop = 0;
    loadTasks();
  }

  function openDevDrawer() {
    if (!isDevMode) return;
    syncViewportMetrics();
    closeDrawers();
    devMemoryDrawer.style.display = "block";
    devMemoryDrawer.classList.add("open");
    drawerOverlay.classList.add("active");
    devMemoryDrawer.setAttribute("aria-hidden", "false");
    const devContent = devMemoryDrawer.querySelector(".drawer-content");
    if (devContent) devContent.scrollTop = 0;
    loadDevData();
  }

  function closeDrawers() {
    taskDrawer.classList.remove("open");
    taskDrawer.setAttribute("aria-hidden", "true");
    
    if (devMemoryDrawer) {
      devMemoryDrawer.classList.remove("open");
      devMemoryDrawer.setAttribute("aria-hidden", "true");
    }
    
    drawerOverlay.classList.remove("active");
  }

  tasksBtn.addEventListener("click", openTaskDrawer);
  closeTaskBtn.addEventListener("click", closeDrawers);

  if (devMemoryBtn) {
    devMemoryBtn.addEventListener("click", openDevDrawer);
  }
  if (closeDevMemoryBtn) {
    closeDevMemoryBtn.addEventListener("click", closeDrawers);
  }
  if (devRefreshBtn) {
    devRefreshBtn.addEventListener("click", loadDevData);
  }

  drawerOverlay.addEventListener("click", closeDrawers);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeDrawers();
      settingsModal.style.display = "none";
      purgeConfirmModal.style.display = "none";
      if (taskDeleteModal) {
        taskDeleteModal.style.display = "none";
        taskToDeleteId = null;
      }
    }
  });

  // ========================================================
  // SETTINGS & QUIET HOURS MANAGER (STEP 6B)
  // ========================================================
  async function loadSettings() {
    try {
      const res = await fetch("/api/settings");
      if (!res.ok) return;
      const data = await res.json();
      const s = data.settings || {};

      if (persistenceSelect && s.persistence) {
        persistenceSelect.value = s.persistence;
      }
      if (countrySelect && s.country) {
        countrySelect.value = s.country;
      }
      if (timezoneSelect) {
        if (s.timezone) {
          timezoneSelect.value = s.timezone;
        } else {
          const autoTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
          if (autoTz) timezoneSelect.value = autoTz;
        }
      }
      if (quietHoursToggle && s.quiet_hours_enabled !== undefined) {
        const isEnabled = (s.quiet_hours_enabled === "true" || s.quiet_hours_enabled === true);
        quietHoursToggle.checked = isEnabled;
        if (quietTimePickerRow) {
          quietTimePickerRow.style.display = isEnabled ? "flex" : "none";
        }
      }
      if (quietStartInput && s.quiet_hours_start) {
        quietStartInput.value = s.quiet_hours_start;
      }
      if (quietEndInput && s.quiet_hours_end) {
        quietEndInput.value = s.quiet_hours_end;
      }
      if (webSearchToggle && s.web_search_enabled !== undefined) {
        webSearchToggle.checked = (s.web_search_enabled === "true" || s.web_search_enabled === true);
      }

      // Alarm-Grade Reminder settings
      const settingUserDisplayName = document.getElementById("settingUserDisplayName");
      const settingSoundModeSelect = document.getElementById("settingSoundModeSelect");
      const settingSongPickerGroup = document.getElementById("settingSongPickerGroup");
      const settingPickedSongName = document.getElementById("settingPickedSongName");
      const dndAllowAlarmsToggle = document.getElementById("dndAllowAlarmsToggle");

      if (settingUserDisplayName && s.user_display_name !== undefined) {
        settingUserDisplayName.value = s.user_display_name;
      }
      if (settingSoundModeSelect && s.reminder_sound_mode) {
        settingSoundModeSelect.value = s.reminder_sound_mode;
        if (settingSongPickerGroup) {
          settingSongPickerGroup.style.display = (s.reminder_sound_mode === "song") ? "block" : "none";
        }
      }
      if (settingPickedSongName && s.reminder_custom_song_uri) {
        settingPickedSongName.textContent = "Custom song configured 🎵";
      }
      if (dndAllowAlarmsToggle && s.dnd_allow_alarms !== undefined) {
        dndAllowAlarmsToggle.checked = (s.dnd_allow_alarms === "true" || s.dnd_allow_alarms === true);
      }

      // Check electron desktop integration
      if (window.electronAPI) {
        try {
          const appStatus = await window.electronAPI.getAppStatus();
          if (dndToggle) dndToggle.checked = Boolean(appStatus.doNotDisturb);
          if (startWithWindowsToggle) startWithWindowsToggle.checked = Boolean(appStatus.startWithWindows);
        } catch (err) {
          console.error("Get app status error:", err);
        }
      }
    } catch (e) {
      console.error("Load settings failed:", e);
    }
  }

  async function saveSettings() {
    try {
      const settingUserDisplayName = document.getElementById("settingUserDisplayName");
      const settingSoundModeSelect = document.getElementById("settingSoundModeSelect");
      const dndAllowAlarmsToggle = document.getElementById("dndAllowAlarmsToggle");

      const payload = {
        persistence: persistenceSelect ? persistenceSelect.value : "normal",
      active_ai_provider: aiProviderSelect ? aiProviderSelect.value : "auto",
        country: countrySelect ? countrySelect.value : "US",
        timezone: timezoneSelect ? timezoneSelect.value : (Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"),
        quiet_hours_enabled: quietHoursToggle ? (quietHoursToggle.checked ? "true" : "false") : "true",
        quiet_hours_start: quietStartInput ? quietStartInput.value : "22:00",
        quiet_hours_end: quietEndInput ? quietEndInput.value : "08:00",
        web_search_enabled: webSearchToggle ? (webSearchToggle.checked ? "true" : "false") : "true",
        reminder_sound_mode: settingSoundModeSelect ? settingSoundModeSelect.value : "alarm_tone",
        reminder_custom_song_uri: window._customSongUri || undefined,
        user_display_name: settingUserDisplayName ? settingUserDisplayName.value.trim() : "",
        dnd_allow_alarms: dndAllowAlarmsToggle ? (dndAllowAlarmsToggle.checked ? "true" : "false") : "true"
      };
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } catch (e) {
      console.error("Save settings failed:", e);
    }
  }

  if (persistenceSelect) persistenceSelect.addEventListener("change", saveSettings);
  if (aiProviderSelect) aiProviderSelect.addEventListener("change", saveSettings);
  if (countrySelect) countrySelect.addEventListener("change", saveSettings);
  if (timezoneSelect) timezoneSelect.addEventListener("change", saveSettings);
  if (quietHoursToggle) {
    quietHoursToggle.addEventListener("change", () => {
      if (quietTimePickerRow) {
        quietTimePickerRow.style.display = quietHoursToggle.checked ? "flex" : "none";
      }
      saveSettings();
    });
  }
  if (quietStartInput) quietStartInput.addEventListener("change", saveSettings);
  if (quietEndInput) quietEndInput.addEventListener("change", saveSettings);
  if (webSearchToggle) webSearchToggle.addEventListener("change", saveSettings);

  const settingUserDisplayName = document.getElementById("settingUserDisplayName");
  const settingSoundModeSelect = document.getElementById("settingSoundModeSelect");
  const settingSongPickerGroup = document.getElementById("settingSongPickerGroup");
  const settingPickSongBtn = document.getElementById("settingPickSongBtn");
  const settingSongFileInput = document.getElementById("settingSongFileInput");
  const settingPickedSongName = document.getElementById("settingPickedSongName");
  const previewVoiceBtn = document.getElementById("previewVoiceBtn");
  const dndAllowAlarmsToggle = document.getElementById("dndAllowAlarmsToggle");

  if (settingUserDisplayName) settingUserDisplayName.addEventListener("change", saveSettings);
  if (dndAllowAlarmsToggle) dndAllowAlarmsToggle.addEventListener("change", saveSettings);

  if (settingSoundModeSelect) {
    settingSoundModeSelect.addEventListener("change", () => {
      if (settingSongPickerGroup) {
        settingSongPickerGroup.style.display = (settingSoundModeSelect.value === "song") ? "block" : "none";
      }
      saveSettings();
    });
  }

  if (settingPickSongBtn && settingSongFileInput) {
    settingPickSongBtn.addEventListener("click", () => {
      settingSongFileInput.click();
    });
    settingSongFileInput.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) {
        if (settingPickedSongName) {
          settingPickedSongName.textContent = file.name;
        }
        const reader = new FileReader();
        reader.onload = function(evt) {
          window._customSongUri = evt.target.result;
          saveSettings();
          showToast(`🎵 Custom song selected: ${file.name}`);
        };
        reader.readAsDataURL(file);
      }
    });
  }

  if (previewVoiceBtn) {
    previewVoiceBtn.addEventListener("click", () => {
      const name = (settingUserDisplayName && settingUserDisplayName.value.trim()) || "Friend";
      const sampleText = `Hey ${name}, it is time to write your notes`;

      if (window.Capacitor && window.Capacitor.isPluginAvailable("SinbhaNative")) {
        try {
          window.Capacitor.Plugins.SinbhaNative.previewSpeechVoice({ text: sampleText });
          showToast("🔊 Playing voice preview...");
          return;
        } catch (e) {}
      }

      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(sampleText);
        utterance.rate = 0.95;
        utterance.pitch = 1.05;
        window.speechSynthesis.speak(utterance);
        showToast("🔊 Playing voice preview...");
      } else {
        showToast("⚠️ Speech synthesis not supported on this device.");
      }
    });
  }

  // Desktop toggles
  if (dndToggle) {
    dndToggle.addEventListener("change", async () => {
      if (window.electronAPI) {
        await window.electronAPI.setDnd(dndToggle.checked);
        showToast(dndToggle.checked ? "🔕 Do Not Disturb enabled" : "🔔 Do Not Disturb disabled");
      }
    });
  }
  if (startWithWindowsToggle) {
    startWithWindowsToggle.addEventListener("change", async () => {
      if (window.electronAPI) {
        await window.electronAPI.setStartWithWindows(startWithWindowsToggle.checked);
        showToast(startWithWindowsToggle.checked ? "🚀 Start with Windows enabled" : "Start with Windows disabled");
      }
    });
  }

  // ========================================================
  // FLYING BIRD REMINDER CONTROLLER (STEP 6B)
  // ========================================================
  async function checkDueReminders() {
    if (remindersPaused) return;
    // If the bird is already active on screen, don't trigger another one simultaneously
    if (birdReminderContainer && birdReminderContainer.style.display !== "none") return;

    try {
      // Send device timezone offset in minutes
      const tzOffset = new Date().getTimezoneOffset();
      const res = await fetch(`/api/reminders/check?tz_offset_minutes=${tzOffset}`);
      if (!res.ok) return;
      const data = await res.json();

      if (data.reminder_needed && data.task) {
        triggerBirdFlight(data.task, data.reminder_id, data.is_explicit);
      }
    } catch (e) {
      console.error("Check due reminders error:", e);
    }
  }

  // Bird Dragging State
  let isDraggingWebBird = false;
  let hasDraggedWebBird = false;
  let webMouseStartX = 0;
  let webMouseStartY = 0;
  let webBirdStartX = 0;
  let webBirdStartY = 0;
  let isWebBirdFlyingReverse = false;

  function repositionWebPopup(birdX, birdY) {
    if (!birdActionPopup) return;
    const popupWidth = 320;
    const popupHeight = 180;
    let left = birdX - popupWidth - 14;
    if (left < 16) {
      left = birdX + 260 + 14;
    }
    if (left + popupWidth > window.innerWidth - 16) {
      left = window.innerWidth - popupWidth - 16;
    }
    if (left < 16) left = 16;
    const top = Math.max(16, Math.min(window.innerHeight - popupHeight - 20, birdY + 10));
    birdActionPopup.style.left = `${left}px`;
    birdActionPopup.style.top = `${top}px`;
    birdActionPopup.style.right = "auto";
    birdActionPopup.style.bottom = "auto";
  }

  function triggerBirdFlight(task, reminderId, isExplicit) {
    if (remindersPaused) return;

    activeReminderTask = task;
    activeReminderId = reminderId;
    isWebBirdFlyingReverse = false;

    // Set note text
    if (birdNoteTitle) birdNoteTitle.textContent = task.title;
    const dueTxt = task.due_time ? task.due_time : (task.due_date ? task.due_date : "Today");
    if (birdNoteDue) birdNoteDue.textContent = `Due: ${dueTxt}`;

    // Set action popup text
    if (birdPopupTaskTitle) birdPopupTaskTitle.textContent = task.title;
    if (birdPopupTaskDue) {
      birdPopupTaskDue.textContent = task.due_date ? `Due: ${task.due_date}${task.due_time ? ' at ' + task.due_time : ''}` : "Pending";
    }

    // Reset popup display
    if (birdActionPopup) birdActionPopup.style.display = "none";
    if (birdSnoozeMenu) birdSnoozeMenu.style.display = "none";

    // Reset wrapper
    if (birdFlightWrapper) {
      birdFlightWrapper.classList.remove("is-flying-reverse", "is-landed");
      birdFlightWrapper.style.transform = "";
      birdFlightWrapper.style.left = "";
      birdFlightWrapper.style.top = "";
      birdFlightWrapper.style.opacity = "1";
      birdFlightWrapper.style.transition = "";
      birdFlightWrapper.style.animation = "";
    }

    // Show bird container
    if (birdReminderContainer) birdReminderContainer.style.display = "block";

    // Check prefers-reduced-motion
    const prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReducedMotion) {
      // Still landed bird in corner
      if (birdFlightWrapper) {
        birdFlightWrapper.classList.remove("is-flying");
        birdFlightWrapper.classList.add("is-landed");
      }
    } else {
      // 3D smooth curved flight
      if (birdFlightWrapper) {
        birdFlightWrapper.classList.remove("is-landed");
        birdFlightWrapper.classList.add("is-flying");

        if (birdFlightTimer) clearTimeout(birdFlightTimer);
        birdFlightTimer = setTimeout(() => {
          if (birdFlightWrapper && birdReminderContainer.style.display !== "none" && !isWebBirdFlyingReverse) {
            birdFlightWrapper.classList.remove("is-flying");
            birdFlightWrapper.classList.add("is-landed");
          }
        }, 4200);
      }
    }

    // Requirement 5: SINBHA sends a short, warm, non-guilt message when bird appears
    const warmGreetings = [
      `🕊️ A little feathered friend just arrived with a gentle note for "${task.title}" Whenever you're ready, no pressure at all.`,
      `🕊️ Your little winged buddy is here with a soft reminder about "${task.title}". Take your time, you're doing great`,
      `🕊️ A gentle check-in from your bird friend for "${task.title}" Just keeping it softly in mind whenever it suits you.`
    ];
    const greeting = warmGreetings[Math.floor(Math.random() * warmGreetings.length)];
    appendAiMessage(greeting);

    // If it was an explicit reminder, mark it fired so it doesn't repeatedly trigger
    if (reminderId || isExplicit) {
      fetch("/api/reminders/fired", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: task.id, reminder_id: reminderId })
      }).catch(console.error);
    }
  }

  // Smooth reverse flight departure when task is completed or snoozed
  function flyAwayReverseWeb(callback) {
    if (isWebBirdFlyingReverse) return;
    isWebBirdFlyingReverse = true;
    if (birdFlightTimer) clearTimeout(birdFlightTimer);

    if (birdActionPopup) birdActionPopup.style.display = "none";
    if (birdSnoozeMenu) birdSnoozeMenu.style.display = "none";

    if (birdFlightWrapper) {
      const rect = birdFlightWrapper.getBoundingClientRect();
      birdFlightWrapper.classList.remove("is-landed", "is-flying");
      birdFlightWrapper.style.animation = "none";
      birdFlightWrapper.style.left = `${rect.left}px`;
      birdFlightWrapper.style.top = `${rect.top}px`;
      birdFlightWrapper.style.transform = "none";

      birdFlightWrapper.classList.add("is-flying-reverse");

      requestAnimationFrame(() => {
        birdFlightWrapper.style.transition = "transform 1.6s cubic-bezier(0.25, 1, 0.4, 1), opacity 0.5s ease 1.1s";
        birdFlightWrapper.style.transform = "translate3d(-360px, -220px, 0) scale(0.65) rotate(-14deg)";
        birdFlightWrapper.style.opacity = "0";
      });
    }

    setTimeout(() => {
      hideBird();
      if (callback) callback();
      // Check for the next reminder in queue after 2 seconds
      setTimeout(checkDueReminders, 2000);
    }, 1650);
  }

  function hideBird() {
    if (birdFlightTimer) clearTimeout(birdFlightTimer);
    if (birdReminderContainer) birdReminderContainer.style.display = "none";
    if (birdActionPopup) birdActionPopup.style.display = "none";
    if (birdSnoozeMenu) birdSnoozeMenu.style.display = "none";
    if (birdFlightWrapper) {
      birdFlightWrapper.classList.remove("is-flying", "is-landed", "is-flying-reverse");
      birdFlightWrapper.style.transform = "";
      birdFlightWrapper.style.left = "";
      birdFlightWrapper.style.top = "";
      birdFlightWrapper.style.opacity = "1";
      birdFlightWrapper.style.transition = "";
      birdFlightWrapper.style.animation = "";
    }
    activeReminderTask = null;
    activeReminderId = null;
    isDraggingWebBird = false;
    hasDraggedWebBird = false;
    isWebBirdFlyingReverse = false;
  }

  // ========================================================
  // DRAG AND DROP BIRD WITH CURSOR (WEB)
  // ========================================================
  if (birdActor) {
    birdActor.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      if (isWebBirdFlyingReverse) return;

      isDraggingWebBird = true;
      hasDraggedWebBird = false;
      webMouseStartX = e.clientX;
      webMouseStartY = e.clientY;

      const rect = birdFlightWrapper.getBoundingClientRect();
      webBirdStartX = rect.left;
      webBirdStartY = rect.top;

      birdActor.classList.add("is-dragging");
    });

    // Tap / click bird to show popup options (only if not dragged)
    birdActor.addEventListener("click", (e) => {
      e.stopPropagation();
      if (hasDraggedWebBird) {
        hasDraggedWebBird = false;
        return;
      }
      if (!birdActionPopup) return;

      const isVisible = birdActionPopup.style.display === "block";
      if (!isVisible) {
        const rect = birdFlightWrapper.getBoundingClientRect();
        repositionWebPopup(rect.left, rect.top);
        birdActionPopup.style.display = "block";
      } else {
        birdActionPopup.style.display = "none";
        if (birdSnoozeMenu) birdSnoozeMenu.style.display = "none";
      }
    });
  }

  window.addEventListener("mousemove", (e) => {
    if (!isDraggingWebBird || !birdFlightWrapper) return;

    const dx = e.clientX - webMouseStartX;
    const dy = e.clientY - webMouseStartY;

    if (Math.hypot(dx, dy) > 5) {
      hasDraggedWebBird = true;

      birdFlightWrapper.classList.remove("is-flying", "is-landed");
      birdFlightWrapper.style.animation = "none";
      birdFlightWrapper.style.transition = "none";

      const clampedX = Math.max(-40, Math.min(window.innerWidth - 220, webBirdStartX + dx));
      const clampedY = Math.max(-20, Math.min(window.innerHeight - 240, webBirdStartY + dy));

      birdFlightWrapper.style.left = `${clampedX}px`;
      birdFlightWrapper.style.top = `${clampedY}px`;
      birdFlightWrapper.style.transform = "none";

      if (birdActionPopup && birdActionPopup.style.display === "block") {
        repositionWebPopup(clampedX, clampedY);
      }
    }
  });

  window.addEventListener("mouseup", () => {
    if (isDraggingWebBird) {
      isDraggingWebBird = false;
      if (birdActor) birdActor.classList.remove("is-dragging");
    }
  });

  if (birdClosePopupBtn) {
    birdClosePopupBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (birdActionPopup) birdActionPopup.style.display = "none";
      if (birdSnoozeMenu) birdSnoozeMenu.style.display = "none";
    });
  }

  // Done button: Marks task complete, celebrates & bird flies in reverse
  if (birdDoneBtn) {
    birdDoneBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!activeReminderTask) return;
      const task = activeReminderTask;

      try {
        await updateTaskStatus(task.id, "completed");
        appendAiMessage(`Wonderful job completing "${task.title}"! 🎉 Every step forward is a victory.`);
        showToast("Task completed!");
        flyAwayReverseWeb();
      } catch (err) {
        console.error("Mark done error:", err);
      }
    });
  }

  // Snooze dropdown toggle
  if (birdSnoozeDropdownBtn) {
    birdSnoozeDropdownBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!birdSnoozeMenu) return;
      const isVis = birdSnoozeMenu.style.display === "flex";
      birdSnoozeMenu.style.display = isVis ? "none" : "flex";
      if (!isVis && birdSnoozeMinsInput) {
        setTimeout(() => birdSnoozeMinsInput.focus(), 50);
      }
    });
  }

  // Execute Snooze
  async function executeWebSnooze(minutes) {
    if (!activeReminderTask) return;
    const task = activeReminderTask;
    const mins = parseInt(minutes, 10);
    if (!mins || isNaN(mins) || mins <= 0) return;

    try {
      await fetch("/api/reminders/snooze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: task.id, minutes: mins })
      });

      // Native Android exact alarm (survives reboot & offline)
      if (window.Capacitor && window.Capacitor.isPluginAvailable && window.Capacitor.isPluginAvailable("SinbhaNative")) {
        try {
          window.Capacitor.Plugins.SinbhaNative.snoozeLocalAlarm({
            taskId: task.id,
            taskTitle: task.title,
            minutes: mins
          });
        } catch (e) {
          console.warn("Native Android snooze failed:", e);
        }
      }

      // Native Windows Electron local timer (works offline)
      if (window.electronAPI && typeof window.electronAPI.snoozeReminder === "function") {
        try {
          window.electronAPI.snoozeReminder(task.id, mins, task.title);
        } catch (e) {
          console.warn("Electron snooze timer failed:", e);
        }
      }

      const label = mins === 60 ? "1 hour" : (mins === 1440 ? "tomorrow" : `${mins} minutes`);
      appendAiMessage(`I've snoozed "${task.title}" for ${label} Take all the time you need, the bird will rest for now.`);
      showToast(`⏰ Snoozed for ${label}`);
      flyAwayReverseWeb();
    } catch (err) {
      console.error("Snooze error:", err);
    }
  }

  // Custom Snooze submit button
  if (birdSnoozeSubmitBtn) {
    birdSnoozeSubmitBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const rawVal = birdSnoozeMinsInput ? parseInt(birdSnoozeMinsInput.value, 10) : 2;
      const mins = (!isNaN(rawVal) && rawVal > 0) ? rawVal : 2;
      executeWebSnooze(mins);
    });
  }

  if (birdSnoozeMinsInput) {
    birdSnoozeMinsInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        const rawVal = parseInt(birdSnoozeMinsInput.value, 10);
        const mins = (!isNaN(rawVal) && rawVal > 0) ? rawVal : 2;
        executeWebSnooze(mins);
      }
    });
  }

  // Quick Snooze chips
  document.querySelectorAll(".bird-snooze-option").forEach(opt => {
    opt.addEventListener("click", (e) => {
      e.stopPropagation();
      const mins = parseInt(opt.dataset.mins, 10);
      executeWebSnooze(mins);
    });
  });

  // Open Chat button
  if (birdChatBtn) {
    birdChatBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      flyAwayReverseWeb(() => {
        if (messageInput) messageInput.focus();
      });
    });
  }

  // Hide bird popup if clicking anywhere else outside
  document.addEventListener("click", (e) => {
    if (birdActionPopup && birdActionPopup.style.display === "block") {
      if (!birdActionPopup.contains(e.target) && !birdActor.contains(e.target)) {
        birdActionPopup.style.display = "none";
        if (birdSnoozeMenu) birdSnoozeMenu.style.display = "none";
      }
    }
  });

  // ========================================================
  // STEP 9: AUTHENTICATION, USER SESSION & ACCOUNT CONTROLLER
  // ========================================================

  function showAuthAlert(msg, type = "error") {
    if (!authAlert) return;
    authAlert.textContent = msg;
    authAlert.className = `auth-alert ${type}`;
    authAlert.style.display = "flex";
  }

  function hideAuthAlert() {
    if (!authAlert) return;
    authAlert.style.display = "none";
    authAlert.textContent = "";
  }

  function showAuthScreen() {
    currentUser = null;
    hideBird();
    if (appContainer) appContainer.style.display = "none";
    if (authScreen) authScreen.style.display = "flex";
    if (userHeaderPill) userHeaderPill.style.display = "none";
    if (devMemoryBtn) devMemoryBtn.style.display = "none";
    hideAuthAlert();
  }

  function showAppScreen(user) {
    currentUser = user;
    if (authScreen) authScreen.style.display = "none";
    if (appContainer) appContainer.style.display = "flex";
    if (userHeaderPill) {
      userHeaderPill.style.display = "inline-flex";
      if (headerUserEmail) headerUserEmail.textContent = user.email;
    }

    // Load user data
    checkAppInfo();
    loadChatHistory();
    loadTasks();
    loadSettings();
    checkDueReminders();
    if (typeof syncSessionWithNativeApp === "function") syncSessionWithNativeApp();
    if (typeof checkNativeCompanionSettings === "function") checkNativeCompanionSettings();
    if (typeof initDeviceChannel === "function") initDeviceChannel();
    if (typeof loadDevices === "function") loadDevices();
  }

  async function checkAuthStatus() {
    const urlParams = new URLSearchParams(window.location.search);
    const wasJustVerified = urlParams.get("verified") === "true";
    if (wasJustVerified) {
      try {
        window.history.replaceState({}, document.title, window.location.pathname);
      } catch (e) {}
    }

    try {
      const res = await fetch("/api/auth/me");
      if (res.ok) {
        const data = await res.json();
        if (data.user) {
          showAppScreen(data.user);
          if (wasJustVerified) {
            showToast("Email confirmed! Welcome to SINBHA! Let's chat!");
            setTimeout(() => {
              if (messageInput) messageInput.focus();
            }, 300);
          }
          return;
        }
      }
      showAuthScreen();
    } catch (e) {
      console.error("Auth check failed:", e);
      showAuthScreen();
    }
  }

  // Auth Tab Switchers
  if (tabLoginBtn && tabSignupBtn) {
    tabLoginBtn.addEventListener("click", () => {
      tabLoginBtn.classList.add("active");
      tabSignupBtn.classList.remove("active");
      if (loginForm) loginForm.style.display = "flex";
      if (signupForm) signupForm.style.display = "none";
      const noticeEl = document.getElementById("signupVerificationNotice");
      if (noticeEl) noticeEl.style.display = "none";
      hideAuthAlert();
    });

    tabSignupBtn.addEventListener("click", () => {
      tabSignupBtn.classList.add("active");
      tabLoginBtn.classList.remove("active");
      if (signupForm) signupForm.style.display = "flex";
      const noticeEl = document.getElementById("signupVerificationNotice");
      if (noticeEl) noticeEl.style.display = "none";
      if (loginForm) loginForm.style.display = "none";
      hideAuthAlert();
    });
  }

  // Login Form Submission
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      hideAuthAlert();

      const email = loginEmail ? loginEmail.value.trim() : "";
      const password = loginPassword ? loginPassword.value : "";
      if (!email || !password) {
        showAuthAlert("Please enter both email and password.");
        return;
      }

      const submitBtn = document.getElementById("loginSubmitBtn");
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Logging In...";
      }

      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        });
        const data = await res.json();

        if (res.ok && data.user) {
          showToast(`Welcome back, ${data.user.email}!`);
          showAppScreen(data.user);
        } else {
          showAuthAlert(data.detail || "Invalid login credentials. Please try again.");
        }
      } catch (err) {
        console.error(err);
        showAuthAlert("Could not connect to the SINBHA server. Please ensure the backend is running.");
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Log In";
        }
      }
    });
  }

  // Signup Form Submission
  if (signupForm) {
    signupForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      hideAuthAlert();

      const email = signupEmail ? signupEmail.value.trim() : "";
      const password = signupPassword ? signupPassword.value : "";
      const ageChecked = signupAgeCheck ? signupAgeCheck.checked : false;
      const termsChecked = signupTermsCheck ? signupTermsCheck.checked : false;

      if (!ageChecked) {
        showAuthAlert("You must confirm that you are 18 years of age or older.");
        return;
      }
      if (!termsChecked) {
        showAuthAlert("You must agree to the Terms of Service and Privacy Policy.");
        return;
      }
      if (!email || !password) {
        showAuthAlert("Please provide email and password.");
        return;
      }
      if (password.length < 8) {
        showAuthAlert("Password must be at least 8 characters long.");
        return;
      }

      const submitBtn = document.getElementById("signupSubmitBtn");
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Creating Account...";
      }

      try {
        const res = await fetch("/api/auth/signup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email,
            password,
            is_18_or_older: ageChecked,
            agree_terms: termsChecked,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
          })
        });
        const data = await res.json();

        if (res.ok && data.requires_verification) {
          if (signupForm) signupForm.style.display = "none";
          let noticeEl = document.getElementById("signupVerificationNotice");
          if (!noticeEl) {
            noticeEl = document.createElement("div");
            noticeEl.id = "signupVerificationNotice";
            signupForm.parentNode.insertBefore(noticeEl, signupForm.nextSibling);
          }
          noticeEl.style.display = "block";
          noticeEl.innerHTML = `
            <div style="background: #fffaf5; border: 1px solid #fed7aa; border-radius: 12px; padding: 24px; text-align: center; margin-top: 15px;">
              <div style="font-size: 36px; margin-bottom: 8px;">✉️</div>
              <h3 style="color: #ea580c; margin-bottom: 8px; font-size: 1.15rem;">Check Your Email</h3>
              <p style="color: #431407; font-size: 0.92rem; line-height: 1.5; margin-bottom: 16px;">
                We sent a confirmation link to <strong>${escapeHtml(email)}</strong>.<br/>
                Please click the link in your email to confirm your account and start chatting with SINBHA!
              </p>
              <button type="button" id="backToLoginFromVerifyBtn" class="primary-btn" style="width: 100%; padding: 10px; border-radius: 8px; font-weight: 600;">Go to Log In</button>
            </div>
          `;
          const backBtn = document.getElementById("backToLoginFromVerifyBtn");
          if (backBtn && tabLoginBtn) {
            backBtn.addEventListener("click", () => {
              tabLoginBtn.click();
              noticeEl.style.display = "none";
            });
          }
          showToast("Account created! Please check your email to confirm.");
        } else if (res.ok && data.user) {
          showToast(`Account created! Welcome to SINBHA, ${data.user.email}!`);
          showAppScreen(data.user);
        } else {
          showAuthAlert(data.detail || "Could not complete signup. Please try another email.");
        }
      } catch (err) {
        console.error(err);
        showAuthAlert("Could not connect to the SINBHA server. Please ensure the backend is running.");
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Create Account";
        }
      }
    });
  }

  // Logout Handler
  async function performLogout() {
    let devToken = null;
    if (window.Capacitor && window.Capacitor.isNativePlatform() && window.Capacitor.Plugins && window.Capacitor.Plugins.SinbhaNative) {
      try {
        const sRes = await window.Capacitor.Plugins.SinbhaNative.getSessionToken();
        if (sRes && sRes.token) devToken = sRes.token;
      } catch (e) {}
    }
    try {
      const headers = devToken ? { "X-Device-Token": devToken } : {};
      await fetch("/api/auth/logout", { method: "POST", headers });
    } catch (e) {
      console.error(e);
    }
    // Also wipe native Android keystore session
    if (window.Capacitor && window.Capacitor.isNativePlatform() && window.Capacitor.Plugins && window.Capacitor.Plugins.SinbhaNative) {
      try {
        await window.Capacitor.Plugins.SinbhaNative.clearSession();
      } catch (ce) {
        console.warn("Failed to clear native session:", ce);
      }
    }
    showToast("Logged out");
    showAuthScreen();
  }

  if (headerLogoutBtn) {
    headerLogoutBtn.addEventListener("click", performLogout);
  }

  // Terms & Privacy Modals
  if (openTermsLink) {
    openTermsLink.addEventListener("click", (e) => {
      e.preventDefault();
      if (termsModal) termsModal.style.display = "flex";
    });
  }
  if (closeTermsBtn) {
    closeTermsBtn.addEventListener("click", () => {
      if (termsModal) termsModal.style.display = "none";
    });
  }
  if (confirmTermsCloseBtn) {
    confirmTermsCloseBtn.addEventListener("click", () => {
      if (termsModal) termsModal.style.display = "none";
    });
  }

  if (openPrivacyLink) {
    openPrivacyLink.addEventListener("click", (e) => {
      e.preventDefault();
      if (privacyModal) privacyModal.style.display = "flex";
    });
  }
  if (closePrivacyBtn) {
    closePrivacyBtn.addEventListener("click", () => {
      if (privacyModal) privacyModal.style.display = "none";
    });
  }
  if (confirmPrivacyCloseBtn) {
    confirmPrivacyCloseBtn.addEventListener("click", () => {
      if (privacyModal) privacyModal.style.display = "none";
    });
  }

  // Delete Account Permanently (Requirement 8)
  if (openDeleteAccountConfirmBtn) {
    openDeleteAccountConfirmBtn.addEventListener("click", () => {
      if (deleteAccountConfirmModal) deleteAccountConfirmModal.style.display = "flex";
    });
  }

  if (cancelDeleteAccountBtn) {
    cancelDeleteAccountBtn.addEventListener("click", () => {
      if (deleteAccountConfirmModal) deleteAccountConfirmModal.style.display = "none";
    });
  }

  if (confirmDeleteAccountBtn) {
    confirmDeleteAccountBtn.addEventListener("click", async () => {
      try {
        confirmDeleteAccountBtn.disabled = true;
        confirmDeleteAccountBtn.textContent = "Deleting account...";

        const res = await fetch("/api/account/delete", { method: "POST" });
        if (res.ok) {
          if (deleteAccountConfirmModal) deleteAccountConfirmModal.style.display = "none";
          if (settingsModal) settingsModal.style.display = "none";
          if (window.Capacitor && window.Capacitor.isNativePlatform() && window.Capacitor.Plugins && window.Capacitor.Plugins.SinbhaNative) {
            try { await window.Capacitor.Plugins.SinbhaNative.clearSession(); } catch (ce) {}
          }
          showToast("Account and all data deleted permanently");
          currentUser = null;
          showAuthScreen();
        } else {
          const d = await res.json().catch(() => ({}));
          showToast(d.detail || "Could not delete account");
        }
      } catch (err) {
        console.error(err);
        showToast("Error deleting account");
      } finally {
        confirmDeleteAccountBtn.disabled = false;
        confirmDeleteAccountBtn.textContent = "Yes, Delete Account & All Data";
      }
    });
  }

    // CSRF Protection & Headers: Auto-attach X-Requested-With to all AJAX requests
    const originalFetch = window.fetch;
    window.fetch = function(url, options = {}) {
      options.headers = options.headers || {};
      if (options.headers instanceof Headers) {
        if (!options.headers.has('X-Requested-With')) {
          options.headers.append('X-Requested-With', 'XMLHttpRequest');
        }
      } else {
        options.headers['X-Requested-With'] = options.headers['X-Requested-With'] || 'XMLHttpRequest';
      }
      return originalFetch(url, options);
    };

    // Download My Data (Requirement 7)
    const downloadDataBtn = document.getElementById("downloadDataBtn");
    if (downloadDataBtn) {
      downloadDataBtn.addEventListener("click", async () => {
        try {
          downloadDataBtn.disabled = true;
          downloadDataBtn.textContent = "Downloading...";
          const res = await fetch("/api/account/export");
          if (res.ok) {
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `sinbha_export_${new Date().toISOString().slice(0, 10)}.json`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
            showToast("📥 Personal data archive downloaded!");
          } else {
            showToast("Failed to download data archive");
          }
        } catch (e) {
          showToast("Error downloading data archive");
        } finally {
          downloadDataBtn.disabled = false;
          downloadDataBtn.textContent = "📥 Download My Data (JSON Export)";
        }
      });
    }

    // Change Password Handlers (Requirement 9)
    const openChangePasswordBtn = document.getElementById("openChangePasswordBtn");
    const changePasswordModal = document.getElementById("changePasswordModal");
    const closeChangePasswordBtn = document.getElementById("closeChangePasswordBtn");
    const cancelChangePasswordBtn = document.getElementById("cancelChangePasswordBtn");
    const changePasswordForm = document.getElementById("changePasswordForm");
    const currentPasswordInput = document.getElementById("currentPasswordInput");
    const newPasswordInput = document.getElementById("newPasswordInput");

    if (openChangePasswordBtn) {
      openChangePasswordBtn.addEventListener("click", () => {
        if (changePasswordModal) {
          changePasswordModal.style.display = "flex";
          if (currentPasswordInput) currentPasswordInput.value = "";
          if (newPasswordInput) newPasswordInput.value = "";
        }
      });
    }
    if (closeChangePasswordBtn) {
      closeChangePasswordBtn.addEventListener("click", () => {
        if (changePasswordModal) changePasswordModal.style.display = "none";
      });
    }
    if (cancelChangePasswordBtn) {
      cancelChangePasswordBtn.addEventListener("click", () => {
        if (changePasswordModal) changePasswordModal.style.display = "none";
      });
    }
    if (changePasswordForm) {
      changePasswordForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const oldPass = currentPasswordInput ? currentPasswordInput.value : "";
        const newPass = newPasswordInput ? newPasswordInput.value : "";
        if (!oldPass || !newPass) return;
        try {
          const res = await fetch("/api/account/change-password", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ old_password: oldPass, new_password: newPass })
          });
          const data = await res.json();
          if (res.ok) {
            showToast("🔑 Password updated successfully!");
            if (changePasswordModal) changePasswordModal.style.display = "none";
          } else {
            showToast(data.detail || "Failed to update password");
          }
        } catch (err) {
          showToast("Error updating password");
        }
      });
    }

    // Escape key closes terms / privacy / delete / password modals
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (termsModal) termsModal.style.display = "none";
        if (privacyModal) privacyModal.style.display = "none";
        if (deleteAccountConfirmModal) deleteAccountConfirmModal.style.display = "none";
        if (changePasswordModal) changePasswordModal.style.display = "none";
      }
    });

    // ========================================================
    // ANDROID CAPACITOR NATIVE BRIDGE CONTROLLER (STEP 14)
    // ========================================================

    async function syncSessionWithNativeApp() {
      if (window.Capacitor && window.Capacitor.isNativePlatform()) {
        try {
          // Requirement 1 & 2: Pass existing token if available to renew (rolling expiry)
          let existingToken = null;
          if (window.Capacitor.Plugins && window.Capacitor.Plugins.SinbhaNative) {
            try {
              const cur = await window.Capacitor.Plugins.SinbhaNative.getSessionToken();
              if (cur && cur.token) existingToken = cur.token;
            } catch (e) {}
          }

          const devId = typeof getOrCreateDeviceId === "function" ? getOrCreateDeviceId() : null;
          const res = await fetch("/api/auth/device-token", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device_token: existingToken, device_name: "Android Phone", device_id: devId })
          });
          if (res.ok) {
            const tData = await res.json();
            let commandToken = tData.command_token;
            if (!commandToken && devId) {
              try {
                const cRes = await fetch("/api/devices/command-token", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ device_id: devId, device_name: "Android Phone" })
                });
                if (cRes.ok) {
                  const cData = await cRes.json();
                  commandToken = cData.command_token;
                }
              } catch (e) {}
            }
            if ((tData.device_token || commandToken) && window.Capacitor?.Plugins?.SinbhaNative) {
              await window.Capacitor.Plugins.SinbhaNative.syncSession({
                token: tData.device_token,
                commandToken: commandToken,
                userId: tData.user_id,
                email: tData.email,
                deviceId: devId,
                emergency_stopped: tData.emergency_stopped,
                quiet_hours: {
                  enabled: quietHoursToggle ? (quietHoursToggle.checked ? "true" : "false") : "true",
                  start: quietStartInput ? quietStartInput.value : "22:00",
                  end: quietEndInput ? quietEndInput.value : "08:00"
                }
              });
              console.log("Dedicated mobile device token & command token stored in Android encrypted keystore.");
            }
          }
        } catch (e) {
          console.warn("Native device token sync failed:", e);
        }
      }
    }

    async function checkNativeCompanionSettings() {
      const androidSec = document.getElementById("settingsAndroidSection");
      const desktopSec = document.getElementById("settingsDesktopSection");

      const isNative = window.Capacitor && window.Capacitor.isNativePlatform();
      if (isNative) {
        if (androidSec) androidSec.style.display = "block";
        if (desktopSec) desktopSec.style.display = "none";

        try {
          if (window.Capacitor.Plugins && window.Capacitor.Plugins.SinbhaNative) {
            const perms = await window.Capacitor.Plugins.SinbhaNative.checkPermissions();

            // Notifications
            const pNotif = document.getElementById("permStatusNotif");
            const bNotif = document.getElementById("reqNotifBtn");
            if (pNotif && bNotif) {
              if (perms.notifications) {
                pNotif.textContent = "✓ Granted";
                pNotif.className = "android-perm-status granted";
                bNotif.textContent = "Enabled";
                bNotif.className = "android-perm-btn granted-btn";
              } else {
                pNotif.textContent = "Action Needed";
                pNotif.className = "android-perm-status missing";
              }
            }

            // Overlay
            const pOverlay = document.getElementById("permStatusOverlay");
            const bOverlay = document.getElementById("reqOverlayBtn");
            if (pOverlay && bOverlay) {
              if (perms.overlay) {
                pOverlay.textContent = "✓ Granted";
                pOverlay.className = "android-perm-status granted";
                bOverlay.textContent = "Enabled";
                bOverlay.className = "android-perm-btn granted-btn";
              } else {
                pOverlay.textContent = "Action Needed";
                pOverlay.className = "android-perm-status missing";
              }
            }

            // Exact Alarm
            const pAlarm = document.getElementById("permStatusAlarm");
            const bAlarm = document.getElementById("reqAlarmBtn");
            if (pAlarm && bAlarm) {
              if (perms.exactAlarm) {
                pAlarm.textContent = "✓ Granted";
                pAlarm.className = "android-perm-status granted";
                bAlarm.textContent = "Enabled";
                bAlarm.className = "android-perm-btn granted-btn";
              } else {
                pAlarm.textContent = "Action Needed";
                pAlarm.className = "android-perm-status missing";
              }
            }

            // Battery Optimization
            const pBatt = document.getElementById("permStatusBattery");
            const bBatt = document.getElementById("reqBatteryBtn");
            if (pBatt && bBatt) {
              if (perms.batteryIgnored) {
                pBatt.textContent = "✓ Unrestricted";
                pBatt.className = "android-perm-status granted";
                bBatt.textContent = "Optimized Excluded";
                bBatt.className = "android-perm-btn granted-btn";
              } else {
                pBatt.textContent = "Action Needed";
                pBatt.className = "android-perm-status missing";
              }
            }

            // Android Accessibility Screen Agent (D1)
            const pAccess = document.getElementById("accessibilityStatusBadge");
            if (pAccess && window.Capacitor.Plugins.SinbhaNative.isAccessibilityServiceEnabled) {
              try {
                const accRes = await window.Capacitor.Plugins.SinbhaNative.isAccessibilityServiceEnabled();
                if (accRes && accRes.enabled) {
                  pAccess.textContent = "✓ Active";
                  pAccess.style.background = "#dcfce7";
                  pAccess.style.color = "#166534";
                  pAccess.style.border = "1px solid #86efac";
                } else {
                  pAccess.textContent = "Inactive / Action Needed";
                  pAccess.style.background = "#fee2e2";
                  pAccess.style.color = "#991b1b";
                  pAccess.style.border = "1px solid #fca5a5";
                }
              } catch (e) {
                console.warn("Could not query accessibility status:", e);
              }
            }
          }
        } catch (err) {
          console.warn("Failed checking native permissions:", err);
        }
      }
    }

    function isOlderVersion(current, minimum) {
      if (!current || !minimum) return false;
      const cParts = current.split('.').map(n => parseInt(n, 10) || 0);
      const mParts = minimum.split('.').map(n => parseInt(n, 10) || 0);
      for (let i = 0; i < Math.max(cParts.length, mParts.length); i++) {
        const c = cParts[i] || 0;
        const m = mParts[i] || 0;
        if (c < m) return true;
        if (c > m) return false;
      }
      return false;
    }

    async function checkAppVersionGate(isManual = false) {
      const checkBtn = document.getElementById("manualCheckUpdateBtn");
      const statusText = document.getElementById("updateStatusText");
      const installedText = document.getElementById("installedVersionText");
      const versionBadge = document.getElementById("currentAppVersionBadge");

      if (isManual && checkBtn) {
        checkBtn.disabled = true;
        checkBtn.textContent = "Checking...";
      }

      try {
        const res = await fetch("/api/app/version-check?t=" + Date.now(), { cache: "no-store" });
        if (!res.ok) {
          if (isManual) showToast("Could not reach update server. Please check your internet connection.");
          return;
        }
        const data = await res.json();

        // Safety guard against accidental lockout
        if (data.min_version_android && data.latest_version_android) {
          if (isOlderVersion(data.latest_version_android, data.min_version_android)) {
            console.warn("⚠️ [SAFETY LOCKOUT PREVENTED] min_version_android cannot exceed latest_version_android. Ignoring check.");
            return;
          }
        }

        let isNative = false;
        let current = "1.0.7";
        let minRequired = "1.0.0";
        let latestAvail = "1.0.7";
        let downloadUrl = "";
        let platformName = "Web";

        if (window.electronAPI && typeof window.electronAPI.getAppStatus === "function") {
          isNative = true;
          platformName = "Windows";
          minRequired = data.min_version_desktop || "1.0.0";
          latestAvail = data.latest_version_desktop || "1.0.7";
          downloadUrl = data.download_url_desktop || "/api/app/download/desktop";
          try {
            const st = await window.electronAPI.getAppStatus();
            current = (st && st.version) ? st.version : "1.0.7";
          } catch (e) {
            current = "1.0.7";
          }
        } else if (window.Capacitor && (window.Capacitor.isNativePlatform() || (typeof window.Capacitor.isPluginAvailable === "function" && window.Capacitor.isPluginAvailable("SinbhaNative")))) {
          isNative = true;
          platformName = "Android";
          minRequired = data.min_version_android || "1.0.0";
          latestAvail = data.latest_version_android || "1.0.7";
          downloadUrl = data.download_url_android || "/api/app/download/android";
          try {
            if (window.Capacitor.Plugins && window.Capacitor.Plugins.SinbhaNative && typeof window.Capacitor.Plugins.SinbhaNative.getAppVersion === "function") {
              const vInfo = await window.Capacitor.Plugins.SinbhaNative.getAppVersion();
              current = (vInfo && vInfo.versionName) ? vInfo.versionName : "1.0.7";
            }
          } catch (e) {
            current = "1.0.7";
          }
        } else {
          // Web Client / Mobile Browser
          const isAndroidDevice = /Android/i.test(navigator.userAgent || "");
          if (isAndroidDevice) {
            platformName = "Android (Web)";
            minRequired = data.min_version_android || "1.0.0";
            latestAvail = data.latest_version_android || "1.0.7";
            downloadUrl = data.download_url_android || "/api/app/download/android";
          } else {
            platformName = "Web";
            minRequired = data.min_version_desktop || "1.0.0";
            latestAvail = data.latest_version_desktop || "1.0.7";
            downloadUrl = data.download_url_desktop || "/api/app/download/desktop";
          }
        }

        // Update settings card badges
        if (versionBadge) versionBadge.textContent = `v${current}`;
        if (installedText) installedText.textContent = `SINBHA ${platformName} (v${current})`;

        const isMandatory = isOlderVersion(current, minRequired);
        const isUpdateAvailable = isOlderVersion(current, latestAvail);

        const topBanner = document.getElementById("newVersionBanner");
        const topBannerText = document.getElementById("newVersionBannerText");
        const topBannerLink = document.getElementById("newVersionBannerDownloadBtn");

        if (isMandatory || isUpdateAvailable) {
          if (statusText) {
            statusText.textContent = `⚡ Update available: v${latestAvail}`;
            statusText.style.color = "#d97706";
          }

          if (topBanner) {
            topBanner.style.display = "flex";
            if (topBannerText) topBannerText.textContent = `v${latestAvail} is ready to install (current: v${current}).`;
            if (topBannerLink) topBannerLink.href = downloadUrl;
          }

          const gateModal = document.getElementById("appUpdateGateModal");
          const gateTitle = document.getElementById("appUpdateGateTitle");
          const gateDesc = document.getElementById("appUpdateGateDesc");
          const gateLink = document.getElementById("appUpdateDownloadLink");
          const laterBtn = document.getElementById("appUpdateLaterBtn");

          if (gateModal && (isMandatory || isManual)) {
            gateModal.style.display = "flex";
            if (gateTitle) {
              gateTitle.textContent = isMandatory ? `Update Required for ${platformName} 🐘` : `New ${platformName} Version Available! 🐘`;
            }
            if (gateDesc) {
              gateDesc.innerHTML = isMandatory
                ? `SINBHA v${minRequired} is required to continue.<br>Your installed app (v${current}) is outdated. Please update now to continue using remote commands.`
                : `A newer version of SINBHA (v${latestAvail}) is available. 🐘<br>You have v${current}. Tap "Update Now" to get the latest companion features!`;
            }
            if (gateLink) {
              gateLink.href = downloadUrl;
              gateLink.onclick = (e) => {
                if (window.electronAPI && typeof window.electronAPI.openExternalUrl === "function") {
                  e.preventDefault();
                  window.electronAPI.openExternalUrl(downloadUrl);
                  showToast("Opening update download in your browser... 🐘");
                  gateModal.style.display = "none";
                }
              };
            }
            if (laterBtn) {
              laterBtn.style.display = "block";
              laterBtn.textContent = "Maybe Later / Continue to App 🐘";
              laterBtn.onclick = () => {
                gateModal.style.display = "none";
              };
            }
          }
          if (isManual) {
            showToast(`⚡ New version v${latestAvail} is available!`);
          }
        } else {
          if (topBanner) topBanner.style.display = "none";
          if (statusText) {
            statusText.textContent = `● You're already up to date (v${current}) ✨`;
            statusText.style.color = "#16a34a";
          }
          if (isManual) {
            showToast(`You're up to date! SINBHA is running the latest version (v${current}).`);
          }
        }
      } catch (e) {
        console.warn("Version check failed:", e);
        if (isManual) showToast("Could not complete version check. Please try again.");
      } finally {
        if (checkBtn) {
          checkBtn.disabled = false;
          checkBtn.innerHTML = "🔄 Check for Updates";
        }
      }
    }

    // Bind Android Settings Button Click Handlers
    const bindNativeAction = (btnId, permType) => {
      const btn = document.getElementById(btnId);
      if (btn) {
        btn.addEventListener("click", async () => {
          if (window.Capacitor?.Plugins?.SinbhaNative) {
            await window.Capacitor.Plugins.SinbhaNative.requestPermission({ type: permType });
            setTimeout(checkNativeCompanionSettings, 1000);
          }
        });
      }
    };

    bindNativeAction("reqNotifBtn", "notifications");
    bindNativeAction("reqOverlayBtn", "overlay");
    bindNativeAction("reqAlarmBtn", "exactAlarm");
    bindNativeAction("reqBatteryBtn", "battery");
    bindNativeAction("reqAutostartBtn", "autostart");

    const enableAccessibilityBtn = document.getElementById("enableAccessibilityBtn");
    if (enableAccessibilityBtn) {
      enableAccessibilityBtn.addEventListener("click", async () => {
        if (window.Capacitor?.Plugins?.SinbhaNative?.openAccessibilitySettings) {
          try {
            await window.Capacitor.Plugins.SinbhaNative.openAccessibilitySettings();
            setTimeout(checkNativeCompanionSettings, 1000);
          } catch (e) {
            console.warn("Failed to open accessibility settings:", e);
          }
        } else {
          showToast("Accessibility controls are available in the Android companion app.");
        }
      });
    }

    const openAppDetailsBtn = document.getElementById("openAppDetailsBtn");
    if (openAppDetailsBtn) {
      openAppDetailsBtn.addEventListener("click", async () => {
        if (window.Capacitor?.Plugins?.SinbhaNative?.openAppDetailsSettings) {
          try {
            await window.Capacitor.Plugins.SinbhaNative.openAppDetailsSettings();
          } catch (e) {
            console.warn("Failed to open app details:", e);
          }
        } else {
          showToast("Available on Android companion app.");
        }
      });
    }

    const testBirdNativeBtn = document.getElementById("testBirdNativeBtn");
    if (testBirdNativeBtn) {
      testBirdNativeBtn.addEventListener("click", async () => {
        if (window.Capacitor?.Plugins?.SinbhaNative) {
          await window.Capacitor.Plugins.SinbhaNative.testBird({
            title: "Evening companion check-in",
            dueText: "Due right now"
          });
          showToast("🕊️ Flying companion bird launched!");
        } else {
          showToast("Available on Android APK");
        }
      });
    }

    const syncRemindersNativeBtn = document.getElementById("syncRemindersNativeBtn");
    if (syncRemindersNativeBtn) {
      syncRemindersNativeBtn.addEventListener("click", async () => {
        if (window.Capacitor?.Plugins?.SinbhaNative) {
          await window.Capacitor.Plugins.SinbhaNative.syncReminders();
          showToast("🔄 Exact alarms scheduled with system!");
        }
      });
    }

    // Handle deep-link event to open task chat from bird or notification
    window.addEventListener("sinbha:openTaskChat", (ev) => {
      const detail = ev.detail || {};
      const taskId = detail.taskId;
      if (taskId) {
        showToast(`Opening chat for task #${taskId}`);
        if (messageInput) {
          messageInput.value = `Tell me about my task #${taskId}`;
          messageInput.focus();
        }
      }
    });

    // ========================================================
    // COMPANION DIAGNOSTICS CONTROLLER (REQUIREMENT 6)
    // ========================================================
    let cachedDiagnosticsText = "";

    async function loadCompanionDiagnostics() {
      const display = document.getElementById("diagnosticsDisplay");
      if (!display) return;
      display.textContent = "Loading companion diagnostics...";

      try {
        let diag = null;
        if (window.Capacitor && window.Capacitor.isNativePlatform() && window.Capacitor.Plugins && window.Capacitor.Plugins.SinbhaNative) {
          diag = await window.Capacitor.Plugins.SinbhaNative.getDiagnostics();
        }
        let electronStatus = null;
        if (window.electronAPI && typeof window.electronAPI.getAppStatus === "function") {
          try {
            electronStatus = await window.electronAPI.getAppStatus();
          } catch (e) {
            console.warn("Could not fetch electron status:", e);
          }
        }

        const lines = [];
        lines.push("=== SINBHA COMPANION DIAGNOSTICS ===");
        lines.push(`Generated: ${new Date().toISOString()}`);
        const isCapacitor = !!(window.Capacitor && window.Capacitor.isNativePlatform());
        const isElectron = !!window.electronAPI;
        lines.push(`Platform: ${isCapacitor ? "Android Native (Capacitor)" : (isElectron ? "Windows Desktop (Electron)" : "Web Browser")}`);

        // Step C2.10: Display Native App Version and Web Client Version separately
        let nativeVer = "None (Pure Web Client)";
        if (isElectron && electronStatus) {
          nativeVer = `v${electronStatus.version || "1.4.25"} (Windows Electron)`;
        } else if (diag) {
          nativeVer = `v${diag.versionName || "1.4.25"} (Android Native, versionCode: ${diag.versionCode || 52})`;
        }
        lines.push(`Native App Version: ${nativeVer}`);
        lines.push(`Web Client Version: v1.4.25`);

        if (isElectron && electronStatus) {
          lines.push(`Backend URL: ${electronStatus.backendUrl || "Configured"}`);
          lines.push(`Reminders Paused: ${electronStatus.paused ? "Yes" : "No"}`);
          lines.push(`DND: ${electronStatus.dnd ? "Enabled" : "Disabled"}`);
          lines.push(`Start with Windows: ${electronStatus.startWithWindows ? "Enabled" : "Disabled"}`);
        }
        if (isElectron && window.electronAPI && typeof window.electronAPI.getInstalledApps === "function") {
          try {
            const winApps = await window.electronAPI.getInstalledApps();
            lines.push(`Installed Apps (Windows): ${winApps ? winApps.length : 0}`);
          } catch (e) {}
        } else if (diag) {
          if (diag.deviceInfo) {
            lines.push(`Device: ${diag.deviceInfo.manufacturer} ${diag.deviceInfo.brand} ${diag.deviceInfo.model} (SDK ${diag.deviceInfo.androidSdk})`);
          }
          lines.push(`Device Token: ${diag.tokenStatus}`);
          lines.push(`Last Sync Time: ${diag.lastSyncTime}`);
          
          lines.push("\n--- COMMAND CHANNEL (C2.6) ---");
          const cmdChan = diag.commandChannel || {};
          const isWs = diag.wsConnected || cmdChan.wsConnected;
          lines.push(`• WebSocket: ${isWs ? "CONNECTED (Real-time native WebSocket)" : "DISCONNECTED (Polling fallback active)"}`);
          if (diag.lastWsError && diag.lastWsError !== "None") {
            lines.push(`  WS Error: ${diag.lastWsError}`);
          }
          const pTime = diag.lastPollTime || cmdChan.lastPollTime || "Never polled";
          const hStatus = diag.lastHttpStatus !== undefined ? diag.lastHttpStatus : (cmdChan.lastHttpStatus !== undefined ? cmdChan.lastHttpStatus : -1);
          const lastErr = diag.lastError || cmdChan.lastError;
          const statusDesc = (hStatus >= 200 && hStatus <= 299) ? `HTTP ${hStatus} (OK)` : (hStatus === -1 ? "Offline / Network timeout" : `HTTP ${hStatus} (ERROR)`);
          lines.push(`• Last Poll: ${pTime} [${statusDesc}]`);
          if (lastErr && lastErr !== "None") {
            lines.push(`• Last Poll Error: ${lastErr}`);
          }

          if (diag.isOnePlusOppo || cmdChan.isOnePlusOppo) {
            lines.push("\n--- ONEPLUS / OPPO (COLOROS / OXYGENOS) GUIDANCE ---");
            lines.push(diag.backgroundGuidance || cmdChan.backgroundGuidance || "1) App Info -> Battery -> Allow background activity & Auto-launch. 2) Settings -> Battery -> Don't optimize. 3) Recents -> Lock SINBHA.");
          }

          lines.push("\n--- PERMISSIONS ---");
          lines.push(`• Floating Bird Overlay: ${diag.permissions?.overlay ? "GRANTED" : "ACTION NEEDED"}`);
          lines.push(`• Notifications: ${diag.permissions?.notifications ? "GRANTED" : "ACTION NEEDED"}`);
          lines.push(`• Exact Alarms: ${diag.permissions?.exactAlarm ? "GRANTED" : "ACTION NEEDED"}`);
          lines.push(`• Battery Optimization: ${diag.permissions?.batteryIgnored ? "UNRESTRICTED (Excluded)" : "OPTIMIZED (May throttle)"}`);

          lines.push("\n--- SCHEDULED EXACT ALARMS ---");
          if (diag.scheduledAlarms && diag.scheduledAlarms.length > 0) {
            diag.scheduledAlarms.forEach((a, idx) => {
              lines.push(`${idx + 1}. [${a.time}] ${a.taskTitle} (${a.label || 'Task'})`);
            });
          } else {
            lines.push("None scheduled currently in local cache.");
          }

          lines.push("\n--- RECENT ERRORS (LAST 20) ---");
          if (diag.recentErrors && diag.recentErrors.length > 0) {
            diag.recentErrors.forEach((e, idx) => {
              lines.push(`[${e.time}] ${e.message}`);
            });
          } else {
            lines.push("No errors logged. All systems operating smoothly");
          }
        } else {
          // Web / Desktop fallback
          lines.push(`Client: Browser / Desktop Webview`);
          lines.push(`App Version: v1.4.25`);
          lines.push(`Online: ${navigator.onLine ? "Yes" : "No"}`);
          lines.push(`Timezone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}`);
          lines.push(`User Agent: ${navigator.userAgent}`);
          lines.push(`Auth: ${currentUser ? "Logged in" : "Not logged in"}`);
        }

        // Step C2.9 Item 1: Command Trace (local only, no private text)
        let commandTraces = [];
        if (window.electronAPI && typeof window.electronAPI.getCommandTrace === "function") {
          try {
            commandTraces = (await window.electronAPI.getCommandTrace()) || [];
          } catch (e) {
            console.warn("Failed to get Electron command trace:", e);
          }
        } else if (window.Capacitor && window.Capacitor.isPluginAvailable && window.Capacitor.isPluginAvailable("SinbhaNative")) {
          try {
            const trRes = await window.Capacitor.Plugins.SinbhaNative.getCommandTrace();
            commandTraces = (trRes && trRes.traces) ? trRes.traces : [];
          } catch (e) {
            console.warn("Failed to get Android command trace:", e);
          }
        }

        lines.push("\n--- RECENT COMMAND TRACE (LOCAL ONLY, STEP C2.9) ---");
        if (commandTraces && commandTraces.length > 0) {
          commandTraces.forEach((t, i) => {
            const cmdId = t.command_id || t.id || "N/A";
            const cmdType = t.type || "unknown";
            const rxTime = t.time_received || "unknown";
            const handler = t.handler || "unknown";
            const resOrErr = typeof t.result_or_error === "object" ? JSON.stringify(t.result_or_error) : (t.result_or_error || "none");
            const sentTime = t.time_sent || "in_progress";
            lines.push(`${i + 1}. [${rxTime}] id=${cmdId} type=${cmdType}`);
            lines.push(`   handler: ${handler}`);
            lines.push(`   result: ${resOrErr}`);
            lines.push(`   sent_at: ${sentTime}`);
          });
        } else {
          lines.push("No remote commands processed on this local device yet.");
        }

        cachedDiagnosticsText = lines.join("\n");
        display.textContent = cachedDiagnosticsText;
      } catch (err) {
        display.textContent = "Error gathering diagnostics: " + err.message;
        cachedDiagnosticsText = display.textContent;
      }
    }

    const refreshDiagBtn = document.getElementById("refreshDiagnosticsBtn");
    if (refreshDiagBtn) {
      refreshDiagBtn.addEventListener("click", loadCompanionDiagnostics);
    }

    const copyDiagBtn = document.getElementById("copyDiagnosticsBtn");
    if (copyDiagBtn) {
      copyDiagBtn.addEventListener("click", async () => {
        if (!cachedDiagnosticsText) {
          await loadCompanionDiagnostics();
        }
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(cachedDiagnosticsText);
          } else {
            const ta = document.createElement("textarea");
            ta.value = cachedDiagnosticsText;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand("copy");
            document.body.removeChild(ta);
          }
          showToast("📋 Diagnostics copied to clipboard (safe / no personal data)");
        } catch (e) {
          showToast("Could not copy diagnostics: " + e.message);
        }
      });
    }

    // Step C2.10 Item 1: One-Button "Real device check"
    const btnRealDeviceCheck = document.getElementById("btnRealDeviceCheck");
    const realDeviceResultsContainer = document.getElementById("realDeviceCheckResultsContainer");
    const realDeviceSummaryBadge = document.getElementById("realDeviceSummaryBadge");
    const realDeviceResultsList = document.getElementById("realDeviceResultsList");

    if (btnRealDeviceCheck) {
      btnRealDeviceCheck.addEventListener("click", async () => {
        btnRealDeviceCheck.disabled = true;
        const chkDelay = document.getElementById("chkDelay20s");
        const delaySeconds = (chkDelay && chkDelay.checked) ? 20 : 0;

        if (realDeviceResultsContainer) realDeviceResultsContainer.style.display = "block";
        if (realDeviceSummaryBadge) {
          realDeviceSummaryBadge.textContent = delaySeconds > 0 ? "Countdown..." : "Testing...";
          realDeviceSummaryBadge.style.background = "#dbeafe";
          realDeviceSummaryBadge.style.color = "#1e40af";
        }

        if (delaySeconds > 0) {
          for (let sec = delaySeconds; sec > 0; sec--) {
            btnRealDeviceCheck.textContent = `🌙 Lock phone now! Starting in ${sec}s...`;
            if (realDeviceResultsList) {
              realDeviceResultsList.innerHTML = `<div style="color: #2563eb; font-weight: 600;">🔒 Lock your phone now! Commands run in ${sec} seconds...</div>`;
            }
            await new Promise(r => setTimeout(r, 1000));
          }
        }

        btnRealDeviceCheck.textContent = "⏳ Running Real Device Check (6 Apps)...";
        if (realDeviceSummaryBadge) realDeviceSummaryBadge.textContent = "Testing...";
        if (realDeviceResultsList) {
          realDeviceResultsList.innerHTML = '<div style="color: #6b7280; font-style: italic;">Sending 6 commands through chat path to all connected devices...</div>';
        }

        try {
          const res = await fetch("/api/devices/real-device-check", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rounds: 1, delay_seconds: delaySeconds })
          });
          const data = await res.json();

          if (!data.success) {
            if (realDeviceSummaryBadge) {
              realDeviceSummaryBadge.textContent = data.error || "Failed";
              realDeviceSummaryBadge.style.background = "#fee2e2";
              realDeviceSummaryBadge.style.color = "#991b1b";
            }
            if (realDeviceResultsList) {
              realDeviceResultsList.innerHTML = `<div style="color: #ef4444; font-weight: 600;">${escapeHtml(data.message || data.error || "Device check failed")}</div>`;
            }
            return;
          }

          const devices = data.devices || [];
          if (devices.length === 0) {
            if (realDeviceSummaryBadge) {
              realDeviceSummaryBadge.textContent = "No Devices";
              realDeviceSummaryBadge.style.background = "#fee2e2";
              realDeviceSummaryBadge.style.color = "#991b1b";
            }
            if (realDeviceResultsList) {
              realDeviceResultsList.innerHTML = '<div style="color: #ef4444;">No trusted devices found. Please register or connect your laptop or phone first.</div>';
            }
            return;
          }

          let totalCommands = 0;
          let totalSuccess = 0;

          const deviceBlocksHtml = devices.map(d => {
            const cmds = d.commands || [];
            totalCommands += cmds.length;
            const cmdRows = cmds.map(c => {
              // Step C2.10 Item 2: Real apps pass ONLY on "succeeded". Nonexistent app passes ONLY on "not_installed".
              // A timeout is ALWAYS a failure.
              const isNonexistent = c.app === "nonexistent_test_app_xyz";
              const isOk = c.passed === true || (isNonexistent ? c.result === "not_installed" : c.result === "succeeded");
              if (isOk) totalSuccess++;

              const icon = isOk ? "✅" : "❌";
              const badgeBg = isOk ? "#dcfce7" : "#fee2e2";
              const badgeColor = isOk ? "#166534" : "#991b1b";

              // Step C2.10 & C2.11 Item 3: Render stage table for every command (passed or failed) with real command_id
              let stageTableHtml = "";
              if (c.stage_table && Array.isArray(c.stage_table) && c.stage_table.length > 0) {
                const stageRows = c.stage_table.map(s => {
                  const isFail = s.is_failure_point;
                  const rowBg = isFail ? "#fef2f2" : "#ffffff";
                  const textCol = isFail ? "#991b1b" : "#374151";
                  const statusCol = s.status === "OK" ? "#166534" : "#dc2626";
                  return `
                    <tr style="background: ${rowBg}; border-bottom: 1px solid #e5e7eb;">
                      <td style="padding: 2px 4px; font-weight: ${isFail ? '700' : 'normal'}; color: ${textCol};">${escapeHtml(s.description)}</td>
                      <td style="padding: 2px 4px; font-weight: 700; color: ${statusCol};">${escapeHtml(s.status)}</td>
                      <td style="padding: 2px 4px; font-family: monospace; font-size: 0.68rem; color: #6b7280;">${s.timestamp ? escapeHtml(s.timestamp) : '—'}</td>
                    </tr>
                  `;
                }).join("");

                const failureHeader = (!isOk && c.first_missing_stage) ? `
                  <div style="color: #991b1b; font-weight: 700; font-size: 0.72rem; margin-bottom: 3px;">
                    ⚠️ Failure point: missing stage <code>${escapeHtml(c.first_missing_stage)}</code>
                  </div>` : "";

                stageTableHtml = `
                  <div style="margin-top: 6px; padding: 6px; background: ${isOk ? '#f0fdf4' : '#fff5f5'}; border: 1px solid ${isOk ? '#bbf7d0' : '#fecaca'}; border-radius: 6px;">
                    ${failureHeader}
                    <div style="font-size: 0.68rem; color: #6b7280; margin-bottom: 3px;">Command ID: <code>${escapeHtml(c.command_id || 'N/A')}</code></div>
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.70rem;">
                      <thead>
                        <tr style="text-align: left; background: #f3f4f6; border-bottom: 1px solid #d1d5db;">
                          <th style="padding: 2px 4px;">Stage</th>
                          <th style="padding: 2px 4px;">Status</th>
                          <th style="padding: 2px 4px;">Timestamp</th>
                        </tr>
                      </thead>
                      <tbody>${stageRows}</tbody>
                    </table>
                  </div>
                `;
              }

              return `
                <div style="background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 6px 10px; margin-bottom: 4px;">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <strong style="color: #1f2937;">${icon} ${escapeHtml(c.app)}</strong>
                    <span style="font-size: 0.72rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: ${badgeBg}; color: ${badgeColor};">${escapeHtml(c.result.toUpperCase())} (${c.time_taken_ms}ms)</span>
                  </div>
                  <div style="font-size: 0.72rem; color: #4b5563; margin-top: 2px;">
                    Sent: ${c.sent ? "Yes" : "No"} | Received: ${c.received ? "Yes" : "No"} | Started: ${c.started ? "Yes" : "No"} | ID: <code>${escapeHtml(c.command_id || '')}</code>
                  </div>
                  <div style="font-size: 0.70rem; color: #6b7280; font-family: monospace; margin-top: 2px;">
                    ${escapeHtml(c.message || '')}
                  </div>
                  ${stageTableHtml}
                </div>
              `;
            }).join("");

            return `
              <div style="margin-bottom: 12px; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px; background: #f9fafb;">
                <div style="font-weight: 700; color: #1e3a8a; margin-bottom: 6px;">
                  📱 ${escapeHtml(d.name)} (${escapeHtml(d.platform)}) [v${escapeHtml(d.client_version || 'unknown')}]
                </div>
                ${cmdRows}
              </div>
            `;
          }).join("");

          if (realDeviceResultsList) {
            realDeviceResultsList.innerHTML = deviceBlocksHtml;
          }
          if (realDeviceSummaryBadge) {
            const allPassed = (totalSuccess === totalCommands) && (totalCommands > 0);
            realDeviceSummaryBadge.textContent = `${totalSuccess}/${totalCommands} Verified`;
            realDeviceSummaryBadge.style.background = allPassed ? "#dcfce7" : "#fee2e2";
            realDeviceSummaryBadge.style.color = allPassed ? "#166534" : "#991b1b";
          }

          // Refresh Diagnostics display with the updated trace
          await loadCompanionDiagnostics();
        } catch (err) {
          if (realDeviceSummaryBadge) {
            realDeviceSummaryBadge.textContent = "Error";
            realDeviceSummaryBadge.style.background = "#fee2e2";
            realDeviceSummaryBadge.style.color = "#991b1b";
          }
          if (realDeviceResultsList) {
            realDeviceResultsList.innerHTML = `<div style="color: #ef4444;">Real device check failed: ${escapeHtml(err.message)}</div>`;
          }
        } finally {
          btnRealDeviceCheck.disabled = false;
          btnRealDeviceCheck.textContent = "🔍 Run Real Device Check (Cross-Device 6-App Test)";
        }
      });
    }

    // Milestone M1+M2 Item 1: Background Launch Test Runner
    const btnBackgroundLaunchTest = document.getElementById("btnBackgroundLaunchTest");
    const bgLaunchResultsContainer = document.getElementById("bgLaunchResultsContainer");
    const bgLaunchSummaryBadge = document.getElementById("bgLaunchSummaryBadge");
    const bgLaunchDeviceInfo = document.getElementById("bgLaunchDeviceInfo");
    const bgLaunchResultsList = document.getElementById("bgLaunchResultsList");

    if (btnBackgroundLaunchTest) {
      btnBackgroundLaunchTest.addEventListener("click", async () => {
        btnBackgroundLaunchTest.disabled = true;
        const chkDelay = document.getElementById("chkDelay20s");
        const delaySeconds = (chkDelay && chkDelay.checked) ? 20 : 0;

        if (bgLaunchResultsContainer) bgLaunchResultsContainer.style.display = "block";
        if (bgLaunchSummaryBadge) {
          bgLaunchSummaryBadge.textContent = delaySeconds > 0 ? "Countdown..." : "Testing...";
          bgLaunchSummaryBadge.style.background = "#dbeafe";
          bgLaunchSummaryBadge.style.color = "#1e40af";
        }

        if (delaySeconds > 0) {
          for (let sec = delaySeconds; sec > 0; sec--) {
            btnBackgroundLaunchTest.textContent = `🌙 Lock phone now! Starting in ${sec}s...`;
            if (bgLaunchResultsList) {
              bgLaunchResultsList.innerHTML = `<div style="color: #059669; font-weight: 600;">🔒 Screen-off mode: Lock your phone now! Starting in ${sec}s...</div>`;
            }
            await new Promise(r => setTimeout(r, 1000));
          }
        }

        btnBackgroundLaunchTest.textContent = "⏳ Testing Background Launch Routes...";
        if (bgLaunchSummaryBadge) bgLaunchSummaryBadge.textContent = "Testing...";
        if (bgLaunchResultsList) {
          bgLaunchResultsList.innerHTML = '<div style="color: #6b7280; font-style: italic;">Testing app, settings, url, and deep link via route ladder...</div>';
        }

        try {
          const res = await fetch("/api/devices/background-launch-test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ delay_seconds: delaySeconds })
          });
          const data = await res.json();

          if (!data.success) {
            if (bgLaunchSummaryBadge) {
              bgLaunchSummaryBadge.textContent = data.error || "Failed";
              bgLaunchSummaryBadge.style.background = "#fee2e2";
              bgLaunchSummaryBadge.style.color = "#991b1b";
            }
            if (bgLaunchResultsList) {
              bgLaunchResultsList.innerHTML = `<div style="color: #ef4444; font-weight: 600;">${escapeHtml(data.message || data.error || "Background test failed")}</div>`;
            }
            return;
          }

          if (bgLaunchDeviceInfo) {
            bgLaunchDeviceInfo.textContent = `📱 ${data.phone_model} (Android ${data.android_version}, API ${data.sdk_int}) — Device: ${data.device_name}`;
          }

          const results = data.results || [];
          let passedCount = 0;
          const rowsHtml = results.map(r => {
            const isOk = r.status === "succeeded" || r.status === "needs_tap" || r.status === "sent_not_verified";
            if (r.status === "succeeded") passedCount++;
            const icon = r.status === "succeeded" ? "✅" : (r.status === "needs_tap" ? "🔔" : "⚠️");
            const badgeBg = r.status === "succeeded" ? "#dcfce7" : (r.status === "needs_tap" ? "#fef3c7" : "#fee2e2");
            const badgeCol = r.status === "succeeded" ? "#166534" : (r.status === "needs_tap" ? "#92400e" : "#991b1b");
            return `
              <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 6px 8px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                  <span style="font-weight: 600; color: #1f2937;">${icon} ${escapeHtml(r.name)}</span>
                  <div style="font-size: 0.72rem; color: #6b7280;">Route: <strong style="color: #4b5563;">${escapeHtml(r.route_used)}</strong> (${r.elapsed_ms}ms)</div>
                </div>
                <span style="font-size: 0.72rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: ${badgeBg}; color: ${badgeCol};">
                  ${escapeHtml(r.status)}
                </span>
              </div>
            `;
          }).join("");

          if (bgLaunchResultsList) {
            bgLaunchResultsList.innerHTML = rowsHtml;
          }

          if (bgLaunchSummaryBadge) {
            bgLaunchSummaryBadge.textContent = `${passedCount}/${results.length} Verified`;
            bgLaunchSummaryBadge.style.background = passedCount === results.length ? "#dcfce7" : "#fee2e2";
            bgLaunchSummaryBadge.style.color = passedCount === results.length ? "#166534" : "#991b1b";
          }
        } catch (err) {
          if (bgLaunchSummaryBadge) {
            bgLaunchSummaryBadge.textContent = "Error";
            bgLaunchSummaryBadge.style.background = "#fee2e2";
            bgLaunchSummaryBadge.style.color = "#991b1b";
          }
          if (bgLaunchResultsList) {
            bgLaunchResultsList.innerHTML = `<div style="color: #ef4444;">Error: ${escapeHtml(err.message)}</div>`;
          }
        } finally {
          btnBackgroundLaunchTest.disabled = false;
          btnBackgroundLaunchTest.textContent = "📱 Run Background Launch Test (App, Settings, URL, Deep Link)";
        }
      });
    }

    // Real Device Self-Test Runner (Step C2.5 Item 7)
    const runDeviceSelfTestBtn = document.getElementById("runDeviceSelfTestBtn");
    const selfTestResultsContainer = document.getElementById("selfTestResultsContainer");
    const selfTestSummaryBadge = document.getElementById("selfTestSummaryBadge");
    const selfTestList = document.getElementById("selfTestList");

    if (runDeviceSelfTestBtn) {
      runDeviceSelfTestBtn.addEventListener("click", async () => {
        runDeviceSelfTestBtn.disabled = true;
        runDeviceSelfTestBtn.textContent = "⏳ Running Self-Test on Devices...";
        if (selfTestResultsContainer) selfTestResultsContainer.style.display = "block";
        if (selfTestSummaryBadge) {
          selfTestSummaryBadge.textContent = "Testing...";
          selfTestSummaryBadge.style.background = "#fef3c7";
          selfTestSummaryBadge.style.color = "#92400e";
        }
        if (selfTestList) {
          selfTestList.innerHTML = '<div style="color: #6b7280; font-style: italic;">Pinging devices, launching apps, and confirming process/lifecycle on laptop and phone...</div>';
        }

        try {
          const res = await fetch("/api/diagnostics/self-test", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
          });
          const data = await res.json();
          if (selfTestSummaryBadge) {
            selfTestSummaryBadge.textContent = data.summary || (data.success ? "All Passed" : "Tests Failed");
            if (data.success) {
              selfTestSummaryBadge.style.background = "#dcfce7";
              selfTestSummaryBadge.style.color = "#166534";
            } else {
              selfTestSummaryBadge.style.background = "#fee2e2";
              selfTestSummaryBadge.style.color = "#991b1b";
            }
          }

          if (selfTestList && Array.isArray(data.tests)) {
            selfTestList.innerHTML = data.tests.map(t => {
              const isPass = t.status === "pass";
              const badgeBg = isPass ? "#dcfce7" : "#fee2e2";
              const badgeColor = isPass ? "#166534" : "#991b1b";
              const badgeText = isPass ? "PASS" : "FAIL";
              const icon = isPass ? "✅" : "❌";
              return `
                <div style="background: #faf5ff; border: 1px solid #f3e8ff; border-radius: 6px; padding: 6px 10px;">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <strong style="color: #4b5563;">${icon} ${escapeHtml(t.name)}</strong>
                    <span style="font-size: 0.7rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: ${badgeBg}; color: ${badgeColor};">${badgeText}</span>
                  </div>
                  <div style="font-size: 0.74rem; color: #6b7280; margin-top: 3px;">${escapeHtml(t.detail || '')}</div>
                </div>
              `;
            }).join("");
          }
        } catch (err) {
          if (selfTestSummaryBadge) {
            selfTestSummaryBadge.textContent = "Error";
            selfTestSummaryBadge.style.background = "#fee2e2";
            selfTestSummaryBadge.style.color = "#991b1b";
          }
          if (selfTestList) {
            selfTestList.innerHTML = `<div style="color: #ef4444;">Self-test request failed: ${escapeHtml(err.message)}</div>`;
          }
        } finally {
          runDeviceSelfTestBtn.disabled = false;
          runDeviceSelfTestBtn.textContent = "🚀 Run Device Self-Test";
        }
      });
    }


    // Check settings open hook
    if (openSettingsBtn) {
      openSettingsBtn.addEventListener("click", () => {
        checkNativeCompanionSettings();
        loadCompanionDiagnostics();
        loadDevices();
      });
    }

    // ========================================================
    // STEP 16: DEVICE PAIRING & SECURE CHANNEL LOGIC
    // ========================================================
    let currentDeviceData = null;
    let deviceWs = null;
    let pairingPollTimer = null;
    let ringAudioCtx = null;
    let ringInterval = null;
    let activePendingRemoteCmd = null;

    let cachedNativeDeviceId = null;

    async function initNativeDeviceId() {
      if (cachedNativeDeviceId) return cachedNativeDeviceId;
      // 1. Electron Desktop
      if (window.electronAPI && typeof window.electronAPI.getDeviceId === "function") {
        try {
          const nativeId = await window.electronAPI.getDeviceId();
          if (nativeId && nativeId.trim()) {
            cachedNativeDeviceId = nativeId.trim();
            localStorage.setItem("sinbha_device_id", cachedNativeDeviceId);
            return cachedNativeDeviceId;
          }
        } catch (e) {}
      }
      // 2. Android Capacitor Native Companion
      if (window.Capacitor && window.Capacitor.isPluginAvailable && window.Capacitor.isPluginAvailable("SinbhaNative")) {
        try {
          const res = await window.Capacitor.Plugins.SinbhaNative.getDeviceId();
          if (res && res.deviceId && res.deviceId.trim()) {
            cachedNativeDeviceId = res.deviceId.trim();
            localStorage.setItem("sinbha_device_id", cachedNativeDeviceId);
            return cachedNativeDeviceId;
          }
        } catch (e) {}
      }
      cachedNativeDeviceId = getOrCreateDeviceId();
      return cachedNativeDeviceId;
    }

    function getOrCreateDeviceId() {
      if (cachedNativeDeviceId) return cachedNativeDeviceId;
      let devId = localStorage.getItem("sinbha_device_id");
      if (!devId) {
        devId = "dev_" + Math.random().toString(36).substring(2, 9) + "_" + Date.now().toString(36);
        localStorage.setItem("sinbha_device_id", devId);
      }
      return devId;
    }

    async function getDevicePlatformAndName() {
      // 1. Electron Desktop (Windows / Mac / Linux)
      if (window.electronAPI && typeof window.electronAPI.getComputerName === "function") {
        try {
          const compName = await window.electronAPI.getComputerName();
          if (compName && compName.trim()) {
            return { platform: "windows", name: compName.trim() };
          }
        } catch (e) {}
        return { platform: "windows", name: "Windows PC" };
      }

      // 2. Android Capacitor Native Companion
      if (window.Capacitor && window.Capacitor.isPluginAvailable && window.Capacitor.isPluginAvailable("SinbhaNative")) {
        try {
          const info = await window.Capacitor.Plugins.SinbhaNative.getPhoneModel();
          if (info && info.model && info.model.trim()) {
            return { platform: "android", name: info.model.trim() };
          }
        } catch (e) {}
        return { platform: "android", name: "Android Companion" };
      }

      // 3. Fallback Web Browser with user agent detection
      const ua = navigator.userAgent || "";
      let platform = "web";
      let name = "Web Browser";

      if (/Android/i.test(ua)) {
        platform = "android";
        name = "Android Companion";
      } else if (/Windows/i.test(ua)) {
        platform = "windows";
        name = "Windows PC";
      } else if (/iPhone|iPad|iPod/i.test(ua)) {
        platform = "ios";
        name = "iPhone";
      } else if (/Mac/i.test(ua)) {
        platform = "macos";
        name = "Mac";
      } else if (/Linux/i.test(ua)) {
        platform = "linux";
        name = "Linux PC";
      }
      return { platform, name };
    }

    function getPlatformIcon(platform) {
      const p = (platform || "").toLowerCase();
      if (p === "android") return "📱";
      if (p === "windows") return "💻";
      if (p === "ios") return "🍏";
      if (p === "macos") return "🍎";
      if (p === "linux") return "🐧";
      return "🌐";
    }

    // Audio synthesizer & native alarm ring for "ring my phone" (Step 16b Rule 6)
    function startRingtone(sender = "Paired Device") {
      try {
        stopRingtone();
        // Native Android alarm stream (STREAM_ALARM)
        if (window.Capacitor && window.Capacitor.isPluginAvailable && window.Capacitor.isPluginAvailable("SinbhaNative")) {
          try {
            window.Capacitor.Plugins.SinbhaNative.startAlarmRing({ sender: sender });
          } catch (e) {}
        }
        // Native Windows Electron
        if (window.electronAPI && window.electronAPI.startAlarmRing) {
          try {
            window.electronAPI.startAlarmRing(sender);
          } catch (e) {}
        }

        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return;
        ringAudioCtx = new AudioContext();

        const playBurst = () => {
          if (!ringAudioCtx || ringAudioCtx.state === "closed") return;
          const osc1 = ringAudioCtx.createOscillator();
          const osc2 = ringAudioCtx.createOscillator();
          osc1.type = "sine";
          osc2.type = "sine";
          osc1.frequency.setValueAtTime(520, ringAudioCtx.currentTime);
          osc2.frequency.setValueAtTime(660, ringAudioCtx.currentTime);
          const burstGain = ringAudioCtx.createGain();
          burstGain.gain.setValueAtTime(0.35, ringAudioCtx.currentTime);
          burstGain.gain.exponentialRampToValueAtTime(0.001, ringAudioCtx.currentTime + 0.7);
          osc1.connect(burstGain);
          osc2.connect(burstGain);
          burstGain.connect(ringAudioCtx.destination);
          osc1.start();
          osc2.start();
          osc1.stop(ringAudioCtx.currentTime + 0.75);
          osc2.stop(ringAudioCtx.currentTime + 0.75);
        };

        playBurst();
        ringInterval = setInterval(playBurst, 1400);
      } catch (e) {
        console.warn("AudioContext failed:", e);
      }
    }

    function stopRingtone() {
      // Native Android alarm stop
      if (window.Capacitor && window.Capacitor.isPluginAvailable && window.Capacitor.isPluginAvailable("SinbhaNative")) {
        try {
          window.Capacitor.Plugins.SinbhaNative.stopAlarmRing({});
        } catch (e) {}
      }
      // Native Windows Electron stop
      if (window.electronAPI && window.electronAPI.stopAlarmRing) {
        try {
          window.electronAPI.stopAlarmRing();
        } catch (e) {}
      }
      if (ringInterval) {
        clearInterval(ringInterval);
        ringInterval = null;
      }
      if (ringAudioCtx) {
        try { ringAudioCtx.close(); } catch (e) {}
        ringAudioCtx = null;
      }
    }

    async function getActiveClientVersion() {
      try {
        if (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.SinbhaNative && typeof window.Capacitor.Plugins.SinbhaNative.getAppVersion === "function") {
          const vInfo = await window.Capacitor.Plugins.SinbhaNative.getAppVersion();
          if (vInfo && (vInfo.versionName || vInfo.version)) {
            return vInfo.versionName || vInfo.version;
          }
        }
      } catch (e) {}

      try {
        if (window.electronAPI && typeof window.electronAPI.getDiagnostics === "function") {
          const diag = await window.electronAPI.getDiagnostics();
          if (diag && diag.version) {
            return diag.version;
          }
        }
      } catch (e) {}

      return "1.4.25";
    }

    // Register or handshake this device on server
    async function initDeviceChannel() {
      if (!currentUser) return;
      const deviceId = await initNativeDeviceId();
      const { platform, name } = await getDevicePlatformAndName();
      const appVer = await getActiveClientVersion();

      const nameEl = document.getElementById("currentDeviceName");
      if (nameEl && (!currentDeviceData || nameEl.textContent === "Detecting...")) {
        nameEl.textContent = `${getPlatformIcon(platform)} ${name}`;
      }

      try {
        const res = await fetch("/api/devices/register", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Client-Version": appVer
          },
          body: JSON.stringify({
            device_id: deviceId,
            name: name,
            platform: platform,
            client_version: appVer
          })
        });
        const data = await res.json();
        if (data.success && data.device) {
          currentDeviceData = data.device;
          updateCurrentDeviceUI(currentDeviceData);

          if (currentDeviceData.status === "trusted") {
            connectDeviceWebSocket(deviceId);
            pollPendingCommands(deviceId);
          } else if (currentDeviceData.status === "pending") {
            if (currentDeviceData.requires_first_device_trust) {
              openFirstDeviceTrustModal();
            }
            showPendingPairingUI(currentDeviceData);
            startPairingPolling(deviceId);
          }
        }
      } catch (e) {
        console.warn("Device registration error:", e);
      }
    }

    function openFirstDeviceTrustModal() {
      const modal = document.getElementById("firstDeviceTrustModal");
      const input = document.getElementById("firstDeviceModalPasswordInput");
      const err = document.getElementById("firstDeviceModalError");
      if (modal) {
        modal.style.display = "flex";
        if (err) err.style.display = "none";
        if (input) {
          input.value = "";
          setTimeout(() => input.focus(), 150);
        }
      }
    }

    function closeFirstDeviceTrustModal() {
      const modal = document.getElementById("firstDeviceTrustModal");
      if (modal) modal.style.display = "none";
    }

    function updateCurrentDeviceUI(device) {
      const nameEl = document.getElementById("currentDeviceName");
      const badgeEl = document.getElementById("currentDeviceStatusBadge");
      const pendingBanner = document.getElementById("pendingPairingBanner");
      const topBanner = document.getElementById("topPairingBanner");
      const trustModal = document.getElementById("firstDeviceTrustModal");

      if (nameEl) nameEl.textContent = `${getPlatformIcon(device.platform)} ${device.name}`;
      if (badgeEl) {
        if (device.status === "trusted") {
          badgeEl.textContent = "● Trusted";
          badgeEl.style.color = "#059669";
          if (pendingBanner) pendingBanner.style.display = "none";
          if (topBanner) topBanner.style.display = "none";
          if (trustModal) trustModal.style.display = "none";
        } else if (device.status === "pending") {
          badgeEl.textContent = "⏳ Pending Pairing Approval";
          badgeEl.style.color = "#b45309";
        } else {
          badgeEl.textContent = "🛑 Revoked";
          badgeEl.style.color = "#dc2626";
          if (topBanner) topBanner.style.display = "none";
        }
      }
    }

    function showPendingPairingUI(device) {
      const pendingBanner = document.getElementById("pendingPairingBanner");
      const codeDisplay = document.getElementById("pairingCodeDisplay");
      const countdownText = document.getElementById("pairingCountdownText");

      const topBanner = document.getElementById("topPairingBanner");
      const topCodeDisplay = document.getElementById("topPairingCodeDisplay");
      const topCountdown = document.getElementById("topPairingCountdown");

      if (pendingBanner) pendingBanner.style.display = "block";
      if (topBanner) topBanner.style.display = "flex";

      const c = device.pairing_code || "------";
      const formattedCode = c.length === 6 ? `${c.slice(0, 3)} ${c.slice(3)}` : c;

      if (codeDisplay) codeDisplay.textContent = formattedCode;
      if (topCodeDisplay) topCodeDisplay.textContent = formattedCode;

      let sec = device.expires_in_seconds || 300;
      const updateText = () => {
        const m = Math.floor(sec / 60);
        const s = sec % 60;
        const msg = `Expires in ${m}:${s < 10 ? "0" : ""}${s}`;
        if (countdownText) countdownText.textContent = msg;
        if (topCountdown) topCountdown.textContent = `(${msg})`;
        if (sec > 0) sec--;
      };
      updateText();
    }

    function startPairingPolling(deviceId) {
      if (pairingPollTimer) clearInterval(pairingPollTimer);
      pairingPollTimer = setInterval(async () => {
        try {
          const res = await fetch(`/api/devices/status?device_id=${encodeURIComponent(deviceId)}`);
          if (!res.ok) return;
          const data = await res.json();
          if (data.device && data.device.status === "trusted") {
            clearInterval(pairingPollTimer);
            pairingPollTimer = null;
            currentDeviceData = data.device;
            updateCurrentDeviceUI(currentDeviceData);
            showToast("Device paired and approved successfully!");
            connectDeviceWebSocket(deviceId);
            loadDevices();
          }
        } catch (e) {}
      }, 3000);
    }

    // Connect authenticated WebSocket relay channel
    let wsHeartbeatTimer = null;
    let wsReconnectTimer = null;
    let wsReconnectDelay = 3000;
    let commandPollInterval = null;
    let pollBackoffUntil = 0;

    async function connectDeviceWebSocket(deviceId) {
      if (!deviceId) deviceId = getOrCreateDeviceId();
      if (deviceWs && (deviceWs.readyState === WebSocket.OPEN || deviceWs.readyState === WebSocket.CONNECTING)) {
        return;
      }

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      let tokenParam = "";
      if (currentUser && currentUser.token) {
        tokenParam = `&token=${encodeURIComponent(currentUser.token)}`;
      }
      const clientVer = await getActiveClientVersion();
      const wsUrl = `${protocol}//${window.location.host}/api/ws/devices?device_id=${encodeURIComponent(deviceId)}${tokenParam}&version=${encodeURIComponent(clientVer)}`;

      try {
        deviceWs = new WebSocket(wsUrl);

        deviceWs.onopen = () => {
          console.log("Secure device channel connected");
          wsReconnectDelay = 3000; // Reset exponential backoff on successful connection
          try {
            if (currentUser && currentUser.token) {
              deviceWs.send(JSON.stringify({
                type: "auth",
                token: currentUser.token,
                device_id: deviceId,
                version: clientVer,
                client_version: clientVer
              }));
            }
            deviceWs.send(JSON.stringify({ type: "ping" }));
          } catch(e) {}
          reportDeviceBattery();
          syncNotificationsFromPhone();

          if (wsHeartbeatTimer) clearInterval(wsHeartbeatTimer);
          wsHeartbeatTimer = setInterval(() => {
            if (deviceWs && deviceWs.readyState === WebSocket.OPEN) {
              deviceWs.send(JSON.stringify({ type: "ping" }));
            }
          }, 15000); // 15s ping/pong beats Render 55s proxy idle timeout
        };

        deviceWs.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === "pong") return;
            handleIncomingDeviceMessage(msg);
          } catch (e) {
            console.error("Device WS message parse error:", e);
          }
        };

        deviceWs.onclose = (evt) => {
          console.warn(`[DeviceWS] Closed: code=${evt ? evt.code : 'unknown'}, reason=${evt ? (evt.reason || 'none') : 'none'}`);
          deviceWs = null;
          if (wsHeartbeatTimer) {
            clearInterval(wsHeartbeatTimer);
            wsHeartbeatTimer = null;
          }
          // Exponential backoff with jitter on reconnects: 3s -> 6s -> 12s -> max 30s
          if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
          wsReconnectTimer = setTimeout(() => {
            if (currentUser) {
              connectDeviceWebSocket(deviceId);
            }
          }, wsReconnectDelay);
          wsReconnectDelay = Math.min(Math.round(wsReconnectDelay * 1.5), 30000);
        };

        deviceWs.onerror = (err) => {
          console.warn("[DeviceWS] Error encountered:", err);
        };
      } catch (e) {
        console.warn("WebSocket init error:", e);
      }
    }

    // Resilient command polling watchdog: runs every 10 seconds as offline fallback
    if (!commandPollInterval) {
      commandPollInterval = setInterval(() => {
        if (currentUser) {
          const devId = getOrCreateDeviceId();
          // If WebSocket is open and healthy, it delivers live commands instantaneously - no HTTP poll spam needed
          if (deviceWs && deviceWs.readyState === WebSocket.OPEN) {
            return;
          }
          // If currently in rate-limit or error backoff, skip polling
          if (Date.now() < pollBackoffUntil) {
            return;
          }
          pollPendingCommands(devId);
          if (!deviceWs || deviceWs.readyState === WebSocket.CLOSED) {
            if (!wsReconnectTimer) {
              connectDeviceWebSocket(devId);
            }
          }
        }
      }, 10000);
    }

    // Reports battery telemetry to backend
    async function reportDeviceBattery() {
      try {
        let batteryPct = 100;
        let isCharging = false;
        let platform = isAndroidPlatform() ? "android" : (window.electronAPI ? "windows" : "web");
        let supportedTools = [];
        if (platform === "windows") {
          supportedTools = ["open_app", "open_url", "find_installed_app", "type_text", "press_keys", "send_note", "ring_phone"];
        } else if (platform === "android") {
          supportedTools = ["open_app", "open_url", "send_note", "ring_phone"];
        } else {
          supportedTools = ["send_note", "open_url"];
        }

        if (window.electronAPI && window.electronAPI.getDesktopBattery) {
          const res = await window.electronAPI.getDesktopBattery();
          if (res && res.percentage !== undefined) {
            batteryPct = res.percentage;
            isCharging = res.isPlugged || false;
          }
        } else if (window.Capacitor && window.Capacitor.isPluginAvailable && window.Capacitor.isPluginAvailable("SinbhaNative")) {
          const res = await window.Capacitor.Plugins.SinbhaNative.getBatteryStatus();
          if (res && res.percentage !== undefined) {
            batteryPct = res.percentage;
            isCharging = res.isCharging || false;
          }
        } else if (navigator.getBattery) {
          const b = await navigator.getBattery();
          batteryPct = Math.round(b.level * 100);
          isCharging = b.charging;
        }

        let installedApps = null;
        if (window.electronAPI && typeof window.electronAPI.getInstalledApps === "function") {
          try {
            installedApps = await window.electronAPI.getInstalledApps();
          } catch (e) {}
        } else if (window.Capacitor && window.Capacitor.isPluginAvailable && window.Capacitor.isPluginAvailable("SinbhaNative")) {
          try {
            const appRes = await window.Capacitor.Plugins.SinbhaNative.getInstalledApps();
            installedApps = (appRes && appRes.apps) || null;
          } catch (e) {}
        }

        if (deviceWs && deviceWs.readyState === WebSocket.OPEN) {
          const clientVer = await getActiveClientVersion();
          const statusPayload = {
            type: "device_status",
            battery: batteryPct,
            is_charging: isCharging,
            platform: platform,
            version: clientVer,
            supported_tools: supportedTools
          };
          if (installedApps && Array.isArray(installedApps) && installedApps.length > 0) {
            statusPayload.installed_apps = installedApps;
          }
          deviceWs.send(JSON.stringify(statusPayload));
        }
      } catch (e) {}
    }

    // Syncs notifications buffer from Android phone
    async function syncNotificationsFromPhone() {
      if (window.Capacitor && window.Capacitor.isPluginAvailable && window.Capacitor.isPluginAvailable("SinbhaNative")) {
        try {
          const res = await window.Capacitor.Plugins.SinbhaNative.getRecentNotifications();
          if (res && res.notifications && Array.isArray(res.notifications)) {
            await fetch("/api/devices/notifications/sync", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ notifications: res.notifications })
            });
            if (deviceWs && deviceWs.readyState === WebSocket.OPEN) {
              deviceWs.send(JSON.stringify({
                type: "sync_notifications",
                notifications: res.notifications
              }));
            }
          }
        } catch (e) {}
      }
    }

    // Fallback/offline pending command draining with 429 rate limit backoff
    async function pollPendingCommands(deviceId) {
      if (!deviceId) deviceId = getOrCreateDeviceId();
      if (Date.now() < pollBackoffUntil) return;
      try {
        const clientVer = await getActiveClientVersion();
        const platform = isAndroidPlatform() ? "android-webview" : (window.electronAPI ? "desktop-electron" : "web-browser");
        const res = await fetch(`/api/devices/commands/pending?device_id=${encodeURIComponent(deviceId)}&version=${encodeURIComponent(clientVer)}`, {
          headers: {
            "X-Client-Version": clientVer,
            "X-Client-Platform": platform
          }
        });
        if (res.status === 429) {
          const retryHeader = res.headers.get("Retry-After");
          const retrySec = retryHeader ? parseInt(retryHeader, 10) : 30;
          pollBackoffUntil = Date.now() + (retrySec * 1000);
          console.warn(`[Client Backoff] Received HTTP 429 on command poll. Backing off for ${retrySec}s.`);
          return;
        }
        if (!res.ok) {
          if (res.status >= 500) {
            pollBackoffUntil = Date.now() + 15000;
          }
          return;
        }
        const data = await res.json();
        if (data.commands && Array.isArray(data.commands)) {
          for (const cmd of data.commands) {
            handleIncomingDeviceMessage(cmd);
          }
        }
      } catch (e) {}
    }

    // Dispatcher for incoming remote commands and pairing events (Step 16 / 16b / 16c / C2.7)
    function handleIncomingDeviceMessage(msg) {
      if (!msg) return;
      const rawType = msg.type || msg.command_type;
      const isCommand = rawType === "remote_command" || Boolean(msg.command_type) ||
        ["open_app", "open_url", "open_link", "find_installed_app", "type_text", "type_input", "press_keys", "send_note", "ring_phone", "sync_tasks", "system_control", "get_battery"].includes(rawType);

      if (isCommand) {
        if (msg.requires_confirmation) {
          showRemoteConfirmModal(msg);
        } else {
          executeRemoteCommand(msg);
        }
      } else if (msg.type === "pairing_requested") {
        const d = msg.device || {};
        const reqTime = d.created_at ? new Date(d.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Just now";
        showToast(`🔔 New device pairing requested: ${d.name || "Device"} (${d.platform || "unknown"}) at ${reqTime}`);
        if (window.Capacitor && window.Capacitor.isPluginAvailable && window.Capacitor.isPluginAvailable("SinbhaNative")) {
          try {
            window.Capacitor.Plugins.SinbhaNative.showNoteNotification({
              title: "New Device Pairing Requested",
              text: `${d.name || "Device"} (${d.platform || "unknown"}) requested to pair at ${reqTime}. Approve in Settings.`
            });
          } catch (e) {}
        } else if (window.electronAPI && window.electronAPI.showNotification) {
          try {
            window.electronAPI.showNotification(
              "New Device Pairing Requested",
              `${d.name || "Device"} (${d.platform || "unknown"}) requested to pair at ${reqTime}. Approve in Settings.`
            );
          } catch (e) {}
        } else if (window.Notification && Notification.permission === "granted") {
          new Notification("New Device Pairing Requested", {
            body: `${d.name || "Device"} (${d.platform || "unknown"}) requested to pair at ${reqTime}. Open Settings to approve.`,
            icon: "/static/favicon.png"
          });
        }
        loadDevices();
      } else if (msg.type === "emergency_stop") {
        setStopUiState(true);
        showToast("🛑 Remote channel paused by emergency STOP");
      }
    }

    // Confirmation modal for Level > 1 or open_link (Step 16b Rule 6)
    function showRemoteConfirmModal(cmd) {
      activePendingRemoteCmd = cmd;
      const modal = document.getElementById("remoteConfirmModal");
      const desc = document.getElementById("remoteConfirmDesc");
      const details = document.getElementById("remoteConfirmDetails");

      if (!modal) return;
      if (desc) {
        desc.textContent = `Device '${cmd.sender_name || "Paired Companion"}' requested to execute: ${cmd.command_type}`;
      }
      if (details) {
        let text = "";
        if (cmd.command_type === "open_link") {
          text = `URL: ${cmd.payload && cmd.payload.url ? cmd.payload.url : "(No URL specified)"}\n\nTap 'Allow' to open in browser.`;
        } else if (cmd.command_type === "send_note") {
          text = `Note: ${cmd.payload && cmd.payload.text ? cmd.payload.text : ""}`;
        } else if (cmd.command_type === "ring_phone") {
          text = "Action: Audible ring phone alert";
        } else {
          text = JSON.stringify(cmd.payload || {});
        }
        details.textContent = text;
      }
      modal.style.display = "flex";
    }

    // Reports command lifecycle transition (started, succeeded, not_installed, failed) back to server (Step C2.5 & C2.10)
    async function reportCommandLifecycle(commandId, status, result = null, error = null) {
      if (!commandId) return;
      const clientTs = new Date().toISOString();
      const packet = {
        type: "command_status",
        command_id: commandId,
        id: commandId,
        status: status,
        result: result,
        error: error,
        client_timestamp: clientTs
      };
      if (deviceWs && deviceWs.readyState === WebSocket.OPEN) {
        try {
          deviceWs.send(JSON.stringify(packet));
        } catch (e) {}
      }
      try {
        await fetch("/api/devices/command-status", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(packet)
        });
      } catch (e) {}
    }

    // Execute remote command on this target device (Step 16b / 16c / C2.5)
    async function executeRemoteCommand(cmd) {
      const cmdId = cmd.id || cmd.command_id || (cmd.payload && cmd.payload.id);
      if (cmdId) {
        reportCommandLifecycle(cmdId, "started");
      }
      const type = cmd.command_type || cmd.type;
      const payload = cmd.payload || {};
      const sender = cmd.sender_name || "Paired Device";

      try {
        if (type === "open_app") {
          const appName = payload.app || "";
          showToast(`🚀 Opening ${appName}...`);

          let launchStatus = "failed";
          let launchResult = null;
          let launchError = null;

          // 1. If running inside Electron desktop app (Windows)
          if (window.electronAPI && window.electronAPI.launchDesktopApp) {
            try {
              const res = await window.electronAPI.launchDesktopApp(payload);
              launchResult = res;
              if (res && res.success) {
                showToast(`✨ Launched ${appName} on laptop!`);
                launchStatus = res.status || "succeeded";
              } else if (res && (res.status === "not_installed" || res.error === "not_installed")) {
                launchStatus = "not_installed";
                launchError = res.error || "not_installed";
                showToast(`App '${appName}' is not installed.`);
              } else if (res && res.status === "sent_not_verified") {
                launchStatus = "sent_not_verified";
                launchError = res.error || "sent, not verified";
                showToast(`Sent ${appName}, but verification failed.`);
              } else {
                launchStatus = "failed";
                launchError = res ? (res.error || res.message) : "Launch failed";
                showToast(`Could not launch ${appName}: ${launchError}`);
              }
            } catch (e) {
              launchStatus = "failed";
              launchError = e.message;
            }
          }
          // 2. If running inside Capacitor Android app via native SinbhaPlugin
          else if (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.SinbhaNative) {
            try {
              const res = await window.Capacitor.Plugins.SinbhaNative.openApp(payload);
              launchResult = res;
              showToast(`✨ Opened ${appName} on phone!`);
              launchStatus = "succeeded";
            } catch (e) {
              const code = e && (e.code || (e.data && e.data.status));
              const isNotInstalled = code === "APP_NOT_FOUND" || code === "not_installed" || (e.message && e.message.toLowerCase().includes("not installed"));
              launchStatus = isNotInstalled ? "not_installed" : "failed";
              launchError = e.message || "Failed to open app";
              launchResult = {
                app: appName,
                status: launchStatus,
                error: launchError,
                candidates: (e.data && e.data.candidates) || []
              };
              showToast(`Could not launch ${appName}: ${launchError}`);
            }
          }
          // 3. Fallback browser/webview: only open if explicit URL was provided; NEVER fallback to web silently!
          else if (payload.url) {
            window.open(payload.url.startsWith("http") ? payload.url : `https://${payload.url}`, "_blank");
            launchStatus = "succeeded";
            launchResult = { method: "direct_url", url: payload.url };
          } else {
            launchStatus = "not_installed";
            launchError = `App '${appName}' is not installed or companion launcher is unavailable.`;
            launchResult = { app: appName, status: "not_installed", error: launchError, candidates: [] };
          }

          if (cmdId) {
            reportCommandLifecycle(cmdId, launchStatus, launchResult, launchError);
            try {
              await fetch(`/api/devices/commands/${encodeURIComponent(cmdId)}/ack`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  status: launchStatus === "succeeded" ? "executed" : launchStatus,
                  command_id: cmdId,
                  result: launchResult,
                  error: launchError
                })
              });
            } catch (e) {}
          }
          return;
        } else if (type === "type_input" || (type === "system_control" && payload.action === "type_input")) {
          if (window.electronAPI && window.electronAPI.typeInput) {
            await window.electronAPI.typeInput(payload);
            const enterStr = payload.press_enter ? " + Enter ↵" : "";
            showToast(`⌨️ Typed: "${payload.text || ""}"${enterStr}`);
          }
        } else if (type === "system_control") {
          const action = payload.action || "";
          if (action === "lock_screen" || action === "lock_workstation") {
            if (window.electronAPI && window.electronAPI.lockWorkstation) {
              await window.electronAPI.lockWorkstation();
              showToast("🔒 Workstation locked!");
            }
          }
        } else if (type === "get_battery") {
          await reportDeviceBattery();
        } else if (type === "query_notifications") {
          await syncNotificationsFromPhone();
        } else if (type === "send_note") {
          const noteText = payload.text || "(empty note)";
          showToast(`💌 Note from ${sender}: ${noteText.slice(0, 60)}`);
          appendMessage("assistant", `💌 **Remote Note from ${sender}:**\n${noteText}`);

          if (window.Capacitor && window.Capacitor.isPluginAvailable && window.Capacitor.isPluginAvailable("SinbhaNative")) {
            try {
              window.Capacitor.Plugins.SinbhaNative.showNoteNotification({
                title: `Note from ${sender}`,
                text: noteText
              });
            } catch (e) {}
          } else if (window.electronAPI && window.electronAPI.showNotification) {
            try {
              window.electronAPI.showNotification(`Note from ${sender}`, noteText);
            } catch (e) {}
          } else if (window.Notification && Notification.permission === "granted") {
            new Notification(`Note from ${sender}`, { body: noteText, icon: "/static/favicon.png" });
          }
        } else if (type === "open_link") {
          const url = payload.url || "";
          if (url && (url.startsWith("http://") || url.startsWith("https://"))) {
            if (window.electronAPI && window.electronAPI.showConfirmDialog) {
              const allowed = await window.electronAPI.showConfirmDialog({
                title: "Open Link from Paired Device?",
                message: `Open link from '${sender}':`,
                detail: url
              });
              if (allowed) {
                window.open(url, "_blank");
                showToast(`🌐 Opened link from ${sender}`);
              } else {
                showToast("Link open canceled.");
              }
            } else {
              window.open(url, "_blank");
              showToast(`🌐 Opened link from ${sender}`);
            }
          }
        } else if (type === "ring_phone") {
          const ringModal = document.getElementById("ringAlertModal");
          const ringSender = document.getElementById("ringAlertSender");
          if (ringSender) ringSender.textContent = `Ringing triggered by ${sender}`;
          if (ringModal) ringModal.style.display = "flex";
          startRingtone(sender);
        } else if (type === "sync_tasks") {
          await loadTasks();
          await loadUpcomingReminders();
          await loadFacts();
          showToast(`🔄 Instant sync from ${sender}`);
        }

        // Send ACK back to server and mark lifecycle succeeded
        if (cmdId) {
          reportCommandLifecycle(cmdId, "succeeded", { executed: true, type: type, app: payload.app || "" });
          try {
            await fetch(`/api/devices/commands/${encodeURIComponent(cmdId)}/ack`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ status: "executed", command_id: cmdId, result: { executed: true, type: type, app: payload.app || "" } })
            });
          } catch(e) {}
        }
      } catch (e) {
        console.error("Error executing remote command:", e);
        if (cmdId) {
          reportCommandLifecycle(cmdId, "failed", null, e.message);
        }
      }
    }

    // Open pair approval modal showing device name, platform, and request time (Step 16b Rule 3)
    function openPairingApprovalModal(targetDev) {
      const modal = document.getElementById("pairDeviceModal");
      const cardContainer = document.getElementById("pendingDeviceCardContainer");
      const input = document.getElementById("pairCodeInput");
      const warn = document.getElementById("pairAttemptsWarning");

      if (!modal) return;
      if (input) input.value = "";
      if (warn) {
        warn.style.display = "none";
        warn.textContent = "";
      }

      if (cardContainer) {
        if (targetDev) {
          const reqTime = targetDev.created_at ? new Date(targetDev.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Recently";
          const attempts = targetDev.pairing_attempts || 0;
          const isLocked = targetDev.is_locked || (attempts >= 5);

          cardContainer.innerHTML = `
            <div style="background: #fdf2f8; border: 1.5px solid #fbcfe8; border-radius: 8px; padding: 10px; font-size: 0.82rem;">
              <div style="font-weight: 700; color: #9d174d; margin-bottom: 2px;">
                ${getPlatformIcon(targetDev.platform)} ${escapeHtml(targetDev.name)}
              </div>
              <div style="color: #6b7280; font-size: 0.78rem;">
                Platform: <strong>${targetDev.platform}</strong> • Requested at: <strong>${reqTime}</strong>
              </div>
              ${isLocked ? `
                <div style="color: #dc2626; font-weight: 700; margin-top: 6px;">
                  🔒 Code Locked (5 failed attempts). Generate a fresh code on that device.
                </div>
              ` : attempts > 0 ? `
                <div style="color: #d97706; margin-top: 4px;">
                  ⚠️ ${attempts} failed attempt(s). Code locks after 5 wrong attempts.
                </div>
              ` : ""}
            </div>
          `;
        } else {
          cardContainer.innerHTML = "";
        }
      }

      modal.style.display = "flex";
      if (input) input.focus();
    }

    // Load and render devices list in Settings
    async function loadDevices() {
      const container = document.getElementById("devicesList");
      const badge = document.getElementById("devicesCountBadge");
      if (!container) return;

      try {
        const res = await fetch("/api/devices");
        if (!res.ok) return;
        const data = await res.json();
        const devices = data.devices || [];

        if (badge) badge.textContent = devices.length;
        container.innerHTML = "";

        if (devices.length === 0) {
          container.innerHTML = `<div style="font-size: 0.82rem; color: #9ca3af; text-align: center; padding: 12px;">No paired devices found.</div>`;
          return;
        }

        const currentId = getOrCreateDeviceId();
        const thisDev = devices.find(d => d.device_id === currentId);
        if (thisDev) {
          updateCurrentDeviceUI(thisDev);
        } else if (currentUser) {
          initDeviceChannel();
        }

        devices.forEach(d => {
          const isThisDevice = (d.device_id === currentId);
          const icon = getPlatformIcon(d.platform);

          const card = document.createElement("div");
          card.className = "device-item-card";

          let statusClass = "trusted";
          let statusLabel = "Trusted";
          if (d.status === "pending") {
            statusClass = "pending";
            statusLabel = d.is_locked ? "Code Locked" : "Pending Code";
          } else if (d.status === "revoked") {
            statusClass = "revoked";
            statusLabel = "Revoked";
          }

          const lastActiveStr = d.last_seen_at ? new Date(d.last_seen_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Just now";

          card.innerHTML = `
            <div class="device-item-left">
              <div class="device-platform-icon">${icon}</div>
              <div class="device-item-info">
                <div class="device-item-name-row">
                  <span class="device-item-title">${escapeHtml(d.name)}</span>
                  ${isThisDevice ? `<span class="device-current-badge">This device</span>` : ""}
                  <span class="device-status-pill ${statusClass}">${statusLabel}</span>
                </div>
                <div class="device-item-meta">
                  <span>Level ${d.permission_level}</span>
                  <span>•</span>
                  <span>Active: ${lastActiveStr}</span>
                </div>
              </div>
            </div>
            <div class="device-item-actions">
              <button type="button" class="device-action-icon-btn rename-dev-btn" data-id="${d.device_id}" title="Rename Device">✏️</button>
              ${d.status === "trusted" ? `
                <button type="button" class="device-action-icon-btn manage-dev-btn" data-id="${d.device_id}" title="Device Settings & Capabilities">⚙️ Settings</button>
              ` : ""}
              ${d.status === "pending" ? `
                <button type="button" class="device-action-icon-btn enter-code-btn" data-id="${d.device_id}" title="Enter 6-Digit Code to Approve" style="color: #059669; border-color: #a7f3d0; background: #ecfdf5;">🔑 Enter Code</button>
              ` : ""}
              <button type="button" class="device-action-icon-btn revoke-dev-btn" data-id="${d.device_id}" title="Revoke Device" style="color: #be123c;">🗑️</button>
            </div>
          `;

          // Hook rename button (Step 1C Item 4: Rename in Settings)
          const renBtn = card.querySelector(".rename-dev-btn");
          if (renBtn) {
            renBtn.addEventListener("click", async () => {
              const newName = prompt(`Enter a new name for '${d.name}':`, d.name);
              if (newName && newName.trim() && newName.trim() !== d.name) {
                try {
                  const res = await fetch(`/api/devices/${encodeURIComponent(d.device_id)}/rename`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name: newName.trim() })
                  });
                  const data = await res.json();
                  if (res.ok && data.success) {
                    showToast("Device renamed");
                    await loadDevices();
                  } else {
                    showToast(data.detail || "Failed to rename device.");
                  }
                } catch (e) {
                  showToast("Error renaming device: " + e.message);
                }
              }
            });
          }

          // Hook manage button
          const mBtn = card.querySelector(".manage-dev-btn");
          if (mBtn) {
            mBtn.addEventListener("click", () => openDeviceDetailsModal(d));
          }

          // Hook enter code button (Step 16b Rule 3: Typing code always required, no one-click approve)
          const eBtn = card.querySelector(".enter-code-btn");
          if (eBtn) {
            eBtn.addEventListener("click", () => {
              openPairingApprovalModal(d);
            });
          }

          // Hook revoke / delete button
          const rBtn = card.querySelector(".revoke-dev-btn");
          if (rBtn) {
            rBtn.addEventListener("click", async () => {
              const isRevoked = (d.status === "revoked");
              const promptMsg = isRevoked
                ? `Permanently delete '${d.name}'? This removes it completely.`
                : `Revoke access for '${d.name}' immediately?`;
              if (confirm(promptMsg)) {
                await revokeDevice(d.device_id, isRevoked);
              }
            });
          }

          container.appendChild(card);
        });
      } catch (e) {
        container.innerHTML = `<div style="font-size: 0.82rem; color: #ef4444; text-align: center;">Error loading devices.</div>`;
      }
    }

    // Modal: Device Details & Permissions with Password Gate (Step 16b Rule 4)
    function openDeviceDetailsModal(device) {
      const modal = document.getElementById("deviceDetailsModal");
      const title = document.getElementById("devModalTitle");
      const idInput = document.getElementById("editDeviceId");
      const nameInput = document.getElementById("editDeviceNameInput");
      const permSelect = document.getElementById("editDevicePermLevel");
      const capNote = document.getElementById("capNoteToggle");
      const capOpenLink = document.getElementById("capOpenLinkToggle");
      const capRing = document.getElementById("capRingToggle");
      const capSync = document.getElementById("capSyncToggle");
      const elevateGroup = document.getElementById("elevatePasswordGroup");
      const elevateInput = document.getElementById("elevatePasswordInput");

      if (!modal) return;
      if (title) title.textContent = `⚙️ ${device.name}`;
      if (idInput) idInput.value = device.device_id;
      if (nameInput) nameInput.value = device.name;
      if (permSelect) permSelect.value = String(device.permission_level ?? 1);

      const caps = device.capabilities || {};
      if (capNote) capNote.checked = caps.note !== false;
      if (capOpenLink) capOpenLink.checked = caps.open_link !== false;
      if (capRing) capRing.checked = caps.ring !== false;
      if (capSync) capSync.checked = caps.sync !== false;

      // Track baseline settings to know when password elevation is needed
      modal.dataset.initialLevel = String(device.permission_level ?? 1);
      modal.dataset.initialOpenLink = String(caps.open_link !== false);
      if (elevateGroup) elevateGroup.style.display = "none";
      if (elevateInput) elevateInput.value = "";

      const updateElevateVisibility = () => {
        const initLevel = parseInt(modal.dataset.initialLevel || "1", 10);
        const curLevel = parseInt(permSelect ? permSelect.value : "1", 10);
        const initOpenLink = modal.dataset.initialOpenLink === "true";
        const curOpenLink = capOpenLink ? capOpenLink.checked : false;

        const isRaisingLevel = curLevel >= 2 && curLevel > initLevel;
        const isEnablingOpenLink = curOpenLink && !initOpenLink;

        if (elevateGroup) {
          elevateGroup.style.display = (isRaisingLevel || isEnablingOpenLink) ? "block" : "none";
        }
      };

      if (permSelect) permSelect.onchange = updateElevateVisibility;
      if (capOpenLink) capOpenLink.onchange = updateElevateVisibility;

      modal.style.display = "flex";
    }

    async function revokeDevice(deviceId, permanent = false) {
      try {
        const url = `/api/devices/${encodeURIComponent(deviceId)}${permanent ? "?permanent=true" : ""}`;
        const res = await fetch(url, {
          method: "DELETE"
        });
        const data = await res.json();
        if (data.success) {
          showToast(permanent ? "🗑️ Device permanently deleted." : "🗑️ Device revoked immediately.");
          await loadDevices();
        } else {
          showToast(data.detail || "Failed to remove device.");
        }
      } catch (e) {
        showToast("Error removing device: " + e.message);
      }
    }

    // Send a remote command helper
    async function sendRemoteCommand(targetDeviceId, type, payload) {
      const myId = getOrCreateDeviceId();
      const cmdId = "cmd_" + Math.random().toString(36).substring(2, 9) + "_" + Date.now();
      try {
        const res = await fetch("/api/devices/commands/send", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id: cmdId,
            sender_device: myId,
            target_device: targetDeviceId,
            type: type,
            payload: payload,
            created_at: Date.now() / 1000,
            expiry: 60
          })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`⚡ Command '${type}' dispatched! (${data.result})`);
        } else {
          showToast(`❌ ${data.detail || "Command failed"}`);
        }
      } catch (e) {
        showToast("Error sending command: " + e.message);
      }
    }

    // UI Event Listeners for Step 16 / 16b
    const refreshDevBtn = document.getElementById("refreshDevicesBtn");
    if (refreshDevBtn) {
      refreshDevBtn.addEventListener("click", async () => {
        await initDeviceChannel();
        await loadDevices();
        showToast("Refreshed connected devices!");
      });
    }

    const openPairBtn = document.getElementById("openPairModalBtn");
    const pairModal = document.getElementById("pairDeviceModal");
    const closePairBtn = document.getElementById("closePairModalBtn");
    const cancelPairBtn = document.getElementById("cancelPairCodeBtn");
    const submitPairBtn = document.getElementById("submitPairCodeBtn");
    const pairCodeInput = document.getElementById("pairCodeInput");

    if (openPairBtn && pairModal) {
      openPairBtn.addEventListener("click", async () => {
        // Fetch devices to see if there is any pending device to show
        let pendingDev = null;
        try {
          const res = await fetch("/api/devices");
          if (res.ok) {
            const data = await res.json();
            const devs = data.devices || [];
            pendingDev = devs.find(d => d.status === "pending") || null;
          }
        } catch (e) {}
        openPairingApprovalModal(pendingDev);
      });
    }

    if (closePairBtn && pairModal) {
      closePairBtn.addEventListener("click", () => pairModal.style.display = "none");
    }
    if (cancelPairBtn && pairModal) {
      cancelPairBtn.addEventListener("click", () => pairModal.style.display = "none");
    }

    // Typing 6-digit code is strictly required (Step 16b Rule 3)
    if (submitPairBtn && pairCodeInput) {
      submitPairBtn.addEventListener("click", async () => {
        const code = pairCodeInput.value.trim();
        const warn = document.getElementById("pairAttemptsWarning");
        if (!code || code.length < 6) {
          showToast("Please enter the complete 6-digit pairing code.");
          if (warn) {
            warn.textContent = "Please enter all 6 digits.";
            warn.style.display = "block";
          }
          return;
        }
        try {
          const res = await fetch("/api/devices/approve-pairing", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              code: code,
              approver_device_id: getOrCreateDeviceId()
            })
          });
          const data = await res.json();
          if (data.success) {
            showToast("Device approved and paired successfully!");
            if (pairModal) pairModal.style.display = "none";
            await loadDevices();
          } else {
            const errMsg = data.detail || data.message || "Pairing approval failed.";
            showToast(`❌ ${errMsg}`);
            if (warn) {
              warn.textContent = errMsg;
              warn.style.display = "block";
            }
            await loadDevices();
          }
        } catch (e) {
          showToast("Error approving device: " + e.message);
        }
      });
    }

    // Trust first device for existing accounts using password (Step 16b Rule 2)
    const trustFirstDevBtn = document.getElementById("trustFirstDeviceBtn");
    const firstDevPassInput = document.getElementById("firstDevicePasswordInput");
    if (trustFirstDevBtn && firstDevPassInput) {
      trustFirstDevBtn.addEventListener("click", async () => {
        const pwd = firstDevPassInput.value;
        if (!pwd) {
          showToast("Please enter your account password.");
          firstDevPassInput.focus();
          return;
        }
        const myId = getOrCreateDeviceId();
        const { platform, name } = await getDevicePlatformAndName();
        try {
          const res = await fetch("/api/devices/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              device_id: myId,
              name: name,
              platform: platform,
              password: pwd
            })
          });
          const data = await res.json();
          if (data.success && data.device && data.device.status === "trusted") {
            currentDeviceData = data.device;
            updateCurrentDeviceUI(currentDeviceData);
            showToast("First device verified with password and trusted!");
            connectDeviceWebSocket(myId);
            loadDevices();
          } else {
            showToast(data.detail || data.message || "Incorrect password.");
          }
        } catch (e) {
          showToast("Error trusting device: " + e.message);
        }
      });
    }

    // Refresh pairing code button for pending device
    const refreshCodeBtn = document.getElementById("refreshPairCodeBtn");
    const topRefreshCodeBtn = document.getElementById("topRefreshPairCodeBtn");
    const triggerCodeRefresh = async () => {
      const myId = getOrCreateDeviceId();
      try {
        const res = await fetch(`/api/devices/refresh-code?device_id=${encodeURIComponent(myId)}`, {
          method: "POST"
        });
        const data = await res.json();
        if (data.success && data.device) {
          currentDeviceData = data.device;
          showPendingPairingUI(currentDeviceData);
          showToast("Fresh pairing code generated");
        }
      } catch (e) {}
    };

    if (refreshCodeBtn) refreshCodeBtn.addEventListener("click", triggerCodeRefresh);
    if (topRefreshCodeBtn) topRefreshCodeBtn.addEventListener("click", triggerCodeRefresh);

    const topOpenSettingsBtn = document.getElementById("topOpenPairSettingsBtn");
    if (topOpenSettingsBtn && openSettingsBtn) {
      topOpenSettingsBtn.addEventListener("click", () => {
        openSettingsBtn.click();
      });
    }

    // First Device Trust Modal Form Submission (Requirement 4: Prominent full-screen prompt with password)
    const firstTrustForm = document.getElementById("firstDeviceTrustForm");
    const firstTrustDismissBtn = document.getElementById("firstDeviceModalDismissBtn");
    if (firstTrustDismissBtn) {
      firstTrustDismissBtn.addEventListener("click", () => {
        closeFirstDeviceTrustModal();
      });
    }

    if (firstTrustForm) {
      firstTrustForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = document.getElementById("firstDeviceModalPasswordInput");
        const err = document.getElementById("firstDeviceModalError");
        const submitBtn = document.getElementById("firstDeviceModalSubmitBtn");
        const pwd = input ? input.value : "";
        if (!pwd) return;

        if (err) err.style.display = "none";
        const originalText = submitBtn ? submitBtn.textContent : "✓ Verify & Trust Device 🐘";
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.textContent = "⏳ Verifying & Trusting...";
        }

        const myId = getOrCreateDeviceId();
        const { platform, name } = await getDevicePlatformAndName();

        try {
          const res = await fetch("/api/devices/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              device_id: myId,
              name: name,
              platform: platform,
              password: pwd
            })
          });
          const data = await res.json();
          if (data.success && data.device) {
            // Case 1: Immediately trusted
            if (data.device.status === "trusted") {
              currentDeviceData = data.device;
              closeFirstDeviceTrustModal();
              updateCurrentDeviceUI(currentDeviceData);
              showToast("Device verified with password and trusted! 🐘");
              connectDeviceWebSocket(myId);
              loadDevices();
              return;
            }

            // Case 2: Generated token for password-verified first device
            const token = data.device.first_device_token || (data.confirmation_token);
            if (token) {
              try {
                // Auto-confirm token immediately so user is never stuck
                const confRes = await fetch(`/api/devices/confirm-first-device?token=${encodeURIComponent(token)}`, {
                  method: "POST"
                });
                const confData = await confRes.json();
                if (confData.success) {
                  currentDeviceData = { ...data.device, status: "trusted" };
                  closeFirstDeviceTrustModal();
                  updateCurrentDeviceUI(currentDeviceData);
                  showToast("Device verified with password and trusted! 🐘");
                  connectDeviceWebSocket(myId);
                  loadDevices();
                  return;
                }
              } catch (cfErr) {
                console.warn("Auto-confirm error:", cfErr);
              }

              if (err) {
                err.innerHTML = `✉️ Authorization link sent! <a href="/api/devices/confirm-first-device?token=${encodeURIComponent(token)}" style="color: #2563eb; font-weight: 700; text-decoration: underline;">Click here to trust immediately 🐘</a>`;
                err.style.color = "#059669";
                err.style.display = "block";
              }
              return;
            }
          }

          if (err) {
            err.textContent = data.detail || data.message || "Incorrect password. Please try again.";
            err.style.color = "#dc2626";
            err.style.display = "block";
          }
          if (input) input.focus();
        } catch (ex) {
          if (err) {
            err.textContent = "Error trusting device: " + ex.message;
            err.style.color = "#dc2626";
            err.style.display = "block";
          }
        } finally {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
          }
        }
      });
    }

    // Disconnect all devices button
    const disconnAllBtn = document.getElementById("disconnectAllDevicesBtn");
    if (disconnAllBtn) {
      disconnAllBtn.addEventListener("click", async () => {
        if (confirm("Disconnect and revoke all devices immediately? Remote commands will be halted immediately.")) {
          try {
            const res = await fetch("/api/devices/disconnect-all", { method: "POST" });
            const data = await res.json();
            if (data.success) {
              showToast("🔌 All devices disconnected and revoked immediately.");
              if (deviceWs) {
                try { deviceWs.close(); } catch (e) {}
                deviceWs = null;
              }
              await loadDevices();
              await initDeviceChannel();
            }
          } catch (e) {
            showToast("Error disconnecting devices: " + e.message);
          }
        }
      });
    }

    // Device Details Modal events
    const closeDevModalBtn = document.getElementById("closeDeviceDetailsBtn");
    const cancelDevModalBtn = document.getElementById("cancelDeviceDetailsBtn");
    const devModal = document.getElementById("deviceDetailsModal");

    if (closeDevModalBtn && devModal) {
      closeDevModalBtn.addEventListener("click", () => devModal.style.display = "none");
    }
    if (cancelDevModalBtn && devModal) {
      cancelDevModalBtn.addEventListener("click", () => devModal.style.display = "none");
    }

    const saveDevNameBtn = document.getElementById("saveDeviceNameBtn");
    if (saveDevNameBtn) {
      saveDevNameBtn.addEventListener("click", async () => {
        const id = document.getElementById("editDeviceId").value;
        const name = document.getElementById("editDeviceNameInput").value.trim();
        if (!name) return;
        try {
          const res = await fetch(`/api/devices/${encodeURIComponent(id)}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: name })
          });
          const data = await res.json();
          if (data.success) {
            showToast("Device renamed");
            loadDevices();
          }
        } catch (e) {}
      });
    }

    const saveDevPermsBtn = document.getElementById("saveDevicePermissionsBtn");
    if (saveDevPermsBtn) {
      saveDevPermsBtn.addEventListener("click", async () => {
        const id = document.getElementById("editDeviceId").value;
        const permLevel = parseInt(document.getElementById("editDevicePermLevel").value, 10);
        const caps = {
          note: document.getElementById("capNoteToggle").checked,
          open_link: document.getElementById("capOpenLinkToggle").checked,
          ring: document.getElementById("capRingToggle").checked,
          sync: document.getElementById("capSyncToggle").checked
        };
        const elevateGroup = document.getElementById("elevatePasswordGroup");
        const elevateInput = document.getElementById("elevatePasswordInput");
        const isElevateActive = elevateGroup && elevateGroup.style.display !== "none";
        const passwordVal = isElevateActive ? (elevateInput ? elevateInput.value : "") : null;

        if (isElevateActive && !passwordVal) {
          showToast("Please enter your account password to authorize permission elevation.");
          if (elevateInput) elevateInput.focus();
          return;
        }

        try {
          const bodyPayload = {
            permission_level: permLevel,
            capabilities: caps
          };
          if (passwordVal) {
            bodyPayload.password = passwordVal;
          }

          const res = await fetch(`/api/devices/${encodeURIComponent(id)}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(bodyPayload)
          });
          const data = await res.json();
          if (data.success) {
            showToast("Device settings saved");
            if (devModal) devModal.style.display = "none";
            loadDevices();
          } else {
            showToast(data.detail || data.message || "Failed to update device settings.");
          }
        } catch (e) {
          showToast("Error saving device settings: " + e.message);
        }
      });
    }

    const revokeModalBtn = document.getElementById("revokeDeviceBtn");
    if (revokeModalBtn) {
      revokeModalBtn.addEventListener("click", async () => {
        const id = document.getElementById("editDeviceId").value;
        if (confirm("Revoke this device immediately?")) {
          await revokeDevice(id);
          if (devModal) devModal.style.display = "none";
        }
      });
    }

    // Quick remote test buttons
    const testRingBtn = document.getElementById("testRingDeviceBtn");
    if (testRingBtn) {
      testRingBtn.addEventListener("click", () => {
        const id = document.getElementById("editDeviceId").value;
        sendRemoteCommand(id, "ring_phone", { duration: 10 });
      });
    }

    const testNoteBtn = document.getElementById("testSendNoteBtn");
    if (testNoteBtn) {
      testNoteBtn.addEventListener("click", () => {
        const id = document.getElementById("editDeviceId").value;
        const text = prompt("Enter note to send to device:", "Hello from SINBHA!");
        if (text) {
          sendRemoteCommand(id, "send_note", { text: text });
        }
      });
    }

    const testSyncBtn = document.getElementById("testSyncDeviceBtn");
    if (testSyncBtn) {
      testSyncBtn.addEventListener("click", () => {
        const id = document.getElementById("editDeviceId").value;
        sendRemoteCommand(id, "sync_tasks", { reason: "manual_sync" });
      });
    }

    // Incoming Remote Confirmation Modal actions
    const allowRemoteBtn = document.getElementById("allowRemoteCmdBtn");
    const denyRemoteBtn = document.getElementById("denyRemoteCmdBtn");
    const remoteModal = document.getElementById("remoteConfirmModal");

    if (allowRemoteBtn && remoteModal) {
      allowRemoteBtn.addEventListener("click", async () => {
        remoteModal.style.display = "none";
        if (activePendingRemoteCmd) {
          await executeRemoteCommand(activePendingRemoteCmd);
          activePendingRemoteCmd = null;
        }
      });
    }

    if (denyRemoteBtn && remoteModal) {
      denyRemoteBtn.addEventListener("click", async () => {
        remoteModal.style.display = "none";
        if (activePendingRemoteCmd) {
          try {
            await fetch(`/api/devices/commands/${encodeURIComponent(activePendingRemoteCmd.id)}/ack`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ status: "denied" })
            });
          } catch (e) {}
          activePendingRemoteCmd = null;
        }
      });
    }

    // Dismiss ringing button
    const dismissRingBtn = document.getElementById("dismissRingBtn");
    const ringModal = document.getElementById("ringAlertModal");
    if (dismissRingBtn && ringModal) {
      dismissRingBtn.addEventListener("click", () => {
        stopRingtone();
        ringModal.style.display = "none";
      });
    }

    // Manual App Update Check Button
    const manualUpdateBtn = document.getElementById("manualCheckUpdateBtn");
    if (manualUpdateBtn) {
      manualUpdateBtn.addEventListener("click", () => {
        checkAppVersionGate(true);
      });
    }

    // ========================================================
    // MOBILE BOTTOM NAVIGATION (Phase 6)
    // ========================================================
    const navChatBtn = document.getElementById("navChatBtn");
    const navTasksBtn = document.getElementById("navTasksBtn");
    const navDevicesBtn = document.getElementById("navDevicesBtn");
    const navMemoryBtn = document.getElementById("navMemoryBtn");

    function setActiveNav(btn) {
      [navChatBtn, navTasksBtn, navDevicesBtn, navMemoryBtn].forEach(b => {
        if (b) b.classList.remove("active");
      });
      if (btn) btn.classList.add("active");
    }

    if (navChatBtn) {
      navChatBtn.addEventListener("click", () => {
        setActiveNav(navChatBtn);
        closeDrawers();
        if (settingsModal) settingsModal.style.display = "none";
        if (messageInput) {
          messageInput.focus();
          messageInput.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      });
    }

    if (navTasksBtn) {
      navTasksBtn.addEventListener("click", () => {
        setActiveNav(navTasksBtn);
        openTaskDrawer();
      });
    }

    if (navDevicesBtn) {
      navDevicesBtn.addEventListener("click", () => {
        setActiveNav(navDevicesBtn);
        closeDrawers();
        if (settingsModal) {
          settingsModal.style.display = "flex";
          loadSettings();
          loadDevices();
          setTimeout(() => {
            const devSec = document.getElementById("settingsDevicesSection");
            if (devSec) devSec.scrollIntoView({ behavior: "smooth", block: "start" });
          }, 150);
        }
      });
    }

    if (navMemoryBtn) {
      navMemoryBtn.addEventListener("click", () => {
        setActiveNav(navMemoryBtn);
        closeDrawers();
        if (settingsModal) {
          settingsModal.style.display = "flex";
          loadSettings();
          loadUserMemory();
          setTimeout(() => {
            const memSec = document.getElementById("settingsMemorySection");
            if (memSec) memSec.scrollIntoView({ behavior: "smooth", block: "start" });
          }, 150);
        }
      });
    }

    // ========================================================
    // USER MEMORY MANAGEMENT (Phase 2 & Phase 6)
    // ========================================================
    const userMemoryToggle = document.getElementById("userMemoryToggle");
    const userMemoryBadge = document.getElementById("userMemoryBadge");
    const userMemoryCount = document.getElementById("userMemoryCount");
    const userMemoryListContainer = document.getElementById("userMemoryListContainer");
    const refreshUserMemoryBtn = document.getElementById("refreshUserMemoryBtn");
    const exportUserMemoryBtn = document.getElementById("exportUserMemoryBtn");
    const wipeUserMemoryBtn = document.getElementById("wipeUserMemoryBtn");

    async function loadUserMemory() {
      if (!userMemoryListContainer) return;
      try {
        const res = await fetch("/api/user/memory");
        if (!res.ok) return;
        const data = await res.json();
        const facts = data.facts || [];
        const isEnabled = data.memory_enabled !== false;

        if (userMemoryToggle) userMemoryToggle.checked = isEnabled;
        if (userMemoryBadge) {
          userMemoryBadge.textContent = isEnabled ? "Active" : "Disabled";
          userMemoryBadge.style.color = isEnabled ? "#db2777" : "#6b7280";
        }
        if (userMemoryCount) userMemoryCount.textContent = facts.length;

        if (facts.length === 0) {
          userMemoryListContainer.innerHTML = `<div style="text-align: center; color: #9ca3af; font-size: 0.8rem; padding: 18px;">No remembered facts yet. Tell SINBHA about your studies, goals, or preferences in chat!</div>`;
          return;
        }

        userMemoryListContainer.innerHTML = facts.map(f => `
          <div class="user-memory-item">
            <div style="flex: 1;">
              <div>${escapeHtml(f.fact || "")}</div>
              <div class="memory-meta">Category: ${escapeHtml(f.category || "general")} • Source: ${escapeHtml(f.source || "user")}</div>
            </div>
            <span class="memory-badge">${escapeHtml(f.fact_type || "fact")}</span>
          </div>
        `).join("");
      } catch (err) {
        console.error("Failed to load user memory:", err);
      }
    }

    if (refreshUserMemoryBtn) {
      refreshUserMemoryBtn.addEventListener("click", loadUserMemory);
    }

    if (userMemoryToggle) {
      userMemoryToggle.addEventListener("change", async () => {
        try {
          const res = await fetch("/api/user/memory/toggle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: userMemoryToggle.checked })
          });
          if (res.ok) {
            loadUserMemory();
          }
        } catch (e) {
          console.error("Failed to toggle memory:", e);
        }
      });
    }

    if (exportUserMemoryBtn) {
      exportUserMemoryBtn.addEventListener("click", async () => {
        try {
          const res = await fetch("/api/user/memory/export");
          if (!res.ok) return;
          const data = await res.json();
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `sinbha_memory_export_${new Date().toISOString().split("T")[0]}.json`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        } catch (e) {
          console.error("Export memory error:", e);
        }
      });
    }

    if (wipeUserMemoryBtn) {
      wipeUserMemoryBtn.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to permanently erase all your remembered facts, goals, and study context?")) {
          return;
        }
        try {
          const res = await fetch("/api/user/memory", { method: "DELETE" });
          if (res.ok) {
            loadUserMemory();
          }
        } catch (e) {
          console.error("Wipe memory error:", e);
        }
      });
    }

    // Startup: Verify Authentication status first
    checkAuthStatus();
    checkAppVersionGate(false);

    // Step C2.10: Check server versions every 3 hours
    setInterval(() => {
      checkAppVersionGate(false);
    }, 3 * 60 * 60 * 1000);



    // Periodic reminder checker every 60 seconds (only fires if logged in)
    setInterval(() => {
      if (currentUser) {
        checkDueReminders();
        syncSessionWithNativeApp();
      }
    }, 60000);
  });

