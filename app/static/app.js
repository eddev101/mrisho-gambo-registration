document.addEventListener('DOMContentLoaded',()=>{
 const langSelect=document.getElementById('language');
 const applyLang=lang=>{document.documentElement.lang=lang;document.querySelectorAll('[data-en][data-sw]').forEach(el=>{el.textContent=el.dataset[lang]||el.dataset.en});localStorage.setItem('mg_language',lang)};
 if(langSelect){const saved=localStorage.getItem('mg_language')||'en';langSelect.value=saved;applyLang(saved);langSelect.addEventListener('change',()=>applyLang(langSelect.value))}
 const steps=[...document.querySelectorAll('.form-step')], labels=[...document.querySelectorAll('.stepper span')];let active=0;
 const show=n=>{active=n;steps.forEach((s,i)=>s.classList.toggle('hidden',i!==n));labels.forEach((l,i)=>{l.classList.toggle('active',i===n);l.classList.toggle('done',i<n)});window.scrollTo({top:document.querySelector('.card')?.offsetTop||0,behavior:'smooth'})};
 const validate=()=>{const form=steps[active];for(const input of form.querySelectorAll('input,select,textarea')){if(input.type==='file')continue;if(!input.checkValidity()){input.reportValidity();return false}}if(active===1){const p=form.querySelector('[name="guardian_phone"]');const digits=(p.value.match(/\d/g)||[]).length;if(digits<9||digits>15){p.setCustomValidity('Enter a valid telephone number');p.reportValidity();p.setCustomValidity('');return false}}return true};
 document.querySelectorAll('.next').forEach(b=>b.addEventListener('click',()=>{if(validate())show(Math.min(steps.length-1,active+1))}));document.querySelectorAll('.prev').forEach(b=>b.addEventListener('click',()=>show(Math.max(0,active-1))));
 const type=document.getElementById('student_type'), boarding=document.getElementById('boarding-fields');if(type&&boarding)type.addEventListener('change',()=>boarding.classList.toggle('hidden',type.value!=='Boarding'));
 const canvas=document.getElementById('signature-pad'), hidden=document.getElementById('signature_data');let signed=false;
 if(canvas){const ctx=canvas.getContext('2d');const setup=()=>{const r=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;canvas.width=Math.max(300,r.width*dpr);canvas.height=150*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.lineWidth=2;ctx.lineCap='round';ctx.strokeStyle='#153f2e'};setup();window.addEventListener('resize',setup);let drawing=false,last=null;
 const point=e=>{const r=canvas.getBoundingClientRect();return{x:e.clientX-r.left,y:e.clientY-r.top}};
 canvas.addEventListener('pointerdown',e=>{drawing=true;last=point(e);signed=true;canvas.setPointerCapture(e.pointerId)});canvas.addEventListener('pointermove',e=>{if(!drawing)return;const p=point(e);ctx.beginPath();ctx.moveTo(last.x,last.y);ctx.lineTo(p.x,p.y);ctx.stroke();last=p});['pointerup','pointercancel','lostpointercapture'].forEach(ev=>canvas.addEventListener(ev,()=>drawing=false));
 document.getElementById('clear-signature')?.addEventListener('click',()=>{ctx.clearRect(0,0,canvas.width,canvas.height);signed=false;hidden.value=''});
 document.getElementById('reg-form')?.addEventListener('submit',e=>{if(!signed){e.preventDefault();alert('Please draw the parent/guardian signature. / Tafadhali chora sahihi.');return}hidden.value=canvas.toDataURL('image/png')});
 }
});
