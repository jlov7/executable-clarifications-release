"use strict";
(() => {
 const $=id=>document.getElementById(id),engine=window.ExampleEngine;
 const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
 const clone=x=>JSON.parse(JSON.stringify(x));
 let current=null,previous=null,pending=null,draft=null,editing=false,revision=0;
 let keyboard=null,savedCurrent=null,savedPrevious=null;
 let auditRevision=0,candidatePolicy=null,candidateAudit=null,explanation=null;
 const saveState=window.ReviewState;
 $('examples-editor').addEventListener('input',()=>saveState.setDirty("examples-draft",true));
 $('examples-editor').addEventListener('keydown',event=>{keyboard={node:event.target,step:event.key==='Tab'?(event.shiftKey?-1:1):0};});
 document.addEventListener('keyup',event=>{const action=keyboard;if(event.key===' '&&event.target.tagName==='BUTTON')setTimeout(()=>{if(keyboard===action)keyboard=null;},0);else keyboard=null;});
 document.addEventListener('pointerdown',()=>{keyboard=null;});
 const blank=()=>({schema:'executable-clarifications/example-set-v1',fields:{days:'integer'},examples:[{id:'case1',input:{days:0},expected:false}]});
 const download=(value,name,type='application/json')=>{const url=URL.createObjectURL(new Blob([value],{type})),a=el('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 function button(parent,text,action){const b=el('button',text);b.type='button';b.onclick=action;parent.append(b);return b;}
 function control(parent,label,kind,value,change,options){
  const wrap=el('label',label+' '),n=el(options?'select':'input');
  if(options)for(const value of options){const o=el('option',String(value));o.value=String(value);n.append(o);}
  else {n.type=kind;if(kind==='number')n.step='1';}
  n.value=String(value);n.setAttribute('aria-label',label);n.onchange=()=>{change(kind==='number'?n.valueAsNumber:n.value);changed();};wrap.append(n);parent.append(wrap);return n;
 }
 const defaultValue=kind=>kind==='integer'?0:kind==='boolean'?false:kind.enum[0];
 function clearExplanation(){explanation=null;$('examples-explanation').hidden=true;$('examples-explanation-json').textContent='';$('examples-explanation-body').replaceChildren();}
 function invalidateAudit(){auditRevision++;candidatePolicy=null;candidateAudit=null;$('examples-audit').textContent='';$('examples-audit-policy').textContent='';$('examples-audit-review').hidden=true;$('examples-audit-confirm').checked=false;$('examples-explain').disabled=true;clearExplanation();}
 function changed(){revision++;pending=null;editing=true;invalidateAudit();$('examples-preview').replaceChildren();render();}
 function retainKeyboardFocus(){
  if(!keyboard)return ()=>{};
  const {node,step}=keyboard;keyboard=null;
  const section=node.closest('#examples-fields,#examples-cases');
  const row=node.closest('#examples-fields > fieldset,#examples-cases > fieldset');
  if(!section||!row)return ()=>{};
  const index=Array.from(section.children).indexOf(row),name=n=>n.getAttribute('aria-label')||n.textContent;
  const matches=n=>n.tagName===node.tagName&&name(n)===name(node);
  return ()=>queueMicrotask(()=>{
   const replacement=section.children[Math.min(index,section.children.length-1)];
   if(!replacement)return;
   const enabled=Array.from(replacement.querySelectorAll('input,select,button')).filter(n=>!n.disabled);
   let target=enabled.find(matches)||enabled[0];
   if(step){const controls=Array.from(document.querySelectorAll('a[href],input,select,textarea,button,summary,[tabindex]')).filter(n=>!n.disabled&&n.tabIndex>=0&&n.getClientRects().length);target=controls[controls.indexOf(target)+step]||target;}
   target?.focus();
  });
 }
 function editor(){
  const restoreFocus=retainKeyboardFocus();
  $('examples-editor').hidden=false;$('examples-fields').replaceChildren();$('examples-cases').replaceChildren();
  for(const [name,kind] of Object.entries(draft.fields)){
   const box=el('fieldset');box.append(el('legend','Field '+name));$('examples-fields').append(box);
   control(box,'Name','text',name,value=>{
    if(Object.hasOwn(draft.fields,value)&&value!==name){$('examples-error').textContent='Field name already exists';return;}
    draft.fields=Object.fromEntries(Object.entries(draft.fields).map(([k,v])=>[k===name?value:k,v]));
    for(const row of draft.examples){row.input[value]=row.input[name];if(value!==name)delete row.input[name];}editor();
   });
   control(box,'Type','text',typeof kind==='string'?kind:'enum',v=>{draft.fields[name]=v==='enum'?{enum:['standard','partner']}:v;for(const row of draft.examples)row.input[name]=defaultValue(draft.fields[name]);editor();},['integer','boolean','enum']);
   if(typeof kind==='object')control(box,'Enum values (comma separated)','text',kind.enum.join(', '),v=>{kind.enum=v.split(',').map(x=>x.trim());editor();});
   button(box,'Remove field',()=>{delete draft.fields[name];for(const row of draft.examples)delete row.input[name];changed();editor();}).disabled=Object.keys(draft.fields).length<=1;
  }
  draft.examples.forEach((row,index)=>{
   const box=el('fieldset');box.append(el('legend','Example '+(index+1)));$('examples-cases').append(box);
   control(box,'Example ID','text',row.id,v=>{row.id=v;});
   for(const [name,kind] of Object.entries(draft.fields))control(box,name,kind==='integer'?'number':'text',row.input[name],v=>{row.input[name]=kind==='boolean'?v==='true':v;},kind==='boolean'?[false,true]:typeof kind==='object'?kind.enum:null);
   control(box,'Expected boolean','text',row.expected,v=>{row.expected=v==='true';},[false,true]);
   button(box,'Remove example',()=>{draft.examples.splice(index,1);changed();editor();}).disabled=draft.examples.length<=1;
  });
  $('examples-add-field').disabled=Object.keys(draft.fields).length>=16;$('examples-add-case').disabled=draft.examples.length>=256;
  restoreFocus();
 }
 function updateExport(){
  let destination=null;
  try{destination=engine.target($('examples-target').value);$('examples-target').setAttribute('aria-invalid','false');}
  catch(_){$('examples-target').setAttribute('aria-invalid','true');}
  $('examples-export').disabled=!current||!!pending||editing||!destination;
  $('examples-target-status').textContent=destination?'Will call '+destination.module+'.'+destination.function+'(example). Nothing runs in this browser.':'Enter a valid module:function. Export is blocked; no target code is imported.';
 }
 $('examples-target').addEventListener('input',updateExport);
 function render(){
  saveState.setDirty("examples-draft",editing||!!pending);
  saveState.setDirty("examples",!!current&&engine.canonical(current.record())!==savedCurrent);
  saveState.setDirty("original-examples",!!previous&&engine.canonical(previous.record())!==savedPrevious);
  const shown=pending||(!editing?current:null),record=shown?.record();
  $('examples-status').textContent=editing?'PENDING_REVIEW: draft edits need review and confirmation.':pending?'PENDING_REVIEW: inspect every input and expected boolean, then confirm.':current?current.status()+': supplied truth confirmed.':'PENDING_REVIEW: supply your known cases.';
  $('examples-digest').textContent=record?'SHA-256 '+record.version_digest:'No reviewed draft digest yet.';
  $('examples-confirm').disabled=!pending;updateExport();
  $('examples-save').disabled=!shown;$('examples-download-set').disabled=!shown;$('examples-original').disabled=!current;
  $('examples-edit').disabled=!shown;$('examples-audit-file').disabled=!current||!!pending||editing;
  $('examples-record').textContent=record?engine.canonical(record):'';
  $('examples-preview').replaceChildren();
  if(record)for(const row of record.example_set.examples){const box=el('article');box.dataset.exampleId=row.id;box.append(el('h3',row.id),el('pre',engine.canonical(row.input)),el('p','Supplied expected boolean: '+row.expected));$('examples-preview').append(box);}
 }
 function openEditor(source){draft=clone(source||blank());changed();editor();$('examples-panel').hidden=false;}
 $('try-examples').onclick=async()=>{if(!saveState.confirmDiscard(['examples-draft']))return;invalidateAudit();const token=++revision,next=await engine.create(window.CLARIFICATION_EXAMPLE_SET);if(token!==revision)return;pending=next;editing=false;$('examples-panel').hidden=false;$('examples-editor').hidden=true;$('examples-error').textContent='Supplied synthetic examples. Review every expected boolean before confirming.';render();$('examples-review-title').focus();};
 $('start-examples').onclick=()=>{if(!saveState.confirmDiscard(['examples-draft']))return;openEditor(current?.record().example_set);$('examples-title').focus();};
 $('examples-edit').onclick=()=>openEditor((pending||current).record().example_set);
 $('examples-add-field').onclick=()=>{let name='field'+(Object.keys(draft.fields).length+1);while(Object.hasOwn(draft.fields,name))name+='_';draft.fields[name]='integer';for(const row of draft.examples)row.input[name]=0;changed();editor();};
 $('examples-add-case').onclick=()=>{let id='case'+(draft.examples.length+1);while(draft.examples.some(row=>row.id===id))id+='_';draft.examples.push({id,input:Object.fromEntries(Object.entries(draft.fields).map(([name,kind])=>[name,defaultValue(kind)])),expected:false});changed();editor();};
 $('examples-review').onclick=async()=>{
  const token=++revision;
  try{const next=await engine.create(draft);if(token!==revision)return;pending=next;editing=false;$('examples-editor').hidden=true;$('examples-error').textContent='';render();$('examples-review-title').focus();}
  catch(e){$('examples-error').textContent='Draft rejected: '+e.message;}
 };
 $('examples-file').onchange=async event=>{
  const file=event.target.files[0];if(!file)return;invalidateAudit();const token=++revision;
  try{
   if(file.size>262144)throw Error('JSON exceeds 262144 bytes');
   const data=engine.parse(await file.text()),next=data.schema==='executable-clarifications/example-review-v1'?await engine.restore(data):await engine.create(data);
   if(token!==revision)return;if(!saveState.confirmDiscard(['examples-draft'])){event.target.value='';return;}pending=next;editing=false;$('examples-editor').hidden=true;$('examples-error').textContent='Imported locally. Review the complete supplied table.';$('examples-audit').textContent='';render();$('examples-review-title').focus();
  }catch(e){if(token===revision)$('examples-error').textContent='Import rejected: '+e.message;}
  event.target.value='';
 };
 $('examples-confirm').onclick=()=>{if(!pending)return;if(current&&current.record().version_digest!==pending.record().version_digest){if(!saveState.confirmDiscard(['original-examples']))return;previous=current;savedPrevious=savedCurrent;}invalidateAudit();pending.confirm();current=pending;pending=null;revision++;$('examples-error').textContent='All supplied inputs and expected booleans explicitly confirmed.';render();};
 $('examples-cancel').onclick=()=>{revision++;invalidateAudit();pending=null;editing=false;draft=null;$('examples-editor').hidden=true;$('examples-error').textContent='Draft cancelled. Original retained.';render();};
 $('examples-save').onclick=()=>{const content=engine.canonical((pending||current).record());download(content,'example-review.json');if(!pending&&!editing)savedCurrent=content;render();};
 $('examples-download-set').onclick=()=>download(engine.canonical((pending||current).record().example_set),'example-set.json');
 $('examples-original').onclick=()=>{const original=pending||editing?current:previous||current,content=engine.canonical(original.record());download(content,'original-example-review.json');if(original===previous)savedPrevious=content;else savedCurrent=content;render();};
 $('examples-export').onclick=()=>{try{if(pending||editing)throw Error('Confirm these examples before export');download(current.contract($('examples-target').value),'test_known_examples.py','text/x-python');}catch(e){$('examples-error').textContent=e.message;}};
 $('examples-audit-file').onchange=async event=>{
  const file=event.target.files[0];if(!file)return;invalidateAudit();const token=revision,auditToken=auditRevision;
  try{if(!current||pending||editing)throw Error('Confirm the supplied examples before candidate audit');if(file.size>262144)throw Error('JSON exceeds 262144 bytes');const source=engine.parse(await file.text()),report=await current.audit(source);if(token!==revision||auditToken!==auditRevision)return;candidatePolicy=source;candidateAudit=report;$('examples-audit').textContent=JSON.stringify(report,null,2);$('examples-audit-policy').textContent=JSON.stringify(source,null,2);$('examples-audit-review').hidden=false;$('examples-error').textContent='Inspect this candidate policy and its audit separately before explaining the gap.';}
  catch(e){if(token===revision&&auditToken===auditRevision)$('examples-error').textContent='Audit rejected: '+e.message;}
  event.target.value='';
 };
 $('examples-audit-confirm').onchange=()=>{auditRevision++;clearExplanation();$('examples-explain').disabled=!$('examples-audit-confirm').checked||!candidateAudit;};
 $('examples-explain').onclick=async()=>{
  if(!current||pending||editing||!candidateAudit||!$('examples-audit-confirm').checked)return;
  const token=revision,auditToken=auditRevision,report=await current.explainConflict(candidatePolicy);
  if(token!==revision||auditToken!==auditRevision)return;
  explanation=report;const body=$('examples-explanation-body');body.replaceChildren();
  body.append(el('p',report.status==='OFFERED_CANDIDATE_FITS'?'Offered candidates fit all confirmed examples: '+report.fitting_candidates.join(', ')+'. No conflict subset is needed.':'No offered candidate fits all confirmed examples. Implicated confirmed example IDs: '+report.core_example_ids.join(', ')+'.'));
  if(report.core_example_ids.length){
   body.append(el('p','This subset is deletion-minimal: omitting any one retained example admits a candidate. It is not guaranteed to be the globally smallest subset. Witness candidates fit the remaining subset, not necessarily every supplied example.'));
   const rows=candidateAudit.matrix.filter(row=>report.core_example_ids.includes(row.id));
   for(const row of rows){const box=el('article');box.append(el('h4','Confirmed example '+row.id),el('pre',engine.canonical(row.input)),el('p','Supplied expected boolean: '+row.expected));body.append(box);}
   body.append(el('h4','Why each offered candidate is eliminated'));
   const eliminations=el('ul');
   for(const witness of report.candidate_eliminations){const row=rows.find(item=>item.id===witness.mismatched_core_example);eliminations.append(el('li',witness.candidate_id+' predicts '+row.predictions[witness.candidate_id]+' for '+row.id+'; supplied expected boolean: '+row.expected+'.'));}body.append(eliminations);
   body.append(el('h4','Check by omitting one implicated example'));
   const removals=el('ul');
   for(const witness of report.removal_witnesses)removals.append(el('li','Omit '+witness.removed_example_id+': '+witness.fitting_candidate+' fits the other implicated examples.'));body.append(removals);
  }
  body.append(el('p','This report does not judge labels incorrect or infer truth, intent or candidate completeness. Review the full example table and prediction matrix above to check each witness.'));
  $('examples-explanation-json').textContent=JSON.stringify(report,null,2);$('examples-explanation').hidden=false;$('examples-explanation-title').focus();
 };
 $('examples-explanation-save').onclick=()=>{if(explanation)download(engine.canonical(explanation),'conflict-explanation.json');};
 render();
})();
