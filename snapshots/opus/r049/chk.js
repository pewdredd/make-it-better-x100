const s = require('fs').readFileSync('index.html', 'utf8');
const m = s.match(/<script>([\s\S]*)<\/script>/);
try { new Function(m[1]); console.log('syntax ok'); } catch (e) { console.log(e); }
