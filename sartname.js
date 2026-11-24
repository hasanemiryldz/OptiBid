const node=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n};
const btn=(text,action)=>{const n=node('button',text);n.type='button';n.onclick=action;return n};
export const belgeBolumleri=[
 ['İhale özeti',['ihale_adi','ikn','idare','butce','kdv']],
 ['Teslimat ve ödeme',['yer','sure','gun_turu','baslangic','sure_kosulu','depo','teslim_kosulu','odeme']],
 ['Kritik yükümlülükler',['teminat_gecici','teminat_kesin','garanti','ceza','numune','belge','teklif_kosulu']]
];
export function belgeAdimlari(active){
 const list=node('ol');list.className='belge-adimlari';list.setAttribute('aria-label','Belge analizi adımları');
 ['Şartname yükle','Bilgileri incele','Analiz et','Raporu indir'].forEach((text,i)=>{
  const step=node('li',text);if(i===active)step.setAttribute('aria-current','step');list.append(step)
 });
 return list
}
function select(label,values){
 const wrap=node('label',label), input=node('select');
 wrap.append(input);input.required=true;
 setOptions(input,values);
 return [wrap,input];
}
function setOptions(input,values){
 const first=node('option','Seçin');first.value='';
 input.replaceChildren(first,...values.map(value=>node('option',value)));
}
function preview(pages,source){
 const box=node('details');box.append(node('summary','Şartname metni ve sayfalar'));
 const selector=node('select');selector.setAttribute('aria-label','Belge sayfası');
 pages.forEach((_,i)=>selector.append(node('option',(source==='pdf'?'Sayfa ':'Belge bölümü ')+(i+1))));
 const content=node('pre',pages[0]||'Okunamadı');selector.onchange=()=>content.textContent=pages[selector.selectedIndex]||'Okunamadı';
 box.append(selector,content);
 return [box,index=>{box.open=true;selector.selectedIndex=index-1;selector.onchange();selector.focus()}];
}

export function sartnameSayfalari(target,digest){
 const control=btn('Şartname metnini aç',async()=>{
  control.disabled=true;
  try{
   const response=await fetch('/api/sartname-sayfalari/'+encodeURIComponent(digest));
   if(!response.ok)throw Error();
   const result=await response.json();
   const [box]=preview(result.sayfalar,result.ad.toLowerCase().endsWith('.pdf')?'pdf':'docx');
   target.classList.add('sartname');
   box.open=true;control.replaceWith(box);
  }catch{
   control.textContent='Şartname açılamadı. Yeniden dene';control.disabled=false
  }
 });
 target.append(control);
}

export function sartnameEkrani(app,config,{manual,home,accept}){
 const heading=node('h1','Şartname yükle'), section=node('section'), form=node('form');
 section.className='sartname';
 const file=node('input');file.type='file';file.accept='.pdf,.docx,.txt';file.required=true;
 const label=node('label','Şartnameyi yükle');label.append(file);
 const send=node('button','Yükle ve incele');send.type='submit';send.className='primary';
 const status=node('p');status.setAttribute('role','status');
 form.append(label,node('p','PDF, DOCX veya UTF-8 TXT · en fazla 25 MB'),send,status);
 const options=node('nav');options.append(btn('Elle başla',manual),btn('Hazırlıklara dön',home));
 section.append(heading,form,options);app.className='v6-wizard belge-akisi';app.replaceChildren(belgeAdimlari(0),section);
 form.onsubmit=async event=>{
  event.preventDefault();
  if(send.disabled)return;
  const selected=file.files[0];
  if(!selected||selected.size===0){status.textContent='Boş dosya yüklenemez.';return}
  if(selected.size>25*1024*1024){status.textContent='Dosya en fazla 25 MB olabilir.';return}
  send.disabled=true;form.setAttribute('aria-busy','true');status.textContent='Şartname yükleniyor ve metin okunuyor…';
  try{
   const res=await fetch('/api/sartname-yukle',{method:'POST',
    headers:{'Content-Type':'application/octet-stream','X-OptiBid-Bicim':selected.name.split('.').pop().toLowerCase(),
     'X-OptiBid-Dosya':encodeURIComponent(selected.name)},
    body:selected,signal:AbortSignal.timeout(70000)});
   const result=await res.json();
   if(!res.ok)throw Error(result.hata);
   if(section.isConnected){
    app.firstElementChild.replaceWith(belgeAdimlari(1));
    approve(result,config,section,accept,()=>sartnameEkrani(app,config,{manual,home,accept}));
   }
  }catch(e){
   status.textContent=e.name==='TimeoutError'?'Belgeyi okuma süresi doldu. Tekrar deneyin.':e.message;
   send.disabled=false;
  }finally{
   form.removeAttribute('aria-busy');
  }
 };
}

