const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n};
const number=new Intl.NumberFormat('tr-TR',{maximumFractionDigits:2});
const money=new Intl.NumberFormat('tr-TR',{minimumFractionDigits:2,maximumFractionDigits:2});
const tl=(v,currency)=>v==null?'—':money.format(v)+' '+(currency==='TRY'?'TL':currency??'(para birimi belirsiz)');
function table(headings,rows){
 const wrap=el('div',null,'v19-price-table'),t=el('table'),h=t.createTHead().insertRow(),b=t.createTBody();
 for(const s of headings){const th=el('th',s);th.scope='col';h.append(th)}
 for(const values of rows){const tr=b.insertRow();values.forEach((v,i)=>{const td=tr.insertCell();td.dataset.label=headings[i];if(v instanceof Node)td.append(v);else td.textContent=v??'—'})}
 wrap.append(t);return wrap
}
function rowsTable(rows){
 return table(['Kimlik','Kategori / kaynak birimi','Miktar','Sözleşme toplamı','Dosya birim fiyatı','Fiyat tarihi / ortak dönem','Dayanak'],rows.map(r=>{
  const a=el('a','Dosya satırı');a.href='/api/dosya-fiyat-dayanagi/'+encodeURIComponent(r.ikn);a.target='_blank';a.rel='noopener';
  const details=el('details');details.append(el('summary','Kaynak ve sınırlar'),a);
  for(const s of r.kaynaklar){
   details.append(el('p',s.dosya+' · '+s.konum));
   if(s.url){const link=el('a','EKAP kaynağı');link.href=s.url;link.target='_blank';link.rel='noopener';details.append(link)}
  }
  for(const s of r.notlar)details.append(el('p',s));
  const provenance=r.ekap_teyit_durumu==='EKAP_BEDELI_ESLESTI_DIGER_ALANLAR_KISMI'?'Bedel eşleşti · kısmi teyit':'Bağımsız teyit bekliyor';
  const source=el('div');source.append(el('small',provenance),details);
  const id=r.kaynak_sozlesme_sirasi==null?r.ikn:r.ikn+' · Sözleşme '+r.kaynak_sozlesme_sirasi;
  return [id,r.kategori+' · '+(r.birim??'birim belirsiz'),r.miktar==null?'—':number.format(r.miktar),
   tl(r.toplam,r.para),r.kullanilan_birim_fiyat==null?'—':tl(r.kullanilan_birim_fiyat,r.para)+' / '+(r.birim??'belirsiz'),
   r.endeksli_birim_fiyat?tl(r.endeksli_birim_fiyat,r.para)+' · '+r.endeks_iz.hedef_ay:(r.fiyat_tarihi??'tarih eksik'),source]
 }))
}
export function dosyaFiyatPanel(a){
 const section=el('section',null,'v19-file-prices report-part');
 section.append(el('p','YÜKLENEN VERİ SETİ · EKAP TEYİDİ BEKLEYEN FİYATLAR','v19-eyebrow'),el('h2','Dosyalardaki fiyatlarla ön analiz'));
 if(!a){section.append(el('p','Dosya fiyatları bu rapor sürümünde yok; raporu yenileyin.'));return section}
 section.append(el('p','Dosyadaki '+a.havuz_ozeti.benzersiz+' fiyat kaydının tamamı işlendi. Seçilen kategoride '+a.kategori_adayi+' kayıt · '+a.kullanilan_fiyat+' fiyat gösteriliyor.'));
 const items=a.grup_ozetleri.filter(s=>s.kapsam==='urun_adayi');
 for(const s of items){
  const card=el('div',null,'v19-price-card');
  card.append(el('div',tl(s.medyan,s.para)+' / '+s.birim,'estimate'),
   el('p',s.sayi+' dosya kaydı · '+s.donem+' · KDV '+s.kdv),
   el('p','Dosya fiyatları aralığı '+tl(s.alt,s.para)+' – '+tl(s.ust,s.para)),
   el('p','Dosya temelli koşullu ortanca. Kaynak fiyatlarının ve teknik eşdeğerliğin bağımsız EKAP teyidi tamamlanmadı.','muted'));
  section.append(card)
 }
 const others=a.grup_ozetleri.filter(s=>s.kapsam!=='urun_adayi');
 if(others.length)section.append(table(['Ayrı fiyat grubu','Kayıt','Birim','Fiyat esası','Özgün fiyatların ortancası'],others.map(s=>[s.kategori,s.sayi,s.birim,s.donem,tl(s.medyan,s.para)])));
 section.append(el('p','Karma alımlar ve farklı iş kapsamları ayrı gruplardadır. Hizmet/bakım fiyatları uygun endeks yoksa güncel fiyat gibi gösterilmez. Bu bölüm resmî EKAP emsalleriyle tek ortalamada birleştirilmez.','muted'));
 const candidates=a.kayitlar.filter(r=>r.kapsam==='urun_adayi');
 const mixed=a.kayitlar.filter(r=>r.kapsam==='karma_veya_teknik_eksik');
 const rest=a.kayitlar.filter(r=>!['urun_adayi','karma_veya_teknik_eksik'].includes(r.kapsam));
 for(const [title,rows] of [['A4 ürün adayları',candidates],['Karma ve teknik eksiği olan alımlar',mixed],['Kategori fiyatları',rest]]){
  if(rows.length)section.append(el('h3',title+' · '+rows.length),rowsTable(rows));
 }
 if(!a.kayitlar.length)section.append(el('p','Bu kategoriyle eşleşen dosya fiyatı bulunamadı.'));
 const all=el('a','Tüm dosya fiyatlarını Excel indir');all.href='/api/dosya-fiyatlari.xlsx';all.download='OptiBid_Tum_Dosya_Fiyatlari.xlsx';section.append(all);
 return section
}

