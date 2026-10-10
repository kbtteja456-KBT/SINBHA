// ========================================================
// SINBHA - Client Script (Step 2 Interface)
// ========================================================

document.addEventListener("DOMContentLoaded", () => {
  const messageInput = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendBtn");
  const chatMessages = document.getElementById("chatMessages");
  const chatContainer = document.getElementById("chatContainer");
  const scrollAnchor = document.getElementById("scrollAnchor");
  
  const tasksBtn = document.getElementById("tasksBtn");
  const stopBtn = document.getElementById("stopBtn");
  const taskDrawer = document.getElementById("taskDrawer");
  const drawerOverlay = document.getElementById("drawerOverlay");
  const closeDrawerBtn = document.getElementById("closeDrawerBtn");
  const toast = document.getElementById("toast");

  // Format current time (e.g. "8:25 PM")
  function formatTime(date = new Date()) {
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  // Update welcome message timestamp
  const welcomeTime = document.getElementById("welcomeTime");
  if (welcomeTime) {
    welcomeTime.textContent = formatTime();
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
    // Auto resize height up to max
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + "px";
    sendBtn.disabled = messageInput.value.trim().length === 0;
  });

  // Handle Enter key (Shift+Enter allows newline)
  messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled) {
        sendMessage();
      }
    }
  });

  // Add a user bubble to chat
  function appendUserMessage(text) {
    const group = document.createElement("div");
    group.className = "message-group user-group";
    group.innerHTML = `
      <div class="message-bubble user-bubble">
        <p>${escapeHtml(text)}</p>
        <span class="message-time">${formatTime()}</span>
      </div>
    `;
    chatMessages.appendChild(group);
    scrollToBottom();
  }

  // Add an AI bubble to chat
  function appendAiMessage(text) {
    const group = document.createElement("div");
    group.className = "message-group ai-group";
    group.innerHTML = `
      <div class="message-avatar">🌸</div>
      <div class="message-bubble ai-bubble">
        <p>${escapeHtml(text)}</p>
        <span class="message-time">${formatTime()}</span>
      </div>
    `;
    chatMessages.appendChild(group);
    scrollToBottom();
  }

  // Add a system notice (e.g., STOP confirmation)
  function appendSystemNotice(text) {
    const notice = document.createElement("div");
    notice.className = "system-bubble";
    notice.textContent = text;
    chatMessages.appendChild(notice);
    scrollToBottom();
  }

  // Escape HTML to prevent accidental injection
  function escapeHtml(string) {
    const div = document.createElement("div");
    div.innerText = string;
    return div.innerHTML;
  }

  // Send message function
  async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text) return;

    // Reset input field
    messageInput.value = "";
    messageInput.style.height = "auto";
    sendBtn.disabled = true;

    // Show user message immediately
    appendUserMessage(text);

    // If user typed STOP directly in chat
    if (text.toUpperCase() === "STOP") {
      triggerEmergencyStop();
      return;
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
    } catch (err) {
      appendAiMessage("I had a little hiccup connecting right now. Don't worry, please check if the server is still running on your computer 🌸");
      console.error(err);
    }
  }

  sendBtn.addEventListener("click", sendMessage);

  // Emergency STOP button functionality
  async function triggerEmergencyStop() {
    showToast("🛑 Emergency STOP activated", 3500);
    appendSystemNotice("🛑 Emergency STOP triggered. All processing halted.");

    try {
      await fetch("/api/stop", { method: "POST" });
    } catch (e) {
      console.error("Stop call failed", e);
    }
  }

  stopBtn.addEventListener("click", () => {
    triggerEmergencyStop();
  });

  // Task Drawer open/close toggles
  function openTaskDrawer() {
    taskDrawer.classList.add("open");
    drawerOverlay.classList.add("active");
    taskDrawer.setAttribute("aria-hidden", "false");
  }

  function closeTaskDrawer() {
    taskDrawer.classList.remove("open");
    drawerOverlay.classList.remove("active");
    taskDrawer.setAttribute("aria-hidden", "true");
  }

  tasksBtn.addEventListener("click", openTaskDrawer);
  closeDrawerBtn.addEventListener("click", closeTaskDrawer);
  drawerOverlay.addEventListener("click", closeTaskDrawer);

  // Close drawer with Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && taskDrawer.classList.contains("open")) {
      closeTaskDrawer();
    }
  });

  // Scroll to bottom on initial load
  scrollToBottom();
});
