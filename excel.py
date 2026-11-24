import io
import re
from decimal import Decimal
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

def excel(rows):
    if not isinstance(rows,list) or len(rows)>1048576:raise ValueError()
    xml=[]
    for n,row in enumerate(rows,1):
        if not isinstance(row,list) or len(row)>20:raise ValueError()
        cells=''.join(f'<c r="{chr(65+i)}{n}" t="n"><v>{v}</v></c>' if isinstance(v,Decimal)
                      else f'<c r="{chr(65+i)}{n}" t="inlineStr"><is><t xml:space="preserve">{xml_text(v)}</t></is></c>'
                      for i,v in enumerate(row))
        xml.append(f'<row r="{n}">{cells}</row>')
    buf=io.BytesIO()
    ns='http://schemas.openxmlformats.org/'
    with ZipFile(buf,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',f'<Types xmlns="{ns}package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        def rel(file,kind,target):
            z.writestr(file,f'<Relationships xmlns="{ns}package/2006/relationships"><Relationship Id="rId1" Type="{ns}officeDocument/2006/relationships/{kind}" Target="{target}"/></Relationships>')
        rel('_rels/.rels','officeDocument','xl/workbook.xml')
        rel('xl/_rels/workbook.xml.rels','worksheet','worksheets/sheet1.xml')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}spreadsheetml/2006/main" xmlns:r="{ns}officeDocument/2006/relationships"><sheets><sheet name="OptiBid" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="6" width="30" customWidth="1"/><col min="7" max="7" width="70" customWidth="1"/><col min="8" max="20" width="27" customWidth="1"/></cols><sheetData>{"".join(xml)}</sheetData></worksheet>')
    return buf.getvalue()

def xml_text(value):
    return escape(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]','',str(value) if value is not None else '')[:32767])

