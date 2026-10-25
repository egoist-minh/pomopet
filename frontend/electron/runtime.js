const net = require('net');


function findAvailablePort(host = '127.0.0.1') {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once('error', reject);
    server.listen(0, host, () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : null;
      server.close(error => {
        if (error) reject(error);
        else if (port === null) reject(new Error('Could not allocate backend port'));
        else resolve(port);
      });
    });
  });
}

async function waitForHealth({ apiBaseUrl, token, timeoutMs = 20000, intervalMs = 200, fetchImpl = fetch }) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;

  while (Date.now() < deadline) {
    try {
      const response = await fetchImpl(`${apiBaseUrl.replace(/\/api$/, '')}/health`, {
        headers: { 'X-PomoPet-Token': token },
      });
      if (response.ok) {
        const body = await response.json();
        if (body.status === 'ok') return;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }

  const detail = lastError instanceof Error ? `: ${lastError.message}` : '';
  throw new Error(`Backend did not become ready within ${timeoutMs}ms${detail}`);
}

module.exports = { findAvailablePort, waitForHealth };
