"use strict";
(() => {
 const cases = window.CLARIFICATION_CASES;
 if (!Array.isArray(cases) || !cases.length) return;
 let selected = cases[0], current = "root", history = [], custom = null, original = null, revisedPolicy = null, revisionStarted = false, suggestions = null;
 const byId = id => document.getElementById(id);
 let savedRecord = null;
 const saveState = window.ReviewState;
 const saveKeys = ["policy", "policy-draft", "original-policy"];
 for (const item of cases) {
  const option = document.createElement("option");
  option.value = item.id; option.textContent = item.title;
  byId("scenario").appendChild(option);
 }
 const node = () => {
  if (!custom) return selected.nodes[current];
  const examples = custom.examples();
  return {record: custom.record(), question: custom.question(), status: custom.status(), remaining: custom.remaining,
   contract: custom.stopped || !examples.length ? null : custom.contract("implementation:decide", window.CLARIFICATION_CONTRACT_TEMPLATE),
   assumptions: "# Recorded behavioral assumptions\n\nStatus: " + custom.status() + "\nOnly recorded inputs are specified. Candidate agreement is not verified intent.\n\n" + JSON.stringify(examples, null, 2)};
 };
 const candidates = state => custom ? custom.policy.candidates : state.record.candidates;
 const formatRule = r => {
  if(r.shared)return "shared clause "+r.shared;
  if (r.and || r.or) return "(" + (r.and || r.or).map(formatRule).join(r.and ? " AND " : " OR ") + ")";
  return r.field + " " + r.op + " " + JSON.stringify(r.value);
 };
 const rule = c => custom ? formatRule(c.rule) : c.field + " " + c.operator + " " + c.threshold;
 const input = x => Object.entries(x).map(([k,v]) => k + " = " + (custom ? JSON.stringify(v) : v)).join(", ");
 const count = () => custom ? custom.actions === null ? custom.decisions.length : custom.actions.length : history.length;
 const element = (tag,text) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
 const differenceNode = r => {
  if(r.shared)return element("span","shared clause "+r.shared);
  if(r.and||r.or){const n=element("span","("),children=r.and||r.or;children.forEach((child,i)=>{if(i)n.append(document.createTextNode(r.and?" AND ":" OR "));n.append(differenceNode(child));});n.append(document.createTextNode(")"));return n;}
  return element("mark",formatRule(r));
 };
 const displayImpact = impact => {
  byId("impact-json").textContent=window.PolicyEngine.canonical(impact);
  byId("impact-candidates").replaceChildren();byId("impact-witnesses").replaceChildren();
  if(!impact.compatible){
   byId("impact-summary").textContent="Incompatible field vocabulary. No outputs compared. Fields: "+impact.incompatible_fields.map(x=>x.field).join(", ");
   byId("impact-limits").textContent="Review the baseline and proposed field definitions in the exact report below.";return;
  }
  const c=impact.coverage,o=impact.output;
  byId("impact-summary").textContent=c.checked_combinations+" of "+c.total_combinations+" reported finite inputs checked; "+c.omitted_combinations+" omitted. "+(c.finite_domain_complete?"Every combination of the retained values was checked. ":"Incomplete finite input coverage. ")+"Added candidates: "+(impact.added_candidates.join(", ")||"none")+". Removed candidates: "+(impact.removed_candidates.join(", ")||"none")+".";
  byId("impact-limits").textContent="Values at and beside integer literals and supplied cases in both revisions, both booleans and all declared enum values. Includes fields absent from every rule: "+(c.unreferenced_fields.join(", ")||"none")+". At most "+c.attempt_limit+" attempts ("+c.attempts+" used), "+c.input_limit+" distinct inputs, "+c.domain_value_limit+" values per field, "+o.witness_limit+" representative witnesses and "+o.report_byte_limit+" report bytes. Domain omissions: "+window.PolicyEngine.canonical(c.domain_sizes)+". Coverage limits reached: "+(c.stop_reasons.join(", ")||"none")+". "+o.omitted_change_pairs+" changed candidate/input pairs omitted from witness samples ("+(o.stop_reason||"none")+"). Exact domains and counts are in the report below. Other integers, intended outputs and universal equivalence remain unverified.";
  for(const item of impact.candidate_impacts){
   const observed=item.observed_false_to_true_count+item.observed_true_to_false_count,missed=item.unobserved_false_to_true_count+item.unobserved_true_to_false_count;
   byId("impact-candidates").append(element("p",item.candidate_id+": "+item.status+". False to true: "+item.false_to_true_count+". True to false: "+item.true_to_false_count+". "+observed+" distinct recorded inputs exercise changes; "+missed+" changed checked inputs missed by recorded examples."));
  }
  for(const witness of impact.witnesses){const row=element("article");row.append(element("h3",witness.candidate_id+": "+witness.before+" to "+witness.after),element("p",input(witness.input)),element("p",(witness.exercised_by_observed_example?"Already exercised by a recorded example. ":"Missed by recorded examples. ")+"Unlabelled comparison witness. Predictions do not supply an intended output."));byId("impact-witnesses").append(row);}
 };
 const display = () => {
  const state = node(), q = state.question;
  const fingerprint=window.PolicyEngine.canonical(state.record);
  if(savedRecord===null)savedRecord=fingerprint;
  saveState.setDirty("policy",fingerprint!==savedRecord);
  byId("reset").textContent = custom ? "Reset this policy" : "Reset this example";
  byId("request").textContent = custom ? "Your reviewed custom policy" : selected.title;
  byId("load-status").textContent = "Ready. Only recorded examples are specified.";
  byId("provenance-note").textContent = custom ? "Rules and cases come from your reviewed local policy. No model calls or external services are used." : "These are synthetic examples, not legal or operational policy advice. No model calls or external services are used.";
  byId("status").textContent = state.status + " · " + state.remaining.length + " candidate(s) remain";
  byId("record").textContent = JSON.stringify(state.record, null, 2);
  byId("question-panel").hidden = q === null;
  byId("outcome").hidden = q !== null;
  byId("outcome-title").textContent = state.status === "UNRESOLVED" ? "No rule chosen" : state.status === "NO_CANDIDATE_MATCH" ? "No rule matches the recorded examples" : "Remaining interpretations";
  byId("outcome-help").textContent = state.status === "UNRESOLVED" ? "Undo the last answer to return to the question." : state.status === "NO_CANDIDATE_MATCH" ? "Review or revise the candidates. Your recorded examples remain available for export." : "These rules match the recorded examples. Other behavior remains unspecified.";
  byId("remaining-rules").replaceChildren();
  if (state.status !== "UNRESOLVED") {
   for (const c of candidates(state).filter(c => state.remaining.includes(c.id))) {
    const item = document.createElement("li");
    item.textContent = c.id + ": " + rule(c);
    byId("remaining-rules").appendChild(item);
   }
  }
  byId("answer-history").replaceChildren();
  if(custom){
   for(const e of custom.examples())byId("answer-history").append(element("li",input(e.input)+": "+String(e.expected)));
   if(custom.stopped)byId("answer-history").append(element("li","neither"));
  }else for(let i=0;i<history.length;i++)byId("answer-history").append(element("li",input(selected.nodes[history[i]].question.input)+": "+String(state.record.decisions[i].expected===null?"neither":state.record.decisions[i].expected)));
  byId("history-empty").hidden = count()>0;
  byId("undo").disabled = count()===0;
  byId("all-cases-panel").hidden=!custom;
  byId("suggest-cases").hidden=!custom;
  byId("suggestions-panel").hidden=!suggestions;
  byId("case-review").replaceChildren();
  const review=custom?custom.caseReview():[],reviewById=new Map(review.map(c=>[c.id,c]));
  for(const c of review){
   const row=element("article");row.dataset.caseId=c.id;
   row.append(element("h3",c.id+" · "+c.review_status),element("p",input(c.input)),element("p","Candidate predictions: "+Object.entries(c.predictions).map(([id,v])=>id+" = "+v).join(", ")));
   row.append(element("p",c.observed===null?"No operator label recorded.":"Observed operator label: "+c.observed));
   for(const expected of [true,false]){const b=element("button","Label "+expected);b.type="button";b.disabled=c.review_status!=="unasked";b.onclick=()=>{custom.labelCase(c.id,expected);display();};row.append(b);}
   byId("case-review").append(row);
  }
  if(original && revisedPolicy){
   const preview=original.revisionPreview(revisedPolicy);
   byId("revision-panel").hidden=false;byId("start-revision").hidden=revisionStarted;
   byId("revision-summary").textContent="Changed rules: "+(preview.changed_rules.join(", ")||"none")+"\nChanged cases: "+(preview.changed_cases.join(", ")||"none")+"\nFields changed: "+preview.fields_changed;
   displayImpact(preview.impact);
   byId("pending-review").replaceChildren();
   for(const item of preview.pending){const row=element("li",item.case_id+": old output "+item.expected+" · "+item.review_status);if(revisionStarted&&item.review_status==="pending-review"){
    const b=element("button","Reconfirm "+item.case_id+" as "+item.expected);b.type="button";b.disabled=reviewById.get(item.case_id).review_status!=="unasked";b.onclick=async()=>{await custom.reconfirm(original.record(),item.case_id);display();};row.append(b);}
    byId("pending-review").append(row);
   }
  }else byId("revision-panel").hidden=true;
  if (q) {
   byId("question").textContent = "For " + input(q.input) + ", what should the output be?";
   byId("remaining").textContent = "This case separates " + q.remaining_count + " remaining rules.";
   const visibleCandidates = candidates(state).filter(c => state.remaining.includes(c.id));
   byId("interpretations").replaceChildren();
   byId("shared-conditions").replaceChildren();
   const comparison=custom?window.PolicyEngine.comparison(visibleCandidates):null;
   if(comparison&&comparison.shared.length){byId("shared-conditions").append(element("h3","Structurally shared clauses"));comparison.shared.forEach((c,i)=>byId("shared-conditions").append(element("p","Shared clause "+(i+1)+": "+formatRule(c.rule))));}
   for (const c of visibleCandidates) {
    const row = document.createElement("tr");
    row.append(element("td",c.id));
    const cell=element("td");
    if(custom){const delta=comparison.differences.find(d=>d.id===c.id);cell.append(differenceNode(delta.rule));const full=element("details"),summary=element("summary","Full exact rule");full.append(summary,element("p",rule(c)));cell.append(full);}else cell.textContent=rule(c);
    row.append(cell,element("td",String(q.outputs[c.id])));
    byId("interpretations").appendChild(row);
   }
   byId("true-group").textContent = "Retain " + q.groups.true.join(", ");
   for(const value of ["true","false"]){const group=q.groups[value];byId("answer-"+value).setAttribute("aria-label","Intended output "+value+". Retain "+visibleCandidates.filter(c=>group.includes(c.id)).map(c=>c.id+": "+rule(c)).join("; "));}
   byId("false-group").textContent = "Retain " + q.groups.false.join(", ");
  }
  byId("download-test").disabled = state.contract === null;
  byId("export-status").textContent = state.status === "UNRESOLVED" ? "Unresolved: no test assertions may be exported." : state.contract ? "Example-scoped test available. Other behavior remains unspecified." : "Answer a question before exporting test assertions.";
 };
 for (const answer of ["true", "false", "neither"]) {
  byId("answer-" + answer).addEventListener("click", () => {
   if (custom) { const q = custom.question(); if (!q) return; custom.answer(q.id, {true:true,false:false,neither:null}[answer]); display(); (custom.question() ? byId("question") : byId("outcome-title")).focus(); return; }
   const next = node().branches[answer];
   if (!next) return;
   history.push(current);
   current = next; display();
   if (node().question) byId("question").focus();
   else byId("outcome-title").focus();
  });
 }
 byId("scenario").addEventListener("change", () => {
  if(!saveState.confirmDiscard(saveKeys)){byId("scenario").value=selected.id;return;}
  savedRecord=null;saveKeys.forEach(key=>saveState.setDirty(key,false));byId("policy-editor").hidden=true;
  suggestions=null;original=null;revisedPolicy=null;revisionStarted=false;custom = null; selected = cases.find(c => c.id === byId("scenario").value) || cases[0]; current = "root"; history = []; display();
 });
 byId("undo").addEventListener("click", () => {
  if (custom) { if (!count()) return; custom.undo(); display(); byId("question").focus(); return; }
  if (!history.length) return;
  current = history.pop(); display(); byId("question").focus();
 });
 byId("reset").addEventListener("click", () => { if(!saveState.confirmDiscard(saveKeys))return; suggestions=null;original=null;revisedPolicy=null;revisionStarted=false;byId("policy-editor").hidden=true; if (custom) { while (count()) custom.undo(); } current = "root"; history = []; savedRecord=null;saveKeys.forEach(key=>saveState.setDirty(key,false)); display(); (node().question?byId("question"):byId("outcome-title")).focus(); });
 function download(text, filename, type) {
  if (typeof text !== "string") return;
  const url = URL.createObjectURL(new Blob([text], {type}));
  const link = document.createElement("a"); link.href = url; link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  byId("export-status").textContent = "Download prepared: " + filename;
 }
 byId("download-record").addEventListener("click", () => {const record=node().record;download(JSON.stringify(record), "clarification-session.json", "application/json");savedRecord=window.PolicyEngine.canonical(record);saveState.setDirty("policy",false);if(original&&window.PolicyEngine.canonical(original.record())===savedRecord)saveState.setDirty("original-policy",false);});
 byId("download-test").addEventListener("click", () => download(node().contract, "test_implementation_contract.py", "text/x-python"));
 byId("download-assumptions").addEventListener("click", () => download(node().assumptions, "ASSUMPTIONS.md", "text/markdown"));
 byId("policy-file").addEventListener("change", async () => {
  const file = byId("policy-file").files[0]; if (!file) return;
  try {
   if (file.size > 262144) throw new Error("JSON exceeds 262144 bytes");
   const data = window.PolicyEngine.parse(await file.text());
   let imported=null,builtin=null;
   if(data&&data.schema==="executable-clarifications/session-v1"){
    const exact=window.PolicyEngine.canonical(data);
    for(const scenario of cases)for(const [identity,state] of Object.entries(scenario.nodes)){
     if(window.PolicyEngine.canonical(state.record)===exact)builtin={scenario,identity};
    }
    if(!builtin)throw new Error("This integer session is not a supplied browser example. Resume custom integer grids with the CLI.");
   }else imported=data&&["executable-clarifications/policy-session-v1","executable-clarifications/policy-session-v2"].includes(data.schema)?await window.PolicyEngine.restore(data):await window.PolicyEngine.create(data);
   if(!saveState.confirmDiscard(saveKeys)){byId("policy-file").value="";return;}
   suggestions=null;original=null;revisedPolicy=null;revisionStarted=false;custom=imported;history=[];current="root";
   if(builtin){
    selected=builtin.scenario;current=builtin.identity;byId("scenario").value=selected.id;
    let step="root";for(const answer of current.split("-").slice(1)){history.push(step);step+="-"+answer;}
   }
   savedRecord=window.PolicyEngine.canonical(node().record);saveKeys.forEach(key=>saveState.setDirty(key,false));byId("policy-editor").hidden=true;display();
   byId("import-status").textContent = "Imported locally: " + file.name + ". Answer the next case, then download the session to resume later.";
  } catch (error) { byId("import-status").textContent = "Import rejected: " + error.message + ". Your current session is unchanged."; }
  byId("policy-file").value = "";
 });
 byId("open-editor").onclick=()=>{if(!saveState.confirmDiscard(["policy-draft"]))return;if(!revisionStarted){original=null;revisedPolicy=null;saveState.setDirty("original-policy",false);}saveState.setDirty("policy-draft",false);display();window.PolicyEditor.open(custom?custom.policy:null,async policy=>{
  if(!custom&&!saveState.confirmDiscard(["policy"]))return;
  suggestions=null;
  if(custom&&window.PolicyEngine.canonical(custom.policy)!==window.PolicyEngine.canonical(policy)){
   if(revisionStarted&&!saveState.confirmDiscard(["original-policy"]))return;
   saveState.setDirty("original-policy",window.PolicyEngine.canonical(custom.record())!==savedRecord);saveState.setDirty("policy-draft",true);
   original=await window.PolicyEngine.restore(custom.record());revisedPolicy=policy;revisionStarted=false;byId("policy-editor").hidden=true;display();byId("revision-panel").scrollIntoView();
  }else{if(!custom)custom=await window.PolicyEngine.create(policy);saveState.setDirty("policy-draft",false);history=[];current="root";display();byId("policy-editor").hidden=true;byId("all-cases-panel").scrollIntoView();}
 });};
 byId("cancel-policy-edit").onclick=()=>{saveState.setDirty("policy-draft",false);if(!revisionStarted){saveState.setDirty("original-policy",false);original=null;revisedPolicy=null;}byId("policy-editor").hidden=true;display();byId("open-editor").focus();};
 byId("policy-editor").addEventListener("click",event=>{const button=event.target.closest("button");if(button&&!["apply-policy","download-policy","cancel-policy-edit"].includes(button.id))saveState.setDirty("policy-draft",true);});
 byId("policy-editor").addEventListener("input",()=>saveState.setDirty("policy-draft",true));
 byId("policy-editor").addEventListener("change",()=>saveState.setDirty("policy-draft",true));
 byId("start-revision").onclick=async()=>{original=await window.PolicyEngine.restore(custom.record());saveState.setDirty("original-policy",window.PolicyEngine.canonical(original.record())!==savedRecord);saveState.setDirty("policy-draft",false);custom=await window.PolicyEngine.create(revisedPolicy);revisionStarted=true;byId("policy-editor").hidden=true;display();};
 byId("download-original").onclick=()=>{const record=original.record();download(JSON.stringify(record),"original-clarification-session.json","application/json");saveState.setDirty("original-policy",false);if(window.PolicyEngine.canonical(record)===window.PolicyEngine.canonical(node().record)){savedRecord=window.PolicyEngine.canonical(record);saveState.setDirty("policy",false);}};
 byId("suggest-cases").onclick=()=>{
  try{
   suggestions=custom.suggestCases();
   const c=suggestions.coverage;
   byId("suggestions-summary").textContent=suggestions.added_cases.length+" new, unreviewed cases. No labels inferred. "+custom.examples().length+" old answer(s) will require explicit review under the changed policy digest. "+c.covered_combinations+" of "+c.total_combinations+" finite-domain combinations represented; "+c.omitted_combinations+" omitted. "+(c.finite_domain_complete?"All combinations of the reported finite values are present. ":"Incomplete finite-domain coverage. ")+c.attempts+" attempts. "+(c.truncated?"Stopped at "+c.stop_reason+". ":"")+"Other integers and user intent remain unverified. Domains: "+window.PolicyEngine.canonical(c.domains);
   byId("suggestions-limits").textContent="Integer values at and beside rule/seed values, both booleans and declared categorical alternatives, including fields absent from every rule: "+(c.unreferenced_fields.join(", ")||"none")+". At most 4096 attempts, 256 total cases and 131072 policy bytes. Small grids enumerate every multi-field combination of the reported values when all bounds permit. Larger grids prioritize seed single/pair changes before the Cartesian pass; limits may leave combinations omitted. Complete finite-domain coverage excludes other integers and does not establish exception truth or user intent.";
   byId("suggestions-cases").replaceChildren();
   for(const item of suggestions.added_cases){const row=element("article");row.append(element("h3",item.id),element("p",input(item.input)),element("p","Unreviewed. No operator label."));byId("suggestions-cases").append(row);}
   byId("apply-suggestions").disabled=!suggestions.added_cases.length;
   display();byId("suggestions-title").focus({preventScroll:true});byId("suggestions-title").scrollIntoView({block:"start"});
  }catch(error){byId("import-status").textContent="Suggestions rejected: "+error.message+". Your current session is unchanged.";}
 };
 byId("apply-suggestions").onclick=async()=>{
  if(!suggestions||!suggestions.added_cases.length)return;
  if(!saveState.confirmDiscard(["policy-draft",...(revisionStarted?["original-policy"]:[])]))return;
  saveState.setDirty("original-policy",window.PolicyEngine.canonical(custom.record())!==savedRecord);saveState.setDirty("policy-draft",true);
  original=await window.PolicyEngine.restore(custom.record());revisedPolicy=suggestions.policy;revisionStarted=false;suggestions=null;byId("policy-editor").hidden=true;
  display();byId("revision-panel").scrollIntoView();byId("start-revision").focus();
 };
 byId("cancel-suggestions").onclick=()=>{suggestions=null;display();byId("suggest-cases").focus();};
 display();
})();
