---
name: vault
description: Kullanıcının Obsidian vault'unu proje bazlı kişisel wiki olarak yönetir. Bilgi kaydetme, kaynak işleme (PDF, link, metin → bağlantılı notlar), notlarda arama ve notlara dayalı cevap verme, projeyi vault'a ekleme, vault bakımı. Use when the user says "vault'a kaydet", "notlarıma ekle", "notlarımda ara", "notlarıma göre", "bunu işle", "bu projeyi vault'a ekle", "obsidian", "wiki'ye ekle", "ders notu", or asks something that their notes may answer. Also for Zotero: "Zotero'dan işle", "Zotero'yu senkronla", "import from Zotero".
---

# Vault (proje bazlı LLM-wiki)

## Vault yolu

Vault yolu `CLAUDE.md` dosyalarındaki `vault: <yol>` satırından okunur. Sırayla şunlara bak:

1. Çalışılan projenin `CLAUDE.md` dosyası (o projeye özel vault)
2. Global `~/.claude/CLAUDE.md` (varsayılan vault)
3. İkisinde de yoksa kullanıcıya vault yolunu sor. Global `CLAUDE.md`'ye `vault: <yol>` satırını eklemeyi teklif et; bir daha sorulmasın.

Git Bash'te Windows yolunu çevir: `C:\...\Vault` → `/c/.../Vault`. Yol boşluk içerebilir, tırnak içinde kullan.

Seçilen vault'ta kökte `index.md` yoksa önce aşağıdaki yapıyı kur.

Not sözdizimi için `obsidian-markdown` skill'ine, görsel harita için `json-canvas`'a, tablo ya da kart görünümü için `obsidian-bases`'e başvur.

## Yapı

```
<Vault>/
├── index.md                      ← vault girişi: proje tablosu + kategori listesi. Her sorguda ilk bunu oku
├── log.md                        ← SADECE vault düzeyi işlemler (kurulum, yapı değişikliği, yeni proje açılışı)
├── Vault Kullanımı.md            ← kullanıcı rehberi
├── Inbox/                        ← işlenecek ham kaynaklar (kökte duran = bekleyen)
│   └── İşlendi/                  ← işlenmiş kaynaklar buraya taşınır
├── Kavramlar/                    ← ortak kavram sayfaları, tek kopya, projesiz
│   └── Kategoriler/              ← kategori sayfaları: kavram listesi + birer satır özet
└── Projeler/<Ad>/
    ├── <Ad> Projesi.md           ← projenin merkezi ve içerik listesi
    ├── <Ad> Log.md               ← bu projedeki işlemler
    └── (alt klasörler: Literatür/, Toplantılar/, Kararlar/ … gerektikçe)
```

**Index küçük kalır.** `index.md`'de kavram listelenmez; sadece proje tablosu ve kategori sayfalarına linkler (kategori başına bir satır: ne içerdiği, kaç kavram) durur. Kavramlar kendi kategori sayfasında listelenir: `Kavramlar/Kategoriler/<Kategori> Kavramları.md`, her kavram için `- [[Kavram]] — tek satır özet`. Böylece bir sorgu index + tek kategori sayfası okur; kavram sayısı arttıkça maliyet sabit kalır. Bir kategori ~30 kavramı geçerse alt kategorilere böl. Her kavram tam olarak bir kategori sayfasında listelenir.

Yukarıdakiler dışındaki kök klasörler ve dosyalar kullanıcının kendi notlarıdır. Onları oku ve link ver, ama **izin almadan taşıma, yeniden adlandırma, silme veya düzenleme yapma**.

## Projeler

Kural: **Projeye ait her şey kendi klasöründe. Kavramlar ortak ve projesiz.**

1. **Projeyi tespit et:** Git repo adı ya da çalışma klasörünün adı kullanılır. Kullanıcının ev dizini veya vault'un kendisi "proje" sayılmaz; o durumda not projesiz yazılır (`Kavramlar/` altına ya da kullanıcıya sorarak). Emin değilsen sor.
2. **Yeni proje açma** ("bu projeyi vault'a ekle" ya da projeye ilk kayıt):
   - `Projeler/<Ad>/` klasörünü, `<Ad> Projesi.md` ve `<Ad> Log.md` dosyalarını oluştur.
   - `index.md`'deki proje tablosuna bir satır ekle.
   - Kök `log.md`'ye "yeni proje" satırı ekle.
   - Proje sayfasının içeriği: amaç, repo yolu, stack, tarihli kararlar, kullanılan kavramlar, proje notları listesi (log dahil).
