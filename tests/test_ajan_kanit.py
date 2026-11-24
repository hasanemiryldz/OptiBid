from contextlib import closing
from copy import deepcopy
from io import BytesIO
import json
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

from _ortak import ROOT
import arastirma
import asistan
import baslat
import belge_indeksi
import ekap_veri
import motor
import sqlite3
import sartname
import sartname_alanlari
import senaryo
from hesap_araclari import birim_donustur

PAPER='Kalem adı: A4 fotokopi kâğıdı\n'
PAPER_SPEC='Miktar: 1.000 koli\nHer kolide 5 paket, her pakette 500 yaprak bulunur.\nA4 boyut ve 80 g/m² şarttır.'


class SourceTests(TestCase):
    def cikar(self,*pages):
        with patch.dict('os.environ',{'OPTIBID_LLM':'off'}):
            return sartname_alanlari.cikar(pages,'a'*64)

    def test_a4_ambalaj_ve_kapsam(self):
        r=self.cikar(PAPER+PAPER_SPEC+'\nTeslimat sözleşmeden itibaren 10 takvim günü içinde 1 depoya yapılacaktır.',
                     'Kalem adı | Birim | Miktar\nTOPLAM | koli | 1000')
        f=r['alanlar']
        self.assertEqual(1,len(r['kalemler']))
        self.assertEqual('5000',birim_donustur(f['miktar']['deger'],'koli','paket',
                                             f['teknik:Kolideki paket sayısı']['deger'])['miktar'])
        self.assertEqual('500',f['teknik:Paketteki yaprak sayısı']['deger'])
        self.assertEqual(('80','A4','10','Takvim günü','1'),tuple(f[k]['deger'] for k in
              ('teknik:Gramaj (g/m²)','teknik:Boyut','sure','gun_turu','depo')))
        self.assertIn('sözleşmeden itibaren',f['baslangic']['deger'])
        self.assertEqual('a'*64,f['miktar']['kural']['belge_sha256'])
        self.assertEqual('1.000',f['miktar']['kural']['ham_deger'])

    def test_son_bolum_ve_celiski(self):
        r=self.cikar(PAPER+('Başka açıklama\n'*180)+PAPER_SPEC,
            'Teslim süresi: 10 takvim günü.\nTeslimat 20 takvim günü sürer.\n'
            'Ödeme kabul ve fatura tarihinden itibaren 30 gün içinde yapılır.\nİKN: Belirsiz\nBütçe: Gizli')
        g=r['genel']
        self.assertEqual('80',r['alanlar']['teknik:Gramaj (g/m²)']['deger'])
        self.assertIsNone(g['sure']['deger'])
        self.assertEqual('uyuşmuyor',g['sure']['durum'])
        self.assertEqual({'10','20'},{c['deger'] for c in g['sure']['adaylar']})
        self.assertIn('kabul ve fatura',g['odeme']['deger'])
        self.assertIsNone(g['butce']['deger'])
        self.assertIsNone(g['ikn']['deger'])

    def test_olumsuz_alternatif_ve_alakasiz_sayi(self):
        r=self.cikar(PAPER+'500 adet sandalye açıklaması.\nHer kolide 500 paket olmamalı.\n'
                     'Alternatif olarak 75 g/m² olabilir.\nKalem adı: Alternatif fotokopi kâğıdı\nMiktar: 300 paket')
        for k in ('teknik:Kolideki paket sayısı','teknik:Gramaj (g/m²)','miktar','kdv'):
            self.assertIsNone(r['alanlar'][k]['deger'])

    def test_farkli_kalem_kapsamlari(self):
        r=self.cikar(PAPER+'Miktar: 1 000 paket\n80 g/m² zorunludur.\n'
                     'Kalem adı: Ofis bilgisayarı\nMiktar: 12 adet\n16 GB RAM ve 512 GB SSD gerekir.')
        p,c=r['kalemler']
        self.assertEqual('1000',p['alanlar']['miktar']['deger'])
        self.assertEqual(['Mal','Bilişim','Bilgisayar'],c['kategori'])
        self.assertEqual('16',c['alanlar']['teknik:RAM']['deger'])
        self.assertNotIn('teknik:RAM',p['alanlar'])
        self.assertNotIn('teknik:Gramaj (g/m²)',c['alanlar'])

    def test_kullanici_beyani_sahte_etikete_donusmez(self):
        r=self.cikar(PAPER+PAPER_SPEC)
        d={'ihale_turu':'Mal','kategori':['Kırtasiye','Kâğıt'],'teslimat':{},'tamam':False,
           'kalemler':[{'id':'a','kaynak_kalem':'kalem-1','miktar':'888','birim':'koli','teknik':{}}],
           'ek_bilgiler':{'sartname':{'sha':'a'*64,'kanitlar':{'a':{'miktar':{'tur':'kaynak_bulgusu'}}}}}}
        sartname.taslak_kanitlari(d,r)
        proof=d['ek_bilgiler']['sartname']['kanitlar']['a']['miktar']
        self.assertEqual('kullanici_beyani',proof['tur'])
        self.assertEqual('1000',proof['onceki']['deger'])

    def test_model_dogru_kimlige_yanlis_iddia_baglayamaz(self):
        fake={'content':json.dumps({'kimlikler':['KALEM-1'],'metin':'İstek 5 değil, fiyat 5 TL.'})}
        with patch('ajan.model_sec',return_value=fake):
            r=asistan.genel(None,'Fiyat 5 TL mi?',context={'kalemler':[{'miktar':'5','birim':'paket'}]})
        self.assertEqual('yerel',r['mod'])
        self.assertEqual([],r['claims'])
        self.assertNotIn('fiyat 5 TL',r['metin'])

    def test_web_giris_sayfasi(self):
        url='https://ekap.kik.gov.tr/EKAP/Ortak/BirBakistaIhale.aspx'
        body=b'<html><body><form><input type=password></form>'+b'normal page text '*20+b'</body></html>'
        with patch('arastirma.indir',return_value=(body,'text/html',url)):
            result=arastirma.oku(url)
        self.assertEqual('okunamadı',result['durum'])
        self.assertFalse(result['fiyat_teyidi'])

    def test_bagimsiz_maliyet_ve_sahte_arac_sonucu(self):
        args=dict(miktar='2500',alis='50',nakliye='4000',diger='1000',finansman='0',oran='5',esas='maliyet')
        self.assertEqual('54.60',senaryo.hesap(**args)['birim_teklif'])
        snap=dict(belge={'id':'deneme','rev':2,'kalemler':[]},sonuc={'birim':'paket','standart_miktar':'2500'})
        async def fake(values):
            answer=senaryo.hesap(**values)
            return {**answer,'birim_teklif':'54.61'},{}
        with patch('senaryo.arac',side_effect=fake):
            reply=senaryo.cevap(snap,'KDV hariç alış 50 TL/paket, nakliye 4.000, diğer gider 1.000, finansman 0. Maliyet üzerine %5.')
        self.assertEqual('CONFLICT',reply['answer_status'])
        self.assertNotIn('hesap',reply)

    def test_txt_yanlis_imza_ve_docx_tablo(self):
        source=(PAPER+PAPER_SPEC).encode()
        _,ext,pages,_=sartname.oku(BytesIO(source),len(source),'txt')
        self.assertEqual('.txt',ext)
        with self.assertRaisesRegex(ValueError,'PDF veya DOCX'):
            sartname.oku(BytesIO(source),len(source),'pdf')
        b=BytesIO()
        word='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        def row(values):
            return '<w:tr>'+''.join('<w:tc><w:p><w:r><w:t>'+s+'</w:t></w:r></w:p></w:tc>' for s in values)+'</w:tr>'
        with ZipFile(b,'w') as z:
            z.writestr('[Content_Types].xml','application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml')
            z.writestr('word/document.xml',f'<w:document xmlns:w="{word}"><w:body><w:tbl>'+
                       row(['Kalem adı','Birim','Miktar'])+row(['Bilgisayar','adet','12'])+
                       row(['Toplam','adet','12'])+'</w:tbl></w:body></w:document>')
        _,ext,pages,_=sartname.oku(BytesIO(b.getvalue()),len(b.getvalue()),'docx')
        r=self.cikar(*pages)
        self.assertEqual(1,len(r['kalemler']))
        self.assertEqual('12',r['alanlar']['miktar']['deger'])

    def test_fts_konumu_fiyata_donusmez(self):
        db=self.enterContext(closing(sqlite3.connect(':memory:')))
        keep=('2026/888','sentetik.txt','a'*64,2,'A4 fotokopi için bir depo gerekir.',None,'["Kâğıt"]',None)
        other=('2026/889','sentetik.txt','b'*64,7,'A4 fotokopi için iki depo gerekir.',None,'["Kâğıt"]',None)
        belge_indeksi.initialize(db,[keep,other])
        result,=belge_indeksi.search(db,'A4 fotokopi " OR *','2026/888')
        self.assertEqual((keep[0],keep[2],keep[3],keep[4]),
                         (result['ikn'],result['sha256'],result['satir'],result['alinti']))
        self.assertEqual('FTS5',result['yontem'])
        belge_indeksi.initialize(db,[other])
        self.assertEqual([],belge_indeksi.search(db,'A4','2026/888'))

    def test_azami_teslim_ayni_esasla(self):
        base={'gun_turu':'Takvim günü','baslangic':'Sözleşmeden itibaren'}
        goal={**base,'sure':'10'}
        offer={**base,'teslim_suresi':'8'}
        self.assertFalse(motor.teslim_karsilastir(goal,offer))
        self.assertTrue(motor.teslim_karsilastir({**goal,'sure_kosulu':'en_gec'},offer))
        self.assertFalse(motor.teslim_karsilastir({**goal,'sure_kosulu':'en_az'},offer))
        self.assertFalse(motor.teslim_karsilastir({**goal,'sure_kosulu':'en_gec'},{**offer,'gun_turu':'İş günü'}))
        self.assertFalse(motor.teslim_karsilastir({**goal,'sure_kosulu':'en_gec'},{**offer,'baslangic':'Siparişten itibaren'}))

    def test_farkli_fiziksel_birimlerde_parasal_toplam(self):
        base=motor.oku('kagit_ornegi.json')
        a,b=deepcopy(base['kalemler'][0]),deepcopy(base['kalemler'][0])
        a.update(id='x',ad='Bağlantı cihazı',birim='adet',miktar='2')
        b.update(id='y',ad='Destek süresi',birim='saat',miktar='7')
        doc={**base,'kalemler':[a,b],'teklifler':[]}
        common={'kdv':'hariç','ay':'2026-06','para_birimi':'TRY','degerlendirme_surumu':'sentetik-fixture'}
        first={**common,'birim':'adet','toplam':'230.11'}
        second={**common,'birim':'saat','toplam':'111.89'}
        with patch('ekap_veri.snapshot',return_value=([],{}, {'surum':'sentetik-fixture'})), \
             patch('ekap_veri.degerlendir',side_effect=[first,second]):
            result=motor.analiz(doc)
        self.assertEqual('342.00',result['toplam'])
        self.assertNotIn('standart_miktar',result)
        with patch('ekap_veri.snapshot',return_value=([],{}, {'surum':'sentetik-fixture'})), \
             patch('ekap_veri.degerlendir',side_effect=[first,{**second,'para_birimi':'EUR'}]):
            self.assertNotIn('toplam',motor.analiz(doc))

    def test_farkli_sozlesmeler_tek_ikn_olsa_da_korunur(self):
        doc=motor.oku('kagit_ornegi.json')
        two=dict(tur=doc['ihale_turu'],kategori=doc['kategori'],sozlesmeler=[
            dict(fiyat='1000.00',para='TRY',konum='Web metni 11',tarih='2025-06-01'),
            dict(fiyat='2000.00',para='TRY',konum='Web metni 15',tarih='2025-06-03')])
        rows=ekap_veri.coklu_sozlesmeler({'2025/876':two},doc)
        self.assertEqual([(1,'1000.00'),(2,'2000.00')],[(r['sira'],r['tutar']) for r in rows])
        self.assertEqual([],ekap_veri.nominal({'2025/876':two},doc))
