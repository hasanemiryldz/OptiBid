import {arastirmaSonucu,kaynakLinki} from '/arastirma.js';
const make=(tag,text,cls)=>{const el=document.createElement(tag);el.textContent=text??'';if(cls)el.className=cls;return el};
const format=value=>{
 if(value==null)return '—';
 const [whole,fraction='']=String(value).split('.');
 return whole.replace(/\B(?=(\d{3})+(?!\d))/g,'.')+','+fraction.padEnd(2,'0').slice(0,2)
};
const fields={maliyet:'Toplam maliyet',basabas:'Başabaş / birim',birim_teklif:'Hedef teklif / birim',satis:'Toplam satış',kar:'Kâr',kar_maliyet_yuzde:'Maliyete göre kâr (%)',ciro_marji:'Ciro marjı (%)'};
const labels={SUPPORTED:'Dayanaklı yanıt',PARTIAL:'Kapsamı sınırlı',UNAVAILABLE:'Bilgiye ulaşılamadı',CONFLICT:'Hesap uyuşmazlığı',NEEDS_CLARIFICATION:'Bilgi gerekiyor'};

let active=null;
const mobile=matchMedia('(max-width: 999px)');
function shellState(panel){
 const open=panel&&!panel.hidden;
 document.body.classList.toggle('assistant-split',Boolean(open&&mobile.matches));
}
mobile.addEventListener('change',()=>shellState(active?.panel));
if(window.visualViewport){
 const resize=()=>document.documentElement.style.setProperty('--assistant-vh',window.visualViewport.height+'px');
 window.visualViewport.addEventListener('resize',resize);
 resize();
}
export function asistanGoster(doc,report,when,api,printArea,options={}){
 const host=document.querySelector('#assistant-host');
 const owner=doc?.id??options.taslak?.id??null;
 const mode=doc?'rapor':'taslak';
 const key=[owner,mode,doc?.rev,when].join('|');
 if(active?.key===key){
  active.update(options);
  return;
 }
 const next=kararPanel(doc,report,when,api,printArea,options);
 const carry=active?.owner!=null&&active.owner===owner;
 if(carry)next.carry(active.draft(),!active.panel.hidden,
  active.mode==='taslak'&&mode==='rapor'?active.history():[]);
 host.replaceChildren(next.dock);
 active={...next,owner,key,mode};
 shellState(next.panel);
}

