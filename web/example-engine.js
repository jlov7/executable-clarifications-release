"use strict";
// Supplied truth is never passed to the policy generator or suggestion engine.
(function(root){
 const policy=typeof module!=="undefined"?require('./policy-engine.js'):root.PolicyEngine;
 const SCHEMA='executable-clarifications/example-set-v1',REVIEW='executable-clarifications/example-review-v1',SCOPE='supplied-examples-only';
 const {canonical,parse}=policy, fail=m=>{throw Error(m);},clone=x=>parse(canonical(x));
 const object=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
 // Match Python's explicit module:function contract grammar, not a filesystem path.
 const PYTHON_KEYWORDS=new Set('False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield'.split(' '));
 function target(value){
  if(typeof value!=='string'||value.length>256||value.split(':').length!==2)fail('Use a module:function target of at most 256 ASCII characters');
  const [module,functionName]=value.split(':'),parts=[...module.split('.'),functionName];
  if(parts.some(part=>!/^[A-Za-z_][A-Za-z0-9_]*(?![\s\S])/.test(part)||PYTHON_KEYWORDS.has(part)))fail('Use Python module and function identifiers, not paths or expressions');
  return {module,function:functionName};
 }
 const keys=(x,names)=>{if(!object(x)||Object.keys(x).sort().join('|')!==[...names].sort().join('|'))fail('Unknown or missing example fields');};
 const id=x=>{if(typeof x!=='string'||['__proto__','prototype','constructor'].includes(x)||!/^[A-Za-z_][A-Za-z0-9_-]{0,63}(?![\s\S])/.test(x))fail('Invalid or unsafe identifier');};
 function validate(spec){
  spec=clone(spec);if(new TextEncoder().encode(canonical(spec)).length>131072)fail('Example set exceeds 131072 bytes');
  keys(spec,['schema','fields','examples']);if(spec.schema!==SCHEMA)fail('Unsupported example set schema');
  if(!object(spec.fields)||Object.keys(spec.fields).length<1||Object.keys(spec.fields).length>16)fail('Provide 1..16 fields');
  for(const [name,kind] of Object.entries(spec.fields)){
   id(name);if(['integer','boolean'].includes(kind))continue;keys(kind,['enum']);
   if(!Array.isArray(kind.enum)||kind.enum.length<1||kind.enum.length>32||new Set(kind.enum).size!==kind.enum.length||kind.enum.some(v=>typeof v!=='string'||!/^[A-Za-z0-9 _.-]{1,64}(?![\s\S])/.test(v)))fail('Invalid categorical values');
  }
  if(!Array.isArray(spec.examples)||spec.examples.length<1||spec.examples.length>256)fail('Provide 1..256 examples');
  const ids=new Set(),inputs=new Set();
  for(const row of spec.examples){
   keys(row,['id','input','expected']);id(row.id);if(ids.has(row.id))fail('Duplicate example identity');ids.add(row.id);
   keys(row.input,Object.keys(spec.fields));
   for(const [name,v] of Object.entries(row.input)){
    const kind=spec.fields[name];if(!(kind==='integer'?Number.isSafeInteger(v):kind==='boolean'?typeof v==='boolean':typeof v==='string'&&kind.enum.includes(v)))fail('Value does not match declared field type');
   }
   if(typeof row.expected!=='boolean')fail('Expected must be boolean');
   const key=canonical(row.input);if(inputs.has(key))fail('Duplicate or contradictory example input');inputs.add(key);
  }
  return spec;
 }
 async function hash(value){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(value))))).map(b=>b.toString(16).padStart(2,'0')).join('');}
 async function create(source){
  const spec=validate(source),version=await hash(spec);let confirmed=false;
  const status=()=>confirmed?'REVIEWED_EXAMPLES':'PENDING_REVIEW';
  const examples=()=>confirmed?spec.examples.map(row=>({input:clone(row.input),expected:row.expected,question_id:row.id})):[];
  function audit(sourcePolicy){
   if(!confirmed)fail('Confirm the supplied examples before candidate audit');
   const p=policy.validate(sourcePolicy);if(canonical(p.fields)!==canonical(spec.fields))fail('Candidate audit requires the exact declared field vocabulary');
   const matrix=spec.examples.map(row=>({id:row.id,input:clone(row.input),expected:row.expected,predictions:Object.fromEntries(p.candidates.map(c=>[c.id,policy.evaluate(c.rule,row.input)]))}));
   const candidates=p.candidates.map(c=>({candidate_id:c.id,mismatch_ids:matrix.filter(row=>row.predictions[c.id]!==row.expected).map(row=>row.id)}));
   const fitting=candidates.filter(c=>!c.mismatch_ids.length).map(c=>c.candidate_id);
   return {status:fitting.length?'CANDIDATE_FIT':'NO_CANDIDATE_MATCH',fitting_candidates:fitting,candidates,matrix,example_digest:version,scope:'supplied examples only; no completeness or authenticity proof'};
  }
  return {status,confirm(){confirmed=true;},examples,
   record:()=>clone({schema:REVIEW,example_set:spec,version_digest:version,confirmed,scope:SCOPE}),
   async audit(sourcePolicy){const result=audit(sourcePolicy);result.policy_digest=await hash(policy.validate(sourcePolicy));return result;},
   async explainConflict(sourcePolicy){
    const report=audit(sourcePolicy),rows=[...report.matrix].sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0);
    const candidates=report.candidates.map(c=>c.candidate_id).sort();
    const fits=subset=>candidates.filter(candidate=>subset.every(row=>row.predictions[candidate]===row.expected));
    const fitting=fits(rows),result={schema:'executable-clarifications/conflict-explanation-v1',
     status:fitting.length?'OFFERED_CANDIDATE_FITS':'NO_OFFERED_CANDIDATE_FITS',
     example_digest:report.example_digest,policy_digest:await hash(policy.validate(sourcePolicy)),
     fitting_candidates:fitting,core_example_ids:[],candidate_eliminations:[],removal_witnesses:[],
     minimum_cardinality_claimed:false,labels_judged_incorrect:false,
     scope:'Deletion-minimal mismatch within the offered candidates and confirmed examples; not inferred intent, a complete specification or a diagnosis of incorrect labels.'};
    if(fitting.length)return result;
    let core=[...rows];
    for(const row of rows){const remaining=core.filter(item=>item.id!==row.id);if(!fits(remaining).length)core=remaining;}
    result.core_example_ids=core.map(row=>row.id);
    result.candidate_eliminations=candidates.map(candidate=>({candidate_id:candidate,mismatched_core_example:core.find(row=>row.predictions[candidate]!==row.expected).id}));
    result.removal_witnesses=core.map(row=>({removed_example_id:row.id,fitting_candidate:fits(core.filter(item=>item.id!==row.id))[0]}));
    return result;
   },
   contract(destination,template=root.CLARIFICATION_CONTRACT_TEMPLATE){
    if(!confirmed)fail('Confirm the supplied examples before assertion export');
    const data={...target(destination),examples:examples(),specification_digest:version,session_status:status()};
    return template.replace('__DATA__',"'"+canonical(data).replaceAll('\\','\\\\').replaceAll("'","\\'")+"'");
   }
  };
 }
 async function restore(source){
  const r=clone(source);keys(r,['schema','example_set','version_digest','confirmed','scope']);
  if(r.schema!==REVIEW||r.scope!==SCOPE||typeof r.confirmed!=='boolean')fail('Invalid example review record');
  const s=await create(r.example_set);if(s.record().version_digest!==r.version_digest)fail('Example set digest mismatch');
  if(r.confirmed)s.confirm();return s;
 }
 const api={target,create,restore,validate,parse,canonical};if(typeof module!=='undefined')module.exports=api;else root.ExampleEngine=api;
})(globalThis);
