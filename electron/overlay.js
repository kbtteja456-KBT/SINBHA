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
  let alarmAudioCtx = null;
  let alarmGainNode = null;
  let alarmOscInterval = null;
  let customSongAudio = null;
  let isAlarmPlaying = false;

  function stopWindowsAlarm() {
    isAlarmPlaying = false;
    if (alarmOscInterval) {
      clearInterval(alarmOscInterval);
      alarmOscInterval = null;
    }
    if (alarmGainNode && alarmAudioCtx) {
      try {
        alarmGainNode.gain.cancelScheduledValues(alarmAudioCtx.currentTime);
        alarmGainNode.gain.setValueAtTime(0, alarmAudioCtx.currentTime);
      } catch (e) {}
    }
    if (alarmAudioCtx) {
      try {
        alarmAudioCtx.close();
      } catch (e) {}
      alarmAudioCtx = null;
      alarmGainNode = null;
    }
    if (customSongAudio) {
      try {
        customSongAudio.pause();
        customSongAudio.currentTime = 0;
      } catch (e) {}
      customSongAudio = null;
    }
    if (window.speechSynthesis) {
      try {
        window.speechSynthesis.cancel();
      } catch (e) {}
    }
  }

  function startWindowsAlarmTone(gradualRamp = true) {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      alarmAudioCtx = new AudioCtx();
      alarmGainNode = alarmAudioCtx.createGain();
      alarmGainNode.gain.setValueAtTime(0.05, alarmAudioCtx.currentTime);
      alarmGainNode.connect(alarmAudioCtx.destination);

      let currentVolume = 0.05;
      const targetVolume = 0.7;

      function playBeep() {
        if (!isAlarmPlaying || !alarmAudioCtx) return;
        try {
          const osc1 = alarmAudioCtx.createOscillator();
          const osc2 = alarmAudioCtx.createOscillator();
          osc1.type = "sine";
          osc2.type = "triangle";
          osc1.frequency.setValueAtTime(880, alarmAudioCtx.currentTime);
          osc2.frequency.setValueAtTime(1760, alarmAudioCtx.currentTime);

          const beepGain = alarmAudioCtx.createGain();
          beepGain.gain.setValueAtTime(0.6, alarmAudioCtx.currentTime);
          beepGain.gain.exponentialRampToValueAtTime(0.001, alarmAudioCtx.currentTime + 0.35);

          osc1.connect(beepGain);
          osc2.connect(beepGain);
          beepGain.connect(alarmGainNode);

          osc1.start();
          osc2.start();
          osc1.stop(alarmAudioCtx.currentTime + 0.35);
          osc2.stop(alarmAudioCtx.currentTime + 0.35);

          setTimeout(() => {
            if (!isAlarmPlaying || !alarmAudioCtx) return;
            try {
              const osc3 = alarmAudioCtx.createOscillator();
              osc3.type = "sine";
              osc3.frequency.setValueAtTime(1320, alarmAudioCtx.currentTime);
              const bg2 = alarmAudioCtx.createGain();
              bg2.gain.setValueAtTime(0.7, alarmAudioCtx.currentTime);
              bg2.gain.exponentialRampToValueAtTime(0.001, alarmAudioCtx.currentTime + 0.45);
              osc3.connect(bg2);
              bg2.connect(alarmGainNode);
              osc3.start();
              osc3.stop(alarmAudioCtx.currentTime + 0.45);
            } catch (e) {}
          }, 180);

          if (gradualRamp && currentVolume < targetVolume) {
            currentVolume = Math.min(targetVolume, currentVolume + 0.05);
            alarmGainNode.gain.setValueAtTime(currentVolume, alarmAudioCtx.currentTime);
          }
        } catch (e) {}
      }

      playBeep();
      alarmOscInterval = setInterval(playBeep, 1600);
    } catch (e) {
      console.error("AudioContext alarm failed:", e);
    }
  }

  function startWindowsAlarm(task) {
    stopWindowsAlarm();
    isAlarmPlaying = true;
    const option = task.sound_option || "voice_then_tone";
    const songUri = task.song_uri || "";
    const userName = task.user_name || "friend";
    const spokenText = task.spoken_text || `Hey ${userName}, it is time to ${task.title || "take care of your task"}.`;

    function speakVoice(callback) {
      if (!window.speechSynthesis) {
        if (callback) callback();
        return;
      }
      try {
        window.speechSynthesis.cancel();
        const utter = new SpeechSynthesisUtterance(spokenText);
        utter.rate = 1.0;
        utter.pitch = 1.0;
        utter.volume = 1.0;
        utter.onend = () => {
          if (callback && isAlarmPlaying) callback();
        };
        utter.onerror = () => {
          if (callback && isAlarmPlaying) callback();
        };
        window.speechSynthesis.speak(utter);
      } catch (e) {
        if (callback && isAlarmPlaying) callback();
      }
    }

    if (option === "spoken_voice") {
      speakVoice(() => {
        const voiceInterval = setInterval(() => {
          if (!isAlarmPlaying) {
            clearInterval(voiceInterval);
          } else {
            speakVoice();
          }
        }, 8000);
      });
    } else if (option === "song" && songUri) {
      try {
        customSongAudio = new Audio(songUri);
        customSongAudio.loop = true;
        customSongAudio.volume = 0.2;
        let v = 0.2;
        const ramp = setInterval(() => {
          if (!isAlarmPlaying || !customSongAudio) {
            clearInterval(ramp);
          } else if (v < 1.0) {
            v = Math.min(1.0, v + 0.1);
            customSongAudio.volume = v;
          }
        }, 1500);
        customSongAudio.play().catch(() => {
          startWindowsAlarmTone(true);
        });
      } catch (e) {
        startWindowsAlarmTone(true);
      }
    } else if (option === "voice_then_tone") {
      speakVoice(() => {
        if (isAlarmPlaying) {
          startWindowsAlarmTone(true);
        }
      });
    } else {
      startWindowsAlarmTone(true);
    }
  }

  // Show bird with forward arrival animation
  function showBird(task, reminderId) {
    currentTask = task;
    currentReminderId = reminderId;
    isFlyingReverse = false;

    // Start Windows alarm audio and speech loop until dismissed
    startWindowsAlarm(task);

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
    stopWindowsAlarm();

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
    stopWindowsAlarm();
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
