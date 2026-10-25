const DEFAULT_CHASE_LAYOUT = Object.freeze({
  petCenterOffsetX: 96,
  petCenterOffsetY: 228,
  petHalfWidth: 80,
  petHalfHeight: 96,
  cursorGapX: 115,
  cursorGapY: 110,
  maximumStep: 6,
  settleDistance: 3,
});

const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));

function calculateCursorChaseStep({
  windowBounds,
  cursor,
  workArea,
  layout = DEFAULT_CHASE_LAYOUT,
}) {
  const minimumPetX = workArea.x + layout.petHalfWidth;
  const maximumPetX = workArea.x + workArea.width - layout.petHalfWidth;
  const minimumPetY = workArea.y + layout.petHalfHeight;
  const maximumPetY = workArea.y + workArea.height - layout.petHalfHeight;
  const targetPetX = clamp(cursor.x - layout.cursorGapX, minimumPetX, maximumPetX);
  const targetPetY = clamp(cursor.y - layout.cursorGapY, minimumPetY, maximumPetY);
  const targetWindowX = targetPetX - layout.petCenterOffsetX;
  const targetWindowY = targetPetY - layout.petCenterOffsetY;
  const deltaX = targetWindowX - windowBounds.x;
  const deltaY = targetWindowY - windowBounds.y;
  const distance = Math.hypot(deltaX, deltaY);

  if (distance <= layout.settleDistance) {
    return { x: windowBounds.x, y: windowBounds.y, moving: false };
  }

  const scale = Math.min(1, layout.maximumStep / distance);
  return {
    x: Math.round(windowBounds.x + (deltaX * scale)),
    y: Math.round(windowBounds.y + (deltaY * scale)),
    moving: true,
  };
}

function registerPetPoke({
  count,
  lastPokeAt,
  now,
  sequenceWindowMs = 2_000,
  requiredPokes = 3,
}) {
  const nextCount = now - lastPokeAt <= sequenceWindowMs ? count + 1 : 1;
  return nextCount >= requiredPokes
    ? { count: 0, lastPokeAt: 0, triggered: true }
    : { count: nextCount, lastPokeAt: now, triggered: false };
}

function hasCursorLeftPokeArea(origin, cursor, minimumDistance = 80) {
  if (!origin) return false;
  return Math.hypot(cursor.x - origin.x, cursor.y - origin.y) >= minimumDistance;
}

module.exports = {
  DEFAULT_CHASE_LAYOUT,
  calculateCursorChaseStep,
  hasCursorLeftPokeArea,
  registerPetPoke,
};
