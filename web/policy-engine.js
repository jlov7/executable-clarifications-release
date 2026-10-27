"use strict";
// policy-v1 has a paired Python implementation and cross-runtime truth-table/replay tests.
(function(root) {
 const SCHEMA = "executable-clarifications/policy-v1", SESSION = "executable-clarifications/policy-session-v1";
 const REVIEW = "executable-clarifications/policy-session-v2";
 const forbidden = ["__proto__", "prototype", "constructor"];
 const fail = text => { throw new Error(text); };
 const object = x => x !== null && typeof x === "object" && !Array.isArray(x);
 const keys = (x, expected) => { if (!object(x) || Object.keys(x).sort().join("|") !== [...expected].sort().join("|")) fail("Unknown or missing policy fields"); };
 const id = x => { if (typeof x !== "string" || forbidden.includes(x) || !/^[A-Za-z_][A-Za-z0-9_-]{0,63}(?![\s\S])/.test(x)) fail("Invalid or unsafe identifier"); };
 const canonical = x => Array.isArray(x) ? "[" + x.map(canonical).join(",") + "]" : object(x) ? "{" + Object.keys(x).sort().map(k => JSON.stringify(k) + ":" + canonical(x[k])).join(",") + "}" : JSON.stringify(x);
 function parse(text) {
  if (typeof text !== "string" || new TextEncoder().encode(text).length > 262144) fail("JSON exceeds 262144 bytes");
  let at = 0;
  const space = () => { while (/[ \t\r\n]/.test(text[at] || "") && at < text.length) at++; };
  function value(depth) {
   if (depth > 17) fail("JSON nesting exceeds session envelope limit 17");
   space(); const start = at, ch = text[at++];
   if (ch === '"') { while (at < text.length) { const c = text[at++]; if (c === "\\") at++; else if (c === '"') return JSON.parse(text.slice(start, at)); } fail("Invalid string"); }
   if (ch === "{" || ch === "[") {
    const isObject = ch === "{", out = isObject ? {} : [], end = isObject ? "}" : "]";
    space(); if (text[at] === end) { at++; return out; }
    while (at < text.length) {
     if (isObject) {
      space(); if (text[at] !== '"') fail("Expected object key");
      const k = value(depth + 1); space();
      if (text[at++] !== ":" || forbidden.includes(k) || Object.hasOwn(out, k)) fail("Duplicate or unsafe JSON key");
      out[k] = value(depth + 1);
     } else out.push(value(depth + 1));
     space(); const next = text[at++]; if (next === end) return out; if (next !== ",") fail("Invalid JSON separator");
    }
    fail("Incomplete JSON");
   }
   at = start;
   const token = /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(text.slice(at));
   if (!token) fail("Invalid JSON value"); if (/[.eE]/.test(token[0]) && !["true","false"].includes(token[0])) fail("Only integer JSON numbers are supported"); at += token[0].length;
   const result = JSON.parse(token[0]); if (typeof result === "number" && !Number.isFinite(result)) fail("Nonfinite number"); return result;
  }
  const result = value(0); space(); if (at !== text.length) fail("Trailing JSON data");
  const depthLimit = object(result) && [SESSION,REVIEW].includes(result.schema) ? 17 : 16;
  function checkDepth(x, depth = 0) {
   if (depth > depthLimit) fail("JSON nesting exceeds " + depthLimit);
   if (x !== null && typeof x === "object") for (const child of Object.values(x)) checkDepth(child, depth + 1);
  }
  checkDepth(result); return result;
 }
 function validate(spec) {
  if (new TextEncoder().encode(canonical(spec)).length > 131072) fail("Policy exceeds 131072 bytes");
  spec = parse(canonical(spec)); keys(spec, ["schema", "fields", "candidates", "cases"]);
  if (spec.schema !== SCHEMA) fail("Unsupported policy schema");
  if (!object(spec.fields) || Object.keys(spec.fields).length < 1 || Object.keys(spec.fields).length > 16) fail("Provide 1..16 fields");
  for (const [name, kind] of Object.entries(spec.fields)) {
   id(name); if (["integer", "boolean"].includes(kind)) continue; keys(kind, ["enum"]);
   if (!Array.isArray(kind.enum) || kind.enum.length < 1 || kind.enum.length > 32 || new Set(kind.enum).size !== kind.enum.length || kind.enum.some(v => typeof v !== "string" || !/^[A-Za-z0-9 _.-]{1,64}(?![\s\S])/.test(v))) fail("Invalid categorical values");
  }
  function scalar(field, v) {
   const kind = spec.fields[field];
   if (!(kind === "integer" ? Number.isSafeInteger(v) : kind === "boolean" ? typeof v === "boolean" : typeof v === "string" && kind.enum.includes(v))) fail("Value does not match declared field type");
  }
  function rule(n, depth = 0, count = {n:0}) {
   if (depth > 6 || ++count.n > 128) fail("Predicate exceeds depth 6 or 128 nodes");
   if (object(n) && Object.keys(n).length === 1 && (Object.hasOwn(n,"and") || Object.hasOwn(n,"or"))) {
    const children = Object.values(n)[0];
    if (!Array.isArray(children) || children.length < 2 || children.length > 16) fail("and/or requires 2..16 predicates");
    children.forEach(c => rule(c, depth + 1, count)); return;
   }
   keys(n, ["field", "op", "value"]);
   if (typeof n.field !== "string" || !Object.hasOwn(spec.fields, n.field) || !["==","!=","<","<=",">",">=","in"].includes(n.op)) fail("Unknown field or comparison");
   if (n.op === "in") {
    if (!Array.isArray(n.value) || n.value.length < 1 || n.value.length > 32 || new Set(n.value.map(canonical)).size !== n.value.length) fail("Invalid membership values");
    n.value.forEach(v => scalar(n.field, v));
   } else {
    if (!["==","!="].includes(n.op) && spec.fields[n.field] !== "integer") fail("Ordering requires integer field");
    scalar(n.field, n.value);
   }
  }
  for (const [collection, min, max] of [["candidates",2,32],["cases",1,256]]) {
   const items = spec[collection];
   if (!Array.isArray(items) || items.length < min || items.length > max) fail("Collection limit exceeded");
   const seen = new Set();
   for (const item of items) {
    keys(item, ["id", collection === "candidates" ? "rule" : "input"]); id(item.id);
    if (seen.has(item.id)) fail("Duplicate identity"); seen.add(item.id);
    if (collection === "candidates") rule(item.rule);
    else { keys(item.input, Object.keys(spec.fields)); for (const [field,v] of Object.entries(item.input)) scalar(field,v); }
   }
   items.sort((a,b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  }
  return spec;
 }
 function evaluate(n, x) {
  if (Object.hasOwn(n,"and")) return n.and.every(c => evaluate(c,x));
  if (Object.hasOwn(n,"or")) return n.or.some(c => evaluate(c,x));
  const a=x[n.field], b=n.value;
  return ({"==":()=>a===b,"!=":()=>a!==b,"<":()=>a<b,"<=":()=>a<=b,">":()=>a>b,">=":()=>a>=b,"in":()=>b.includes(a)})[n.op]();
 }
 function suggestCases(policy) {
  policy=validate(policy);
  const fields=Object.keys(policy.fields).sort(), values=Object.fromEntries(fields.map(f=>[f,new Set()])), referenced=new Set();
  function collect(n) {
   if(n.and||n.or){for(const child of n.and||n.or)collect(child);}
   else {referenced.add(n.field);if(policy.fields[n.field]==="integer")for(const v of n.op==="in"?n.value:[n.value])values[n.field].add(v);}
  }
  for(const candidate of policy.candidates)collect(candidate.rule);
  const seeds=policy.cases.slice();
  for(const field of fields){
   const kind=policy.fields[field];
   if(kind==="boolean")values[field]=[false,true];
   else if(kind==="integer"){
    const anchors=new Set([...values[field],...seeds.map(c=>c.input[field])]),near=new Set();
    for(const n of anchors)for(const offset of [-1,0,1])if(Number.isSafeInteger(n+offset))near.add(n+offset);
    values[field]=[...near].sort((a,b)=>a-b);
   }else values[field]=kind.enum.slice().sort();
  }
  const added=[],seen=new Set(seeds.map(c=>canonical(c.input))),ids=new Set(seeds.map(c=>c.id));let serial=0;
  const total=fields.reduce((n,f)=>n*BigInt(values[f].length),1n);
  const coverage={method:total<=4096n?"finite-cartesian-grid":"seeded-variations-then-grid",attempts:0,attempt_limit:4096,case_limit:256,policy_byte_limit:131072,truncated:false,stop_reason:null,domains:values,total_combinations:String(total),unreferenced_fields:fields.filter(f=>!referenced.has(f)),scope:"unlabeled finite-domain inputs only; excludes other integers, undeclared fields and intent or exception truth"};
  function* grid(index=0,example={}){
   if(index===fields.length){yield {...example};return;}
   const field=fields[index];for(const value of values[field]){example[field]=value;yield* grid(index+1,example);}
  }
  function* variations(){
   if(total<=4096n){yield* grid();return;}
   for(const width of [1,2])for(const seed of seeds)for(let i=0;i<fields.length;i++){
    const first=fields[i];for(const a of values[first]){
     if(a===seed.input[first])continue;
     if(width===1)yield {...seed.input,[first]:a};
     else for(const second of fields.slice(i+1))for(const b of values[second])if(b!==seed.input[second])yield {...seed.input,[first]:a,[second]:b};
    }
   }
   yield* grid();
  }
  for(const example of variations()){
   if(coverage.attempts===coverage.attempt_limit){coverage.stop_reason="attempt-limit";break;}
   coverage.attempts++;
   const key=canonical(example);if(seen.has(key))continue;
   if(policy.cases.length===256){coverage.stop_reason="case-limit";break;}
   let identity;do{identity="suggested_"+String(++serial).padStart(4,"0");}while(ids.has(identity));
   const c={id:identity,input:example};policy.cases.push(c);
   if(new TextEncoder().encode(canonical(policy)).length>131072){policy.cases.pop();coverage.stop_reason="policy-byte-limit";break;}
   ids.add(identity);seen.add(key);added.push(c);
  }
  coverage.truncated=coverage.stop_reason!==null;
  coverage.covered_combinations=String(seen.size);
  coverage.omitted_combinations=String(total-BigInt(seen.size));
  coverage.finite_domain_complete=BigInt(seen.size)===total;
  return {policy:validate(policy),added_cases:added,coverage};
 }
 function comparePolicies(baseline,proposed,observedCaseIds=[]) {
  baseline=validate(baseline);proposed=validate(proposed);
  const cases=new Map(baseline.cases.map(c=>[c.id,c.input]));
  if(!Array.isArray(observedCaseIds)||observedCaseIds.length>256||observedCaseIds.some(x=>typeof x!=="string"||!cases.has(x))||new Set(observedCaseIds).size!==observedCaseIds.length)fail("Observed case IDs must be distinct known baseline cases");
  const observed=new Set(observedCaseIds.map(x=>canonical(cases.get(x)))),old=new Map(baseline.candidates.map(c=>[c.id,c.rule])),next=new Map(proposed.candidates.map(c=>[c.id,c.rule]));
  const fields=[...new Set([...Object.keys(baseline.fields),...Object.keys(proposed.fields)])].sort();
  const vocabulary=kind=>object(kind)?{enum:kind.enum.slice().sort()}:kind;
  const declared=(spec,f)=>Object.hasOwn(spec.fields,f)?spec.fields[f]:null;
  const incompatible=fields.filter(f=>canonical(vocabulary(declared(baseline,f)))!==canonical(vocabulary(declared(proposed,f)))).map(f=>({field:f,baseline:declared(baseline,f),proposed:declared(proposed,f)}));
  const report={schema:"executable-clarifications/policy-impact-v1",compatible:!incompatible.length,incompatible_fields:incompatible,added_candidates:[...next.keys()].filter(x=>!old.has(x)).sort(),removed_candidates:[...old.keys()].filter(x=>!next.has(x)).sort(),candidate_impacts:[],coverage:null,witnesses:[],output:{witness_limit:128,report_byte_limit:1048576,sampling:"first input per candidate, direction and observed status",omitted_change_pairs:0,truncated:false,stop_reason:null},scope:"checked finite inputs only; outputs are not labels, intent or universal semantic equivalence"};
  function finish(){report.output.report_bytes=0;for(let i=0;i<4;i++)report.output.report_bytes=new TextEncoder().encode(canonical(report)).length;if(report.output.report_bytes>1048576)fail("Comparison report exceeds byte limit");return report;}
  if(incompatible.length)return finish();
  const seeds=[...baseline.cases,...proposed.cases].map(c=>c.input),values=Object.fromEntries(fields.map(f=>[f,new Set()])),references=[];
  function collect(n,referenced){
   if(n.and||n.or){for(const child of n.and||n.or)collect(child,referenced);}
   else {referenced.add(n.field);if(baseline.fields[n.field]==="integer")for(const v of n.op==="in"?n.value:[n.value])values[n.field].add(v);}
  }
  for(const spec of [baseline,proposed]){const referenced=new Set();for(const c of spec.candidates)collect(c.rule,referenced);references.push(referenced);}
  const sizes={};
  for(const f of fields){
   const kind=baseline.fields[f];let count;
   if(kind==="integer"){
    const supplied=new Set(seeds.map(x=>x[f])),anchors=new Set([...values[f],...supplied]),eligible=new Set();
    for(const n of anchors)for(const offset of [-1,0,1])if(Number.isSafeInteger(n+offset))eligible.add(n+offset);
    const extra=[...eligible].filter(n=>!supplied.has(n)).sort((a,b)=>a-b).slice(0,1024-supplied.size);
    values[f]=[...new Set([...supplied,...extra])].sort((a,b)=>a-b);count=eligible.size;
   }else{values[f]=kind==="boolean"?[false,true]:kind.enum.slice().sort();count=values[f].length;}
   sizes[f]={eligible_values:count,retained_values:values[f].length,omitted_values:count-values[f].length};
  }
  const total=fields.reduce((n,f)=>n*BigInt(values[f].length),1n);
  const coverage={method:"supplied-inputs-then-finite-cartesian-grid",input_limit:4096,domain_value_limit:1024,attempt_limit:5120,attempts:0,domains:values,domain_sizes:sizes,baseline_unreferenced_fields:fields.filter(f=>!references[0].has(f)),proposed_unreferenced_fields:fields.filter(f=>!references[1].has(f)),unreferenced_fields:fields.filter(f=>!references[0].has(f)&&!references[1].has(f)),total_combinations:String(total),checked_combinations:"0",omitted_combinations:String(total),finite_domain_complete:false,domain_complete:!Object.values(sizes).some(s=>s.omitted_values),truncated:false,stop_reasons:[]};
  report.coverage=coverage;
  for(const identity of [...old.keys()].filter(x=>next.has(x)).sort())report.candidate_impacts.push({candidate_id:identity,status:"unchanged-on-checked-inputs",false_to_true_count:0,true_to_false_count:0,observed_false_to_true_count:0,observed_true_to_false_count:0,unobserved_false_to_true_count:0,unobserved_true_to_false_count:0});
  function* grid(index=0,example={}){if(index===fields.length){yield {...example};return;}const f=fields[index];for(const value of values[f]){example[f]=value;yield* grid(index+1,example);}}
  function* inputs(){yield* seeds;yield* grid();}
  const seen=new Set(),samples=new Map();
  for(const example of inputs()){
   if(coverage.attempts===5120)break;coverage.attempts++;
   const key=canonical(example);if(seen.has(key))continue;if(seen.size===4096)break;seen.add(key);
   const exercised=observed.has(key);
   for(const item of report.candidate_impacts){
    const identity=item.candidate_id,before=evaluate(old.get(identity),example),after=evaluate(next.get(identity),example);if(before===after)continue;
    const direction=before?"true_to_false":"false_to_true";item.status="changed-on-checked-inputs";item[direction+"_count"]++;item[(exercised?"observed_":"unobserved_")+direction+"_count"]++;
    const sampleKey=canonical([identity,direction,exercised]);if(!samples.has(sampleKey))samples.set(sampleKey,{candidate_id:identity,input:{...example},before,after,exercised_by_observed_example:exercised});
   }
  }
  coverage.checked_combinations=String(seen.size);coverage.omitted_combinations=String(total-BigInt(seen.size));coverage.finite_domain_complete=BigInt(seen.size)===total;
  if(!coverage.domain_complete)coverage.stop_reasons.push("domain-value-limit");if(BigInt(seen.size)<total)coverage.stop_reasons.push(coverage.attempts===5120?"attempt-limit":"input-limit");coverage.truncated=!!coverage.stop_reasons.length;
  const output=report.output;output.omitted_change_pairs=report.candidate_impacts.reduce((n,c)=>n+c.false_to_true_count+c.true_to_false_count,0);
  for(const sample of samples.values()){
   if(report.witnesses.length===128){output.stop_reason="witness-limit";break;}
   report.witnesses.push(sample);output.omitted_change_pairs--;
   if(new TextEncoder().encode(canonical(report)).length>1048576-128){report.witnesses.pop();output.omitted_change_pairs++;output.stop_reason="report-byte-limit";break;}
  }
  output.truncated=output.omitted_change_pairs>0;if(output.truncated&&output.stop_reason===null)output.stop_reason="representative-samples";return finish();
 }
 async function create(spec) {
  spec = validate(spec);
  const bytes = await root.crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical(spec)));
  const version = Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2,"0")).join("");
  return new Session(spec, version);
 }
 class Session {
  constructor(spec, version) { this.policy=spec; this.version=version; this.decisions=[]; this.actions=null;this.labels=[]; this.remaining=spec.candidates.map(c=>c.id); this.stopped=false; }
  suggestCases() { return suggestCases(this.policy); }
  comparePolicy(policy) { return comparePolicies(this.policy,policy,this.caseReview().filter(c=>c.observed!==null).map(c=>c.id)); }
  question() {
   if (this.stopped || this.remaining.length < 2) return null;
   let best=null;
   for (const c of this.policy.cases) {
    const outputs={}, groups={false:[],true:[]};
    for (const candidate of this.policy.candidates.filter(c=>this.remaining.includes(c.id))) { const v=evaluate(candidate.rule,c.input); outputs[candidate.id]=v; groups[String(v)].push(candidate.id); }
    if (!groups.false.length || !groups.true.length) continue;
    const score=groups.false.length**2+groups.true.length**2;
    if (!best || score < best.score) best={score, id:this.version+":"+this.decisions.length+":"+c.id, case_id:c.id, input:{...c.input},outputs,groups,remaining_count:this.remaining.length,uniform_expected_remaining:score/this.remaining.length,scope:"candidate-disagreement-not-proven-ambiguity"};
   }
   if (!best) return null; delete best.score; return best;
  }
  status() { return this.stopped ? "UNRESOLVED" : !this.remaining.length ? "NO_CANDIDATE_MATCH" : this.remaining.length === 1 ? "CANDIDATE_SET_NARROWED" : this.question() ? "OPEN" : "NO_FURTHER_DISAGREEMENT"; }
  answer(questionId, expected) {
   if (expected !== null && typeof expected !== "boolean") fail("Invalid answer");
   const q=this.question(); if (!q || q.id !== questionId) fail("Stale or unavailable question");
   this.decisions.push({question_id:questionId,expected});
   if(this.actions!==null)this.actions.push({kind:"answer",question_id:questionId,expected});
   if (expected === null) this.stopped=true; else this.remaining=this.remaining.filter(c=>q.outputs[c]===expected);
  }
  record() { if(this.actions!==null)return parse(canonical({schema:REVIEW,policy:this.policy,version_digest:this.version,actions:this.actions,scope:"observed-examples-only"}));return JSON.parse(JSON.stringify({schema:SESSION, policy:this.policy,version_digest:this.version,decisions:this.decisions,scope:"observed-examples-only"})); }
  undo() { if(this.actions!==null){if(!this.actions.length)fail("No answer to undo");const actions=this.actions.slice(0,-1);this.decisions=[];this.actions=[];this.labels=[];this.remaining=this.policy.candidates.map(c=>c.id);this.stopped=false;actions.forEach(a=>this.apply(a));return;}if (!this.decisions.length) fail("No answer to undo"); const previous=this.decisions.slice(0,-1); this.decisions=[];this.remaining=this.policy.candidates.map(c=>c.id);this.stopped=false;previous.forEach(d=>this.answer(d.question_id,d.expected)); }
  apply(a) {
   if(a.kind==="answer"){keys(a,["kind","question_id","expected"]);this.answer(a.question_id,a.expected);}
   else if(["label","reconfirmed"].includes(a.kind)){keys(a,a.kind==="label"?["kind","case_id","expected"]:["kind","case_id","expected","source_digest"]);this.labelCase(a.case_id,a.expected,a.source_digest);}
   else fail("Invalid review action");
  }
  caseReview() {
   const observed=new Map(this.examples().map(e=>[e.question_id.split(":").at(-1),e.expected]));
   return this.policy.cases.map(c=>({...c,input:{...c.input},predictions:Object.fromEntries(this.policy.candidates.map(p=>[p.id,evaluate(p.rule,c.input)])),review_status:this.decisions.some(d=>d.question_id.endsWith(":"+c.id))?"asked":this.labels.some(l=>l.case_id===c.id)?"explicitly-labeled":"unasked",observed:observed.has(c.id)?observed.get(c.id):null}));
  }
  labelCase(caseId,expected,sourceDigest) {
   const c=this.policy.cases.find(x=>x.id===caseId);
   if(!c||typeof expected!=="boolean")fail("Explicit label requires a known case and boolean");
   if(this.labels.some(l=>l.case_id===caseId)||this.decisions.some(d=>d.question_id.endsWith(":"+caseId)))fail("Case already answered; undo before relabeling");
   if(sourceDigest!==undefined && (typeof sourceDigest!=="string"||!/^[0-9a-f]{64}$/.test(sourceDigest)||sourceDigest===this.version))fail("Invalid revision source digest");
   if(this.actions===null)this.actions=this.decisions.map(d=>({kind:"answer",...d}));
   if(this.actions.length>=288)fail("Invalid review history");
   const action={kind:sourceDigest===undefined?"label":"reconfirmed",case_id:caseId,expected};
   if(sourceDigest!==undefined)action.source_digest=sourceDigest;
   this.actions.push(action);this.labels.push(action);
   this.remaining=this.remaining.filter(id=>evaluate(this.policy.candidates.find(x=>x.id===id).rule,c.input)===expected);
  }
  revisionPreview(policy) {
   policy=validate(policy);
   if(canonical(policy)===canonical(this.policy))fail("Revision must change policy");
   const changed=collection=>{const old=new Map(this.policy[collection].map(x=>[x.id,x])),next=new Map(policy[collection].map(x=>[x.id,x]));return [...new Set([...old.keys(),...next.keys()])].filter(k=>canonical(old.get(k))!==canonical(next.get(k))).sort();};
   return {source_digest:this.version,changed_rules:changed("candidates"),changed_cases:changed("cases"),fields_changed:canonical(this.policy.fields)!==canonical(policy.fields),pending:this.caseReview().filter(x=>x.observed!==null).map(x=>({case_id:x.id,input:x.input,expected:x.observed,review_status:policy.cases.some(c=>c.id===x.id&&canonical(c.input)===canonical(x.input))?"pending-review":"fresh-answer-required"})),impact:this.comparePolicy(policy)};
  }
  async reconfirm(record,caseId) {
   const original=await restore(record),preview=original.revisionPreview(this.policy),item=preview.pending.find(p=>p.case_id===caseId);
   if(!item||item.review_status!=="pending-review")fail("Changed or unobserved input requires a fresh answer");
   this.labelCase(caseId,item.expected,original.version);
  }
  examples() { if(this.actions!==null){const replay=new Session(this.policy,this.version),result=[];replay.actions=[];for(const a of this.actions){if(a.kind==="answer"){const q=replay.question();if(a.expected!==null)result.push({input:q.input,expected:a.expected,question_id:q.id});}else {const c=this.policy.cases.find(c=>c.id===a.case_id);result.push({input:{...c.input},expected:a.expected,question_id:this.version+":review:"+c.id});}replay.apply(a);}return result;}const replay=new Session(this.policy,this.version),result=[];for (const d of this.decisions) { const q=replay.question(); if (d.expected !== null) result.push({input:q.input,expected:d.expected,question_id:d.question_id});replay.answer(d.question_id,d.expected); }return result; }
  contract(target, template) {
   if (this.stopped || !this.examples().length) fail("Unresolved or unanswered session cannot export");
   // Fixed reviewed target, matching the existing browser export. CLI supports validated explicit targets.
   if (target !== "implementation:decide") fail("Browser target must be implementation:decide");
   const data={module:"implementation",function:"decide",examples:this.examples(),specification_digest:this.version,session_status:this.status()};
   return template.replace("__DATA__", "'" + canonical(data).replaceAll("\\", "\\\\").replaceAll("'", "\\'") + "'");
  }
 }
 async function restore(record) {
  if(object(record)&&record.schema===REVIEW){
   record=parse(canonical(record));keys(record,["schema","policy","version_digest","actions","scope"]);
   const s=await create(record.policy);if(s.version!==record.version_digest||record.scope!=="observed-examples-only")fail("Policy version mismatch");
   if(!Array.isArray(record.actions)||record.actions.length>288)fail("Invalid review history");s.actions=[];record.actions.forEach(a=>s.apply(a));return s;
  }
  keys(record,["schema","policy","version_digest","decisions","scope"]);
  if (record.schema!==SESSION || record.scope!=="observed-examples-only") fail("Unsupported session");
  const s=await create(record.policy);
  if(s.version!==record.version_digest) fail("Policy version mismatch");
  if(!Array.isArray(record.decisions)||record.decisions.length>32)fail("Invalid history");
  for(const d of record.decisions){keys(d,["question_id","expected"]);s.answer(d.question_id,d.expected);}return s;
 }
 function comparison(candidates) {
  const shared=[];
  function walk(nodes,path) {
   if(nodes.every(n=>canonical(n)===canonical(nodes[0]))){const index=shared.length+1;shared.push({path,rule:nodes[0]});return nodes.map(()=>({shared:index}));}
   const op=Object.hasOwn(nodes[0],"and")?"and":Object.hasOwn(nodes[0],"or")?"or":null;
   if(op&&nodes.every(n=>Object.hasOwn(n,op)&&n[op].length===nodes[0][op].length)){
    const children=nodes[0][op].map((_,i)=>walk(nodes.map(n=>n[op][i]),path.concat([op,i])));
    return nodes.map((_,i)=>({[op]:children.map(c=>c[i])}));
   }
   return nodes;
  }
  const rules=candidates.length?walk(candidates.map(c=>c.rule),[]):[];
  return {shared,differences:candidates.map((c,i)=>({id:c.id,rule:rules[i]}))};
 }
 const api={comparison,comparePolicies,parse,validate,evaluate,create,suggestCases,restore,canonical};
 if (typeof module!=="undefined") module.exports=api; else root.PolicyEngine=api;
})(globalThis);
