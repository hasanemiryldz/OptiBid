const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n};
const btn=(text,fn,cls)=>{const b=el('button',text,cls);b.type='button';b.onclick=fn;return b};
const link=(text,url)=>{const a=el('a',text);a.href=url;return a};
export async function calismaMerkezi({app,rows,config,onNew,onExample,onPrices,onImport,onResearch}){
 app.className='v20-home';app.replaceChildren();
 const top=el('header',null,'v20-topline');top.append(el('span','OptiBid / Çalışma alanı'),el('span','Yerel çalışma · Kaynaklı karar desteği','v20-status'));app.append(top);
 const hero=el('section',null,'v20-hero'),copy=el('div');
 copy.append(el('small','İHALE İSTİHBARATI & TEKLİF ANALİZİ','v20-eyebrow'),el('h1','İhale çalışma alanı'),el('p','Mal, hizmet, yapım ve danışmanlık alımlarında ihtiyacı tanımlayın, geçmiş verileri inceleyin ve teklif senaryosu hazırlayın.'));
 const actions=el('div',null,'v20-actions');actions.append(btn('Yeni çalışma başlat ↗',onNew,'primary'),btn('Örnek senaryolar',()=>examples(onExample),'v20-secondary'));copy.append(actions);
 const flow=el('div',null,'v20-flow');
 for(const [title,caption] of [['İhtiyaç','Tür, kategori ve teknik profil'],['Araştırma','Yerel havuz ve EKAP kaynakları'],['Karşılaştırma','Fiyat, koşullar ve senaryolar']]){
  const row=el('div');row.append(el('strong',title),el('small',caption));flow.append(row)
 }
 hero.append(copy,flow);app.append(hero);
 const stats=el('div',null,'v20-stats');app.append(stats);
 const lower=el('div',null,'v20-work-grid');
 const data=el('section',null,'v20-card');data.id='veri-havuzu';
 data.append(el('h2','Veri merkezi'),el('p','Dosya fiyatlarını ve EKAP dayanaklarını kaynak durumuna göre inceleyin.'));
 const categoryLabel=el('label','Kategori kapsamını incele'),select=el('select');select.append(new Option('Tüm ihale türleri',''));
 for(const key of Object.keys(config.turler))select.append(new Option(key,key));categoryLabel.append(select);data.append(categoryLabel);
 const coverage=el('div',null,'v20-category-list');data.append(coverage);
 const dataActions=el('div',null,'v20-actions');dataActions.append(btn('Veri merkezini aç',onPrices),btn('Kayıt ekle',onImport));data.append(dataActions);
 const audit=el('details',null,'v20-audit');audit.append(el('summary','Kaynak ve doğrulama ayrıntıları'));const details=el('div');audit.append(details,link('Kaynak denetimini indir','/api/kaynak-denetimi'));data.append(audit);
 const research=el('section',null,'v20-card v20-research-card');research.append(el('h2','Benzer ihale araştırması'),el('p','Ürün, hizmet veya iş adıyla EKAP kaynakları arayın. Sonuçları ve erişim durumunu inceleyin.'));
 research.append(btn('Benzer ihale araştır',onResearch,'primary'));
 lower.append(data,research);app.append(lower);
 const foot=el('footer',null,'v20-home-footer');foot.append(el('span','Standart JSON · Kategori sözlüğü · Yerel kayıt'),el('span','Karar desteği taslağı; kaynak ve hukuki kontrol gerekir.'));app.append(foot);
 try{
  const [files,pool]=await Promise.all([fetch('/api/dosya-fiyatlari').then(r=>{if(!r.ok)throw Error();return r.json()}),fetch('/api/havuz?durum=tumu').then(r=>{if(!r.ok)throw Error();return r.json()})]);
  if(!stats.isConnected)return;
  const categories=new Set(files.kayitlar.map(r=>[r.tur,...(r.kategori_yolu??[])].join(' / ')));
  for(const [value,label] of [[files.ozet.fiyati_bulunan,'İşlenen dosya fiyatı'],[categories.size,'Fiyat bulunan kategori'],[rows.length,'Kaydedilen çalışma']]){const card=el('div');card.append(el('strong',value),el('span',label));stats.append(card)}
  function draw(){coverage.replaceChildren();
   const groups=new Map();for(const r of files.kayitlar){if(select.value&&r.tur!==select.value)continue;const key=[r.tur,...(r.kategori_yolu??[])].join(' / ');groups.set(key,(groups.get(key)||0)+1)}
   for(const [key,count] of groups){const row=el('div');row.append(el('span',key),el('strong',count+' fiyat'));coverage.append(row)}
   if(!groups.size)coverage.append(el('p','Bu türde dosya fiyatı henüz yok. Yeni çalışma açabilir veya EKAP araştırması yapabilirsiniz.'))
  }select.onchange=draw;draw();
  for(const [value,label] of [[pool.ham,'İçe aktarılan satır'],[pool.benzersiz_ikn,'İKN biçiminde kimlik'],[pool.ekap,'EKAP dayanaklı kimlik'],[pool.bekliyor,'Doğrulama bekliyor'],[pool.karantina,'Haricî arşiv']])details.append(el('p',label+' · '+value));
  details.append(el('small','Sayaçlar farklı kapsamları gösterir; toplanarak toplam fiyat sayısı elde edilmez. Dosya fiyatı sayısı, resmî teyit sayısı değildir.'));
 }catch{stats.append(el('p','Veri özeti yüklenemedi. Veri merkezini açarak tekrar deneyin.'))}
}
async function examples(load){
 const dialog=el('dialog',null,'v20-examples');dialog.append(el('small','ÖRNEK SENARYOLAR','v20-eyebrow'),el('h2','Bir iş akışını deneyin.'),el('p','Örnekler sunum içindir; örnek çalışma olarak kaydedilir.'));
 const list=el('div',null,'v20-example-grid');dialog.append(list,btn('Kapat',()=>dialog.close()));document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove(),{once:true});dialog.showModal();
 try{const response=await fetch('/api/ornekler');if(!response.ok)throw Error();
  for(const row of await response.json()){
   const button=btn('',async()=>{button.disabled=true;try{await load(row.id);dialog.close()}catch(error){button.disabled=false;list.append(el('p',error.message))}},'v20-example');
   button.append(el('strong',row.baslik),el('span',row.aciklama));list.append(button)
  }
 }catch{list.append(el('p','Örnek senaryolar yüklenemedi. Pencereyi kapatıp tekrar deneyin.'))}
}
