function createWindowDragTracker(
  onChange,
  {
    settleMs = 160,
    setTimer = setTimeout,
    clearTimer = clearTimeout,
  } = {},
) {
  let dragging = false;
  let settleTimer = null;

  const emit = value => {
    if (dragging === value) return;
    dragging = value;
    onChange(value);
  };

  const scheduleStop = () => {
    if (settleTimer !== null) clearTimer(settleTimer);
    settleTimer = setTimer(() => {
      settleTimer = null;
      emit(false);
    }, settleMs);
  };

  const signalMovement = () => {
    emit(true);
    scheduleStop();
  };

  return {
    start: signalMovement,
    move: signalMovement,
    stop() {
      if (settleTimer !== null) clearTimer(settleTimer);
      settleTimer = null;
      emit(false);
    },
    dispose() {
      if (settleTimer !== null) clearTimer(settleTimer);
      settleTimer = null;
    },
  };
}

module.exports = { createWindowDragTracker };
