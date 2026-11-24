import {api} from '/sunum.js';

const trigger=document.querySelector('#open-settings');
const dialog=document.querySelector('#settings-dialog');
const form=dialog.querySelector('form');
const model=form.elements.model;
const save=form.querySelector('.primary');
const notice=dialog.querySelector('[role=status]');

trigger.onclick=async()=>{
 dialog.showModal();
 model.replaceChildren();
 save.disabled=true;
 notice.textContent='Yerel Ollama kontrol ediliyor…';
 try{
  const res=await fetch('/api/ayarlar');
  if(!res.ok)throw Error();
  const settings=await res.json();
  for(const row of settings.modeller){
   const option=new Option(row.ad+(row.kurulu===false?' · kurulu değil':''),row.ad,false,row.ad===settings.secili);
   option.disabled=row.kurulu===false&&row.ad!==settings.secili;
   model.add(option);
  }
  const web=await fetch('/api/arastirma-durumu').then(r=>r.json()).catch(()=>null);
  notice.textContent='Ollama '+settings.durum+'. İnternet araması: '+(web?.saglayici??'durum alınamadı')+'.';
  save.disabled=false;
 }catch{notice.textContent='Ayarlar yüklenemedi. Pencereyi yeniden açıp tekrar deneyin.'}
};
form.onsubmit=async event=>{
 event.preventDefault();
 save.disabled=true;
 try{
  const result=await api('ayarlar',{model:model.value},10000);
  notice.textContent='Seçili model kaydedildi · '+result.secili;
 }catch(error){notice.textContent=error.message}
 finally{save.disabled=false}
};
dialog.querySelector('[data-close]').onclick=()=>dialog.close();
