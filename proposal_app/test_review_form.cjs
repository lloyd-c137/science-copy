const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('proposal_app/static/app.js','utf8');
const context=vm.createContext({names:['A','B','C','D','E','F'],esc:s=>s,textField:(k,l,v,t,required)=>`<textarea name="${k}" ${required?'required':''}>${v}</textarea>`});
vm.runInContext(source.slice(source.indexOf('function reviewInputs('),source.indexOf('async function verifyReviewDraft')),context);
for(const decision of ['approve','supplement','redirect']){
 const html=context.reviewInputs(decision,{annual_acceptance:'当前活动验收说明'});
 assert.equal((html.match(/name="annual_acceptance"/g)||[]).length,1,decision);
 assert(html.includes('当前活动验收说明'),decision);
}
console.log('PASS all review decisions retain editable acceptance field');
