'use strict';
document.getElementById('login').addEventListener('submit',async event=>{
  event.preventDefault(); const form=event.currentTarget;const button=form.querySelector('button');const error=document.getElementById('error');
  button.disabled=true;error.textContent='';
  try{
    const response=await fetch('/api/v1/auth/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:form.elements.username.value,password:form.elements.password.value})});
    const data=await response.json();
    if(!response.ok) throw new Error(data.error?.message||'Sign-in failed.');
    form.elements.password.value='';location.replace('/');
  }catch(e){error.textContent=e.message;button.disabled=false;}
});
