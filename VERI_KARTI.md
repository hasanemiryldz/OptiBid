# Yerel veri kartı

Aşağıdaki tablo, 24 Kasım 2026 tarihinde çalıştırılan yerel envanterin gözlemidir. Dinamik veri havuzu bu sayılara sabitlenmez.

| Ölçüm | Gözlem |
| --- | ---: |
| Yüklenen fiyat kaynaklarında ham satır | 879 |
| Benzersiz fiyat kaydı | 679 |
| Birim fiyatı olan kayıt | 201 |
| Dosya kategorisi | 23 |
| İhale arşivi ham kaynak satırları | 770 |
| İhale arşivi benzersiz kimlikler | 299 |
| İKN biçimindeki kimlikler | 285 |
| EKAP kaynak kanıtıyla eşleşen kimlik | 25 |
| Kaynaklı sözleşme fiyat gözlemi | 23 |
| Kaynaklı teklif cetveli kalemi | 16 |
| İndekslenebilir arşiv alıntısı | 7.602 |
| A4 raporunda incelenen dosya fiyatı | 68 |
| A4 raporunda tarihli EKAP sözleşme gözlemi | 18 |
| A4 örneğinde doğrudan karşılaştırılabilir fiyat | 0 |

A4 raporundaki dosya beyanları ve EKAP sözleşme toplamları ayrı sunulur. Birim fiyatı kanıtlanmış bir satır, aynı Türkiye/para, teknik eşdeğerlik, KDV esası, dönem ve kapsam koşullarında doğrudan emsal olabilir. Birden fazla sözleşmesi olan ihalelerde özgün toplamlar ayrı kalır. Sözleşme toplamları asıl kalem fiyatı diye sunulmaz.

Kâğıt örneğinde kullanılan yerel TÜİK serisi C17, 2003 bazlıdır. Yereldeki son yayımlanmış ay Ekim 2026’dır. Kaynak ve hedef ay, endeks değeri, çarpan ve kaynak dosya özeti hesap izinde bulunur. Geçmiş araştırma için zamana bağlı yayımlanma sürümleri ayrıca edinilmelidir.

## Yerel veri paketi

Kişisel hazırlıklar, yüklenen belgeler ve sohbetler yerel SQLite dosyalarında korunur. Paylaşım arşivi sentetik vaka dosyalarıyla çalışır. Dağıtım yetkisi teyit edilen veri için arşiv veritabanını proje üst dizinine, EKAP kanıtlarını `data/ekap`, Yİ-ÜFE verilerini `data/tuik`, standart aktarım dosyalarını `data/alim` dizinine yerleştirin. Arşiv yolu `OPTIBID_ARSIV_DB`, veri kökü `OPTIBID_HOME` üzerinden seçilebilir.

Özgün üçüncü taraf verileri ayrı veri paketi ve kaynak manifestosuyla yönetin. Manifestoda kaynak URL, alım tarihi, sağlayıcı, yeniden dağıtım kararı ve SHA-256 tutun. Bu paket için proje lisansı atanmadı. Font lisans metinleri fontlarla birlikte yer alır.
