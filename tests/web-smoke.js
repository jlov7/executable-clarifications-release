'use strict';
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const nodes = new Map();
for (const id of ['inclusive','exclusive','neither','artifact','copy']) {
  nodes.set(id, {attributes:{},handlers:{},textContent:'',disabled:true,
    setAttribute(k,v){this.attributes[k]=v;},
    addEventListener(k,fn){this.handlers[k]=fn;},
    click(){this.handlers.click();}});
}
let copied='';
const context={document:{getElementById(id){return nodes.get(id);}},navigator:{clipboard:{writeText(text){copied=text;return Promise.resolve();}}},console};
vm.runInNewContext(fs.readFileSync('web/app.js','utf8'),context,{filename:'web/app.js'});
nodes.get('inclusive').click();
let record=JSON.parse(nodes.get('artifact').textContent);
assert.strictEqual(record.expected,true);
assert.strictEqual(record.scope,'example-only');
assert.strictEqual(nodes.get('inclusive').attributes['aria-pressed'],'true');
nodes.get('exclusive').click();
record=JSON.parse(nodes.get('artifact').textContent);
assert.strictEqual(record.expected,false);
assert.strictEqual(nodes.get('inclusive').attributes['aria-pressed'],'false');
nodes.get('neither').click();
record=JSON.parse(nodes.get('artifact').textContent);
assert.strictEqual(record.status,'UNRESOLVED');
assert.strictEqual(record.expected,null);
nodes.get('copy').click();
assert.strictEqual(JSON.parse(copied).status,'UNRESOLVED');
console.log('web-smoke: four interactive assertions passed, no browser network or model calls');
