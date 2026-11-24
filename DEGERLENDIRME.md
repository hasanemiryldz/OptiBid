# Değerlendirme

24 Kasım 2026 ölçümü Windows, Python 3.12.14, yerel Chrome, Ollama ve MCP stdio ortamında yapıldı. Alan karşılaştırması aynı 20 etiketli sentetik vaka ve Ollama kapalı koşulda çalıştırıldı.

| Ölçüm | Başlangıç | Güncel |
| --- | ---: | ---: |
| Doğru alan değeri | 6/20 | 20/20 |
| Doğru değer, kaynak alıntısı ve sayfa | 1/12 | 12/12 |
| Belirsiz alanı boş bırakan vaka | 5/8 | 8/8 |
| Çelişki örneğinin durumu | Eksik | Çelişkili |
| Vaka başına ortalama süre | 0,89 ms | 4,35 ms |

Sentetik örnekler genellenebilir doğruluk veya hukuk uygunluğu ölçümü değildir. Gerçek EKAP DOCX dosyasıyla ayrı bir kabul testi bulunur.

MCP maliyet aracı ve rapor üzerinden gerçek Chrome akışı 5.000 paket, 493.000 TL maliyet, 542.300 TL satış ve 108,46 TL/paket sonucu üretti. Canlı Ollama yanıtı qwen3:8b olarak döndü ve etiket digest’i kayıt altına alındı. Gerçek MCP araması, bir İKN’nin 7 alıntısı için FTS5 ve embeddinggemma sonuçlarını birleştirdi. Tüm arşivin vektörü hazırlanmadı. Reranker kullanılmadı.

Windows başlatma ölçümü aynı süreç kimliğinin yeniden kullanıldığını, durdurup açınca yeni süreç oluştuğunu ve beş hazırlığın aynı kaldığını gösterdi. Ayrı sürecin tuttuğu port korunurken test çalışması anlaşılır hata verdi. Windows oturum açılışının kendisi, işletim sistemi klavyesi, gerçek yüzde 125 Chrome yakınlaştırması ve taranmış PDF’de başarılı OCR bu oturumda sınanmadı.