def rapor_excel(snapshot,scenarios=()):
    doc=snapshot["belge"]
    r=snapshot["sonuc"]
    def money(v):return Decimal(v) if v is not None else None
    source=r.get('sartname_durumu') or {}
    general=(source.get('kanitlar') or {}).get('genel',{})
    subject=(general.get('ihale_adi') or {}).get('deger') or ', '.join(x['ad'] for x in doc['kalemler'] if x.get('ad'))
    rows=[["OptiBid",subject or 'İhale raporu'],
          ["Rapor tarihi",snapshot['tarih']],["Durum",r.get("durum"),r.get("neden")],
          ["Dönem",r.get("ay") or (r.get('endeks') or {}).get('son_ay')],
          ["Hedef KDV esası",r.get("kdv")],["Veri sürümü",r.get("veri_surumu")],
          ["Çalışma revizyonu",doc.get('rev')],
          ["Hesap aracı",(r.get('hesap_izi') or {}).get('arac')],
          ["Ortanca birim fiyat",money(r.get("medyan")),r.get('birim')],["Toplam",money(r.get("toplam")),r.get('para_birimi')]]
    if source.get('sha'):
        rows.append(['Şartname SHA-256',source['sha'],(source.get('okuma') or {}).get('durum'),
                     'İnceleme tamamlandı' if source.get('inceleme_tamamlandi') else 'İnceleme sürüyor'])
        rows.append(['Şartname dosyası',source.get('belge_adi')])
        if source.get('model_durumu'):
            rows.append(['Ollama',source['model_durumu']])
        rows.append(['Kapsam','Alan','Değer','Durum','Tür','Kaynak konumu','Kaynak alıntısı'])
        names={item['id']:item['ad'] for item in doc['kalemler']}
        for scope,fields in (source.get('kanitlar') or {}).items():
            for field,proof in fields.items():
                label=proof.get('etiket') or field
                state={'eksik':'Belgede bulunamadı','uyuşmuyor':'Çelişkili kaynaklar'}.get(proof.get('durum'),proof.get('durum'))
                rows.append([names.get(scope) or 'Genel',label,proof.get('deger'),state,proof.get('tur'),
                             proof.get('konum'),proof.get('alinti') or ' / '.join(
                                 ' · '.join(filter(None,(p.get('konum'),p['alinti']))) for p in proof.get('adaylar',[]) if p.get('alinti'))])
        rows.append(['Teklif senaryosu','Alış fiyatı, giderler, KDV esası ve kâr/marj bilgisi gerekir.'] if not scenarios else
                    ['Teklif senaryosu','Seçilen hesaplar aşağıda yer alıyor.'])
    rows.append(["İKN","Tarih","Miktar","Birim","Özgün birim fiyat","İşlenmiş birim fiyat","Kaynak"])
    rows.extend([e["ikn"],e["tarih"],money(e["miktar"]),e["birim"],money(e["ham_birim"]),money(e.get('islenmis_birim') or e.get('donusturulmus')),e["kaynak"]]
                for e in r.get("emsal_ayrinti",[]))
    reports = r.get('kalem_sonuclari') or [{'ad':next(iter(doc['kalemler']),{}).get('ad'),'sonuc':r}]
    if r.get('kalem_sonuclari'):
        rows.append(['Kalem','Kategori','Birim','Ortanca','Kalem toplamı','Durum'])
        for item in reports:
            result = item['sonuc']
            rows.append([item['ad'],' / '.join(item['kategori']),result.get('birim'),money(result.get('medyan')),
                         money(result.get('toplam')),'Mükerrer' if item['mukerrer'] else result['durum']])
    for item in reports:
        vat_scenarios = item['sonuc'].get('kdv_senaryolari')
        if vat_scenarios:
            rows.append(['KDV esası belirsiz: iki senaryo',item['ad'],
                         vat_scenarios['ay'],vat_scenarios['birim'],'Varsayılan oran (%)',vat_scenarios['oran']])
            rows.append(['Varsayım','Dönem','Gözlem sayısı','En düşük','Ortanca','En yüksek'])
            for key,title in (('haric_varsayimi','Kaynakta KDV hariç'),('dahil_varsayimi','Kaynakta KDV dahil')):
                for scope,label in (('ufuk_ici','Ufuk içi'),('duyarlilik','Duyarlılık')):
                    s=vat_scenarios[key][scope]
                    rows.append([title,label,s['sayi'],money(s['alt']),money(s['medyan']),money(s['ust'])])
    files=r.get('dosya_fiyat_analizi')
    if files:
        rows.append(['YÜKLENEN DOSYA FİYATLARI — EKAP TEYİDİ AYRI',files['havuz_ozeti']['benzersiz'],
                     'Seçilen kategori',files['kategori_adayi'],'Fiyat gösterilen',files['kullanilan_fiyat']])
        rows.append(['Dosya fiyat grubu','Kayıt','Birim','Fiyat esası','Ortanca','Alt','Üst','KDV'])
        rows.extend([s['kategori'],s['sayi'],s['birim'],s['donem'],money(s['medyan']),money(s['alt']),money(s['ust']),s['kdv']]
                    for s in files['grup_ozetleri'])
        rows.extend(dosya_fiyat_satirlari(files['kayitlar']))
    for s in r.get('kosullu_ozetler',[]):
        rows.extend([['Koşullu fiyat referansı / '+s['birim'],money(s['medyan']),'KDV '+s['kdv'],s['ay']],
                     ['Gözlem sayısı',s['sayi']],['Koşullu alt / üst',money(s['alt']),money(s['ust'])],
                     ['Varsayımlar',' / '.join(s['varsayimlar'])],
                     ['Sınır','Doğrulanmış piyasa fiyatı veya teklif önerisi değildir.']])
    if r.get('fiyat_referanslari'):
        rows.append(['Koşullu birim fiyat / İKN','Miktar','Kaynak birimi','Özgün birim fiyat',
                     'Endeksli birim fiyat','Hedef birim','Ay','KDV','Teknik eşleşme','Varsayımlar','Kaynak'])
        for e in r['fiyat_referanslari']:
            rows.append([e['ikn'],money(e['miktar']),e['kaynak_birim'],money(e['ham_birim']),
                         money(e['islenmis_birim']),e['birim'],e.get('hedef_ay'),e.get('kdv') or 'belirsiz',
                         'Hedef profil eşleşti' if e['teknik_eslesme'] else 'Teknik eksik',
                         ' / '.join(e['varsayimlar']),e.get('kaynak_url') or e['kaynak']])
    if r.get("nominal"):
        rows.append(["Tarihli EKAP bedelleri","İmza tarihi","Özgün bedel","Para","Kaynak",
                     "Endeksli nominal bedel","Yİ-ÜFE hedef ayı","Endeks dayanağı","Kaynak ayı","Çarpan",
                     "Kaynak miktarı","Kaynak birimi","Kaynak alıntısı","Grup","Dışlama nedeni","EKAP adresi","Türetilmiş nominal birim","Endeksli birim","KDV","Zaman ufku"])
        for o in r['nominal']:
            index=o.get('endeks_iz') or {}
            item=o.get('teklif_cetveli') or {}
            rows.append([o['ikn'],o['tarih'],money(o['fiyat']),o['para'],o['kaynak'],
                         money(index.get('tutar_endeksli')),index.get('hedef_ay'),index.get('bulten'),
                         index.get('kaynak_ay'),index.get('carpan'),money(item.get('miktar')),item.get('birim'),
                         ' / '.join(item.get('alinti',[])),o.get('grup'),o.get('neden') or o.get('endeks_eksik'),o.get('kaynak_url') or o.get('ekap_arama'),
                         money((o.get('turetilmis_birim') or {}).get('tutar')),money((o.get('endeksli_birim') or {}).get('tutar')),
                         o.get('kdv') or 'Belirsiz', f"Ufuk dışı ({abs(o['ufuk']['ay'])} ay)" if (o.get('ufuk') or {}).get('disinda') else None])
    if r.get('ayri_sozlesmeler'):
        rows.append(['Çok sözleşmeli İKN','Sözleşme sırası','Özgün toplam','Para','Tarih','KDV','Konum','EKAP sayfası'])
        rows.extend([x['ikn'],x['sira'],money(x['tutar']),x['para'],x['tarih'],x['kdv'],x['konum'],x['url']]
                    for x in r['ayri_sozlesmeler'])
    if r.get('teklifler'):
        rows.append(['Firma teklifi','Tutar','Para','KDV esası','Teslim süresi','Gün türü','Karşılaştırma'])
        rows.extend([t['firma'],money(t.get('tutar')),t.get('para'),t.get('kdv'),t.get('gun'),t.get('gun_turu'),
                     'Aynı esasta en düşük' if t.get('en_dusuk') else 'Kapsam eşleşti' if t.get('karsilastirilabilir') else 'İnceleme gerekli']
                    for t in r['teklifler'])
    if scenarios:
        rows.append(["Seçili senaryo","Toplam maliyet","Birim teklif","Satış","Kâr"])
        rows.extend([s["id"],*[money(s["hesap"][k]) for k in ("maliyet","birim_teklif","satis","kar")]] for s in scenarios)
    rows.append(["Dışlanan İKN","Gerekçe"])
    rows.extend(r.get("haric",[]))
    rows.append(["Taslak karar desteğidir. Teknik ve hukuki kontrol gerekir."])
    return excel(rows)


