"use strict";
const engine = require('../web/policy-engine.js'), fs = require('node:fs');
(async () => {
 const session = await engine.create(JSON.parse(fs.readFileSync(0, 'utf8')));
 process.stdout.write(engine.canonical(session.suggestCases()));
})().catch(e => { process.stderr.write(e.stack); process.exitCode = 1; });
