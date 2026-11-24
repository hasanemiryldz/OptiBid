const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n};
function button(text,fn,cls){
 const n=node('button',text,cls);n.type='button';n.onclick=fn;return n
}
export function historyPanel({open,newAnalysis,home,api}){
 const sidebar=document.querySelector('#history');
 const toggle=document.querySelector('#history-toggle');
 const shade=document.querySelector('#history-shade');
 const notice=document.querySelector('#history-status');
 let rows=[],active=null,mode=false,generation=0;
 const marked=new Set();
 const pending=new Map();
 const search=node('input');search.type='search';search.placeholder='Konuya göre ara';search.setAttribute('aria-label','Önceki kayıtlarda ara');
 const body=node('div',null,'history-rows');
 const options=node('div',null,'history-actions');
 const mobile=matchMedia('(max-width: 760px)');
 function drawer(flag){
   const open=flag&&mobile.matches;
   document.body.classList.toggle('drawer-open',open);
   toggle.setAttribute('aria-expanded',String(open));
   sidebar.inert=mobile.matches&&!open;
   if(open)search.focus();else if(mobile.matches&&sidebar.contains(document.activeElement))toggle.focus()
 }
 toggle.onclick=()=>drawer(toggle.getAttribute('aria-expanded')!=='true');
 shade.onclick=()=>drawer(false);mobile.addEventListener('change',()=>drawer(false));drawer(false);
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('drawer-open'))drawer(false)});
 const heading=node('div',null,'history-heading');
 const logo=node('img');logo.src='/static/brand/ob.webp';logo.alt='OptiBid OB';
 heading.append(logo,node('h2','Önceki çalışmalar'),button('Kapat',()=>drawer(false),'drawer-close'));
 sidebar.replaceChildren(heading,button('Yeni çalışma',()=>{drawer(false);newAnalysis()},'primary'),
  button('Veri havuzu',async()=>{drawer(false);await home();document.querySelector('#veri-havuzu summary')?.focus()}),search,options,body);
 search.oninput=draw;
 function draw(){
   options.replaceChildren(button(mode?'Seçimi bitir':'Kayıt seç',()=>{mode=!mode;marked.clear();draw()}));
   if(mode){
     const remove=button('Seçilenleri sil ('+marked.size+')',()=>erase({id:[...marked]}));
     remove.disabled=!marked.size;
     options.append(remove,button('Tüm kayıtları sil',confirmAll,'delete-all'))
   }
   body.replaceChildren();
   const q=search.value.trim().toLocaleLowerCase('tr');
   for(const row of rows){
     const subject=(row.kalemler??[]).map(k=>k.ad).filter(Boolean).join(', ')||row.ihale_turu||'Adsız hazırlık';
     if(!subject.toLocaleLowerCase('tr').includes(q))continue;
     const record=node('div',null,'history-row');
     if(row.id===active)record.classList.add('is-active');
     if(mode){
       const choice=node('input');choice.type='checkbox';choice.checked=marked.has(row.id);
       choice.setAttribute('aria-label',subject+' kaydını seç');
       choice.onchange=()=>{if(choice.checked)marked.add(row.id);else marked.delete(row.id);draw()};
       record.append(choice)
     }
     const launch=button('',()=>{drawer(false);setActive(row.id);open(row)},'history-open');
     if(row.id===active)launch.setAttribute('aria-current','true');
     const summary=row.rapor_ozeti??{};
     const details=node('span',null,'history-meta');
     const stamp=summary.tarih?new Intl.DateTimeFormat('tr-TR',{dateStyle:'medium'}).format(new Date(summary.tarih)):null;
     details.append(node('span',stamp||(row.tamam?'Raporu aç':'Taslak hazırlık')));
     if(summary.fiyat!=null)details.append(node('span',new Intl.NumberFormat('tr-TR',{minimumFractionDigits:2}).format(summary.fiyat)+' TL/'+(summary.birim||'birim')));
     if(summary.ay)details.append(node('span',summary.ay));
     launch.append(node('strong',subject),details);
     const trash=button('',()=>erase({id:[row.id]}),'history-trash');
     trash.setAttribute('aria-label',subject+' kaydını sil');trash.title='Kaydı sil';
     trash.innerHTML='<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 3v7m4-7v7"/></svg>';
     record.append(launch,trash);body.append(record)
   }
   if(!body.childElementCount)body.append(node('p',q?'Aramanızla eşleşen kayıt yok.':'Henüz kayıt yok. Yeni analiz başlatın.','muted'))
 }
 function setActive(id){active=id;draw()}
 async function reload(){
   const id=++generation;
   try{
     const response=await fetch('/api/hazirliklar');
     if(!response.ok)throw Error();
     const records=await response.json();
     if(id!==generation)return;
     rows=records;draw()
   }catch{if(id===generation)body.replaceChildren(node('p','Kayıtlar yüklenemedi.'),button('Tekrar dene',reload))}
 }
 function confirmAll(){
   const dialog=node('dialog',null,'history-dialog');
   const title=node('h2','Tüm kayıtları sil');
   const label=node('label','Onaylamak için TÜM KAYITLARI SİL yazın.');
   const input=node('input');label.append(input);
   const confirm=button('Tüm kayıtları sil',()=>{dialog.close();void erase({tum:true,onay:input.value})},'delete-all');
   confirm.disabled=true;input.oninput=()=>confirm.disabled=input.value!=='TÜM KAYITLARI SİL';
   dialog.append(title,label,confirm,button('Vazgeç',()=>dialog.close()));
   dialog.addEventListener('close',()=>dialog.remove(),{once:true});
   document.body.append(dialog);dialog.showModal();input.focus()
 }
 async function erase(payload){
   const ids=payload.tum?rows.map(r=>r.id):payload.id;
   try{
     const deleted=await api('kayit-sil',payload,10000);
     if(!deleted.adet){await reload();return}
     generation++;rows=rows.filter(r=>!ids.includes(r.id));
     for(const id of ids)marked.delete(id);
     if(ids.includes(active)){active=null;drawer(false);await home()}
     draw();
     const toast=node('div',deleted.adet===1?'Kayıt silindi.':'Kayıtlar silindi.','history-toast');
     const cancel=button('Geri al',async()=>{
       cancel.disabled=true;
       try{
         const result=await api('kayit-geri-al',{grup:deleted.grup},10000);
         toast.textContent=result.adet?'Kayıt geri alındı.':'Geri alma süresi doldu.';
         await reload()
       }catch(error){toast.textContent=error.message}
     });
     toast.append(cancel);notice.append(toast);
     pending.set(deleted.grup,setTimeout(()=>{toast.remove();pending.delete(deleted.grup)},Math.max(0,deleted.bitis*1000-Date.now())))
   }catch(error){
     const toast=node('div',error.message,'history-toast');notice.append(toast);
     setTimeout(()=>toast.remove(),8000)
   }
 }
 return {reload,setActive,draw,replace(records){generation++;rows=records;draw()}}
}

