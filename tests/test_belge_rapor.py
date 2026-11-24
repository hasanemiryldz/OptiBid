from contextlib import closing
from io import BytesIO
import json
import sqlite3
from unittest import TestCase
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

import _ortak
import excel
import motor
import sartname
import sartname_alanlari


class BelgeRaporTesti(TestCase):
    def test_birlesik_miktar_teknik_tablo_ve_odeme_suresi(self):
        result=self.cikar('Kalem | Miktar ve birim | Ambalaj ilişkisi\n'
                          'A4 fotokopi kağıdı | 1.000 koli | Her kolide 5 paket; her pakette 500 yaprak\n'
                          'Toplam teslim miktarı | 5.000 paket | 2.500.000 yaprak',
                          'Özellik | İstenen değer\nNominal gramaj | 80 g/m²\nKağıt biçimi ve boyut | A4; 210 × 297 mm',
                          'Teslim süresi, sözleşmenin imzalandığı tarihten itibaren 10 takvim günüdür.\n'
                          'Ödeme, ürünlerin teslimi ve fatura kabulünden itibaren 30 takvim günü içinde yapılır.\n'
                          'Teklifler Türk lirası cinsinden, KDV hariç TL/paket birim fiyat üzerinden verilecektir.')
        self.assertEqual(1,len(result['kalemler']))
        f=result['alanlar']
        self.assertEqual(['1000','koli','5','500','80','A4','10','hariç'],[f[k]['deger'] for k in
            ('miktar','birim','teknik:Kolideki paket sayısı','teknik:Paketteki yaprak sayısı',
             'teknik:Gramaj (g/m²)','teknik:Boyut','sure','kdv')])

    def cikar(self,*pages,sha='a'*64):
        with patch.dict('os.environ',{'OPTIBID_LLM':'off'}):
            return sartname_alanlari.cikar(pages,sha,'pdf')

    def test_hukler_idare_ve_konum_belgeden(self):
        result=self.cikar('1.1. İdarenin adı: Örnek İdare\nİhale adı: Cihaz bakım işi',
                          '1.2. İhale kayıt no: 2026/9999\nMadde 8. Kesin teminat: Sözleşme bedelinin %6’sı\n'
                          'Madde 9. Gecikme cezası: Her gün için binde 1\nGaranti süresi: 12 ay\n'
                          'Gerekli belgeler: Yetki belgesi')
        fields=result['genel']
        self.assertEqual('Örnek İdare',fields['idare']['deger'])
        self.assertEqual('2026/9999',fields['ikn']['deger'])
        self.assertEqual('12 ay',fields['garanti']['deger'])
        self.assertEqual('Yetki belgesi',fields['belge']['deger'])
        self.assertEqual('Sayfa 2 · Madde 8',fields['teminat_kesin']['kural']['konum'])
        self.assertEqual('Her gün için binde 1',fields['ceza']['deger'])
        self.assertIsNone(fields['teminat_gecici']['deger'])

    def test_hizali_pdf_tablosunda_miktar_birim_kapsami(self):
        text=('Kalem adı                   Miktar   Birim\n'
              'A4 fotokopi kâğıdı          1.200    paket\n'
              'Mikroskop bakım hizmeti     3        adet\n'
              'Toplam                      1203     adet')
        result=self.cikar(text)
        a,b=result['kalemler']
        self.assertEqual(('1200','paket','3','adet'),tuple(
            item['alanlar'][field]['deger'] for item in (a,b) for field in ('miktar','birim')))
        self.assertEqual(1,b['alanlar']['miktar']['kural']['sayfa'])

    def test_belge_adi_ve_boslugun_ayni_snapshot_excelde_korunmasi(self):
        book=excel.rapor_excel({
            'belge':{'kalemler':[{'id':'x','ad':None}],'rev':3},'tarih':'2026-11-24',
            'sonuc':{'sartname_durumu':{'sha':'a'*64,'belge_adi':'Örnek şartname.pdf',
                     'kanitlar':{'genel':{'idare':{'etiket':'İdare','deger':'Örnek İdare','tur':'kaynak_bulgusu',
                                                  'konum':'Sayfa 1'},
                                        'garanti':{'etiket':'Garanti','deger':None,'durum':'eksik'}}}}}})
        with ZipFile(BytesIO(book)) as zipped:
            root=ElementTree.fromstring(zipped.read('xl/worksheets/sheet1.xml'))
        words=[element.text for element in root.iter() if element.tag.endswith('}t')]
        for value in ['Örnek şartname.pdf','Örnek İdare','Belgede bulunamadı','Sayfa 1']:
            self.assertIn(value,words)

    def test_kategori_bilinmiyorsa_belge_raporu_fiyat_uydurmaz(self):
        doc={'ihale_turu':None,'kategori':[],'kalemler':[{'id':'a','ad':'Mikroskop','kategori_belirsiz':True}],
             'teklifler':[]}
        with patch('ekap_veri.snapshot',return_value=([],{}, {'surum':'fixture'})):
            r=motor.analiz(doc)
        self.assertEqual('Kısmi belge raporu',r['durum'])
        self.assertNotIn('medyan',r)
        self.assertEqual([],r['emsaller'])

    def test_model_baglanti_hatasinda_belge_kaniti_korunur(self):
        with patch.dict('os.environ',{'OPTIBID_LLM':'on'}), patch('ajan.model_sec',side_effect=ConnectionRefusedError):
            result=sartname_alanlari.cikar(['İdare: Örnek İdare'],'b'*64)
        self.assertIn('doğrulanamadı',result['model_durumu'])
        self.assertEqual('Örnek İdare',result['genel']['idare']['deger'])
        self.assertIsNone(result['ollama_izi'])

    def test_iki_dosya_kaynak_adlari_ve_kanitlari_ayri(self):
        first=self.cikar('İdare: Birinci İdare',sha='a'*64)
        second=self.cikar('Garanti süresi: 12 ay',sha='b'*64)
        with closing(sqlite3.connect(':memory:')) as db:
            sartname.init(db)
            sartname.sakla(db,'a'*64,'.pdf',['İdare: Birinci İdare'],BytesIO(b'a'),'İlk.pdf')
            sartname.sakla(db,'b'*64,'.pdf',['Garanti süresi: 12 ay'],BytesIO(b'b'),'İkinci.pdf')
            sartname.cikarim_sakla(db,'a'*64,3,first)
            sartname.cikarim_sakla(db,'b'*64,3,second)
            self.assertEqual('İkinci.pdf',sartname.sayfalar(db,'b'*64)[1])
            self.assertIsNone(sartname.cikarim_oku(db,'b'*64)['genel']['idare']['deger'])
            self.assertEqual('Birinci İdare',sartname.cikarim_oku(db,'a'*64)['genel']['idare']['deger'])
