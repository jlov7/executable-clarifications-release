"use strict";
// Typed controls produce policy-v1; the shared validator is the only acceptance boundary.
(() => {
 const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
 const byId=id=>document.getElementById(id),clone=x=>JSON.parse(JSON.stringify(x));
 let draft=null,onApply=null;
 let keyboard=null;
 byId('policy-editor').addEventListener('keydown',event=>{keyboard={node:event.target,step:event.key==='Tab'?(event.shiftKey?-1:1):0};});
 document.addEventListener('keyup',event=>{const action=keyboard;if(event.key===' '&&event.target.tagName==='BUTTON')setTimeout(()=>{if(keyboard===action)keyboard=null;},0);else keyboard=null;});
 document.addEventListener('pointerdown',()=>{keyboard=null;});
 const button=(text,action)=>{const b=el('button',text);b.type='button';b.addEventListener('click',action);return b;};
 function control(parent,label,node){node.setAttribute('aria-label',label);const wrap=el('label',label+' ');wrap.append(node);parent.append(wrap);return node;}
 function text(parent,label,value,change,type='text'){
  const n=el('input');n.type=type;n.value=value;n.addEventListener('change',()=>change(type==='number'?n.valueAsNumber:n.value));return control(parent,label,n);
 }
 function select(parent,label,options,value,change){const n=el('select');for(const v of options){const o=el('option',String(v));o.value=String(v);n.append(o);}n.value=String(value);n.addEventListener('change',()=>change(n.value));return control(parent,label,n);}
 const names=()=>Object.keys(draft.fields);
 const leaf=()=>{const field=names()[0];const kind=draft.fields[field];return {field,op:'==',value:kind==='integer'?0:kind==='boolean'?false:kind.enum[0]};};
 function scalar(parent,label,field,value,change){
  const kind=draft.fields[field];
  if(kind==='integer')text(parent,label,value,change,'number').step='1';
  else select(parent,label,kind==='boolean'?[false,true]:kind.enum,value,v=>change(kind==='boolean'?v==='true':v));
 }
 function preview(){try{const p=window.PolicyEngine.validate(draft);byId('editor-preview').textContent=JSON.stringify(p,null,2);byId('editor-status').textContent='Valid policy. Review candidates and cases before using it.';byId('apply-policy').disabled=false;byId('download-policy').disabled=false;}catch(e){byId('editor-preview').textContent=JSON.stringify(draft,null,2);byId('editor-status').textContent='Policy needs correction: '+e.message;byId('apply-policy').disabled=true;byId('download-policy').disabled=true;}}
 function rule(parent,node,replace,depth=0){
  const box=el('fieldset'),legend=el('legend',depth?'Condition':'Rule');box.append(legend);parent.append(box);
  const group=node.and?'and':node.or?'or':null;
  select(box,'Condition type',['predicate','and','or'],group||'predicate',v=>{replace(v==='predicate'?leaf():{[v]:[leaf(),leaf()]});render();});
  if(group){
   node[group].forEach((child,i)=>{rule(box,child,v=>node[group][i]=v,depth+1);if(node[group].length>2)box.append(button('Remove condition '+(i+1),()=>{node[group].splice(i,1);render();}));});
   const add=button('Add condition',()=>{node[group].push(leaf());render();});add.disabled=node[group].length>=16||depth>=6;box.append(add);return;
  }
  if(!names().includes(node.field)){replace(leaf());return;}
  select(box,'Field',names(),node.field,v=>{node.field=v;node.op='==';const kind=draft.fields[v];node.value=kind==='integer'?0:kind==='boolean'?false:kind.enum[0];render();});
  const ops=draft.fields[node.field]==='integer'?['==','!=','<','<=','>','>=','in']:['==','!=','in'];
  select(box,'Operator',ops,node.op,v=>{node.op=v;node.value=v==='in'?[Array.isArray(node.value)?node.value[0]:node.value]:Array.isArray(node.value)?node.value[0]:node.value;render();});
  if(node.op==='in'){
   node.value.forEach((v,i)=>{scalar(box,'Member '+(i+1),node.field,v,value=>{node.value[i]=value;preview();});if(node.value.length>1)box.append(button('Remove member '+(i+1),()=>{node.value.splice(i,1);render();}));});
   const add=button('Add membership value',()=>{const kind=draft.fields[node.field];node.value.push(kind==='integer'?0:kind==='boolean'?false:kind.enum[0]);render();});add.disabled=node.value.length>=32;box.append(add);
  }else scalar(box,'Value',node.field,node.value,v=>{node.value=v;preview();});
 }
 function retainKeyboardFocus(){
  if(!keyboard)return ()=>{};
  const {node,step}=keyboard;keyboard=null;
  const section=node.closest('#editor-fields,#editor-candidates,#editor-cases');
  const row=node.closest('#editor-fields > fieldset,#editor-candidates > fieldset,#editor-cases > fieldset');
  if(!section||!row)return ()=>{};
  const index=Array.from(section.children).indexOf(row),name=n=>n.getAttribute('aria-label')||n.textContent;
  const matches=n=>n.tagName===node.tagName&&name(n)===name(node);
  const occurrence=Array.from(row.querySelectorAll('input,select,button')).filter(matches).indexOf(node);
  return ()=>queueMicrotask(()=>{
   const replacement=section.children[Math.min(index,section.children.length-1)];
   if(!replacement)return;
   const enabled=Array.from(replacement.querySelectorAll('input,select,button')).filter(n=>!n.disabled),same=enabled.filter(matches);
   let target=same[Math.min(occurrence,same.length-1)]||enabled[0];
   if(step){const controls=Array.from(document.querySelectorAll('a[href],input,select,textarea,button,summary,[tabindex]')).filter(n=>!n.disabled&&n.tabIndex>=0&&n.getClientRects().length);target=controls[controls.indexOf(target)+step]||target;}
   target?.focus();
  });
 }
 function render(){
  const restoreFocus=retainKeyboardFocus();
  const fields=byId('editor-fields');fields.replaceChildren();
  for(const [name,kind] of Object.entries(draft.fields)){
   const row=el('fieldset');row.append(el('legend','Field '+name));fields.append(row);
   text(row,'Name',name,value=>{if(value===name)return; if(Object.hasOwn(draft.fields,value)){render();byId('editor-status').textContent='Field name already exists; original name retained';return;}
    const rename=n=>{if(n.field===name)n.field=value;else for(const c of n.and||n.or||[])rename(c);};
    draft.fields=Object.fromEntries(Object.entries(draft.fields).map(([k,v])=>[k===name?value:k,v]));draft.candidates.forEach(c=>rename(c.rule));draft.cases.forEach(c=>{c.input[value]=c.input[name];delete c.input[name];});render();});
   select(row,'Type',['integer','boolean','enum'],typeof kind==='string'?kind:'enum',v=>{draft.fields[name]=v==='enum'?{enum:['standard','training']}:v;draft.candidates.forEach(c=>c.rule=leaf());draft.cases.forEach(c=>c.input[name]=v==='integer'?0:v==='boolean'?false:'standard');render();});
   if(typeof kind==='object')text(row,'Enum values (comma separated)',kind.enum.join(', '),v=>{kind.enum=v.split(',').map(x=>x.trim());render();});
   const remove=button('Remove field',()=>{delete draft.fields[name];draft.candidates.forEach(c=>c.rule=leaf());draft.cases.forEach(c=>delete c.input[name]);render();});remove.disabled=names().length<=1;row.append(remove);
  }
  const candidates=byId('editor-candidates');candidates.replaceChildren();
  draft.candidates.forEach((c,i)=>{const row=el('fieldset');row.append(el('legend','Candidate '+(i+1)));candidates.append(row);text(row,'Candidate ID',c.id,v=>{c.id=v;preview();});rule(row,c.rule,v=>c.rule=v);const remove=button('Remove candidate',()=>{draft.candidates.splice(i,1);render();});remove.disabled=draft.candidates.length<=2;row.append(remove);});
  const cases=byId('editor-cases');cases.replaceChildren();
  draft.cases.forEach((c,i)=>{const row=el('fieldset');row.append(el('legend','Case '+(i+1)));cases.append(row);text(row,'Case ID',c.id,v=>{c.id=v;preview();});for(const name of names())scalar(row,name,name,c.input[name],v=>{c.input[name]=v;preview();});const remove=button('Remove case',()=>{draft.cases.splice(i,1);render();});remove.disabled=draft.cases.length<=1;row.append(remove);});
  byId('add-field').disabled=names().length>=16;byId('add-candidate').disabled=draft.candidates.length>=32;byId('add-case').disabled=draft.cases.length>=256;preview();restoreFocus();
 }
 byId('add-field').onclick=()=>{let name='field'+(names().length+1);while(names().includes(name))name+='_';draft.fields[name]='integer';draft.cases.forEach(c=>c.input[name]=0);render();};
 byId('add-candidate').onclick=()=>{let serial=draft.candidates.length+1;while(draft.candidates.some(c=>c.id==='candidate'+serial))serial++;draft.candidates.push({id:'candidate'+serial,rule:leaf()});render();};
 byId('add-case').onclick=()=>{let serial=draft.cases.length+1;while(draft.cases.some(c=>c.id==='case'+serial))serial++;draft.cases.push({id:'case'+serial,input:Object.fromEntries(names().map(name=>[name,draft.fields[name]==='integer'?0:draft.fields[name]==='boolean'?false:draft.fields[name].enum[0]]))});render();};
 byId('apply-policy').onclick=()=>onApply(window.PolicyEngine.validate(draft));
 byId('download-policy').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(window.PolicyEngine.validate(draft))],{type:'application/json'}));const a=el('a');a.href=url;a.download='reviewed-policy.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 window.PolicyEditor={open(policy,apply){onApply=apply;draft=clone(policy||{schema:'executable-clarifications/policy-v1',fields:{score:'integer'},candidates:[{id:'inclusive',rule:{field:'score',op:'>=',value:80}},{id:'exclusive',rule:{field:'score',op:'>',value:80}}],cases:[{id:'boundary',input:{score:80}}]});byId('policy-editor').hidden=false;render();byId('policy-editor').scrollIntoView();}};
})();
