// ========================================================
// SINBHA DESKTOP OVERLAY CONTROLLER
// Handles 3D bird flight, cursor dragging, custom snooze minutes,
// reverse flight departures, and sequential task queueing.
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
  const snoozeMinsInput = document.getElementById("overlaySnoozeMinsInput");
  const snoozeSubmitBtn = document.getElementById("overlaySnoozeSubmitBtn");
  const chatBtn = document.getElementById("overlayChatBtn");

  let currentTask = null;
  let currentReminderId = null;
  let flightTimer = null;
  let isMouseOverInteractive = false;
  let isFlyingReverse = false;

  // Dragging state
  let isDraggingBird = false;
  let hasDraggedBird = false;
  let mouseStartX = 0;
  let mouseStartY = 0;
  let birdStartX = 0;
  let birdStartY = 0;

  // Initial state: click-through everywhere
  if (window.electronAPI) {
    window.electronAPI.setIgnoreMouseEvents(true, { forward: true });
  }

  // Helper to safely update ignore mouse events
  function updateMouseIgnore() {
    if (!window.electronAPI) return;
    if (isDraggingBird || isMouseOverInteractive) {
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
      setTimeout(() => {
        if (!isDraggingBird) {
          const hovered = document.querySelectorAll(".interactive-area:hover");
          if (hovered.length === 0) {
            isMouseOverInteractive = false;
            updateMouseIgnore();
          }
        }
      }, 60);
    });
  });

  // Dynamically position the popup nicely next to wherever the bird lands or is dragged
  function repositionPopup(birdX, birdY) {
    if (!actionPopup) return;
    const popupWidth = 320;
    const popupHeight = 180;
    let left = birdX - popupWidth - 14;
    // If overflowing left edge of screen, position to the right of bird
    if (left < 16) {
      left = birdX + 270 + 14;
    }
    // Clamp to viewport width
    if (left + popupWidth > window.innerWidth - 16) {
      left = window.innerWidth - popupWidth - 16;
    }
    if (left < 16) left = 16;

    // Clamp top
    const top = Math.max(16, Math.min(window.innerHeight - popupHeight - 20, birdY + 10));
    actionPopup.style.left = `${left}px`;
    actionPopup.style.top = `${top}px`;
    actionPopup.style.right = "auto";
    actionPopup.style.bottom = "auto";
  }

  // Show bird with forward arrival animation
  function showBird(task, reminderId) {
    currentTask = task;
    currentReminderId = reminderId;
    isFlyingReverse = false;

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

    // Reset flight wrapper transforms and styles
    if (flightWrapper) {
      flightWrapper.classList.remove("is-flying-reverse", "is-landed");
      flightWrapper.style.transform = "";
      flightWrapper.style.left = "";
      flightWrapper.style.top = "";
      flightWrapper.style.opacity = "1";
      flightWrapper.style.transition = "";
      flightWrapper.style.animation = "";
    }

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
          if (flightWrapper && !isFlyingReverse) {
            flightWrapper.classList.remove("is-flying");
            flightWrapper.classList.add("is-landed");
          }
        }, 4400);
      }
    }
  }

  // Smooth reverse flight departure when task is completed or snoozed
  function flyAwayReverse(callback) {
    if (isFlyingReverse) return;
    isFlyingReverse = true;
    if (flightTimer) clearTimeout(flightTimer);

    if (actionPopup) actionPopup.style.display = "none";
    if (snoozeMenu) snoozeMenu.style.display = "none";

    if (flightWrapper) {
      // Capture current position
      const rect = flightWrapper.getBoundingClientRect();
      flightWrapper.classList.remove("is-landed", "is-flying");
      flightWrapper.style.animation = "none";
      flightWrapper.style.left = `${rect.left}px`;
      flightWrapper.style.top = `${rect.top}px`;
      flightWrapper.style.transform = "none";

      // Trigger reverse flight
      flightWrapper.classList.add("is-flying-reverse");

      // Give browser a frame to commit class, then smoothly transition off-screen
      requestAnimationFrame(() => {
        flightWrapper.style.transition = "transform 1.6s cubic-bezier(0.25, 1, 0.4, 1), opacity 0.5s ease 1.1s";
        flightWrapper.style.transform = "translate3d(-360px, -220px, 0) scale(0.65) rotate(-14deg)";
        flightWrapper.style.opacity = "0";
      });
    }

    setTimeout(() => {
      hideBird();
      if (callback) callback();
      // Notify main process so the next task in the sorted queue can arrive
      if (window.electronAPI && window.electronAPI.birdDeparted) {
        window.electronAPI.birdDeparted();
      }
    }, 1650);
  }

  // Hide bird and return full desktop click-through
  function hideBird() {
    if (flightTimer) clearTimeout(flightTimer);
    if (flightWrapper) {
      flightWrapper.classList.remove("is-flying", "is-landed", "is-flying-reverse");
      flightWrapper.style.display = "none";
      flightWrapper.style.transform = "";
      flightWrapper.style.left = "";
      flightWrapper.style.top = "";
      flightWrapper.style.opacity = "1";
      flightWrapper.style.transition = "";
      flightWrapper.style.animation = "";
    }
    if (actionPopup) actionPopup.style.display = "none";
    if (snoozeMenu) snoozeMenu.style.display = "none";
    currentTask = null;
    currentReminderId = null;
    isDraggingBird = false;
    hasDraggedBird = false;
    isFlyingReverse = false;
    isMouseOverInteractive = false;
    updateMouseIgnore();
  }

  // ========================================================
  // DRAG AND DROP BIRD WITH CURSOR
  // ========================================================
  if (birdActor) {
    birdActor.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return; // Left mouse click only
      if (isFlyingReverse) return;

      isDraggingBird = true;
      hasDraggedBird = false;
      mouseStartX = e.clientX;
      mouseStartY = e.clientY;

      const rect = flightWrapper.getBoundingClientRect();
      birdStartX = rect.left;
      birdStartY = rect.top;

      birdActor.classList.add("is-dragging");
      if (window.electronAPI) {
        window.electronAPI.setIgnoreMouseEvents(false);
      }
    });

    // Tap / click bird to toggle popup options (only if not dragged)
    birdActor.addEventListener("click", (e) => {
      e.stopPropagation();
      if (hasDraggedBird) {
        hasDraggedBird = false;
        return;
      }
      if (!actionPopup) return;

      const isVisible = actionPopup.style.display === "block";
      if (!isVisible) {
        const rect = flightWrapper.getBoundingClientRect();
        repositionPopup(rect.left, rect.top);
        actionPopup.style.display = "block";
        isMouseOverInteractive = true;
        updateMouseIgnore();
      } else {
        actionPopup.style.display = "none";
        if (snoozeMenu) snoozeMenu.style.display = "none";
      }
    });
  }

  window.addEventListener("mousemove", (e) => {
    if (!isDraggingBird || !flightWrapper) return;

    const dx = e.clientX - mouseStartX;
    const dy = e.clientY - mouseStartY;

    if (Math.hypot(dx, dy) > 5) {
      hasDraggedBird = true;

      // Cancel resting animation while actively dragging
      flightWrapper.classList.remove("is-flying", "is-landed");
      flightWrapper.style.animation = "none";
      flightWrapper.style.transition = "none";

      const clampedX = Math.max(-40, Math.min(window.innerWidth - 220, birdStartX + dx));
      const clampedY = Math.max(-20, Math.min(window.innerHeight - 240, birdStartY + dy));

      flightWrapper.style.left = `${clampedX}px`;
      flightWrapper.style.top = `${clampedY}px`;
      flightWrapper.style.transform = "none";

      if (actionPopup && actionPopup.style.display === "block") {
        repositionPopup(clampedX, clampedY);
      }
    }
  });

  window.addEventListener("mouseup", () => {
    if (isDraggingBird) {
      isDraggingBird = false;
      if (birdActor) birdActor.classList.remove("is-dragging");
      setTimeout(() => {
        const hovered = document.querySelectorAll(".interactive-area:hover");
        if (hovered.length === 0) {
          isMouseOverInteractive = false;
          updateMouseIgnore();
        }
      }, 80);
    }
  });

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

  // Done button: Marks completed and bird flies back off-screen in reverse
  if (doneBtn) {
    doneBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!currentTask) return;
      const taskId = currentTask.id;
      if (window.electronAPI) {
        await window.electronAPI.markTaskDone(taskId);
      }
      flyAwayReverse();
    });
  }

  // Snooze dropdown toggle
  if (snoozeToggleBtn) {
    snoozeToggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!snoozeMenu) return;
      const isVis = snoozeMenu.style.display === "flex";
      snoozeMenu.style.display = isVis ? "none" : "flex";
      if (!isVis && snoozeMinsInput) {
        setTimeout(() => snoozeMinsInput.focus(), 50);
      }
    });
  }

  // Execute Snooze for custom or quick minutes
  async function executeSnooze(minutes) {
    if (!currentTask) return;
    const mins = parseInt(minutes, 10);
    if (isNaN(mins) || mins <= 0) return;
    const taskId = currentTask.id;

    if (window.electronAPI) {
      await window.electronAPI.snoozeReminder(taskId, mins);
    }

    flyAwayReverse();
  }

  // Custom Snooze submit button
  if (snoozeSubmitBtn) {
    snoozeSubmitBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const mins = snoozeMinsInput ? parseInt(snoozeMinsInput.value, 10) : 15;
      executeSnooze(mins || 15);
    });
  }

  // Enter key inside custom snooze input
  if (snoozeMinsInput) {
    snoozeMinsInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        const mins = parseInt(snoozeMinsInput.value, 10);
        executeSnooze(mins || 15);
      }
    });
  }

  // Quick Snooze chips
  document.querySelectorAll(".snooze-opt").forEach(opt => {
    opt.addEventListener("click", (e) => {
      e.stopPropagation();
      const mins = parseInt(opt.dataset.mins, 10);
      executeSnooze(mins);
    });
  });

  // Open Chat button
  if (chatBtn) {
    chatBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (window.electronAPI) {
        window.electronAPI.openChatWindow();
      }
      flyAwayReverse();
    });
  }

  // Escape key dismisses bird popup immediately
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
