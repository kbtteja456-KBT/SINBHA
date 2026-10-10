// ========================================================
// SINBHA - Client Script (Step 4: Continuous Memory)
// ========================================================

document.addEventListener("DOMContentLoaded", () => {
  const messageInput = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");
  const chatMessages = document.getElementById("chatMessages");
  const scrollAnchor = document.getElementById("scrollAnchor");
  
  // Header controls
  const memoryBtn = document.getElementById("memoryBtn");
  const tasksBtn = document.getElementById("tasksBtn");
  const stopBtn = document.getElementById("stopBtn");
  const stopBanner = document.getElementById("stopBanner");
  const bannerResumeBtn = document.getElementById("bannerResumeBtn");
  const statusDot = document.getElementById("statusDot");
  const factsCountBadge = document.getElementById("factsCountBadge");
  const factsCountLabel = document.getElementById("factsCountLabel");

  // Drawers
  const memoryDrawer = document.getElementById("memoryDrawer");
  const taskDrawer = document.getElementById("taskDrawer");
  const drawerOverlay = document.getElementById("drawerOverlay");
  const closeMemoryBtn = document.getElementById("closeMemoryBtn");
  const closeTaskBtn = document.getElementById("closeTaskBtn");
  const toast = document.getElementById("toast");

  // Memory Drawer elements
  const manualFactInput = document.getElementById("manualFactInput");
  const addFactBtn = document.getElementById("addFactBtn");
  const factsList = document.getElementById("factsList");
  const purgeBtn = document.getElementById("purgeBtn");

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

  // Add an AI bubble to chat
  function appendAiMessage(text, timeStr = null) {
    const group = document.createElement("div");
    group.className = "message-group ai-group";
    group.innerHTML = `
      <div class="message-avatar">🌸</div>
      <div class="message-bubble ai-bubble">
        <p>${escapeHtml(text)}</p>
        <span class="message-time">${formatTime(timeStr)}</span>
      </div>
    `;
    chatMessages.appendChild(group);
    scrollToBottom();
  }

  // Add a system notice (e.g., STOP confirmation)
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

  function escapeHtml(string) {
    const div = document.createElement("div");
    div.innerText = string;
    return div.innerHTML;
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

  // Load chat messages on startup (Continuous Memory)
  async function loadChatHistory() {
    try {
      const res = await fetch("/api/messages");
      if (!res.ok) return;
      const data = await res.json();
      
      chatMessages.innerHTML = "";
      setStopUiState(data.emergency_stopped);

      if (!data.messages || data.messages.length === 0) {
        // Welcome message if chat history is empty
        appendAiMessage("Hey there! I'm SINBHA 🌸 I'm here to listen, support you, and help keep your days calm and organized. How are you feeling right now?");
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

  // Load Facts count and list
  async function loadFacts() {
    try {
      const res = await fetch("/api/facts");
      if (!res.ok) return;
      const data = await res.json();
      const facts = data.facts || [];

      // Update badge counts
      factsCountBadge.textContent = facts.length;
      factsCountLabel.textContent = facts.length;

      // Render facts list
      renderFactsList(facts);
    } catch (e) {
      console.error("Failed to load facts:", e);
    }
  }

  function renderFactsList(facts) {
    if (!facts || facts.length === 0) {
      factsList.innerHTML = `<div class="empty-facts">No facts remembered yet 🌸<br><small>When you share personal details like your name or favorites, SINBHA will note them here.</small></div>`;
      return;
    }

    factsList.innerHTML = "";
    facts.forEach(f => {
      const item = document.createElement("div");
      item.className = "fact-item";
      item.id = `fact-${f.id}`;
      item.innerHTML = `
        <div class="fact-view-mode">
          <div class="fact-item-text">${escapeHtml(f.fact)}</div>
          <div class="fact-actions">
            <button class="fact-action-btn fact-edit-btn" data-id="${f.id}">✏️ Edit</button>
            <button class="fact-action-btn fact-delete-btn" data-id="${f.id}">🗑️ Delete</button>
          </div>
        </div>
        <div class="fact-edit-group" style="display: none;">
          <input type="text" class="fact-edit-input" value="${escapeHtml(f.fact)}" maxlength="200" />
          <div class="fact-edit-controls">
            <button class="fact-save-btn" data-id="${f.id}">Save</button>
            <button class="fact-cancel-btn" data-id="${f.id}">Cancel</button>
          </div>
        </div>
      `;

      // Hook edit toggle
      const editBtn = item.querySelector(".fact-edit-btn");
      const viewMode = item.querySelector(".fact-view-mode");
      const editMode = item.querySelector(".fact-edit-group");
      const cancelBtn = item.querySelector(".fact-cancel-btn");
      const saveBtn = item.querySelector(".fact-save-btn");
      const editInput = item.querySelector(".fact-edit-input");

      editBtn.addEventListener("click", () => {
        viewMode.style.display = "none";
        editMode.style.display = "flex";
        editInput.focus();
      });

      cancelBtn.addEventListener("click", () => {
        editMode.style.display = "none";
        viewMode.style.display = "block";
      });

      saveBtn.addEventListener("click", async () => {
        const updatedText = editInput.value.trim();
        if (!updatedText) return;
        await updateFact(f.id, updatedText);
      });

      // Hook delete
      const delBtn = item.querySelector(".fact-delete-btn");
      delBtn.addEventListener("click", async () => {
        if (confirm(`Delete memory: "${f.fact}"?`)) {
          await deleteFact(f.id);
        }
      });

      factsList.appendChild(item);
    });
  }

  // Add Fact manually
  async function addManualFact() {
    const text = manualFactInput.value.trim();
    if (!text) return;

    try {
      const res = await fetch("/api/facts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fact: text, category: "manual" })
      });
      if (res.ok) {
        manualFactInput.value = "";
        showToast("🌸 Fact remembered!");
        loadFacts();
      }
    } catch (e) {
      showToast("Could not save fact");
    }
  }

  addFactBtn.addEventListener("click", addManualFact);
  manualFactInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      addManualFact();
    }
  });

  // Update fact
  async function updateFact(id, newText) {
    try {
      const res = await fetch(`/api/facts/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fact: newText })
      });
      if (res.ok) {
        showToast("🌸 Memory updated!");
        loadFacts();
      }
    } catch (e) {
      showToast("Failed to update memory");
    }
  }

  // Delete fact
  async function deleteFact(id) {
    try {
      const res = await fetch(`/api/facts/${id}`, { method: "DELETE" });
      if (res.ok) {
        showToast("Memory deleted");
        loadFacts();
      }
    } catch (e) {
      showToast("Failed to delete memory");
    }
  }

  // Purge All Data (Reset Everything)
  purgeBtn.addEventListener("click", async () => {
    const confirmed = confirm(
      "⚠️ Are you sure you want to delete ALL your data?\n\nThis will permanently wipe:\n- All chat message history\n- All remembered facts\n- All tasks\n\nThis cannot be undone."
    );
    if (!confirmed) return;

    try {
      const res = await fetch("/api/purge", { method: "POST" });
      if (res.ok) {
        showToast("🧹 All data wiped cleanly");
        chatMessages.innerHTML = "";
        appendAiMessage("All past conversations and memory have been wiped cleanly. We have a fresh, blank canvas together 🌸");
        loadFacts();
        closeDrawers();
      }
    } catch (e) {
      showToast("Error wiping data");
    }
  });

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
      // Normal message automatically resumes if stopped
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
      appendAiMessage(data.reply);

      if (data.stopped) {
        setStopUiState(true);
      }

      // If new facts were saved, update facts list in background
      if (data.new_facts && data.new_facts.length > 0) {
        loadFacts();
        showToast(`🌸 SINBHA remembered: ${data.new_facts[0]}`);
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

    try {
      await fetch("/api/stop", { method: "POST" });
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

  // Drawer toggles
  function openMemoryDrawer() {
    closeDrawers();
    memoryDrawer.classList.add("open");
    drawerOverlay.classList.add("active");
    memoryDrawer.setAttribute("aria-hidden", "false");
    loadFacts();
  }

  function openTaskDrawer() {
    closeDrawers();
    taskDrawer.classList.add("open");
    drawerOverlay.classList.add("active");
    taskDrawer.setAttribute("aria-hidden", "false");
  }

  function closeDrawers() {
    memoryDrawer.classList.remove("open");
    taskDrawer.classList.remove("open");
    drawerOverlay.classList.remove("active");
    memoryDrawer.setAttribute("aria-hidden", "true");
    taskDrawer.setAttribute("aria-hidden", "true");
  }

  memoryBtn.addEventListener("click", openMemoryDrawer);
  tasksBtn.addEventListener("click", openTaskDrawer);
  closeMemoryBtn.addEventListener("click", closeDrawers);
  closeTaskBtn.addEventListener("click", closeDrawers);
  drawerOverlay.addEventListener("click", closeDrawers);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeDrawers();
    }
  });

  // Initial loads
  loadChatHistory();
  loadFacts();
});
