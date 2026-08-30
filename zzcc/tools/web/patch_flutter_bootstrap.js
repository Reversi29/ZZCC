#!/usr/bin/env node
const fs = require('fs');
const file = process.argv[2] || '/Users/mac/ZZCC/zzcc/build/web/flutter_bootstrap.js';
let s = fs.readFileSync(file, 'utf8');
let changed = false;
if (!/_flutter\.buildConfig\s*=\s*\{/.test(s)) {
  throw new Error('buildConfig assignment not found');
}
s = s.replace(/_flutter\.buildConfig\s*=\s*\{([^;]+)\};/, (all, body) => {
  const m = body.match(/"canvasKitBaseUrl"\s*:\s*"[^"]*"/);
  if (m) {
    if (m[0] !== '"canvasKitBaseUrl":"canvaskit"') {
      changed = true;
      return all.replace(m[0], '"canvasKitBaseUrl":"canvaskit"');
    }
    return all;
  }
  changed = true;
  if (/,$/.test(body.trim())) {
    return '_flutter.buildConfig = {' + body + '"canvasKitBaseUrl":"canvaskit"};';
  }
  return '_flutter.buildConfig = {' + body + ',"canvasKitBaseUrl":"canvaskit"};';
});
if (!/_flutter\.loader\.load\s*\(\s*\{\s*config\s*:\s*\{[^}]*\}/.test(s)) {
  if (/_flutter\.loader\.load\s*\(\s*\{/.test(s)) {
    changed = true;
    s = s.replace(/_flutter\.loader\.load\s*\(\s*\{/, '_flutter.loader.load({config:{canvasKitBaseUrl:"canvaskit"},');
  } else {
    s += '\n_flutter.loader.load({config:{canvasKitBaseUrl:"canvaskit"}});\n';
    changed = true;
  }
}
fs.writeFileSync(file, s);
const chk = fs.readFileSync(file, 'utf8');
console.log('changed=', changed, 'matches=', (chk.match(/canvasKitBaseUrl/g) || []).length);
if ((chk.match(/canvasKitBaseUrl/g) || []).length < 2) {
  throw new Error('canvasKitBaseUrl patch count too low');
}
