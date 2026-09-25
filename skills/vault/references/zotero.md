# Zotero'dan literatür notu

Bu dosya yalnızca Zotero ile çalışırken okunur. Bir Zotero MCP sunucusu gerekir. Araçlar yoksa kullanıcıya söyle ve normal PDF işleme akışına dön.

**Araç adları sunucuya göre değişir.** Adına değil işlevine göre eşleştir:

| İşlev | Örnek adlar |
|---|---|
| Arama (etiket filtresiyle) | `zotero_search_items` |
| Metadata | `zotero_item_metadata`, `zotero_get_item_metadata` |
| Tam metin | `zotero_item_fulltext`, `zotero_get_item_fulltext` |
| Koleksiyon içeriği (varsa) | `zotero_get_collection_items` |

Aşağıda kısa olsun diye ilk sütundaki adlar kullanılıyor.

## Kimlik: item key

Bir makalenin vault'taki kimliği Zotero **item key**'idir (ör. `TWC7S8K9`). Not adıyla eşleştirme yapma: Zotero'daki yıl (çevrimiçi yayın) ile notta kullanılan yıl (basılı cilt) farklı olabilir, yazar adında yazım hatası olabilir.

## Proje ↔ Zotero etiketi

Proje sayfasının frontmatter'ında `zotero-etiket: <etiket>` durur (ör. `dental-1002A`). Projenin makaleleri = Zotero'da bu etiketi taşıyan kayıtlar. Sunucunun koleksiyon aracı varsa ve kullanıcı makalelerini etiketle değil koleksiyonla düzenliyorsa `zotero-koleksiyon: <ad>` da kullanılabilir. Alan yoksa kullanıcıya hangi etiketi kullandığını sor ve proje sayfasına yaz. Etiketi olmayan bir makalenin hangi projeye ait olduğunu kullanıcıya sor.

## Komutlar

**Tek makale** ("bu makaleyi Zotero'dan işle", "Zotero'da X'i bul ve ekle"): `zotero_search_items` ile ara. Birden fazla sonuç varsa listele ve seçtir. Sonra aşağıdaki akışla işle.

**Senkron** ("Zotero'yu senkronla", "projedeki yeni makaleleri işle"):
1. `zotero_search_items(query="", tag="<zotero-etiket>", limit=100)` ile projenin kayıtlarını al. **Zotero API'si istek başına en fazla 100 kayıt döndürür** ve arama aracında sayfa (offset) parametresi yoksa limiti artırmak işe yaramaz. Dönen sayı 100 ya da verdiğin limite eşitse liste eksik olabilir: bunu kullanıcıya söyle ve aramayı böl (ör. `query` ile yıl ya da yazar aralıkları, `qmode="titleCreatorYear"`). Bölünmüş sonuçları item key'e göre birleştir. Eksik olabilecek bir listeyi "tamamı" diye raporlama.
2. Vault'ta `zotero-key:` değerlerini Grep ile topla. Yalnızca notu olmayan anahtarları işle.
3. İşlenecekleri başlık ve yıl ile listele. 5'ten fazlaysa işlemeden önce onay al (her makale tam metin okuması demek).

## Bir makaleyi işleme

1. **Tekrar kontrolü:** `zotero-key: <KEY>` vault'ta varsa yeni not açma; o notu güncelle. Anahtar yok ama `doi: <DOI>` eşleşiyorsa bu, anahtar eklenmemiş eski bir nottur: frontmatter'a `zotero-key` ekle, yeni not açma.
2. **Oku:** Önce `zotero_item_metadata`, sonra `zotero_item_fulltext`. Tam metin dönmezse ("No suitable attachment") not yalnızca özete dayanır:
   - frontmatter'a `içerik: özet` yaz (tam metin okunduysa `içerik: tam-metin`),
   - başlığın altına şu callout'u koy ve özette olmayan sayı, yöntem ya da sonuç yazma:
     `> [!note] Özete dayalı` / `> Tam metin Zotero'da yok; bu not yalnızca özete dayanıyor.`
   - Tam metin aracı PDF'i bulup metni çıkaramadığını söylerse (ör. "text extraction is not possible", taranmış ya da görüntü tabanlı PDF) de aynı şekilde `içerik: özet` yaz. Callout'ta sebebi belirt (`> PDF taranmış görünüyor; metin çıkarılamadı.`) ve kullanıcıya PDF'e OCR uygulamasını öner (ör. OCRmyPDF, Adobe). Hata mesajını tam metin sanıp not yazma.
   - Kullanıcıya PDF'i Zotero'ya ekleyip notu tam metinle güncelletebileceğini söyle. Güncellerken `içerik: tam-metin` yap, callout'u kaldır ve özetten gelen sayıları tam metinle doğrula.
   - Birçok kayıt için PDF durumunu öğrenmek istenirse `zotero_item_fulltext`'i toplu çağırma: PDF olan her kayıt makalenin tamamını döndürür. Tek bir kayıtta dene; sonuç "No suitable attachment" ise kütüphanede ek olup olmadığını kullanıcıya sor.
3. **Ad:** `<İlk yazarın soyadı> <yıl> - <kısa Türkçe başlık>.md`. Yıl Zotero'daki tarihten alınır. Ad vault'ta benzersiz olmalı.
4. **Şüpheli metadata:** Yazar adında bariz yazım hatası (ör. `Lovelh` → `Lovell`) ya da Zotero yılı ile derginin basılı yılı arasında fark görürsen, notta doğrusunu kullan ve kullanıcıya Zotero'da düzeltmesini öner. Zotero'yu değiştirme.
5. **Yaz:** Aşağıdaki şablonla projenin `Literatür/` klasörüne. İlgili kavram sayfalarına ve öteki literatür notlarına wikilink ver.
6. **Güncelle:** Proje sayfasındaki literatür listesi, gerekiyorsa kavram ve kategori sayfaları, proje log'u (`zotero: <KEY> → [[<not>]]`).

## Şablon

```markdown
---
tags: [literatür, <konu>, proje/<kısa-ad>]
proje: "[[<Ad> Projesi]]"
created: YYYY-MM-DD
updated: YYYY-MM-DD
zotero-key: TWC7S8K9
doi: 10.1016/j.dental.2009.02.010
yıl: 2009
yazarlar: ["Musanje, L.", "Ferracane, J. L.", "Sakaguchi, R. L."]
dergi: "Dental Materials 25(8), 994–1000"
içerik: tam-metin            # ya da: özet
sources: ["https://doi.org/10.1016/j.dental.2009.02.010"]
---
# <Yazarlar> <yıl> — <Türkçe başlık>

**DOI:** https://doi.org/<doi> · [Zotero'da aç](zotero://select/library/items/<KEY>) · *<Dergi>*

## Ne yapıyor?
Soru, yöntem ve veri: 2-4 cümle.

## Önemli noktalar
- Bulgular; sayılar kaynaktaki gibi.

## Projemiz için anlamı
Bu makale projede neyi destekliyor, neyi sorgulatıyor, hangi kararı etkiliyor.

## İlişkili
[[Kavram]] · [[Başka makale notu]]
```