export async function tumDosyaFiyatlari(app,home){
 app.className='v19-file-view';app.replaceChildren(el('h1','Dosyalardaki tüm fiyatlar'),el('p','Veriler okunuyor…'));
 try{
  const response=await fetch('/api/dosya-fiyatlari');if(!response.ok)throw Error('Dosya fiyatları okunamadı.');
  const data=await response.json();if(!app.isConnected)return;
  const back=el('button','Çalışmalara dön');back.onclick=home;
  const select=el('select');select.setAttribute('aria-label','Fiyat kategorisi');
  for(const text of ['Tüm kategoriler',...Object.keys(data.ozet.kategori_sayilari)]){const o=el('option',text);o.value=text;select.append(o)}
  const units=el('select');units.setAttribute('aria-label','Kaynak birimi');
  for(const unit of ['',...new Set(data.kayitlar.map(row=>row.birim).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'tr'))){
   const option=el('option',unit||'Tüm birimler');option.value=unit;units.append(option)
  }
  const download=el('a','Tüm fiyatları Excel indir');download.href='/api/dosya-fiyatlari.xlsx';download.download='OptiBid_Tum_Dosya_Fiyatlari.xlsx';
  const body=el('div'),status=el('p');
  app.replaceChildren(back,el('h1','Dosyalardaki tüm fiyatlar'),
   el('p',data.ozet.benzersiz+' benzersiz kayıt · '+data.ozet.fiyati_bulunan+' fiyat · '+data.ozet.kategori_sayisi+' kategori'),
   el('p','Aynı kayıtların kopyaları tek gözlem sayıldı. Bilinen EKAP dışı ilanlar bu fiyat analizine katılmadı. Kaynak dosyanın “Doğrulandı” etiketi bağımsız resmî teyit değildir.','muted'),select,units,download,status,body);
  const draw=()=>{
   const rows=data.kayitlar.filter(r=>(select.value==='Tüm kategoriler'||r.kategori===select.value)&&(!units.value||r.birim===units.value));
   status.textContent=rows.length+' kayıt gösteriliyor.';
   body.replaceChildren(rowsTable(rows))
  };
  select.onchange=draw;units.onchange=draw;draw()
 }catch(e){app.replaceChildren(el('h1','Dosya fiyatları'),el('p',e.message));const back=el('button','Geri');back.onclick=home;app.append(back)}
}
