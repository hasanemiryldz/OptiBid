import {dosyaFiyatPanel} from '/dosya-fiyatlari.js';
import {emsalForm} from '/emsal.js';
import {sartnameSayfalari,belgeBolumleri,belgeAdimlari} from '/sartname.js';
const el=(tag,text,cls)=>{
 const node=document.createElement(tag);
 if(text!=null)node.textContent=text;
 if(cls)node.className=cls;
 return node
};
const money=new Intl.NumberFormat('tr-TR',{minimumFractionDigits:2,maximumFractionDigits:2});
const qty=new Intl.NumberFormat('tr-TR');
const tl=v=>v==null?'Hesaplanamadı':money.format(v)+' TL';
const asDate=v=>v?new Intl.DateTimeFormat('tr-TR',{dateStyle:'medium',timeZone:'UTC'}).format(new Date(v)):'';
function button(text,click,cls){
 const b=el('button',text,cls);b.type='button';b.onclick=click;return b
}
function part(name){
 const box=el('section',null,'report-part');
 box.append(el('h2',name));return box
}
function fold(name){
 const box=el('details');box.append(el('summary',name));return box
}
function table(headers,rows){
 const t=el('table');const head=t.createTHead().insertRow();
 headers.forEach(h=>{const cell=el('th',h);cell.scope='col';head.append(cell)});
 const body=t.createTBody();
 for(const row of rows){
  const tr=body.insertRow();
  row.forEach((v,i)=>{const cell=tr.insertCell();cell.dataset.label=headers[i];if(v instanceof Node)cell.append(v);else cell.textContent=v??'—'})
 }
 return t
}
function ufukNotu(row){
 return row.ufuk?.disinda?'Ufuk dışı ('+Math.abs(row.ufuk.ay)+' ay)':null
}
function dagilimTablosu(lines){
 return table(['Dönem','n','En düşük','Ortanca','En yüksek'],lines.map(([name,s])=>
  [name,s.sayi,...[s.alt,s.medyan,s.ust].map(value=>value==null?'—':tl(value))]));
}
function kdvSenaryolari(a,id='kdv-senaryolari'){
 const data=a.kdv_senaryolari;
 const section=part('KDV esası belirsiz: iki senaryo');section.id=id;section.classList.add('kdv-senaryolari');
 section.append(el('p','Gözlenen dağılım · TL/'+data.birim+' · Ortak fiyat ayı '+(data.ay??'yok')));
 section.append(el('p','Örnek KDV oranı %'+qty.format(data.oran)+'. Yürürlükteki oranı doğrulayın. Bu değerler teklif ve maliyet karşılaştırmasına katılmaz.','muted'));
 for(const [key,label] of [['haric_varsayimi','Kaynakta KDV hariç varsayımı'],['dahil_varsayimi','Kaynakta KDV dahil varsayımı']]){
  const scenario=data[key];
  section.append(el('h3',label));
  if(key==='dahil_varsayimi')section.append(el('p','KDV hariç karşılık = KDV dahil tutar ÷ (1 + oran/100).','muted'));
  section.append(dagilimTablosu([['Ufuk içi',scenario.ufuk_ici],['Duyarlılık · ufuk dışı dâhil',scenario.duyarlilik]]));
  section.append(table(['EKAP kaynağı','Tarih','Özgün birim fiyat','Kaynak ayında KDV hariç','Ortak ayda KDV hariç','Zaman ufku'],
   scenario.satirlar.map(x=>{
    const link=el('a',x.ikn);link.href=x.kaynak_url??x.kaynak;link.target='_blank';link.rel='noopener';
    const proof=fold('Miktar ve işlem');
    proof.append(el('p',tl(x.fiyat)+' ÷ '+qty.format(x.miktar)+' '+data.birim),el('p',x.alinti.join(' · ')));
    if(x.donusum)proof.append(el('p','Emsalin kendi paket katsayısı '+x.donusum.paket_carpani));
    if(x.endeks_iz)proof.append(el('p',x.endeks_iz.kaynak_ay+' → '+x.endeks_iz.hedef_ay+' · Yİ-ÜFE çarpanı '+x.endeks_iz.carpan));
    const evidence=el('div');evidence.append(link,proof);
    return [evidence,asDate(x.tarih),tl(x.ozgun_birim),tl(x.kaynak_tarihinde_haric),
     x.ortak_ayda_haric==null?'—':tl(x.ortak_ayda_haric),ufukNotu(x)??(x.ufuk?'Ufuk içi':'Ortak ay yok')];
   })));
 }
 return section
}
function kalemFiyatlari(a){
 const section=part('Kalem bazında fiyatlar');
 for(const [i,row] of a.kalem_sonuclari.entries()){
  const report=row.sonuc, card=el('section',null,'v18-price-reference');
  card.append(el('h3',row.ad),el('p',row.kategori.join(' / '),'muted'));
  if(row.mukerrer)card.append(el('p','Mükerrer kalem','v18-warning'));
  if(report.medyan!=null){
   card.append(el('p',tl(report.medyan)+' / '+report.birim+' · '+tl(report.toplam)+' kalem toplamı'));
   card.append(dagilimTablosu([['Ufuk içi',{sayi:report.emsaller.length,alt:report.alt,medyan:report.medyan,ust:report.ust}],
    ['Duyarlılık · ufuk dışı dâhil',report.dogrudan_duyarlilik]]));
   const sources=fold('Doğrudan emsaller');
   for(const ref of report.emsal_ayrinti){
    const link=el('a',ref.ikn+' · '+asDate(ref.tarih));link.href=ref.kaynak;link.target='_blank';link.rel='noopener';
    sources.append(link,el('br'));
   }
   card.append(sources);
  }else if(report.kdv_senaryolari)card.append(kdvSenaryolari(report,'kalem-kdv-'+(i+1)));
  else card.append(el('p','Karşılaştırılabilir emsal yok.'),el('p',report.neden,'muted'));
  section.append(card);
 }
 if(a.toplam!=null)section.append(el('p','Uyumlu kalemler toplamı '+tl(a.toplam)));
 return section;
}
function svgNode(name,attrs,parent,text){
 const n=document.createElementNS('http://www.w3.org/2000/svg',name);
 for(const [key,value] of Object.entries(attrs))n.setAttribute(key,value);
 if(text!=null)n.textContent=text;
 parent.append(n);return n
}
function chart(rows,a,volume=false){
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
 svg.setAttribute('viewBox','0 0 650 220');svg.setAttribute('role','img');
 svg.setAttribute('aria-label',volume?'Miktara göre paket fiyatları':'Tarihe göre özgün ve endeksli paket fiyatları');
 svg.classList.add('price-chart');
 const px=x=>volume?Number(x.paket_miktari):Date.parse(x.tarih);
 const xs=rows.map(px), ys=rows.flatMap(x=>volume?[+x.donusturulmus]:[+x.ham_paket,+x.donusturulmus]);
 const x0=Math.min(...xs),x1=Math.max(...xs);
 const y0=Math.floor((Math.min(...ys)-4)/5)*5,y1=Math.ceil((Math.max(...ys)+4)/5)*5;
 const X=x=>56+(x1===x0?.5:(x-x0)/(x1-x0))*570;
 const Y=y=>178-(y-y0)/(y1-y0)*155;
 if(a.alt!=null&&!volume)svgNode('rect',{x:56,y:Y(+a.ust),width:570,height:Math.max(2,Y(+a.alt)-Y(+a.ust)),class:'chart-band'},svg);
 for(let i=0;i<5;i++){
  const y=y0+(y1-y0)*i/4;
  svgNode('line',{x1:56,x2:626,y1:Y(y),y2:Y(y),class:'chart-grid'},svg);
  svgNode('text',{x:48,y:Y(y)+4,'text-anchor':'end'},svg,qty.format(y))
 }
 if(a.medyan!=null)svgNode('line',{x1:56,x2:626,y1:Y(+a.medyan),y2:Y(+a.medyan),class:'chart-median'},svg);
 for(const row of rows){
  const x=X(px(row));
  if(!volume)svgNode('circle',{cx:x,cy:Y(+row.ham_paket),r:4,class:'chart-raw'},svg);
  const point=svgNode('circle',{cx:x,cy:Y(+row.donusturulmus),r:5,class:'chart-point'},svg);
  svgNode('title',{},point,row.ikn+' · '+tl(row.donusturulmus)+'/paket')
 }
 const formatter=volume?x=>qty.format(x)+' paket':x=>asDate(x);
 svgNode('text',{x:56,y:205},svg,formatter(x0));
 if(x1!==x0)svgNode('text',{x:626,y:205,'text-anchor':'end'},svg,formatter(x1));
 return svg
}
function priceBand(a,target){
 const wrap=el('div',null,'price-band');
 const bar=el('div',null,'band-track');
 const pos=+a.ust===+a.alt?50:100*(+a.medyan-+a.alt)/(+a.ust-+a.alt);
 const mark=el('span',null,'band-mark');mark.style.left=pos+'%';mark.title='Ortanca: '+tl(a.medyan);
 bar.append(mark);
 if(Number.isFinite(+target)&&+target>0){
  const position=+a.ust===+a.alt?50:100*(+target-+a.alt)/(+a.ust-+a.alt);
  const marker=el('span',null,'target-mark');marker.style.left=Math.max(0,Math.min(100,position))+'%';
  marker.title='Hedef '+tl(target);bar.append(marker)
 }
 const labels=el('div',null,'band-labels');
 labels.append(el('span',tl(a.alt)),el('span','Ortanca '+tl(a.medyan)),el('span',tl(a.ust)));
 wrap.setAttribute('aria-label','Gözlenen fiyat aralığı: '+tl(a.alt)+' ile '+tl(a.ust));
 wrap.append(bar,labels);return wrap
}
import {asistanGoster} from '/karar-v10.js';
import {arastirmaEkrani} from '/arastirma.js';
export async function dosyaRaporu(original,app,edit,home,api){
 const doc=structuredClone(original);
 const item=doc.kalemler[0];
 const extra=doc.ek_bilgiler??={};
 const excluded=new Set(original.ek_bilgiler?.rapor_haric??[]);
 const subject=extra.sartname?.genel?.ihale_adi||doc.kalemler.map(x=>x.ad).filter(Boolean).join(', ');
 const identity=el('div',null,'document-mast');
 const brand=el('img');brand.src='/static/brand/optibid-logo.webp';brand.alt='OptiBid, Intelligent Bidding & Optimization';brand.className='report-logo';
 const title=el('div');
 const year=new Date().getFullYear();
 const reference=el('p',null,'document-ref');
 function dateStamp(when){reference.textContent='OB-'+year+'-'+String(doc.id??'').slice(0,8).toUpperCase()+' / '+asDate(when||new Date())}
 dateStamp();
 title.append(reference,el('h1',subject||'İhale fiyat değerlendirmesi'));
 identity.append(brand,title,el('span','Taslak','draft'));
 const actions=el('nav',null,'report-actions');
 const secondary=fold('Diğer işlemler');secondary.className='report-secondary';
 const printing=el('label','PDF görünümü','print-choice');
 const theme=el('select');for(const t of ['Koyu tema','Yazıcı dostu (açık zemin)']){const o=el('option',t);theme.append(o)}
 printing.append(theme);
 secondary.append(button('Hazırlıklara dön',home),button('Hazırlığı düzenle',edit),printing);
 const pdf=button('PDF olarak kaydet',()=>void exportIfActive(()=>{
  document.body.classList.toggle('print-dark',theme.selectedIndex===0);
  window.print()
 }));
 actions.append(secondary);
 const controls=el('div',null,'report-controls');
 const status=el('p','Rapor hazırlanıyor…','report-status');status.setAttribute('role','status');
 const savedNote=el('div',null,'saved-report-note');
 const content=el('div',null,'report-content'),grid=el('div',null,'v6-grid');
 const printScenarios=el('section',null,'v6-print-scenarios');app.className='document';
 grid.append(content);
 asistanGoster(null,null,null,api,null,{taslak:doc});
 const steps=extra.sartname?belgeAdimlari(2):null;
 app.replaceChildren(...(steps?[steps]:[]),identity,actions,controls,savedNote,status,grid,printScenarios);
 let snapshotDate;
 function showAssistant(a,when){
  snapshotDate=when;
  printScenarios.replaceChildren();
  asistanGoster(doc,a,when,api,printScenarios)
  if(steps?.isConnected)steps.replaceWith(belgeAdimlari(3))
 }
 function input(label,value,set,options,min,max,type='number'){
  const l=el('label',label),n=el(options?'select':'input');
  if(options)for(const [key,val] of options){const o=el('option',val);o.value=key;n.append(o)}
  else {n.type=type;n.step='any';if(min!=null)n.min=min;if(max!=null)n.max=max}
  n.value=value??'';n.setAttribute('aria-label',label);
  n.addEventListener(options?'change':'input',()=>{if(n.validity.valid){set(n.value);refresh()}});
  l.append(n);controls.append(l)
 }
 if(item&&doc.kalemler.length===1){
  input('Miktar ('+item.birim+')',item.miktar,v=>item.miktar=v,null,0.001);
  if(item.birim==='koli'){
   input('Kolideki paket sayısı',item.teknik['Kolideki paket sayısı'],v=>item.teknik['Kolideki paket sayısı']=v,null,1);
   controls.lastChild.querySelector('input').step='1'
  }
 }
 input('Karşılaştırma için hedef KDV esası',extra.kdv_esasi||'belirsiz',v=>extra.kdv_esasi=v,
  [['belirsiz','Belirsiz'],['hariç','KDV hariç'],['dahil','KDV dahil']]);
 const vatInput=controls.lastElementChild.querySelector('select');
 let timer,sequence=0,last;
 let requests=Promise.resolve();
 async function exportIfActive(action){
  if(!last||content.getAttribute('aria-busy')==='true')return;
  try{
   const check=await fetch('/api/rapor-kaydi/'+encodeURIComponent(doc.id));
   const snapshot=check.ok?await check.json():null;
   if(snapshot?.tarih!==snapshotDate||snapshot?.sonuc?.source_policy!=='EKAP_ONLY')throw Error('Bu rapor değişti. Güncel kaydı açın.');
   await action()
  }catch(error){status.textContent=error.message}
 }
 const signatures=el('footer',null,'report-signatures');
 signatures.append(el('p','Bu çıktı kaynaklı gözlemler ve koşullu hesaplar içeren bir taslaktır. KDV ve miktar varsayımları teyit edilmeden kesin fiyat veya yaklaşık maliyet olarak kullanılmamalıdır.'));
 const slots=el('div',null,'signature-slots');
 for(const name of ['Hazırlayan','Kontrol eden','Onaylayan'])slots.append(el('span',name));
 signatures.append(slots);
 function refresh(immediately=false,compareSaved=false){
  const revision=++sequence;
  clearTimeout(timer);
  status.textContent='Rapor hazırlanıyor…';
  content.setAttribute('aria-busy','true');
  timer=setTimeout(()=>{
   const draft=structuredClone(doc);draft.ek_bilgiler.rapor_haric=[...excluded];
   requests=requests.catch(()=>{}).then(async()=>{
    if(revision!==sequence)return;
    try{
     const result=await api('rapor-hesap',draft,28000,{'X-OptiBid-Rapor':'kaydet'});
     window.dispatchEvent(new Event('optibid:history'));
     if(revision!==sequence||!status.isConnected)return;
     savedNote.replaceChildren();
     if(compareSaved&&last&&(last.veri_surumu!==result.veri_surumu||last.havuz_kapsami?.surum!==result.havuz_kapsami?.surum||last.endeks?.dosya_sha256!==result.endeks?.dosya_sha256)){
      const before=new Set((last.emsal_ayrinti??[]).map(x=>x.ikn)),after=new Set((result.emsal_ayrinti??[]).map(x=>x.ikn));
      const plus=[...after].filter(i=>!before.has(i)),minus=[...before].filter(i=>!after.has(i));
      savedNote.append(el('p','Veri sürümü değişti · '+tl(last.medyan)+' → '+tl(result.medyan)+' · '+before.size+' → '+after.size+' emsal'),
       el('p','Eklenen '+(plus.join(', ')||'—')+' · Çıkan '+(minus.join(', ')||'—')));
     }
     last=result;dateStamp(result.kayit_tarihi);render(result);showAssistant(result,result.kayit_tarihi);
     status.textContent='';
    }catch(error){
     if(revision!==sequence||!status.isConnected)return;
     status.textContent='Rapor hazırlanamadı. '+error.message;
     status.append(' ',button('Yeniden dene',()=>refresh(true)))
    }finally{if(revision===sequence)content.removeAttribute('aria-busy')}
   })
  },immediately?0:180)
 }
 const workbook=button('Excel indir',()=>void exportIfActive(async()=>{
  if(!last||content.getAttribute('aria-busy')==='true')return;
  try{
   const res=await fetch('/api/rapor-excel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:doc.id,rev:doc.rev,tarih:snapshotDate,ekler:JSON.parse(printScenarios.dataset.ekler||'[]')})});
   if(!res.ok)throw Error();
   const url=URL.createObjectURL(await res.blob()),link=el('a');link.href=url;link.download='OptiBid.xlsx';link.click();
   setTimeout(()=>URL.revokeObjectURL(url),10000)
  }catch{status.textContent='Excel indirilemedi. Tekrar deneyin.'}
 }),'primary');
 actions.prepend(workbook,pdf);
 secondary.insertBefore(button('Standart JSON indir',()=>void exportIfActive(async()=>{
  const result=await api('rapor-json',{id:doc.id,rev:doc.rev,tarih:snapshotDate,ekler:JSON.parse(printScenarios.dataset.ekler??'[]')},18000);
  const link=el('a');link.href=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));
  link.download='OptiBid_Standart_Rapor.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)
 })),printing);
 secondary.insertBefore(button('Benzer ihale araştır',()=>{
  arastirmaEkrani(app,()=>void dosyaRaporu(doc,app,edit,home,api),api,doc.kategori.at(-1));
  asistanGoster(null,null,null,api,null,{taslak:doc})
 }),printing);
 function render(a){
  const scope=a.havuz_kapsami??{};
  const heading=el('section',null,'v10-decision');
  const references=a.fiyat_referanslari??[],summaries=a.kosullu_ozetler??[];
  heading.append(el('h2',a.durum==='Kısmi rapor'?'Kısmi rapor':a.kalem_sonuclari?'Çok kalemli rapor':a.medyan!=null?'Doğrudan emsal referansı':a.kdv_senaryolari?'Emsal fiyatları':references.length?'Kaynaklı birim fiyatlar':'Karşılaştırılabilir fiyat bulunamadı'));
  if(a.medyan!=null)heading.append(el('div',tl(a.medyan)+' / '+a.birim,'estimate'),el('p',tl(a.toplam)+' · '+a.ay+' düzeyinde toplam'),
   el('p','Gözlenen birim fiyat aralığı '+tl(a.alt)+' – '+tl(a.ust)),el('p',a.yontem,'muted'));
  else heading.append(el('p',a.neden));
  if(a.dogrudan_duyarlilik){
   heading.append(dagilimTablosu([['Ufuk içi',{sayi:a.emsaller.length,alt:a.alt,medyan:a.medyan,ust:a.ust}],
    ['Duyarlılık · ufuk dışı dâhil',a.dogrudan_duyarlilik]]));
  }
  if(a.kdv_senaryolari)heading.append(kdvSenaryolari(a));
  if(a.kalem_sonuclari?.length)heading.append(kalemFiyatlari(a));
  if(summaries.length){
   const historical=fold('İhale miktarına dayalı koşullu gözlemler');
   for(const s of summaries){
    const card=el('section',null,'v18-price-reference');
    card.append(el('h3',s.birim+' · '+s.ay+' fiyat düzeyi · KDV '+s.kdv),
     dagilimTablosu([['Ufuk içi',s.ufuk_ici??s],['Duyarlılık · ufuk dışı dâhil',s]]));
    const assumptions=fold('Hesabın varsayımları');
    for(const text of s.varsayimlar)assumptions.append(el('p',text));
    assumptions.append(el('p',s.yontem));card.append(assumptions);historical.append(card)
   }
   heading.append(historical)
  }
  if(a.medyan==null&&!a.kdv_senaryolari&&!a.kalem_sonuclari&&a.durum!=='Kısmi rapor'){
   const links=el('div',null,'report-help-actions');
   const auditLink=el('a','Kaynak denetimini aç');auditLink.href='#rapor-kaynak-denetimi';
   auditLink.onclick=()=>{content.querySelector('#rapor-kaynak-denetimi').open=true};
   links.append(button('KDV esasını seç',()=>vatInput.focus()),button('Emsal ekle',async()=>{
    try{
     const res=await fetch('/catalog.json');
     if(!res.ok)throw Error();
     const catalog=await res.json();
     emsalForm(catalog,()=>dosyaRaporu(doc,app,edit,home,api),app);
    }catch{status.textContent='Emsal formu açılamadı. Tekrar deneyin.'}
   }),auditLink);
   heading.append(links);
  }
  if(a.endeks_ufku_ay!=null)heading.append(el('p',a.endeks_ufku_ay+' ay endeks ufku bir varsayımdır. Geri test için veri yetersiz.','muted'));
  if(a.standart_miktar)heading.append(el('p','Hedef miktar: '+qty.format(a.standart_miktar)+' '+a.birim));
  for(const warning of a.uyarilar??[])heading.append(el('p',warning,'v18-warning'));
  if(a.hesap_izi?.mcp_dogrulandi===false){
   if(a.hesap_izi.neden)heading.append(el('strong',a.hesap_izi.neden,'v18-warning'));
   heading.append(button('Hesaplamayı yeniden dene',()=>refresh(true)));
  }
  const facts=el('dl',null,'v10-facts');
  for(const [label,value] of [
   ['Doğrulanan EKAP',scope.ekap],['Kategori adayı',a.kategori_adayi],
   ['Bedel ve miktar var',a.asama_sayilari?.kaynakta_miktar_ve_bedel??'—'],
   ['Aynı kaynakta tek kalem hesabı',a.asama_sayilari?.tek_kalem_birim_fiyati??'—'],
   ['Endekslenen toplam',a.endekslenen_nominal??0],['Koşullu birim referansı',references.length],
   ['Doğrudan karşılaştırma',a.emsaller?.length??0],['Taranan tüm kimlikler',a.aday_sayisi??scope.benzersiz]
  ]){const c=el('div');c.append(el('dt',label),el('dd',value));facts.append(c)}
  heading.append(facts);
  if(a.endeks){
   const source=el('a','TÜİK bülteni');source.href=a.endeks.bulten;source.target='_blank';source.rel='noopener';
   const indexNote=el('p',a.endeks.ad+' · '+a.endeks.baz+'=100 · Son kayıtlı ay '+a.endeks.son_ay+' · Yayım '+(asDate(a.endeks.yayim_tarihi)||'belirtilmemiş')+' · ','muted');
   indexNote.append(source);heading.append(indexNote)
  }
  const technical=fold('Teknik ayrıntılar');
  technical.append(el('p','Veri sürümü '+(a.veri_surumu??'—')));
  if(a.hesap_izi)technical.append(el('pre',JSON.stringify(a.hesap_izi,null,2)));
  heading.append(technical);
  const referenceSection=part('Fiyatı ve miktarı bulunan kaynaklar');
  referenceSection.append(el('p','EKAP sonuç bedelleri aynı İKN’nin kaynak miktarına bölündü. İhale miktarının sözleşmede aynen gerçekleştiği varsayımı korunuyor. Teknik veya KDV eksiği olan satırlar silinmez; doğrudan fiyatlarla birleştirilmez.','muted'));
  if(references.length)referenceSection.append(table(['İKN','Kaynak miktarı','Özgün birim fiyat','Ortak dönem / birim','Teknik / KDV','Dayanak'],references.map(x=>{
   const source=el('a','Kaynağı incele');source.href=x.kaynak_url??x.kaynak;source.target='_blank';source.rel='noopener';
   const detail=fold('Varsayımlar ve hesap');
   detail.append(el('p',x.fiyat+' TRY ÷ '+x.miktar+' '+x.kaynak_birim));
   for(const note of x.varsayimlar)detail.append(el('p',note));
   detail.append(source);
   return [x.ikn,qty.format(x.miktar)+' '+x.kaynak_birim,tl(x.ham_birim)+' / '+x.kaynak_birim,
    x.islenmis_birim?[tl(x.islenmis_birim)+' / '+x.birim+' · '+x.hedef_ay,ufukNotu(x)].filter(Boolean).join(' · '):'Endeks eksik; özgün fiyat korundu',
    (x.teknik_eslesme?'Hedef profil eşleşti':'Teknik bilgi eksik')+' · KDV '+(x.kdv??'belirsiz'),detail]
  })));
  else referenceSection.append(el('p','Kaynakla eşleşen fiyat ve tek kalem miktarı bulunamadı.'));
  const observations=part('Tarihli EKAP sözleşmeleri');observations.classList.add('v10-nominal');
  observations.append(el('p','Özgün bedeller sözleşme tarihindedir. Birim karşılığı, aynı kapsamı doğrulanan toplam ve miktardan hesaplanır. KDV’si belirsiz bedeller ayrı gösterilir.','muted'));
  if(a.nominal?.length){
   const portal=el('a','EKAP ihale araması');portal.href=a.nominal[0].ekap_arama??'https://ekapv2.kik.gov.tr/ekap/search';
   portal.target='_blank';portal.rel='noopener';observations.append(portal);
   observations.append(table(['İKN / grup','Özgün birim fiyat','Endeksli birim fiyat','Sözleşme tarihi','İş ve kaynak miktarı','Dayanak'],a.nominal.map(x=>{
    const source=el('a',x.kaynak_url?'EKAP asıl sayfası':'Sonuç görüntüsü');
    source.href=x.kaynak_url??'/api/ekap-goruntu/'+x.ikn;source.target='_blank';source.rel='noopener';
    const evidence=el('div');evidence.append(source);
    const item=x.teklif_cetveli;
    if(item){
     const details=fold('Kalem kanıtı');
     const link=el('a','Arşiv dayanağı');link.href=x.kaynak;link.target='_blank';link.rel='noopener';
     details.append(el('p',item.alinti.join(' · ')+' · Satır '+item.satir_baslangic+'–'+item.satir_bitis),
      el('small',item.kapsam??'İhale belgesinde istenen miktar'),link);
     evidence.append(details)
    }
    const index=x.endeks_iz;
    const shifted=el('div',x.endeksli_birim?tl(x.endeksli_birim.tutar)+' / '+x.endeksli_birim.birim:x.endeks_eksik??'—');
    if(ufukNotu(x))shifted.append(el('p',ufukNotu(x),'v18-warning'));
    if(index){const details=fold('Endeks hesabı');
     details.append(el('p',index.kaynak_ay+' ('+index.kaynak_endeks+') → '+index.hedef_ay+' ('+index.hedef_endeks+') · Çarpan '+index.carpan),
      el('p','Endeksli toplam '+tl(index.tutar_endeksli)));
     shifted.append(details)
    }
    const amount=el('div',x.turetilmis_birim?tl(x.turetilmis_birim.tutar)+' / '+x.turetilmis_birim.birim:'—');
    const total=fold('Sözleşme toplamı');total.append(el('p',money.format(x.fiyat)+' '+x.para));amount.append(total);
    return [x.ikn+(x.grup?' · '+x.grup:''),amount,shifted,asDate(x.tarih),x.ad+(item?' · '+qty.format(item.miktar)+' '+item.birim:''),evidence]
   })))
  }else observations.append(el('p','Bu kategori için tarihli EKAP gözlemi bulunamadı.'));
  if(a.ayri_sozlesmeler?.length){
   const multiple=fold('Çok sözleşmeli ihalelerin özgün bedelleri');
   multiple.append(el('p','Kısımların miktar ve KDV esası bilinmediğinden bu bedeller kalem fiyatı hesabına alınmadı.','muted'));
   multiple.append(table(['İKN','Sözleşme sırası','Özgün bedel','Tarih','KDV','Dayanak'],a.ayri_sozlesmeler.map(x=>{
    const source=el('a',x.konum??'EKAP');source.href=x.url??'/api/ekap-dayanagi/'+x.ikn;source.target='_blank';source.rel='noopener';
    return [x.ikn,x.sira,money.format(x.tutar)+' '+x.para,x.tarih??'Bilinmiyor',x.kdv??'Bilinmiyor',source];
   })));
   observations.append(multiple);
  }
  const groups=part('Emsallerin kullanım durumu');
  for(const [key,label] of [['A','Doğrudan karşılaştırılabilir'],['B','Benzer, koşulları farklı'],['C','Fiyat esası belirsiz'],['D','Fiyat veya miktar eksik'],['E','Hesap kapsamı dışında']]){
   const items=a.gruplar?.[key]??[];
   const details=fold(key+' · '+label+' · '+items.length);
   if(items.length)details.append(table(['İKN','Gerekçe'],items.map(x=>{
    const id=el('a',x.ikn);id.href=x.kaynak_url??'/api/ekap-dayanagi/'+x.ikn;id.rel='noopener';id.target='_blank';
    return [id,x.neden]
   })));
   groups.append(details)
  }
  if(a.emsal_ayrinti?.length)groups.append(table(['Kullanılan İKN','Özgün fiyat / birim','Ortak dönem fiyatı','Miktar'],a.emsal_ayrinti.map(x=>
    [x.ikn,tl(x.ham_birim)+' / '+x.birim,tl(x.islenmis_birim)+' / '+x.birim,x.miktar])));
  const audit=fold('Havuz denetimi ve dışlama nedenleri');
  audit.id='rapor-kaynak-denetimi';
  audit.append(el('p',scope.ham+' kaynak satırı · '+scope.benzersiz+' benzersiz kimlik · '+scope.bekliyor+' doğrulama bekliyor · '+scope.karantina+' karantinada'));
  const download=el('a','Tam kaynak denetimini indir');download.href='/api/kaynak-denetimi';audit.append(download);
  if(a.dislanan?.length)audit.append(table(['İKN','Dışlama nedeni'],a.dislanan.map(x=>[x.ikn,x.neden])));
  const quotes=fold(doc.ornek_veri?'Kurgusal örnek teklifler':'Firma teklifleri');
  if(a.teklifler?.length)quotes.append(table(['Firma','Tutar','KDV esası','Teslim','Uygunluk'],a.teklifler.map(t=>{
   const incompatible=t.satirlar?.some(s=>s.uyumsuz.length);
   return [t.firma,t.tutar==null?'Eksik':money.format(t.tutar)+' '+(t.para??''),t.kdv,[t.gun,t.gun_turu].filter(Boolean).join(' '),
    t.en_dusuk?'Aynı esasta en düşük':t.karsilastirilabilir?'Kapsam eşleşti':incompatible?'Teknik uyumsuz':'Eksik bilgi veya teslim farkı']
  })));
  const profile=part('Kalemler ve teknik gereklilikler');
  profile.append(el('p',[doc.ihale_turu,...doc.kategori].filter(Boolean).join(' / ')||'Kategori henüz belirlenmedi.'));
  profile.append(table(['Kalem','Miktar ve birim','Teknik alanlar'],doc.kalemler.map(item=>[item.ad||'Belgede bulunamadı',
   item.miktar==null?'Belgede bulunamadı':qty.format(item.miktar)+' '+(item.birim??'· birim eksik'),
   Object.entries(item.teknik??{}).map(([field,value])=>field+' · '+(value??'Belgede bulunamadı')).join(' / ')||
     (extra.sartname?'Belgede bulunamadı':'Teknik bilgi girilmedi')])));
  const delivery=doc.teslimat??{};
  profile.append(el('p',[delivery.yer,delivery.sure&&(delivery.sure+' '+(delivery.gun_turu??'')),delivery.baslangic].filter(Boolean).join(' · ')||'Teslim koşulları girilmedi.','muted'));
  const source=a.sartname_durumu??doc.ek_bilgiler?.sartname;
  const documentParts=[];
  if(source?.sha){
   const general=source.kanitlar?.genel??{};
   const missing=part('Eksik veya belirsiz bilgiler');
   const gaps=Object.entries(source.kanitlar??{}).flatMap(([scope,fields])=>Object.entries(fields)
    .filter(([,proof])=>proof.deger==null).map(([field,proof])=>[
     scope==='genel'?'İhale':doc.kalemler.find(i=>i.id===scope)?.ad??'Kalem',
     proof.etiket??field.replace(/^teknik:/,''),proof.durum==='uyuşmuyor'?'Çelişkili kaynaklar':'Belgede bulunamadı'
    ]));
   if(gaps.length)missing.append(table(['Kapsam','Alan','Durum'],gaps));
   else missing.append(el('p','İncelenen alanlarda eksik veya çelişkili bilgi işaretlenmedi.'));
   const details=part('Kaynaklar ve hesaplama dayanakları');
   details.classList.add('belge-kaynaklar');
   details.append(el('p',source.belge_adi||'Şartname'),el('p','SHA-256 '+source.sha,'belge-parmakizi'));
   sartnameSayfalari(details,source.sha);
   const read=source.okuma??{};
   details.append(el('p',`Okuma durumu: ${read.durum??'Bilinmiyor'} · Kullanıcı incelemesi: ${source.inceleme_tamamlandi?'tamamlandı':'sürüyor'}`));
   if(read.okunamayan?.length)details.append(el('p','Okunamayan bölüm/sayfa '+read.okunamayan.join(', '),'v18-warning'));
   if(Object.keys(read.uzun_satirlar??{}).length)details.append(el('p','Uzun satır sınırına takılan bölüm/sayfa '+Object.keys(read.uzun_satirlar).join(', '),'v18-warning'));
   const scopes=source.kanitlar??{};
   const statuses={kaynak_bulgusu:'Şartname',kullanici_beyani:'Kullanıcı beyanı',bilinmiyor:'Belgede bulunamadı'};
   const proofText=proof=>[proof.konum,proof.alinti].filter(Boolean).join(' · ');
   const pdfLabel=proof=>proof.durum==='uyuşmuyor'?'Çelişkili kaynaklar, inceleyin':statuses[proof.tur]??'Bilinmiyor';
   const [summary,deliverySection,obligations]=belgeBolumleri.map(([label,fields])=>{
    const section=part(label==='Kritik yükümlülükler'?'Kritik yükümlülükler ve riskler':label);
    section.classList.add('belge-ozet');
    const entries=fields.filter(key=>general[key]?.deger!=null||general[key]?.durum==='uyuşmuyor');
    section.append(entries.length?table(['Alan','Belgedeki veya girilen değer','Köken / konum'],entries.map(key=>{
     const proof=general[key];
     return [proof.etiket??key,proof.deger??'Çelişkili',[
      pdfLabel(proof),proof.konum??(proof.adaylar??[]).map(p=>p.konum).filter(Boolean).join(', ')
     ].filter(Boolean).join(' · ')]
    })):el('p','Bu bölüm için belgede doğrulanabilir bilgi bulunamadı.'));
    return section
   });
   const model=source.model_durumu?el('p','Ollama · '+source.model_durumu,'muted'):null;
   if(model)details.append(model);
   if(a.hesap_izi?.arac)details.append(el('p','Kodla hesaplandı · '+a.hesap_izi.arac+
    (a.hesap_izi.mcp_dogrulandi?' · MCP ile doğrulandı':a.hesap_izi.neden?' · '+a.hesap_izi.neden:'')));
   const evidence=Object.entries(scopes).flatMap(([key,values])=>Object.entries(values)
    .filter(([,proof])=>proof.deger!=null||proof.durum==='uyuşmuyor').map(([field,proof])=>[
     doc.kalemler.find(i=>i.id===key)?.ad??'Genel',proof.etiket??field.replace(/^teknik:/,''),proof.deger??'—',
     pdfLabel(proof),
     [proofText(proof),...(proof.durum==='uyuşmuyor'?(proof.adaylar??[]).map(proofText):[]),
      proof.onceki?.alinti?'Önceki kaynak: '+proofText(proof.onceki):null].filter(Boolean).join(' / ')||'—'
    ]));
   if(evidence.length)details.append(table(['Kapsam','Alan','Değer','Köken','Kanıt'],evidence));
   documentParts.push(summary,profile,deliverySection,obligations,missing,details);
  }else documentParts.push(profile);
  const offer=part('Teklif senaryoları');
  offer.append(el('p','Hesap için alış birim fiyatı, giderler, KDV esası ve hedef kâr veya marj bilgisi gerekir.'));
  offer.append(button('Maliyet senaryosu aç',()=>{
   const toggle=document.querySelector('#assistant-host .v10-launch');
   if(toggle?.getAttribute('aria-expanded')==='false')toggle.click();
   document.querySelector('#assistant-host textarea')?.focus()
  },'rapor-ekran-islemi'));
  content.replaceChildren(...documentParts,heading,dosyaFiyatPanel(a.dosya_fiyat_analizi),
   referenceSection,groups,observations,audit,quotes,offer,el('p','Taslak karar desteği. Teknik ve hukuki kontrol gerekir.','muted'));
 }

 try{
  const response=await fetch('/api/rapor-kaydi/'+encodeURIComponent(doc.id));
  const saved=response.ok?await response.json():null;
  if(!status.isConnected)return;
  if(saved?.onceki_politika){
   status.textContent='Önceki rapor arşivde saklanıyor.';
   savedNote.append(button('Yalnız EKAP ile yeni rapor hesapla',()=>refresh(true)));
   return
  }
  if(saved){
   // Copy saved report controls while retaining the current preparation revision.
   if(saved.belge.kalemler[0]&&item){
    item.miktar=saved.belge.kalemler[0].miktar;
    Object.assign(item.teknik,saved.belge.kalemler[0].teknik);
   }
   Object.assign(extra,saved.belge.ek_bilgiler);
   excluded.clear();for(const id of extra.rapor_haric??[])excluded.add(id);
   const values={['Miktar ('+(item?.birim??'')+')']:item?.miktar,'Kolideki paket sayısı':item?.teknik?.['Kolideki paket sayısı'],
    'Karşılaştırma için hedef KDV esası':extra.kdv_esasi||'belirsiz'};
   for(const label of controls.querySelectorAll('label')){
    label.lastChild.value=values[label.firstChild.textContent]??'';
   }
   last=saved.sonuc;dateStamp(saved.tarih);render(last);showAssistant(last,saved.tarih);status.textContent='';
   if(last.degerlendirme_surumu!=='v20-m3-kalem'){
    savedNote.append(el('p','Fiyat motoru güncellendi. Yeni KDV ve endeks ufku hesaplarını görmek için raporu yenileyin.'));
   }
   savedNote.append(el('p',last.ay?'Bu kayıt '+last.ay+' fiyat düzeyiyle hazırlandı.':'Bu raporun kaydedilen sonucu açık.'),
     button('Güncel veriyle yenile',()=>refresh(true,true)));
   return
  }
 }catch(error){if(!status.isConnected)return}
 refresh(true)
}



