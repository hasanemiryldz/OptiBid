const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n};
const btn=(text,action,cls)=>{const b=el('button',text,cls);b.type='button';b.onclick=action;return b};
export function kaynakLinki(text,url){try{const u=new URL(url,location.origin);if(u.protocol!=='https:'&&u.origin!==location.origin)return el('span',text);const a=el('a',text);a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';return a}catch{return el('span',text)}}
export function arastirmaSonucu(value,api){
 const body=el('div',null,'v20-web-results');
 body.append(el('small',value.saglayici+' · '+new Date(value.erisim_zamani).toLocaleString('tr-TR')),
             el('p',value.not));
 for(const row of value.kaynaklar??[]){
  const card=el('article',null,'v20-source');
  card.append(el('small',(row.sayfa_okundu?'CANLI EKAP OKUMASI':'EKAP ADRESİ · ARAMA SONUCU')+
   (row.erisim_zamani?' · '+new Date(row.erisim_zamani).toLocaleString('tr-TR'):'')),
   kaynakLinki(row.baslik||row.url,row.url),el('p',row.ozet),el('small','Fiyat ve ürün kapsamı ayrıca teyit edilmeli.'));
  const read=btn('Kaynak metnini incele',async()=>{read.disabled=true;const status=el('p','Sayfa okunuyor…');card.append(status);
   try{const result=await api('kaynak-oku',{url:row.url},24000);status.textContent=result.not;
    status.textContent+=(result.iz?.mod==='yerel'?' · Yerel okuma':result.iz?' · MCP':'');
    if(result.metin){const details=el('details');details.append(el('summary','Okunan sayfa metni'),el('p',result.metin));card.append(details)}
   }catch(error){status.textContent=error.message}finally{read.disabled=false}
  });card.append(read);body.append(card)
 }
 if(!value.kaynaklar?.length)body.append(el('p',value.hatalar?.length?'İnternet araması tamamlanamadı. Arama bağlantıları aşağıda; bunlar bulunmuş ihale değildir.':'Bu sorguda EKAP sonucu bulunamadı.'));
 for(const error of value.hatalar??[])body.append(el('p',error,'muted'));
 const fold=el('details');fold.append(el('summary','Arama sorguları ve işlem izi'));
 if(value.iz)fold.append(el('p',value.iz.arac+' · '+(value.iz.mod==='yerel'?'yerel yedek':'gerçek MCP')));
 for(const event of value.olaylar??[])fold.append(el('p',event.sorgu+' · '+event.durum));
 for(const row of value.arama_baglantilari??[])fold.append(kaynakLinki(row.baslik+' ↗',row.url),el('br'));
 body.append(fold);return body
}
export function arastirmaEkrani(app,home,api,topic=''){
 app.className='v20-research';app.replaceChildren();
 app.append(btn('← Çalışma alanı',home),el('small','ARAŞTIRMA AJANI','v20-eyebrow'),el('h1','Benzer ihale araştırın.'),el('p','Ürün, hizmet, iş tanımı veya İKN yazın. Araştırma yalnız EKAP adresli sonuçları getirir.'));
 const form=el('form',null,'v20-research-form'),label=el('label','Arama konusu'),input=el('input');input.type='search';input.required=true;input.minLength=2;input.maxLength=350;input.placeholder='Ürün veya hizmet adı';input.value=topic;label.append(input);
 const submit=el('button','EKAP kaynaklarını ara','primary');submit.type='submit';form.append(label,submit);
 const status=el('p');status.setAttribute('role','status');const result=el('div');app.append(form,status,result);
 const trace=el('p','Arama metni internet sağlayıcısına gönderilir. Çalışmanızdaki maliyet ve iletişim bilgileri otomatik gönderilmez.','muted');app.append(trace);
 form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;status.textContent='Canlı kaynaklar araştırılıyor…';result.replaceChildren();
  try{const response=await api('arastirma',{sorgu:input.value},30000);if(!result.isConnected)return;
   status.textContent=response.durum==='erişilemedi'?'Arama sağlayıcısına erişilemedi.':response.kaynaklar.length+' EKAP adresli sonuç';
   result.append(arastirmaSonucu(response,api));
  }catch(error){status.textContent=error.message}finally{submit.disabled=false}
 }
}