function approve(result,config,section,accept,restart){
 const choice=node('form'), itemControls=[];
 choice.className='belge-inceleme';
 const [pages,go]=preview(result.sayfalar,result.bicim);
 const state=node('p');state.setAttribute('role','status');
 const submit=node('button','Analiz et');submit.type='submit';submit.className='primary';
 const wizard=node('button','Teknik sorulara geç');wizard.type='submit';
 function add(target,inputs,key,label,source){
  const wrap=node('label',label);
  const field=key==='birim'?select(label,config.birimler)[1]:node('input');
  if(key==='birim')field.required=false;
  else {field.maxLength=260;field.autocomplete='off'}
  field.value=source?.deger??'';
  const fallback=source?.durum==='uyuşmuyor'?'Çelişkili kaynaklar':'Belgede bulunamadı';
  const tag=node('small',source?.deger?'Kaynakla destekli':fallback);
  const hint=key+'-'+Math.random().toString(36).slice(2);
  tag.id=hint;field.setAttribute('aria-describedby',hint);
  field.oninput=()=>{tag.textContent=!field.value?fallback:field.value===source?.deger?'Kaynakla destekli':'Kullanıcı beyanı'};
  wrap.append(field,tag);target.append(wrap);inputs[key]=field;
  const sources=source?.durum==='uyuşmuyor'?source.adaylar:source?.kural?[source.kural]:[];
  if(sources.length){
   const evidence=node('details');evidence.append(node('summary',source.durum==='uyuşmuyor'?'Çelişkili alıntılar':'Kaynak alıntısı'));
   for(const x of sources) evidence.append(btn(x.konum,()=>go(x.sayfa)),node('q',x.alinti));
   target.append(evidence);
  }
 }
 const paths=Object.entries(config.turler).flatMap(([kind,groups])=>Object.entries(groups)
   .flatMap(([main,subs])=>Object.keys(subs).map(sub=>[kind,main,sub])));
 for(const [index,item] of result.kalemler.entries()){
  const fieldset=node('fieldset'), technical=node('div'), inputs={}, saved=new Map();
  fieldset.append(node('legend','Kalem '+(index+1)));
  const [label,category]=select('Kalem kategorisi',paths.map(path=>path.join(' / ')));
  category.required=false;
  category.value=item.kategori?.join(' / ')??'';
  fieldset.append(label);
  for(const key of ['ad','miktar','birim'])add(fieldset,inputs,key,item.alanlar[key].etiket,item.alanlar[key]);
  let previous=null;
  function render(){
   if(previous)saved.set(previous,Object.fromEntries(Object.keys(inputs).filter(k=>k.startsWith('teknik:')).map(k=>[k,inputs[k].value])));
   for(const key of Object.keys(inputs))if(key.startsWith('teknik:'))delete inputs[key];
   technical.replaceChildren();
   const path=paths.find(path=>path.join(' / ')===category.value);
   previous=category.value;
   if(path)for(const name of config.turler[path[0]][path[1]][path[2]]){
    const key='teknik:'+name;
    add(technical,inputs,key,name,item.kategori?.join(' / ')===previous?item.alanlar[key]:null);
    if(saved.get(previous)?.[key]!=null){inputs[key].value=saved.get(previous)[key];inputs[key].oninput()}
   }
  }
  category.onchange=render;render();
  fieldset.append(technical);choice.append(fieldset);
  itemControls.push({item,category,inputs});
 }
 const globalInputs={};
 for(const [title,keys] of belgeBolumleri){
  const general=node('fieldset');
  general.append(node('legend',title));
  for(const key of keys){const source=result.genel[key];if(source)add(general,globalInputs,key,source.etiket,source)}
  choice.append(general);
 }
 const controls=node('nav');controls.className='belge-islemleri';controls.append(submit,wizard);
 choice.append(controls,state);
 const heading=node('h1','Şartname taslağını incele');heading.tabIndex=-1;
 section.replaceChildren(heading,node('p',result.belge_adi),btn('Başka dosya seç',restart));
 const unread=result.okuma.okunamayan;
 section.append(node('p',unread.length?'Okunamayan bölümler: '+unread.join(', ')+'. OCR bu sayfalarda sonuç vermedi.':
  result.okuma.toplam+' okunabilir bölüm tarandı.'));
 if(result.model_durumu)section.append(node('p',result.model_durumu));
 if(result.kalemler.some(item=>!item.kategori)){
  const note=node('p','Kategori belirsizse belge raporunu açabilirsiniz. Fiyat karşılaştırması için kalemin kategorisini seçin.');
  note.className='belge-bilgi';section.append(note)
 }
 section.append(pages,choice);
 heading.focus();
 choice.onsubmit=async event=>{
  event.preventDefault();if(submit.disabled)return;
  submit.disabled=true;wizard.disabled=true;
  state.textContent=event.submitter===wizard?'Hazırlık kaydediliyor…':'Hazırlık kaydediliyor. Sonra belge raporu hesaplanacak…';
  const values=inputs=>Object.fromEntries(Object.entries(inputs).map(([key,input])=>[key,input.value.trim()||null]));
  try{await accept(result.sha,itemControls.map(({item,category,inputs})=>({kimlik:item.kimlik,
      kategori:paths.find(path=>path.join(' / ')===category.value),alanlar:values(inputs)})),values(globalInputs),event.submitter!==wizard)}
  catch(e){state.textContent=e.message;submit.disabled=false;wizard.disabled=false}
 };
}
