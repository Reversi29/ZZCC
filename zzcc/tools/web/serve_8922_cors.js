const http = require('http');
const fs = require('fs');
const path = require('path');
const PORT = 8922;
const ROOT = '/Users/mac/ZZCC/zzcc/build/web';
const MIME = {
  '.js': 'application/javascript', '.wasm': 'application/wasm',
  '.html': 'text/html', '.css': 'text/css', '.json': 'application/json',
  '.png': 'image/png', '.gif': 'image/gif', '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon', '.ttf': 'font/ttf', '.otf': 'font/otf',
  '.ttc': 'font/ttc', '.map': 'application/json', '.woff2': 'font/woff2',
};
http.createServer((req, res) => {
  let url = req.url.split('?')[0].replace(/%20/g, ' ');
  let filePath = path.join(ROOT, url === '/' ? 'index.html' : url);
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('Not found: ' + url); return; }
    const ext = path.extname(filePath);
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    });
    res.end(data);
  });
}).listen(PORT, '127.0.0.1', () => console.log(`Server on http://127.0.0.1:${PORT} (COOP/COEP ON)`));
