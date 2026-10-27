"use strict";
(() => {
 const dirty = new Set();
 const names={"policy":"session","policy-draft":"policy draft","original-policy":"original session","examples":"example review","examples-draft":"example draft","original-examples":"original example review"};
 const setDirty = (key, value) => {
  if(value)dirty.add(key);else dirty.delete(key);
  const status=document.getElementById("save-status");
  status.textContent=dirty.size
   ? "Unsaved: "+Array.from(dirty,key=>names[key]).join(", ")+". Download review JSON to keep confirmed work. Finish or cancel draft edits before leaving."
   : "Files stay on your device. Download review JSON to keep your work; import it to continue later.";
 };
 window.ReviewState={
  setDirty,
  confirmDiscard: keys => !keys.some(key=>dirty.has(key)) ||
   window.confirm("Discard unsaved work in this review? Cancel and download its JSON first to keep it.")
 };
 window.addEventListener("beforeunload",event=>{
  if(dirty.size){event.preventDefault();event.returnValue="";}
 });
})();
