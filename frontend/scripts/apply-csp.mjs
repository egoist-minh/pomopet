import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const directory = path.dirname(fileURLToPath(import.meta.url));
const outDirectory = path.resolve(directory, '..', 'out');
const scriptDirective = 'script-src &#x27;self&#x27;';

export function applyScriptHashes(html) {
  const hashes = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)]
    .map(match => createHash('sha256').update(match[1], 'utf8').digest('base64'));
  const uniqueHashes = [...new Set(hashes)];
  if (uniqueHashes.length === 0) return html;
  if (!html.includes(scriptDirective)) {
    throw new Error('Content Security Policy script directive was not found');
  }

  const hashSources = uniqueHashes
    .map(hash => `&#x27;sha256-${hash}&#x27;`)
    .join(' ');
  return html.replace(scriptDirective, `${scriptDirective} ${hashSources}`);
}

async function listHtmlFiles(root) {
  const entries = await fs.readdir(root, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async entry => {
    const entryPath = path.join(root, entry.name);
    if (entry.isDirectory()) return listHtmlFiles(entryPath);
    return entry.isFile() && entry.name.endsWith('.html') ? [entryPath] : [];
  }));
  return nested.flat();
}

async function main() {
  const htmlFiles = await listHtmlFiles(outDirectory);
  if (htmlFiles.length === 0) throw new Error('Next.js export did not contain HTML files');
  for (const htmlFile of htmlFiles) {
    const html = await fs.readFile(htmlFile, 'utf8');
    await fs.writeFile(htmlFile, applyScriptHashes(html), 'utf8');
  }
  process.stdout.write(`Applied CSP hashes to ${htmlFiles.length} HTML files.\n`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}