3. **Projeye özel sayfalar** (literatür notu, karar, toplantı, özet) `Projeler/<Ad>/` altına yazılır. Frontmatter'a `proje: "[[<Ad> Projesi]]"`, `tags`'e `proje/<kısa-ad>` eklenir. Proje sayfasındaki listeye de eklenir.
4. **Kavram sayfaları** (`Kavramlar/`) hiçbir projeye ait değildir: `proje:` alanı ya da `proje/…` etiketi **almaz**. Genel bilgi yazılır. Projeye özel kullanım sayfanın sonundaki `## <Ad> projesinde` bölümüne yazılır; bu bölüm proje sayfasına link verir. Başka bir projenin bilgisini genel doğru gibi yazma. İki proje aynı kavramı kullanıyorsa ikisinin de bölümü olur; bu bilinçli bir bağlantıdır.
5. **Log'lar:** Projedeki işlem `<Ad> Log.md`'ye yazılır. Kök `log.md`'ye yalnızca vault düzeyindeki işlemler yazılır; proje işlemleri oraya **kopyalanmaz**. Log'larda sayfa adları `[[wikilink]]` olarak yazılır; böylece log'dan sayfaya tek tıkla gidilir. Graph görünümünde index ve log'lar her şeye bağlı köprü gibi görünürse Obsidian'da `-file:index -file:log` filtresi önerilir.
6. **Sorgularda:** Kullanıcı bir projedeyken önce o projenin sayfasına ve klasörüne bak, sonra ilgili kavram sayfalarına geç. Cevapta hangi bilginin başka bir projeden geldiğini belirt.

## Sayfa formatı

```markdown
---
tags: [konu, alt-konu]            # projeye özel sayfalarda + proje/<kısa-ad>
proje: "[[<Ad> Projesi]]"         # SADECE projeye özel sayfalarda
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: ["[[dosya.pdf]]", "https://..."]
---
# Başlık

Kısa özet (2-3 cümle).

## İçerik
... ilgili kavramlara [[wikilink]] ...

## <Ad> projesinde      ← sadece kavram sayfalarında, gerekiyorsa
...

## Kaynaklar
- [[dosya.pdf]] — hangi bilgi nereden
```

- Kaynak linklerine klasör yazma: `[[Inbox/dosya.pdf]]` değil `[[dosya.pdf]]`. Kaynak işlenince `Inbox/İşlendi/`'ye taşınır; sadece adla yazılan link taşımadan sonra da çalışır.

- Sayfalar Türkçe, dosya adları okunur başlık olsun.
- **Dosya adları vault genelinde benzersiz olmalı.** Obsidian linkleri dosya adıyla çözer. Bu yüzden proje sayfalarına ve log'lara proje adını koy; `index.md` ve `log.md` adları sadece kökte kullanılır.
- Bir kavram için tek sayfa olsun. Yeni sayfa açmadan önce ilgili kategori sayfasında ve Grep ile var mı diye bak; varsa onu güncelle. Yeni kavramı kategori sayfasına ekle; uygun kategori yoksa yenisini aç ve index'e ekle.
- Kaynağı olmayan iddiaları `> [!warning] Kaynaksız` callout'u ile işaretle.

## İşlemler

**Kaydet** ("bunu vault'a kaydet"): Konuşmadaki cevabı ya da fikri uygun sayfaya ekle veya yeni sayfa aç. Projeye özel bilgi proje klasörüne, genel bilgi kavram sayfasına gider. Transkript değil, damıtılmış bilgi yaz. Ardından proje sayfasının listesini, yeni kavram varsa kategori sayfasını ve ilgili log'u güncelle.

