"use strict";
const fs = require("node:fs"), vm = require("node:vm"), engine = require("../web/policy-engine.js");
globalThis.window=globalThis;
vm.runInThisContext(fs.readFileSync(__dirname + "/../web/session-data.js", "utf8"));
(async () => {
 const source=JSON.parse(fs.readFileSync(0,"utf8"));
 if(source.roundtrip) {
  for(const text of ['['.repeat(17)+'0'+']'.repeat(17), '{"schema":"executable-clarifications/policy-session-v1","extra":'+'['.repeat(17)+'0'+']'.repeat(17)+'}']) {
   let rejected=false;try{engine.parse(text);}catch{rejected=true;}if(!rejected)throw new Error("Depth boundary was relaxed");
  }
  const s=await engine.create(source.roundtrip);
  const text=engine.canonical(s.record()), restored=await engine.restore(engine.parse(text));
  process.stdout.write(JSON.stringify({record:restored.record(),bytes:Buffer.byteLength(text)}));return;
 }
 if(source.table) {
  const p=engine.validate(source.table);
  process.stdout.write(JSON.stringify(p.cases.map(x=>p.candidates.map(c=>engine.evaluate(c.rule,x.input)))));return;
 }
 if(source.invalid) {
  const rejected=source.invalid.map(text=>{try {engine.validate(engine.parse(text));return false;} catch {return true;}});
  process.stdout.write(JSON.stringify(rejected)); return;
 }
 const s=await engine.create(source), states=[];
 async function visit(session) {
  const q=session.question();
  states.push({record:session.record(),question:q,status:session.status(),examples:session.examples(),
   contract:session.stopped||!session.examples().length?null:session.contract("implementation:decide",globalThis.CLARIFICATION_CONTRACT_TEMPLATE)});
  if(q)for(const v of [false,true,null]){const child=await engine.restore(JSON.parse(JSON.stringify(session.record())));child.answer(q.id,v);await visit(child);}
 }
 await visit(s); process.stdout.write(JSON.stringify(states));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});
