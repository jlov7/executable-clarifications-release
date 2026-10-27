"use strict";
const fs=require('fs'), engine=require('../web/example-engine.js');
globalThis.window=globalThis;require('../web/session-data.js');
(async()=>{
 const input=JSON.parse(fs.readFileSync(0,'utf8')), s=await engine.create(input.example_set);
 let refused_pending=false,refused_bad=false;
 try{s.contract('implementation:decide');}catch(_){refused_pending=true;}
 try{await engine.create(input.bad);}catch(_){refused_bad=true;}
 s.confirm();const record=s.record(), restored=await engine.restore(record);
 if(JSON.stringify(restored.record())!==JSON.stringify(record))throw Error('Resume drift');
 console.log(JSON.stringify({record,audit:await s.audit(input.policy),contract:s.contract('implementation:decide'),refused_pending,refused_bad}));
})().catch(e=>{console.error(e);process.exit(1);});
