// ========================================================
// SINBHA - Client Script (Conversational Memory & Tasks Gate)
// ========================================================

document.addEventListener("DOMContentLoaded", () => {
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

  // Toast notification
  const toast = document.getElementById("toast");

  // Global state
  let isDevMode = false;

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

  // Add an AI bubble to chat (with optional proposal action card)
  function appendAiMessage(text, timeStr = null, proposal = null) {
    const group = document.createElement("div");
    group.className = "message-group ai-group";
    
    let proposalHtml = "";
    if (proposal) {
      if (proposal.type === "task_proposal") {
        // Step 5: Task proposal card with Confirm / Cancel gate
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
                <span>📅</span>
                ${proposal.due_date ? `<span class="task-proposal-due-badge">${escapeHtml(proposal.due_date)}</span>` : `<span style="color: #6b7280; font-size: 0.82rem;">No deadline</span>`}
              </div>
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
      }
    }

    group.innerHTML = `
      <div class="message-avatar">🌸</div>
      <div class="message-bubble ai-bubble">
        <p>${escapeHtml(text)}</p>
        ${proposalHtml}
        <span class="message-time">${formatTime(timeStr)}</span>
      </div>
    `;
    chatMessages.appendChild(group);

    // Attach event listeners to task proposal buttons (Step 5)
    if (proposal && proposal.type === "task_proposal") {
      const card = group.querySelector(".task-proposal-card");
      const confirmBtn = group.querySelector(".task-confirm-btn");
      const cancelBtn = group.querySelector(".task-cancel-btn");

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

    scrollToBottom();
  }

  // Handle confirming a proposed task (Step 5)
  async function handleTaskConfirm(proposalId, cardElement) {
    try {
      const res = await fetch("/api/tasks/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposal_id: proposalId })
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
        showToast("🌸 Task saved to your list!");
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
        <button class="resume-btn inline-resume-btn">🌸 Resume Chat</button>
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
      if (!res.ok) return;
      const data = await res.json();
      
      chatMessages.innerHTML = "";
      setStopUiState(data.emergency_stopped);

      if (!data.messages || data.messages.length === 0) {
        appendAiMessage("Hey there! I'm SINBHA 🌸 I'm here to listen, support you, and keep your days calm and organized. How are you feeling right now?");
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
      pendingTaskList.innerHTML = `<li style="font-size: 0.84rem; color: #9ca3af; text-align: center; padding: 14px 0;">All caught up! No pending tasks 🌸</li>`;
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
                ${t.due_date ? `<span class="task-card-due ${t.is_overdue ? "overdue-text" : ""}">📅 Due: ${escapeHtml(t.due_date)}</span>` : `<span class="task-card-due no-date">📅 No due date</span>`}
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
            showToast("🌸 Great job! Task marked as done!");
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
                ${t.due_date ? `<span class="task-card-due no-date">📅 ${escapeHtml(t.due_date)}</span>` : `<span class="task-card-due no-date">📅 No due date</span>`}
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
          showToast("Task brought back to pending 🌸");
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

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text })
      });

      if (!response.ok) {
        throw new Error("Server responded with error");
      }

      const data = await response.json();
      appendAiMessage(data.reply, null, data.proposal);

      if (data.stopped) {
        setStopUiState(true);
      }

      if (data.task_confirmed || data.task_action_performed) {
        loadTasks();
        if (data.task_action_performed) {
          showToast("🌸 Tasks updated!");
        } else {
          showToast("🌸 Task saved to your list!");
        }
      }

      // If facts or proposals were updated, reload dev data in background
      if (isDevMode && (data.new_facts?.length > 0 || data.updated_fact || data.action_performed || data.proposal || data.task_confirmed || data.task_cancelled || data.task_action_performed)) {
        loadDevData();
      }
    } catch (err) {
      appendAiMessage("I had a little hiccup connecting right now. Don't worry, please check if the server is still running on your computer 🌸");
      console.error(err);
    }
  }

  sendBtn.addEventListener("click", sendMessage);

  // Emergency STOP button functionality
  async function triggerEmergencyStop() {
    setStopUiState(true);
    showToast("🛑 Emergency STOP activated", 3500);
    appendSystemNotice("🛑 Emergency STOP triggered. All processing halted.");

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
      showToast("🌸 Welcome back! Chat resumed.");
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
    settingsModal.style.display = "flex";
  });

  closeSettingsBtn.addEventListener("click", () => {
    settingsModal.style.display = "none";
  });

  openPurgeConfirmBtn.addEventListener("click", () => {
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
        appendAiMessage("All past conversations and memory have been wiped cleanly. We have a fresh, blank canvas together 🌸");
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

  // Drawer toggles
  function openTaskDrawer() {
    closeDrawers();
    taskDrawer.classList.add("open");
    drawerOverlay.classList.add("active");
    taskDrawer.setAttribute("aria-hidden", "false");
    loadTasks();
  }

  function openDevDrawer() {
    if (!isDevMode) return;
    closeDrawers();
    devMemoryDrawer.style.display = "block";
    devMemoryDrawer.classList.add("open");
    drawerOverlay.classList.add("active");
    devMemoryDrawer.setAttribute("aria-hidden", "false");
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

  // Initialize
  loadChatHistory();
  loadTasks();
  checkAppInfo();
});
