const MAX_WINDOW_REGIONS = 64;


function normalizeWindowRegions(regions, bounds) {
  if (!Array.isArray(regions) || !bounds) return [];

  const maxWidth = Math.max(0, Math.floor(Number(bounds.width) || 0));
  const maxHeight = Math.max(0, Math.floor(Number(bounds.height) || 0));
  if (maxWidth === 0 || maxHeight === 0) return [];

  const normalized = [];
  for (const region of regions.slice(0, MAX_WINDOW_REGIONS)) {
    if (!region || typeof region !== 'object') continue;

    const values = [region.x, region.y, region.width, region.height].map(Number);
    if (!values.every(Number.isFinite)) continue;

    const [rawX, rawY, rawWidth, rawHeight] = values;
    if (rawWidth <= 0 || rawHeight <= 0) continue;

    const left = Math.max(0, Math.floor(rawX));
    const top = Math.max(0, Math.floor(rawY));
    const right = Math.min(maxWidth, Math.ceil(rawX + rawWidth));
    const bottom = Math.min(maxHeight, Math.ceil(rawY + rawHeight));

    if (right <= left || bottom <= top) continue;
    normalized.push({
      x: left,
      y: top,
      width: right - left,
      height: bottom - top,
    });
  }

  return normalized;
}

module.exports = { MAX_WINDOW_REGIONS, normalizeWindowRegions };
