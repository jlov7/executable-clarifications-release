"use strict";
const caseInput={age_days:30};
const candidates={inclusive:{operator:"<=",threshold:30},exclusive:{operator:"<",threshold:30}};
function evaluate(name, input){const c=candidates[name];if(!c||typeof input.age_days!=="number"||!Number.isInteger(input.age_days))return null;return c.operator==="<="?input.age_days<=c.threshold:input.age_days<c.threshold;}
let record=null;
const choices=["inclusive","exclusive","neither"];
function select(name){
 for(const key of choices.slice(0,2))document.getElementById(key).setAttribute("aria-pressed",String(key===name));
 record=name==="neither"?{status:"UNRESOLVED",selected:name,example:caseInput,expected:null,scope:"example-only"}:{status:"RECORDED_CHOICE",selected:name,example:caseInput,expected:evaluate(name,caseInput),scope:"example-only",candidate:{id:name,field:"age_days",operator:candidates[name].operator,threshold:30}};
 document.getElementById("artifact").textContent=JSON.stringify(record,null,2);
 document.getElementById("copy").disabled=false;
}
for(const key of choices)document.getElementById(key).addEventListener("click",()=>select(key));
document.getElementById("copy").addEventListener("click",()=>{if(record&&navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(JSON.stringify(record,null,2)).catch(()=>{});}});
