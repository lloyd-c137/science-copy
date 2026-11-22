"use strict";
const form=document.getElementById('settings'), fields=document.getElementById('fields'), status=document.getElementById('status');
const save=form.querySelector('button[type=submit]');
let revision='', editable=false;
function showStatus(message,state=''){
  status.textContent=message;
  status.dataset.state=state;
}
async function request(body){
  const response=await fetch('/api/runtime-settings',{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
  const result=await response.json();
  if(!response.ok)throw Error(result.error||'配置请求失败');
  return result;
}
function show(result){
  revision=result.revision;
  form.elements.model.value=result.roles.student.model;
  form.elements.reasoning_effort.value=result.roles.student.reasoning_effort;
}
request().then(result=>{show(result);editable=result.editable;fields.disabled=!editable;save.hidden=!editable;document.getElementById('model-help').hidden=!editable;showStatus(editable?'':'学生可查看，老师可以修改。');}).catch(error=>{showStatus(error.message,'error');});
form.addEventListener('submit',async event=>{
  event.preventDefault();if(!editable)return;fields.disabled=true;
  showStatus('正在保存…');
  try{show(await request({revision,model:form.elements.model.value.trim(),reasoning_effort:form.elements.reasoning_effort.value}));showStatus('已保存。','success');}
  catch(error){showStatus(error.message,'error');}
  finally{fields.disabled=false;}
});