**İşle / ingest** ("Inbox'u işle", "bu PDF'i ekle"):
1. Kaynağı oku. **Son adını belirle:** Vault'ta aynı adda başka bir dosya varsa (Glob ile tüm vault'ta bak, sadece `İşlendi/`'de değil) kaynağı Inbox'tayken `YYYY-MM-DD <ad>` diye yeniden adlandır (ör. `2026-09-25 slides.pdf`). Linkler adla çözüldüğü için aynı ad hem üzerine yazma hem link belirsizliği demektir. Bundan sonraki bütün linkleri bu son adla yaz.
2. Özet sayfası oluştur: projeye aitse proje klasörüne, değilse `Kavramlar/`'a. Kavram sayfalarını oluştur ya da güncelle.
3. Sayfaları birbirine ve kullanıcının mevcut notlarına wikilink ile bağla.
4. Kaynağı `Inbox/İşlendi/`'ye taşı (onay gerekmez). Asla üzerine yazma: `mv -n` kullan ve taşımadan sonra dosyanın hedefte olduğunu kontrol et; hedefte aynı ad varsa dur ve 1. adımdaki gibi yeniden adlandır. Vault'ta `[[Inbox/<dosya>]]` (ya da `](Inbox/<dosya>)`) biçiminde eski linkler varsa `[[<dosya>]]` yap; yoksa taşıma onları kırar. İlgili log'a `işlendi: [[<dosya>]]` satırı ekle. Inbox'ta `İşlendi/` dışında kalan her dosya bekleyen demektir; log taramaya gerek yok.
5. Kategori sayfalarını (yeni kavram varsa), index'i (yeni kategori ya da proje varsa) ve proje sayfasını güncelle.
6. Kullanıcıya hangi sayfaların oluşturulduğunu veya değiştiğini listele.

**Zotero** ("bu makaleyi Zotero'dan işle", "Zotero'yu senkronla", "projedeki yeni makaleleri işle"): Önce bu skill'in klasöründeki `references/zotero.md` dosyasını oku ve oradaki akışı izle. Zotero MCP araçları (`zotero_*`) yoksa kullanıcıya söyle.

**Sor** ("notlarıma göre …"):
1. `index.md`'yi oku, soruyla ilgili kategori sayfasını aç. Projedeysen o projenin sayfasını da oku. Sonra Grep ile ara.
2. Sadece ilgili sayfaları oku. Tüm vault'u okuma; bu token israfı olur.
3. Cevabı `[[sayfa]]` atıflarıyla ver.
4. Notlarda yoksa bunu açıkça söyle. Genel bilgiyle tamamlıyorsan bunu belirt.
5. Faydalı bir sentez çıktıysa kaydetmeyi teklif et.

**Bakım** ("vault'u kontrol et"): Bu skill'in klasöründeki script'i çalıştır. Notları tek tek okuma.

```bash
python3 "<skill klasörü>/scripts/check.py" "<vault yolu>"
```

Python 3.8+ gerekir, ek paket gerekmez. macOS ve Linux'ta genelde yalnızca `python3` vardır; Windows'ta `python` ya da `py` kullan. Hangisi varsa onu çalıştır (`command -v python3 || command -v python`). Script sadece okur. Şunları raporlar: kırık wikilink'ler, aynı adlı notlar, index'te olmayan proje ve kategoriler, hiçbir kategori sayfasında ya da birden fazla kategori sayfasında listelenen kavramlar, proje sayfasında listelenmeyen dosyalar, `proje:` alanı taşıyan kavram sayfaları, yetim sayfalar, Inbox'ta bekleyenler. Raporu özetle ve her bulgu için bir düzeltme öner (ör. kırık link → notu oluştur ya da linki düzelt). Düzeltmeden önce onay al. Kullanıcının kendi notlarındaki bulguları yalnızca bildir.

## Kurallar
- Toplu taşıma ve yeniden adlandırma için shell (bash, PowerShell, python) kullanılabilir. Vault işletim sisteminin korumalı bir klasöründeyse (ör. Windows'ta "Denetimli klasör erişimi") shell yazmaları engellenebilir; o zaman kullanıcıya söyle.
- **Silmeden önce kullanıcıya listeyi göster ve onay al.** Silme geri alınamaz; vault git'te değilse tek güvence bulut servisinin ya da işletim sisteminin geri dönüşüm kutusudur.
- Inbox'u temizlemek için işlenmiş kaynakları silme; `Inbox/İşlendi/`'ye taşı. Taşıma ve yeniden adlandırmada hiçbir zaman var olan bir dosyanın üzerine yazma; üzerine yazmak silmedir.
- Kullanıcının kendi notlarını değiştirmeden önce sor. `Projeler/`, `Kavramlar/`, `Inbox/`, `index.md`, `log.md` ve `Vault Kullanımı.md` Claude'un alanıdır.
- Log satırı: `- YYYY-MM-DD — işlem — etkilenen sayfalar`, en yeni üstte.
- Vault bir bulut klasöründeyse (OneDrive, iCloud, Dropbox) okunamayan bir dosya yalnızca bulutta olabilir; kullanıcıya söyle.
