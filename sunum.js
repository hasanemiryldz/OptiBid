import {dosyaRaporu} from '/rapor.js';
export async function api(path,doc,timeout=95000,headers={}){
 const controller=new AbortController();
 const timer=setTimeout(()=>controller.abort(),timeout);
 try{
   const res=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json',...headers},
     body:JSON.stringify(doc),signal:controller.signal});
   const data=await res.json().catch(()=>null);
   if(!res.ok)throw Object.assign(new Error(data?.hata||'Sunucu isteği tamamlayamadı.'),{status:res.status});
   if(data===null)throw new Error('Sunucudan geçerli yanıt alınamadı.');
   return data
 }catch(error){
   if(error.name==='AbortError')throw new Error('İşlem zaman aşımına uğradı. Tekrar deneyin.');
   if(error instanceof TypeError)throw new Error('OptiBid sunucusuna ulaşılamadı.');
   throw error
 }finally{clearTimeout(timer)}
}
function el(tag,text){const n=document.createElement(tag);n.textContent=text??'';return n}
function btn(parent,text,action){const b=el('button',text);b.type='button';b.onclick=action;parent.append(b);return b}
export async function sorular(d,f,nav,next,back,exit,save){
 f.replaceChildren(el('p','Sıradaki soru hazırlanıyor…'));nav.replaceChildren();
 btn(nav,'Geri',back);btn(nav,'Kaydedip çık',exit);
 let q;try{q=await api('soru',d,55000)}catch(error){f.replaceChildren(el('p','Soru alınamadı. '+error.message));btn(f,'Yeniden dene',()=>sorular(d,f,nav,next,back,exit,save));return}
 if(!f.isConnected)return;
 f.replaceChildren();
 if(q.bitti){f.append(el('p','Teknik profil hazır.'));
 for(const k of d.kalemler){f.append(el('h3',k.ad));for(const [a,v] of Object.entries(k.teknik)){btn(f,a+' · '+(v??'Bilinmiyor'),()=>{delete k.teknik[a];k.bilinmeyen=(k.bilinmeyen||[]).filter(x=>x!==a);save();sorular(d,f,nav,next,back,exit,save)})}}
 const advance=btn(nav,'Devam',async()=>{
   advance.disabled=true;
   try{await next()}catch(error){d.adim=3;f.append(el('p',error.message));advance.disabled=false}
 });return}
 const k=d.kalemler.find(k=>k.id===q.kalem_id);
 f.append(el('small',k.ad+' · Soru '+q.soru_sira+' / '+q.soru_toplam+' · '+q.yontem));
 const l=el('label',q.soru+(q.unit_code?' ('+q.unit_code+')':'')),i=el('input');
 if(q.secenekler?.length){
  const options=el('div');options.className='v10-options';
  i.type='hidden';
  for(const value of q.secenekler)btn(options,value,()=>{
   i.value=value;
   for(const child of options.children)child.setAttribute('aria-pressed',String(child.textContent===value))
  }).setAttribute('aria-pressed','false');
  f.append(l,options);l.append(i)
 }else{
  i.type=q.input_type;i.required=true;if(i.type==='number'){i.step='any';i.min='0.0000000001'}
  l.append(i);f.append(l)
 }
 let submitting=false;
 async function answer(skip){if(submitting)return;if(!skip&&!i.reportValidity())return;const raw=skip?null:i.value.trim();if(!skip&&!raw)return;
 const val=raw===null?null:q.input_type==='number'?raw.replace(/^0+(?=\d)/,'').replace(/(\.\d*?)0+$/,'$1').replace(/\.$/,''):raw;
 k.teknik[q.field_key]=val;if(skip)(k.bilinmeyen??=[]).push(q.field_key);
 (k.cevaplar??={})[q.field_key]={ham:raw,deger:val,birim:q.unit_code,kaynak:'kullanıcı',onay:true,surum:q.profil_surumu};
 submitting=true;
 try{await save();await sorular(d,f,nav,next,back,exit,save)}
 catch(error){f.append(el('p',error.message));submitting=false}
 }
 if(q.bilinmiyor)btn(nav,'Bilinmiyor',()=>answer(true));
 btn(nav,'Yanıtı kaydet',()=>answer(false))
}
export function rapor(d,app,edit,home){
 return dosyaRaporu(d,app,edit,home,api)
}
