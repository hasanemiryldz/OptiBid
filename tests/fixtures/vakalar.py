"""İnsan tarafından tanımlanmış sentetik vakalar. EKAP verisine yazılmaz."""
P='Kalem adı: A4 fotokopi kâğıdı\n'

# Kimlik, sayfalar, alan, beklenen değer ve beklenen alıntının geçtiği sayfa.
CASES=[
    ('A4-koli',(P+'Miktar: 1.000 koli',),'miktar','1000',1),
    ('paket-yaprak',(P+'Her kolide 5 paket, her pakette 500 yaprak bulunur.',),'teknik:Paketteki yaprak sayısı','500',1),
    ('koli-paket',(P+'Her kolide 5 paket, her pakette 500 yaprak bulunur.',),'teknik:Kolideki paket sayısı','5',1),
    ('sayim-bosluk',(P+'Miktar: 1 000 paket',),'miktar','1000',1),
    ('gec-madde',(P+'Bilgi.\n'*250+'A4 boyut ve 80 g/m² şarttır.',),'teknik:Gramaj (g/m²)','80',1),
    ('son-sayfa',(P+'Miktar: 20 paket','Kalem için 80 g/m² istenir.'),'teknik:Gramaj (g/m²)','80',2),
    ('kutle-gramaj-degil',(P+'Paket 80 gr ağırlığındadır.',),'teknik:Gramaj (g/m²)',None,None),
    ('alternatif',(P+'Alternatif olarak 75 g/m² olabilir.',),'teknik:Gramaj (g/m²)',None,None),
    ('olumsuz',(P+'Her kolide 500 paket olmamalı.',),'teknik:Kolideki paket sayısı',None,None),
    ('yan-sayi',(P+'Sayfa referansı 500.',),'teknik:Paketteki yaprak sayısı',None,None),
    ('bilinmeyen-butce',(P+'Bütçe: Belirsiz',),'butce',None,None),
    ('bilinmeyen-ikn',(P+'İKN: Belirsiz',),'ikn',None,None),
    ('kdv-orani-teyitsiz',(P+'Örnek olayda %20 geçer.',),'kdv',None,None),
    ('odeme-kosulu',(P+'Ödeme kabul ve fatura tarihinden itibaren 30 gün içinde yapılır.',),
     'odeme','Ödeme kabul ve fatura tarihinden itibaren 30 gün içinde yapılır.',1),
    ('teslim-celiski',(P+'Teslimat 10 takvim günü içinde.','Teslimat 20 takvim günü içinde.'),'sure',None,None),
    ('sonlarda-yazilan-depo',(P,'Teslimat en geç 10 takvim günü içinde 2 depoya yapılacaktır.'),'depo','2',2),
    ('teslim-azami',(P+'Teslimat en geç 10 takvim günü içinde.',),'sure_kosulu','en_gec',1),
    ('teslim-is-gunu',(P+'Teslimat 15 iş günü içinde yapılır.',),'gun_turu','İş günü',1),
    ('bilgisayar-ram',('Kalem adı: Ofis bilgisayarı\n16 GB RAM ve 512 GB SSD gerekir.',),'teknik:RAM','16',1),
    ('tablo-toplam',('Kalem adı | Birim | Miktar\nBilgisayar | adet | 12\nToplam | adet | 12',),'miktar','12',1),
]
