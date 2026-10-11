// ========================================================
// SINBHA DESKTOP OVERLAY CONTROLLER
// Handles 3D bird flight, click-through hover, and actions
// ========================================================

document.addEventListener("DOMContentLoaded", () => {
  const flightWrapper = document.getElementById("overlayFlightWrapper");
  const birdActor = document.getElementById("overlayBirdActor");
  const noteTitle = document.getElementById("overlayNoteTitle");
  const noteDue = document.getElementById("overlayNoteDue");

  const actionPopup = document.getElementById("overlayActionPopup");
  const closePopupBtn = document.getElementById("overlayClosePopupBtn");
  const popupTitle = document.getElementById("overlayPopupTitle");
  const popupDue = document.getElementById("overlayPopupDue");
  const doneBtn = document.getElementById("overlayDoneBtn");
  const snoozeToggleBtn = document.getElementById("overlaySnoozeToggleBtn");
  const snoozeMenu = document.getElementById("overlaySnoozeMenu");
  const chatBtn = document.getElementById("overlayChatBtn");

  let currentTask = null;
  let currentReminderId = null;
  let flightTimer = null;
  let isMouseOverInteractive = false;

  // Initial state: click-through everywhere
  if (window.electronAPI) {
    window.electronAPI.setIgnoreMouseEvents(true, { forward: true });
  }

  // Helper to safely update ignore mouse events
  function updateMouseIgnore() {
    if (!window.electronAPI) return;
    if (isMouseOverInteractive) {
      window.electronAPI.setIgnoreMouseEvents(false);
    } else {
      window.electronAPI.setIgnoreMouseEvents(true, { forward: true });
    }
  }

  // Set up hover tracking for interactive elements
  const interactiveElements = document.querySelectorAll(".interactive-area");
  interactiveElements.forEach(el => {
    el.addEventListener("mouseenter", () => {
      isMouseOverInteractive = true;
      updateMouseIgnore();
    });
    el.addEventListener("mouseleave", () => {
      // Check if mouse left all interactive elements
      setTimeout(() => {
        const hovered = document.querySelectorAll(".interactive-area:hover");
        if (hovered.length === 0) {
          isMouseOverInteractive = false;
          updateMouseIgnore();
        }
      }, 50);
    });
  });

  // Show bird with flight animation
  function showBird(task, reminderId) {
    currentTask = task;
    currentReminderId = reminderId;

    // Populate note overlay
    if (noteTitle) noteTitle.textContent = task.title || "Task Reminder";
    const dueTxt = task.due_time ? task.due_time : (task.due_date ? task.due_date : "Today");
    if (noteDue) noteDue.textContent = `Due: ${dueTxt}`;

    // Populate action popup
    if (popupTitle) popupTitle.textContent = task.title || "Task Reminder";
    if (popupDue) {
      popupDue.textContent = task.due_date 
        ? `Due: ${task.due_date}${task.due_time ? ' at ' + task.due_time : ''}` 
        : "Pending";
    }

    if (actionPopup) actionPopup.style.display = "none";
    if (snoozeMenu) snoozeMenu.style.display = "none";

    const prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReducedMotion) {
      if (flightWrapper) {
        flightWrapper.style.display = "block";
        flightWrapper.classList.remove("is-flying");
        flightWrapper.classList.add("is-landed");
      }
    } else {
      if (flightWrapper) {
        flightWrapper.style.display = "block";
        flightWrapper.classList.remove("is-landed");
        flightWrapper.classList.add("is-flying");

        if (flightTimer) clearTimeout(flightTimer);
        flightTimer = setTimeout(() => {
          if (flightWrapper) {
            flightWrapper.classList.remove("is-flying");
            flightWrapper.classList.add("is-landed");
          }
        }, 4400);
      }
    }
  }

  // Hide bird and return full click-through
  function hideBird() {
    if (flightTimer) clearTimeout(flightTimer);
    if (flightWrapper) {
      flightWrapper.classList.remove("is-flying", "is-landed");
      flightWrapper.style.display = "none";
    }
    if (actionPopup) actionPopup.style.display = "none";
    if (snoozeMenu) snoozeMenu.style.display = "none";
    currentTask = null;
    currentReminderId = null;
    isMouseOverInteractive = false;
    updateMouseIgnore();
  }

  // Tap bird to toggle popup
  if (birdActor) {
    birdActor.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!actionPopup) return;
      const isVisible = actionPopup.style.display === "block";
      actionPopup.style.display = isVisible ? "none" : "block";
      if (!isVisible) {
        isMouseOverInteractive = true;
        updateMouseIgnore();
      }
    });
  }

  // Close popup button
  if (closePopupBtn) {
    closePopupBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (actionPopup) actionPopup.style.display = "none";
      if (snoozeMenu) snoozeMenu.style.display = "none";
      isMouseOverInteractive = false;
      updateMouseIgnore();
    });
  }

  // Done button
  if (doneBtn) {
    doneBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!currentTask) return;
      if (window.electronAPI) {
        await window.electronAPI.markTaskDone(currentTask.id);
      }
      hideBird();
    });
  }

  // Snooze dropdown toggle
  if (snoozeToggleBtn) {
    snoozeToggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!snoozeMenu) return;
      const isVis = snoozeMenu.style.display === "flex";
      snoozeMenu.style.display = isVis ? "none" : "flex";
    });
  }

  // Snooze option clicks
  document.querySelectorAll(".snooze-opt").forEach(opt => {
    opt.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!currentTask) return;
      const mins = parseInt(opt.dataset.mins, 10);
      if (window.electronAPI && mins) {
        await window.electronAPI.snoozeReminder(currentTask.id, mins);
      }
      hideBird();
    });
  });

  // Open Chat button
  if (chatBtn) {
    chatBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (window.electronAPI) {
        window.electronAPI.openChatWindow();
      }
      hideBird();
    });
  }

  // Escape key dismisses bird or popup immediately
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      hideBird();
    }
  });

  // Listen to IPC events from Electron Main
  if (window.electronAPI) {
    window.electronAPI.onShowBird((data) => {
      if (data && data.task) {
        showBird(data.task, data.reminder_id);
      }
    });

    window.electronAPI.onHideBird(() => {
      hideBird();
    });
  }
});