def dosya_fiyat_satirlari(records):
    def amount(v):return Decimal(str(v)) if v is not None else None
    rows=[['Dosya kimliği','Kategori','Kalem adı','Miktar','Birim','Para','Kaynak birim fiyatı',
           'Toplam/miktar fiyatı','Endeksli birim fiyatı','Ortak ay','KDV','Teyit durumu','Kaynak satırları','Notlar',
           'Gösterilen birim fiyat','Fiyatın hesap esası','Sözleşme toplamı','Fiyat tarihi','Sözleşme sırası','EKAP kaynağı']]
    for r in records:
        rows.append([r['ikn'],r['kategori'],r.get('ad'),amount(r['miktar']),r['birim'],r['para'],
                     amount(r['kaynak_birim_fiyat']),amount(r['toplam_miktar_birim_fiyat']),
                     amount(r['endeksli_birim_fiyat']),(r.get('endeks_iz') or {}).get('hedef_ay'),
                     r['kdv'],r['ekap_teyit_durumu'],
                     ' / '.join(s['dosya']+' · '+s['konum'] for s in r['kaynaklar']),' / '.join(r['notlar']),
                     amount(r.get('kullanilan_birim_fiyat')),r.get('fiyat_yontemi'),amount(r.get('toplam')),
                     r.get('fiyat_tarihi'),r.get('kaynak_sozlesme_sirasi'),
                     ' / '.join(s['url'] for s in r['kaynaklar'] if s.get('url'))])
    return rows


def dosya_fiyat_excel(inventory):
    rows=[['OptiBid — Tüm dosya fiyatları'],['Kaynak politikası',inventory['source_policy']],
          ['Fiyat envanteri sürümü',inventory['surum']],
          ['Benzersiz kayıt',inventory['ozet']['benzersiz']],['Fiyatı bulunan',inventory['ozet']['fiyati_bulunan']],
          ['Kategori',inventory['ozet']['kategori_sayisi']],
          ['Bu fiyatlar resmî teyitli piyasa fiyatı değildir; kategori, kapsam, birim, KDV ve tarih ayrımları korunur.']]
    rows.extend(dosya_fiyat_satirlari(inventory['kayitlar']))
    return excel(rows)
