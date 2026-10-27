const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const engine=require('../web/policy-engine.js');globalThis.window=globalThis;
vm.runInThisContext(fs.readFileSync(__dirname+'/../web/session-data.js','utf8'));
(async()=>{const input=JSON.parse(fs.readFileSync(0,'utf8'));const {policy,revised}=input;const s=await engine.create(policy);
if(input.type_transition){
 s.labelCase('flag',true);const original=engine.canonical(s.record()),preview=s.revisionPreview(revised),next=await engine.create(revised);
 assert.deepEqual(preview.changed_rules,['a','b']);assert.deepEqual(preview.changed_cases,['flag']);assert.equal(preview.pending[0].review_status,'fresh-answer-required');
 await assert.rejects(()=>next.reconfirm(s.record(),'flag'));assert.equal(engine.canonical(s.record()),original);
 process.stdout.write(JSON.stringify({preview,original:s.record(),revised:next.record()}));return;
}
assert.equal(s.caseReview().find(x=>x.id==='training').review_status,'unasked');
s.answer(s.question().id,true);s.labelCase('training',true);
assert.equal(s.status(),'NO_CANDIDATE_MATCH');assert.equal((await engine.restore(s.record())).examples().length,2);
const preview=s.revisionPreview(revised),next=await engine.create(revised);assert.equal(next.examples().length,0);
await next.reconfirm(s.record(),'training');
for(const mutate of [r=>r.actions[0].source_digest=null,r=>r.actions[0].source_digest='invalid',r=>r.actions[0].kind='automatic',r=>r.actions[0].expected=1,r=>r.actions.push({...r.actions[0]})]){
 const bad=JSON.parse(JSON.stringify(next.record()));mutate(bad);await assert.rejects(()=>engine.restore(bad));
}
process.stdout.write(JSON.stringify({record:s.record(),examples:s.examples(),contract:s.contract('implementation:decide',CLARIFICATION_CONTRACT_TEMPLATE),preview, revised:next.record(),revised_contract:next.contract('implementation:decide',CLARIFICATION_CONTRACT_TEMPLATE)}));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1});
const leaf=(field,op,value)=>({field,op,value});
const common=leaf('minutes','<=',30),premium=leaf('tier','==','priority');
const diff=engine.comparison([{id:'and',rule:{and:[common,premium]}},{id:'or',rule:{or:[common,premium]}}]);
assert.equal(diff.shared.length,0);assert.ok(diff.differences[0].rule.and);assert.ok(diff.differences[1].rule.or);
const tiers=engine.comparison([{id:'a',rule:{and:[common,premium]}},{id:'b',rule:{and:[common,leaf('tier','==','standard')]}}]);
assert.equal(tiers.shared.length,1);assert.equal(tiers.differences[1].rule.and[1].value,'standard');