function kararPanel(doc,report,when,api,printArea,{adim,taslak}={}){
 const dock=make('div',null,'v10-dock'),panel=make('section',null,'v10-chat');
 const toggle=button('OptiBid AI · Asistana sor',()=>show(panel.hidden),'v10-launch');
 toggle.setAttribute('aria-controls','optibid-ai-panel');
 panel.id='optibid-ai-panel';panel.setAttribute('aria-label','OptiBid AI sohbeti');
 const header=make('header',null,'v10-chat-top'),title=make('div'),status=make('small','Yerel Ollama · Mesajla bağlantı kurulur');
 title.append(make('h2','OptiBid AI'),status);
 header.append(title,button('Küçült',()=>show(false)));
 const messages=make('div',null,'v10-messages');messages.setAttribute('role','log');messages.setAttribute('aria-live','polite');
 const form=make('form'),ask=make('textarea');ask.rows=2;ask.maxLength=600;ask.required=true;ask.setAttribute('aria-label',doc?'Rapor sorusu':'Uygulama sorusu');
 ask.placeholder=doc?'Bu fiyat nasıl hesaplandı?':'Bu alanı nasıl doldurmalıyım?';
 const send=make('button','Gönder','primary'),formStatus=make('small');formStatus.setAttribute('role','status');
 const saved=make('details',null,'v10-saved');saved.append(make('summary','Senaryolar'));
 form.append(ask,send,formStatus);const chips=make('div',null,'v20-chat-chips');
 for(const caption of ['Benzer ihale bul','Bu raporu açıkla','Nelere dikkat etmeliyim?'])chips.append(button(caption,()=>{ask.value=caption;form.requestSubmit()}));
 panel.append(header,chips,messages,form);if(doc)panel.append(saved);dock.append(panel,toggle);
 const liveContext=()=>doc?{id:doc.id,rev:doc.rev,tarih:when}:{adim,baglam:taslak?{
  id:taslak.id,rev:taslak.rev,tamam:taslak.tamam,ihale_turu:taslak.ihale_turu,kategori:taslak.kategori,
  kalemler:taslak.kalemler,teslimat:taslak.teslimat,sartname:taslak.ek_bilgiler?.sartname??null}:null};
 const id=doc?'optibid.chat.v10:'+doc.id+':'+doc.rev+':'+when:taslak?.id?'optibid.chat.taslak:'+taslak.id:'optibid.chat.yardim';
 let state={draft:'',messages:[],open:false};
 try{state=JSON.parse(localStorage.getItem(id)??sessionStorage.getItem(id))??state}catch{}
 ask.value=state.draft??'';
 const scenarios=[],selected=new Set();
 let busy=false;
 function store(){
  state.draft=ask.value;
  try{localStorage.setItem(id,JSON.stringify({...state,messages:state.messages.slice(-30)}))}catch{}
 }
 function button(text,handler,cls){
  const b=make('button',text,cls);b.type='button';b.onclick=handler;return b
 }
 function show(open,focus=true){
  state.open=open;panel.hidden=!open;toggle.setAttribute('aria-expanded',String(open));
  if(dock.isConnected)shellState(panel);
  store();if(focus)(open?ask:toggle).focus()
 }
 show(state.open,false);
 ask.oninput=store;
 panel.onkeydown=e=>{if(e.key==='Escape'){e.stopPropagation();show(false)}};
 ask.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();form.requestSubmit()}};
 function drawSaved(){
  saved.replaceChildren(make('summary','Senaryolar · '+scenarios.length));
  if(scenarios.length){
   const t=make('table'),head=t.createTHead().insertRow(),body=t.createTBody();
   for(const h of ['Teklif / birim','Kâr','Rapor eki'])head.append(make('th',h));
   for(const r of scenarios){
    const line=body.insertRow();
    line.insertCell().textContent=format(r.hesap.birim_teklif);
    line.insertCell().textContent=format(r.hesap.kar);
    line.insertCell().append(button(selected.has(r.id)?'Çıkar':'PDF’e ekle',()=>{
     if(selected.has(r.id))selected.delete(r.id);else selected.add(r.id);drawSaved()
    }))
   }
   saved.append(t)
  }
  printArea.replaceChildren();
  printArea.dataset.ekler=JSON.stringify([...selected]);
  if(selected.size)printArea.append(make('h2','Seçilen senaryolar'));
  for(const r of scenarios.filter(r=>selected.has(r.id))){
   printArea.append(make('p','Teklif '+format(r.hesap.birim_teklif)+' TL/'+report.birim+' · Satış '+format(r.hesap.satis)+' TL · Kâr '+format(r.hesap.kar)+' TL'))
  }
 }
 function render(row){
  const item=make('article',null,row.user?'v10-user':'v10-reply');
  if(row.user)item.append(make('p',row.user));
  else{
   const r=row.answer;
   status.textContent=r.ollama_izi?.actual_model?'Ollama · '+r.ollama_izi.actual_model:
    r.mod==='yerel'?'Yerel rehber':r.mod==='araç'?'Hesap ve kaynaklar':r.mod==='araştırma'?'Araştırma · Yerel havuz ve internet':'OptiBid AI';
   item.append(make('small',labels[r.answer_status]??''),make('p',r.metin));
   if(r.yerel_sonuclar){const local=r.yerel_sonuclar;
    item.append(make('p','Yerel fiyat taraması: '+local.taranan+' kayıt · '+local.eslesen+' ilgili eşleşme.'));
    const fold=make('details');fold.append(make('summary','Yerel eşleşmeler · dosya beyanları'));
    for(const row of local.kayitlar)fold.append(kaynakLinki(row.ikn+' · '+row.ad,row.kaynak),make('br'));
    item.append(fold)
   }
   if(r.arastirma)item.append(arastirmaSonucu(r.arastirma,api));
   if(r.olaylar?.length){const fold=make('details',null,'v20-agent-trace'),list=make('ul');fold.append(make('summary','Teknik ayrıntılar'));
    for(const event of r.olaylar)list.append(make('li',event.arac+' · '+event.durum));fold.append(list);item.append(fold)
   }
   if(r.uyari)item.append(make('small',r.uyari));
   if(r.kaynaklar?.length&&!r.arastirma){const fold=make('details');fold.append(make('summary','Yanıt bağlamı'));
    for(const source of r.kaynaklar)fold.append(make('p',source.id+' · '+source.baslik));item.append(fold)
   }
   if(r.claims?.length){
    const fold=make('details'),list=make('ul');fold.append(make('summary','İddialar ve dayanakları'));
    const origin={kaynak_bulgusu:'Kaynak bulgusu',kullanici_beyani:'Kullanıcı beyanı',
     arac_hesabi:'Araç hesabı',gelistirici_onerisi:'Geliştirici önerisi',bilinmiyor:'Bilinmiyor'};
    for(const claim of r.claims){
     if(claim.tur){
      list.append(make('li',[origin[claim.tur],claim.metin,claim.konum,claim.belge_sha256].filter(Boolean).join(' · ')));
      continue;
     }
     const value=['sozlesme_bedeli','birim_fiyat'].includes(claim.field)?format(claim.deger)+' '+claim.birim:claim.deger;
     const line=make('li',claim.tarih+' · '+value+' · ');
     if(claim.source_ref&&claim.ikn){
      const link=make('a',claim.ikn);link.href=claim.source_ref;link.target='_blank';link.rel='noopener';
      line.append(link)
     }
     list.append(line)
    }
    fold.append(list);item.append(fold)
   }
   if(r.kapsam){
    const k=r.kapsam;
    item.append(make('p','İncelenen kimlik '+k.benzersiz+' · EKAP dayanaklı '+k.ekap+' · Bekleyen '+k.bekliyor+' · Karantina '+k.karantina));
    if(k.kullanilan!=null)item.append(make('p','Kategori adayı '+k.aday+' · Doğrudan emsal '+k.kullanilan+' · Koşullu fiyat referansı '+(k.kosullu_referans??0)));
    if(k.tum_dosya_fiyati!=null)item.append(make('p','Dosyalarda işlenen fiyat '+k.tum_dosya_fiyati+' · Seçilen kategoride kullanılan '+k.dosya_fiyati));
   }
   if(r.tani){
    const details=make('details'),list=make('ul');
    details.append(make('summary','Veri sürümü ve dışlama nedenleri'));
    list.append(make('li','Veri sürümü '+r.tani.veri_surumu));
    if(r.tani.guncel_veri_surumu)list.append(make('li','Güncel havuz '+r.tani.guncel_veri_surumu));
    if(r.tani.filtreler)list.append(make('li',[r.tani.filtreler.tur,...r.tani.filtreler.kategori,r.tani.filtreler.kdv,r.tani.filtreler.donem].filter(Boolean).join(' · ')));
    const groups=Object.entries(r.tani.gruplar??{});
    if(groups.length)list.append(make('li',groups.map(([key,num])=>key+' '+num).join(' · ')));
    for(const [reason,count] of Object.entries(r.tani.dislamalar??{}))list.append(make('li',count+' kayıt · '+reason));
    for(const error of Object.values(r.tani.hatalar??{}))list.append(make('li',error));
    details.append(list);item.append(details,make('small',(r.iz.mod==='yerel'?'Yerel hesap · ':'MCP · ')+r.iz.arac));
   }
   if(r.endeks)item.append(make('p',r.endeks.ad+' · Son kayıtlı ay '+r.endeks.son_ay));
   for(const calculation of r.calculations??[]){
    const v=calculation.sonuc;
    if(calculation.calc_ref==='senaryo.birim.v1')
     item.append(make('p',v.miktar+' '+v.birim),make('small','MCP · '+r.iz.arac));
    if(calculation.calc_ref==='senaryo.endeks.v1')
     item.append(make('p',format(v.tutar_endeksli)+' TL · '+v.kaynak_ay+' → '+v.hedef_ay),make('small','MCP · '+r.iz.arac));
   }
   if(r.hesap){
    const t=make('dl');
    for(const [key,label] of Object.entries(fields))t.append(make('dt',label),make('dd',format(r.hesap[key])));
    item.append(t,make('small','MCP · '+r.iz.arac));
    if(r.eksik.length)item.append(make('p','Girilmeyen giderler · '+r.eksik.map(k=>k==='diger'?'diğer gider':k).join(', ')));
    const save=button('Senaryoyu kaydet',async()=>{
     save.disabled=true;
     try{
      const value=await api('senaryo-kaydet',{...liveContext(),girdiler:r.girdiler},10000);
      if(!dock.isConnected)return;
      scenarios.push(value);drawSaved();saved.open=true;save.textContent='Kaydedildi'
     }catch(error){save.disabled=false;formStatus.textContent=error.message}
    });
    item.append(save)
   }
  }
  messages.append(item)
 }
 function previousRows(){
  if(!state.previous?.length)return;
  const section=make('details'),body=make('ul');
  section.append(make('summary','Hazırlık sırasındaki sohbet'));
  for(const row of state.previous)body.append(make('li',row.user??row.answer?.metin??''));
  section.append(body);messages.append(section);
 }
 previousRows();
 for(const row of state.messages)render(row);
 if(!state.messages.length)messages.append(make('p',doc?'Rapordaki dayanakları sorun veya giderlerinizle teklif hesabı yapın.':'Kategori, şartlar ve veri havuzunu sorun; benzer ihaleler bulmamı isteyin.','muted'));
 if(doc)fetch('/api/rapor-senaryolari/'+encodeURIComponent(doc.id)).then(async response=>{
  if(!response.ok||!dock.isConnected)return;
  const rows=await response.json();
  if(rows.tarih===when){
   for(const r of rows.senaryolar)if(!scenarios.some(x=>x.id===r.id))scenarios.push(r);
   drawSaved()
  }
 }).catch(()=>{});
 form.onsubmit=async event=>{
  event.preventDefault();if(busy)return;
  const raw=ask.value,question=raw.trim();if(!question)return;
  busy=true;send.disabled=true;formStatus.textContent='İstek işleniyor…';
  try{
   const response=await api(doc?'karar-asistani':'yardim',{...liveContext(),soru:question,gecmis:state.messages.slice(-8)},115000);
   if(!dock.isConnected)return;
   if(doc&&(response.report_id!==doc.id||response.input_revision!==doc.rev||response.data_version!==report.veri_surumu))
    throw Error('Bu yanıt başka bir rapor sürümüne ait.');
   if(!state.messages.length){messages.replaceChildren();previousRows()}
   const entries=[{user:question},{answer:response}];
   for(const row of entries){state.messages.push(row);render(row)}
   if(ask.value===raw&&response.answer_status!=='UNAVAILABLE'&&response.answer_status!=='CONFLICT')ask.value='';
   formStatus.textContent='';store();messages.scrollTop=messages.scrollHeight
  }catch(error){
   if(!dock.isConnected)return;
   formStatus.textContent='Mesaj korundu. '+error.message;
   formStatus.append(' ',button('Tekrar dene',()=>form.requestSubmit()))
  }finally{busy=false;send.disabled=false}
 };
 return {dock,panel,draft:()=>ask.value,history:()=>state.messages.slice(-30),carry:(draft,open,previous)=>{
  if(draft&&!ask.value)ask.value=draft;
  if(previous.length&&!state.previous?.length){state.previous=previous;previousRows();store()}
  if(open)show(true,false);
 },update:options=>{adim=options.adim;taslak=options.taslak}}
}
