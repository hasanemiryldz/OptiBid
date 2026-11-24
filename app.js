import '/ayarlar.js';
import {calismaMerkezi} from '/calisma.js';
import {arastirmaEkrani} from '/arastirma.js';
import {historyPanel} from '/gecmis.js';
import {api,sorular,rapor} from '/sunum.js';
import {emsalForm} from '/emsal.js';
import {asistanGoster} from '/karar-v10.js';
import {tumDosyaFiyatlari} from '/dosya-fiyatlari.js';
import {sartnameEkrani} from '/sartname.js';
const app=document.querySelector('#app'), notice=document.querySelector('#notice');
const config=await (await fetch('/catalog.json')).json();
const titles=['İhale türü','Kategori','Kalemler','Teknik özellikler','Teslimat ve süre'];
let d=null, queue=Promise.resolve(), timer, locked=false;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const item=()=>({id:crypto.randomUUID(),ad:null,miktar:null,birim:null,teknik:{}});
const options=(values,v)=>'<option value="">Seçin</option>'+values.map(x=>'<option '+(v===x?'selected':'')+'>'+esc(x)+'</option>').join('');
const button=(s,fn,cl='')=>{const b=document.createElement('button');b.textContent=s;b.className=cl;b.onclick=fn;return b};
function save({quiet=false}={}){
 clearTimeout(timer);
 const doc=d;
 if(!doc)return queue;
 queue=queue.catch(()=>{}).then(async()=>{
   if(locked)throw Object.assign(new Error('Başka bir sekmede daha yeni bir kayıt var.'),{status:409});
   try{doc.rev=await api('hazirliklar',doc,10000)}
   catch(error){if(error.status===409)locked=true;throw error}
   if(!quiet)notice.textContent='Kaydedildi.';
 window.dispatchEvent(new Event('optibid:history'));
 });
 return queue
}
function changed(){
 notice.textContent='Kaydediliyor…';clearTimeout(timer);
 timer=setTimeout(()=>save().catch(e=>notice.textContent=e.message),220)
}
async function saveAndShowReport(fields, nav, partial=false){
 if(nav.dataset.busy)return;
 for(const input of partial?[]:fields.querySelectorAll('input,select')){
   if(input.reportValidity())continue;
   notice.textContent='İşaretli alanı kontrol edin. '+input.validationMessage;
   return
 }
 nav.dataset.busy='true';
 nav.querySelectorAll('button').forEach(b=>b.disabled=true);
 const doc=d;
 const wasComplete=doc.tamam;
 const previousReview=doc.inceleme_durumu;
 doc.tamam=true;
 doc.inceleme_durumu=partial?'kısmi':'tamamlandı';
 notice.textContent='Rapor hazırlanıyor… Yanıtlar kaydediliyor.';
 try{await save({quiet:true})}
 catch(error){
   doc.tamam=wasComplete;
   doc.inceleme_durumu=previousReview;
   delete nav.dataset.busy;
   nav.querySelectorAll('button').forEach(b=>b.disabled=false);
   notice.textContent=error.status===409
     ?'Bu hazırlık başka bir sekmede güncellendi. Rapor için güncel hazırlığı açın.'
     :'Yanıtlar kaydedilemedi. '+error.message;
   const retry=error.status===409
     ?button('Güncel hazırlığı aç',home)
     :button('Tekrar dene',()=>saveAndShowReport(fields,nav,partial));
   notice.append(' ',retry);
   return
 }
 notice.textContent='';
 await rapor(doc,app,draw,home)
}
const emptyDoc=()=>({id:crypto.randomUUID(),rev:0,sema_surumu:'1',adim:0,tamam:false,ihale_turu:null,kategori:[],kalemler:[item()],teknik_sartlar:[],teslimat:{},teklifler:[],ek_bilgiler:{},ornek_veri:false});
function startManual(){
 d=emptyDoc();
 locked=false;draw();changed()
}
function newAnalysis(){
 notice.textContent='';
 sartnameEkrani(app,config,{manual:startManual,home,accept:async(sha,items,general,direct)=>{
  const doc=emptyDoc();
  const selected=items.find(x=>x.kategori)?.kategori;
  if(!direct&&items.some(x=>!x.kategori))throw Error('Teknik sorular için her kalemin kategorisini seçin veya eldeki bilgilerle analiz edin.');
  if(selected){const [kind,...path]=selected;doc.ihale_turu=kind;doc.kategori=path}
  doc.kalemler=items.map(row=>{
   const values=row.alanlar;
   const amount=values.miktar?.replace(',','.')??null;
   if(amount!==null&&(!/^\d{1,15}(\.\d{1,6})?$/.test(amount)||!(Number(amount)>0)))throw Error('Miktarı pozitif sayı olarak girin.');
   const classification=row.kategori?{ihale_turu:row.kategori[0],kategori:row.kategori.slice(1)}:{kategori_belirsiz:true};
   return {...item(),...classification,ad:values.ad,miktar:amount,birim:values.birim,
    kaynak_kalem:row.kimlik,teknik:Object.fromEntries(Object.entries(values).filter(([key,value])=>key.startsWith('teknik:')&&value).map(([key,value])=>[key.slice(7),value]))};
  });
  if(general.sure&&!/^\d{1,4}$/.test(general.sure))throw Error('Teslim süresini gün sayısı olarak girin.');
  for(const key of ['yer','sure','gun_turu','baslangic','sure_kosulu'])if(general[key])doc.teslimat[key]=general[key];
  if(general.ikn)doc.ek_bilgiler.ikn=general.ikn;
  if(['hariç','dahil'].includes(general.kdv))doc.ek_bilgiler.kdv_esasi=general.kdv;
  doc.ek_bilgiler.sartname={sha,genel:general};
  const missing=doc.kalemler.flatMap(k=>[k.ad,k.miktar,k.birim]).findIndex(value=>!value);
  doc.adim=!selected?0:missing>=0?2:3;
  if(missing>=0)doc.alt_sorular={2:missing};
  if(direct){doc.tamam=true;doc.inceleme_durumu='tamamlandı'}
  d=doc;locked=false;
  await save({quiet:true});
  if(direct)await rapor(doc,app,draw,home);else draw();
 }});
}
function openRecord(record){
 clearTimeout(timer);locked=false;notice.textContent='';d=record;
 if(record.tamam)void rapor(d,app,draw,home);else draw()
}
const history=historyPanel({open:openRecord,newAnalysis,home,api});
window.addEventListener('optibid:history',()=>void history.reload());
async function home(){
 clearTimeout(timer);d=null;locked=false;notice.textContent='';history.setActive(null);
 try{
  const response=await fetch('/api/hazirliklar');if(!response.ok)throw Error('Kayıtlar alınamadı.');
  const rows=await response.json();history.replace(rows);
  void calismaMerkezi({app,rows,config,onNew:newAnalysis,onPrices:()=>tumDosyaFiyatlari(app,home),
   onImport:()=>emsalForm(config,home,app),onResearch:()=>arastirmaEkrani(app,home,api),
   onExample:async id=>{
    const response=await fetch('/api/ornek/'+encodeURIComponent(id));if(!response.ok)throw Error('Örnek yüklenemedi.');
    d=await response.json();d.id=crypto.randomUUID();d.rev=0;
    d.teklifler??=[];
    d.ek_bilgiler??={};if(d.ek_bilgiler.demo_kdv_esasi)d.ek_bilgiler.kdv_esasi=d.ek_bilgiler.demo_kdv_esasi;
    if(d.ek_bilgiler.demo_sorusu)delete d.kalemler[0].teknik[d.ek_bilgiler.demo_sorusu];
    for(const kalem of d.kalemler){const old=kalem.id;kalem.id=crypto.randomUUID();
     for(const teklif of d.teklifler)for(const line of teklif.satirlar??[])if(line.kalem_id===old)line.kalem_id=kalem.id;
    }
    locked=false;draw();await save();
   }});
  asistanGoster(null,null,null,api);
 }catch(error){notice.textContent=error.message;app.replaceChildren(button('Tekrar dene',home))}
}
function draw(){
 app.className='v6-wizard';history.setActive(d.id);
 const step=d.adim;app.innerHTML='<ol class="v10-steps">'+titles.map((label,index)=>'<li'+(step===index?' aria-current="step"':'')+'>'+esc(label)+'</li>').join('')+'</ol><section><h1>'+titles[step]+'</h1><div id="fields"></div><nav></nav></section>';
 const f=app.querySelector('#fields'),nav=app.querySelector('nav');
 const cursor=d.alt_sorular??={};
 const index=cursor[step]??0;
 const max=step===1?2:step===2?3*d.kalemler.length:step===4?4:1;
 if(max>1){const progress=document.createElement('p');progress.className='wizard-substep';
  progress.textContent='Soru '+(index+1)+' / '+max;f.before(progress)}
 asistanGoster(null,null,null,api,null,{adim:step,taslak:d});
 const exportButton=button('Standart JSON indir',async()=>{
  try{await save();const link=document.createElement('a');link.href='/api/standart/'+d.id;link.download='OptiBid_Standart.json';link.click()}catch(e){notice.textContent=e.message}
 });exportButton.className='v20-json-export';app.append(exportButton);
 if(d.ornek_veri){
   const details=document.createElement('details');
   const summary=document.createElement('summary');summary.textContent='Örnek veri · İlk senaryonun firma teklifleri';details.append(summary);
   const note=document.createElement('p');note.textContent=d.ek_bilgiler.varsayim;details.append(note);
   for(const teklif of d.teklifler){
     const row=document.createElement('p'),line=teklif.satirlar[0];
     row.textContent=teklif.firma_adi+' · '+line.birim_fiyat+' TL/'+(line.birim??'birim')+' (örnek fiyat) · '+Object.entries(line.teknik).map(([k,v])=>k+' '+v).join(', ')+' · '+teklif.teslim_suresi+' takvim günü';
     details.append(row);
   }
   f.before(details);
 }
 function field(parent,label,value,choices,set,required=false,numeric=false){const l=document.createElement('label');l.textContent=label;const el=document.createElement(choices?'select':'input');
 if(choices)el.innerHTML=options(choices,value);else{el.type=numeric?'number':'text';if(numeric){el.min='0.0000000001';el.step='any'}el.value=value??''}el.required=required;l.append(el);parent.append(l);
 el.addEventListener(choices?'change':'input',()=>{set(el.value||null);d.tamam=false;changed()});return el}
 if(step===0){
  const choose=field(f,'İhale türü',d.ihale_turu,Object.keys(config.turler),v=>{d.ihale_turu=v;d.kategori=[];cursor[1]=0;cursor[2]=0;d.kalemler.forEach(k=>{k.teknik={};delete k.bilinmeyen;delete k.cevaplar})},true);
  const choices=document.createElement('div');choices.className='v20-type-choices';
  choose.required=false;choose.parentElement.hidden=true;
  for(const kind of Object.keys(config.turler)){
   const b=button(kind,()=>{if(choose.value===kind)return;choose.value=kind;choose.dispatchEvent(new Event('change'));for(const child of choices.children)child.setAttribute('aria-pressed',String(child===b))});
   b.setAttribute('aria-pressed',String(kind===d.ihale_turu));choices.append(b)
  }f.append(choices);
 }
 const bar=document.createElement('progress');bar.className='v20-step-progress';bar.max=titles.length;bar.value=step+1;bar.setAttribute('aria-label','Hazırlık ilerlemesi');app.querySelector('section').prepend(bar);
 if(step===1){
  const cats=config.turler[d.ihale_turu]??{};
  const reset=()=>d.kalemler.forEach(k=>{k.teknik={};delete k.bilinmeyen;delete k.cevaplar});
  if(index===0)field(f,'Ana kategori',d.kategori[0],Object.keys(cats),v=>{d.kategori=[v];reset()},true);
  else field(f,'Alt kategori',d.kategori[1],Object.keys(cats[d.kategori[0]]??{}),v=>{
   d.kategori[1]=v;
   if(d.kalemler.length===1&&v)delete d.kalemler[0].kategori_belirsiz;
   reset()
  },true)
 }
 if(step===2){
  const position=Math.floor(index/3),current=d.kalemler[position],slot=index%3;
  if(d.kalemler.length>1){const caption=document.createElement('p');caption.textContent='Kalem '+(position+1);f.append(caption)}
  if(slot===0){
   field(f,'Kalem adı',current.ad,null,v=>current.ad=v,true);
   const options=new Map(Object.entries(config.turler).flatMap(([kind,types])=>
    Object.entries(types).flatMap(([main,children])=>Object.keys(children).map(sub=>
     [[kind,main,sub].join(' / '),[kind,main,sub]]))));
   const base=[d.ihale_turu,...d.kategori].join(' / ');
   const assigned=current.kategori_belirsiz?'':current.kategori?[current.ihale_turu,...current.kategori].join(' / '):base;
   const alternate=document.createElement('details'),caption=document.createElement('summary');
   caption.textContent='Kalemin kategorisi';alternate.append(caption);f.append(alternate);
   field(alternate,'Bu kalemin kategorisi',assigned,[...options.keys()],v=>{
    if(!options.has(v))return;
    const [kind,...category]=options.get(v);
    delete current.kategori_belirsiz;
    if(v===base){delete current.ihale_turu;delete current.kategori}
    else {current.ihale_turu=kind;current.kategori=category}
    current.teknik={};delete current.bilinmeyen;delete current.cevaplar;
   },true);
  }
  if(slot===1)field(f,'Miktar',current.miktar,null,v=>current.miktar=v,true,true);
  if(slot===2)field(f,'Birim',current.birim,config.birimler,v=>current.birim=v,true);
  if(d.kalemler.length>1)f.append(button('Kalemi kaldır',()=>{
   d.kalemler.splice(position,1);cursor[2]=3*Math.min(position,d.kalemler.length-1);d.tamam=false;draw();changed()
  }));
  if(index===max-1)f.append(button('Kalem ekle',()=>{
   if(!f.querySelector('select').reportValidity())return;
   cursor[2]=max;d.kalemler.push(item());d.tamam=false;draw();changed()
  }))
 }
 if(step===3){
   if(d.ek_bilgiler?.sartname)app.append(button('Eldeki bilgilerle raporu aç',()=>void saveAndShowReport(f,nav,true)));
   sorular(d,f,nav,async()=>{d.adim=4;await save();draw()},async()=>{d.adim=2;await save();draw()},async()=>{await save();await home()},save);
   return;
 }
 if(step===4){
 const t=d.teslimat;
 if(index===0)field(f,'Teslim veya işin yapılacağı yer',t.yer,null,v=>t.yer=v);
 if(index===1){
  field(f,'Süre',t.sure,null,v=>t.sure=v,false,true);
  field(f,'Süre koşulu',({en_gec:'En geç',en_az:'En az',tam:'Belirtilen gün'})[t.sure_kosulu]??'',
   ['Belirtilen gün','En geç','En az'],v=>{t.sure_kosulu=({'En geç':'en_gec','En az':'en_az','Belirtilen gün':'tam'})[v]??null;});
 }
 if(index===2)field(f,'Gün türü',t.gun_turu,['İş günü','Takvim günü'],v=>t.gun_turu=v);
 if(index===3){
 field(f,'Sürenin başlangıcı',t.baslangic,null,v=>t.baslangic=v);
 const extra=d.ek_bilgiler??={};
 const optional=document.createElement('details'),optionalCaption=document.createElement('summary');
 optionalCaption.textContent='Hedef İKN ve KDV esası · isteğe bağlı';optional.append(optionalCaption);f.append(optional);
 field(optional,'Hedef İKN (varsa)',extra.ikn,null,v=>extra.ikn=v);
 field(optional,'Emsaller için KDV esası',extra.kdv_esasi??'belirsiz',['belirsiz','hariç','dahil'],v=>extra.kdv_esasi=v);
 const offers=document.createElement('details'),caption=document.createElement('summary');
 caption.textContent='Firma teklifleri · isteğe bağlı';offers.append(caption);
 const entries=document.createElement('div');offers.append(entries);f.append(offers);
 function drawOffers(){
  entries.replaceChildren();
  for(const [index,offer] of d.teklifler.entries()){
   const box=document.createElement('fieldset'),title=document.createElement('legend');
   title.textContent='Teklif '+(index+1);box.append(title);entries.append(box);
   field(box,'Firma adı',offer.firma_adi,null,v=>offer.firma_adi=v);
   field(box,'Para birimi',offer.para_birimi,['TRY','EUR','USD'],v=>offer.para_birimi=v);
   field(box,'Teklifin KDV esası',offer.kdv_esasi,['hariç','dahil'],v=>offer.kdv_esasi=v);
   field(box,'Teklif teslim süresi',offer.teslim_suresi,null,v=>offer.teslim_suresi=v,false,true);
   field(box,'Teklif gün türü',offer.gun_turu,['İş günü','Takvim günü'],v=>offer.gun_turu=v);
   field(box,'Teklif süresinin başlangıcı',offer.baslangic,null,v=>offer.baslangic=v);
   for(const item of d.kalemler){
    let line=offer.satirlar.find(x=>x.kalem_id===item.id);
    if(!line){line={kalem_id:item.id,teknik:{}};offer.satirlar.push(line)}
    const details=document.createElement('details'),name=document.createElement('summary');
    name.textContent=item.ad;details.append(name);box.append(details);
    field(details,'Teklif birimi',line.birim,config.birimler,v=>line.birim=v);
    field(details,'Teklif edilen miktar',line.miktar,null,v=>line.miktar=v,false,true);
    field(details,'Teklif birim fiyatı',line.birim_fiyat,null,v=>line.birim_fiyat=v,false,true);
    field(details,'Teknik kapsam ve teslim koşulları',line.kapsam_onayi?'Belirtildi ve eşleşiyor':line.kapsam_uyumsuz?'Uyumsuz':'Belirtilmedi',
      ['Belirtildi ve eşleşiyor','Uyumsuz','Belirtilmedi'],v=>{line.kapsam_onayi=v==='Belirtildi ve eşleşiyor';line.kapsam_uyumsuz=v==='Uyumsuz'});
   }
   box.append(button('Teklifi kaldır',()=>{d.teklifler.splice(index,1);d.tamam=false;changed();drawOffers()}))
  }
  if(d.teklifler.length<4)entries.append(button('Firma teklifi ekle',()=>{
   d.teklifler.push({firma_adi:null,satirlar:[]});d.tamam=false;changed();drawOffers()
  }))
 }
 drawOffers()}}
 if(step)nav.append(button('Geri',()=>{
   if(index>0)cursor[step]=index-1;
   else d.adim--;
   draw();changed()
 }));
 const ready=step===4&&index===max-1;
 const advance=button(ready?'Fiyat tahminini ve raporu gör':'Devam',()=>{
   if(step===0&&!d.ihale_turu){notice.textContent='Devam etmek için bir ihale türü seçin.';return}
   if(ready){void saveAndShowReport(f,nav);return}
   for(const input of f.querySelectorAll('input,select')){
     if(input.reportValidity())continue;
     notice.textContent='İşaretli alanı kontrol edin. '+input.validationMessage;
     return
   }
   if(index<max-1)cursor[step]=index+1;
   else d.adim++;
   draw();changed()
 },'primary');
 nav.append(advance,button('Kaydedip çık',async()=>{
   try{await save();await home()}catch(error){notice.textContent=error.message}
 }))
}
await home().catch(error=>notice.textContent='OptiBid yüklenemedi. Sayfayı yenileyin. '+error.message);
