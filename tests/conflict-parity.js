"use strict";
const fs=require('fs'),engine=require('../web/example-engine.js');
(async()=>{
 const input=JSON.parse(fs.readFileSync(0,'utf8')),reports=[];
 for(const item of input){
  const session=await engine.create(item.examples),before=engine.canonical(session.record());
  let pending_refused=false;
  try{await session.explainConflict(item.policy);}catch(_){pending_refused=true;}
  if(!pending_refused||engine.canonical(session.record())!==before)throw Error('Unconfirmed explanation accepted or mutated review');
  session.confirm();const saved=engine.canonical(session.record()),source=engine.canonical(item.policy);
  reports.push(await session.explainConflict(item.policy));
  if(engine.canonical(session.record())!==saved||engine.canonical(item.policy)!==source)throw Error('Explanation mutated inputs');
 }
 console.log(JSON.stringify(reports));
})().catch(e=>{console.error(e);process.exit(1);});
