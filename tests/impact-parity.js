const fs=require('node:fs'),engine=require('../web/policy-engine.js');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(engine.comparePolicies(data.baseline,data.proposed,data.observed)));
