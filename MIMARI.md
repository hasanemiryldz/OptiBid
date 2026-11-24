# OptiBid ihale ajanı mimarisi

## Çalışan akış

1. `baslat.py` uygulama kimliğini ve portu tek yapılandırmadan alır, SQLite göçünü yedek API’siyle yapar ve sağlık yanıtından sonra tarayıcıyı açar.
2. `sartname.py` dosya biçimini ve boyutunu denetler. PDF sayfası ve DOCX bölüm sırası korunur. OCR yalnız metinsiz PDF sayfalarında denenir. `sartname_alanlari.py` alan, ham değer, birim, alıntı, SHA-256 ve konumu bağlar.
3. Belge kuralları desteklenen alanları doldurur. qwen3:8b yalnız mevcut adayların kimliğini seçebilir. Çelişkiler ve bilinmeyenler boş kalabilir. Kullanıcının düzenlemesi kendi kökeniyle saklanır.
4. `karar-v10.js` ortak asistan kabuğudur. Senaryo `mcp_server.py` üzerinden Decimal araçlarına gider. Sunucu sonucu yerel hesapla karşılaştırır. Modelin gönderdiği serbest metin veya rakam sonuç kartına yazılmaz.
5. `belge_indeksi.py` izinli EKAP alıntıları için kalıcı FTS5 kullanır. Aynı model digest’i ve boyutuyla tamamlanan kapsam, Ollama embedding sonuçlarıyla birleştirilebilir. Ayrı reranker devrede değildir.
6. `kayitlar.py` raporu çalışma revizyonuna bağlar. JSON, Excel ve ekrandan yazdırma kayıtlı rapor sonucuna dayanır. `ekap_veri.py`, `dosya_fiyatlari.py` ve `tuik_endeks.py` kaynak kökeni ve fiyat kapsamı için ayrı kanallar tutar.

## Kapsam ve açıklar

Yükleme sınırlı süreyle HTTP isteğinde çalışır. Daha uzun işler için kalıcı belge kuyruğu ve iptal arayüzü bulunmaz. Kullanıcı şartnamesi ortak arşiv dizinine eklenmez. Doküman ve fiyat kabul kanıtlarının düzeyi ayrı gösterilir. Yeni belgenin aynı taslağa kayıt geçmişiyle uygulanması ve satır içi karmaşık revizyonların çözümü henüz kapsam dışındadır.
