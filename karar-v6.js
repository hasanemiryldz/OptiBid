const node=(tag,text)=>{const el=document.createElement(tag);el.textContent=text??'';return el};
const format=value=>value==null?'—':Number(value).toLocaleString('tr-TR',{minimumFractionDigits:2,maximumFractionDigits:2});
const fields={maliyet:'Toplam maliyet',basabas:'Başabaş / birim',birim_teklif:'Hedef teklif / birim',satis:'Toplam satış',kar:'Kâr',ciro_marji:'Ciro marjı (%)'};

export function kararPanel(doc,report,when,api,printArea){
 const box=node('details');box.className='v6-assistant';box.open=true;
 box.append(node('summary','OptiBid Karar Asistanı'));
 const form=node('form'),ask=node('textarea');ask.rows=4;ask.maxLength=600;ask.required=true;ask.setAttribute('aria-label','Rapor sorusu');
 ask.placeholder='Paket başına alış bedelini, giderleri ve hedef kârı yazın.';
 const send=node('button','Senaryoyu incele');send.className='primary';
 const reply=node('div');reply.setAttribute('aria-live','polite');
 const comparison=node('div');comparison.className='v6-assistant-list';
 const history=[],scenarios=[],chosen=new Set(),chips=node('div');
 let compareOpen=false;
 const context={id:doc.id,rev:doc.rev,tarih:when};
 function action(text,handler){
  const b=node('button',text);b.type='button';b.onclick=handler;return b
 }
 function compare(){
  comparison.replaceChildren();
  if(!scenarios.length)return;
  comparison.append(node('h3','Kayıtlı senaryolar'),node('p','Hedef teklif ve giderlerle hesaplanan kâr'));
  const list=node('ul');
  scenarios.forEach(r=>{
   const li=node('li',format(r.hesap.birim_teklif)+' TL/'+(report.birim??'birim')+' · '+format(r.hesap.kar)+' TL kâr');
   const select=action(chosen.has(r.id)?'PDF ekinden çıkar':"PDF’ye ekle",()=>{
    if(chosen.has(r.id))chosen.delete(r.id);else chosen.add(r.id);
    compare()
   });
   li.append(select);list.append(li)
  });
  comparison.append(list);
  if(scenarios.length>=2){
   const toggle=action(compareOpen?'Karşılaştırmayı kapat':'Senaryoları karşılaştır',()=>{compareOpen=!compareOpen;compare()});
   comparison.append(toggle);
   if(compareOpen){
    const t=node('table'),head=node('thead'),headrow=node('tr'),body=node('tbody');
    for(const label of ['Senaryo','Maliyet','Teklif / birim','Satış','Kâr'])headrow.append(node('th',label));
    head.append(headrow);t.append(head,body);
    scenarios.forEach((entry,i)=>{
     const row=node('tr');row.append(node('th',String(i+1)));
     for(const k of ['maliyet','birim_teklif','satis','kar'])row.append(node('td',format(entry.hesap[k])));
     body.append(row)
    });
    comparison.append(t)
   }
  }
  printArea.replaceChildren();
  if(chosen.size)printArea.append(node('h2','Seçilen senaryolar'));
  for(const r of scenarios.filter(r=>chosen.has(r.id))){
   printArea.append(node('p','Teklif '+format(r.hesap.birim_teklif)+' TL/'+report.birim+' · Satış '+format(r.hesap.satis)+' TL · Kâr '+format(r.hesap.kar)+' TL'))
  }
 }
 for(const q of ['Bu fiyatı hangi emsaller destekliyor?','Rakiplerin geçmişini göster.']){
  chips.append(action(q,()=>{ask.value=q;ask.focus()}))
 }
 chips.append(action('Maliyet ve kârı gir',()=>{
  ask.value='KDV hariç alış … TL/'+(report.birim??'paket')+', nakliye … TL, diğer gider … TL, finansman … TL. Maliyet üzerine %… kâr.';
  ask.focus();ask.setSelectionRange(ask.value.indexOf('…'),ask.value.indexOf('…')+1)
 }));
 form.append(ask,send);box.append(chips,form,reply,comparison);
 fetch('/api/rapor-senaryolari/'+encodeURIComponent(doc.id)).then(async response=>{
  if(!response.ok)return;
  const saved=await response.json();
  if(saved.tarih===when){for(const row of saved.senaryolar)if(!scenarios.some(r=>r.id===row.id))scenarios.push(row);compare()}
 }).catch(()=>{});
 form.onsubmit=async event=>{
  event.preventDefault();if(send.disabled)return;
  const question=ask.value.trim();if(!question)return;
  send.disabled=true;reply.textContent='Rapor inceleniyor…';
  try{
   const r=await api('karar-asistani',{...context,soru:[...history.slice(-1),question].join('\n').slice(-900)},55000);
   reply.replaceChildren(node('small',r.mod),node('p',r.metin));
   if(r.emsaller)reply.append(node('p',r.emsaller.join(' · ')));
   if(r.yukleniciler){
    const list=node('ul');
    for(const row of r.yukleniciler){
     const item=node('li',row.ad+' · '+row.tarih+' · ');
     const link=node('a',row.ikn);link.href=row.kaynak;link.target='_blank';link.rel='noopener';
     item.append(link);list.append(item)
    }
    reply.append(list)
   }
   if(r.hesap){
    const t=node('dl');
    for(const [k,l] of Object.entries(fields))t.append(node('dt',l),node('dd',format(r.hesap[k])));
    reply.append(t,node('small','MCP · '+r.iz.arac));
    const labels={alis:'Alış',nakliye:'Nakliye',diger:'Diğer gider',finansman:'Finansman',oran:'Hedef oran'};
    reply.append(node('p','Girdiler · '+Object.entries(labels).map(([k,label])=>label+' '+format(r.girdiler[k])).join(' · ')));
    if(r.eksik.length)reply.append(node('p','Hesaba girilmeyen giderler: '+r.eksik.map(k=>labels[k]).join(', ')));
    const save=action('Senaryoyu kaydet',async()=>{
     save.disabled=true;
     try{
      const item=await api('senaryo-kaydet',{...context,girdiler:r.girdiler},10000);
      scenarios.push(item);compare();save.textContent='Kaydedildi'
     }catch(error){save.disabled=false;reply.append(node('p','Kaydedilemedi. '+error.message))}
    });
    reply.append(save,action('Girdileri düzenle',()=>ask.focus()));
    history.length=0;
   }else if(r.mod!=='yerel'&&!r.emsaller)history.push(question)
  }catch(err){reply.textContent='Yanıt alınamadı. '+err.message}finally{send.disabled=false}
 };
 return box
}
