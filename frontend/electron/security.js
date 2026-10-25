const path = require('path');


function resolveAppAsset(outDirectory, requestUrl, existsSync) {
  const rawPath = requestUrl.replace(/^app:\/\/-?\//, '').split(/[?#]/, 1)[0];
  let decodedPath;
  try {
    decodedPath = decodeURIComponent(rawPath || 'index.html').replaceAll('\\', '/');
  } catch {
    return null;
  }

  if (decodedPath.includes('\0') || decodedPath.split('/').includes('..')) return null;

  const root = path.resolve(outDirectory);
  let candidate = path.resolve(root, decodedPath);
  const relative = path.relative(root, candidate);
  if (relative.startsWith('..') || path.isAbsolute(relative)) return null;

  if (!path.extname(candidate) && existsSync(`${candidate}.html`)) {
    candidate = `${candidate}.html`;
  }
  return existsSync(candidate) ? candidate : null;
}

function isTrustedRendererUrl(url, isDev) {
  try {
    const parsed = new URL(url);
    if (isDev) {
      return parsed.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(parsed.hostname) && parsed.port === '3000';
    }
    return parsed.protocol === 'app:' && parsed.hostname === '-';
  } catch {
    return false;
  }
}

module.exports = { resolveAppAsset, isTrustedRendererUrl };
