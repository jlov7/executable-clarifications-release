"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const engine=require(path.resolve(__dirname,'../web/policy-engine.js'));
const policy=JSON.parse(fs.readFileSync(0,'utf8'));
(async()=>{
 let checks=0;
 for(const [label,mutate,reviewed] of [
  ['question',s=>{s.question().input.x=99;},false],
  ['review input',s=>{s.caseReview()[0].input.x=99;},false],
  ['review prediction',s=>{s.caseReview()[0].predictions.a=false;},false],
  ['v1 record',s=>{const r=s.record();r.policy.cases[0].input.x=99;r.decisions.push({});},false],
  ['v2 record',s=>{const r=s.record();r.policy.cases[0].input.x=99;r.actions[0].expected=false;},true],
  ['examples',s=>{s.examples()[0].input.x=99;},true],
  ['preview',s=>{const next=structuredClone(policy);next.cases[0].input.x=1;s.revisionPreview(next).pending[0].input.x=99;},true]
 ]){
  const s=await engine.create(policy);if(reviewed)s.labelCase('c',true);
  const before=engine.canonical({record:s.record(),question:s.question(),review:s.caseReview(),examples:s.examples(),remaining:s.remaining,contract:reviewed?s.contract('implementation:decide','__DATA__'):null});
  mutate(s);
  assert.equal(engine.canonical({record:s.record(),question:s.question(),review:s.caseReview(),examples:s.examples(),remaining:s.remaining,contract:reviewed?s.contract('implementation:decide','__DATA__'):null}),before,label);
  const restored=await engine.restore(s.record());
  assert.equal(engine.canonical(restored.record()),engine.canonical(s.record()),label+' replay');
  assert.deepEqual(restored.caseReview(),s.caseReview(),label+' review replay');checks++;
 }
 const s=await engine.create(policy),saved=s.record(),before=engine.canonical(saved);
 assert.equal(JSON.stringify(saved),JSON.stringify({schema:'executable-clarifications/policy-session-v1',policy:engine.validate(policy),version_digest:s.version,decisions:[],scope:'observed-examples-only'}),'v1 raw record order');
 s.answer(s.question().id,true);assert.equal(engine.canonical(saved),before,'v1 snapshot must not advance');checks++;
 process.stdout.write(JSON.stringify({checks})+'\n');
})().catch(error=>{console.error(error);process.exitCode=1;});
