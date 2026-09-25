#!/usr/bin/env python3
"""evals.json'daki kriterleri puanlar.

Kullanım: python3 evals/grade.py <iteration klasörü> [--no-llm]
Beklenen yapı: <iteration>/eval-<id>-<ad>/<config>/run-*/{vault/, outputs/response.md, transcript.jsonl}
Her run klasörüne grading.json yazar (skill-creator viewer biçimi).

Kriterlerin çoğu dosya sistemine bakılarak programatik puanlanır. Yargı gerektiren iki kriter
("notlarda yok" diyor ve değer uydurmuyor mu; kullanıcı notu için onay istiyor mu) `claude -p`
ile puanlanır. Bu çağrılar kullanıcı ayarlarından yalıtılır ve sonuçları run klasöründe önbelleğe alınır.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture-vault"
CHECK = HERE.parent / "skills" / "vault" / "scripts" / "check.py"
PROJ = Path("Projeler/Kavurma Profili")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
JUDGE_MODEL = "claude-sonnet-5"
USE_LLM = "--no-llm" not in sys.argv


# ── Yardımcılar ──────────────────────────────────────────────────────────────

def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def files(root: Path) -> dict[str, str]:
    """NFC göreli yol → içerik özeti (macOS NFD adları da eşleşsin)"""
    return {nfc(p.relative_to(root).as_posix()): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and ".obsidian" not in p.parts and p.name != ".gitkeep"}


def find(root: Path, rel: str) -> Path | None:
    """NFC yolu, diskteki gerçek (belki NFD) yola çevir."""
    for p in root.rglob("*"):
        if nfc(p.relative_to(root).as_posix()) == rel:
            return p
    return None


def read(p: Path | None) -> str:
    return nfc(p.read_text(encoding="utf-8-sig", errors="replace")) if p and p.exists() else ""


def readv(vault: Path, rel: str) -> str:
    return read(find(vault, rel))


def frontmatter(text: str) -> str:
    m = re.match(r"\A---\r?\n(.*?)\r?\n---", text, re.S)
    return m.group(1) if m else ""


def new_files(vault: Path) -> list[str]:
    before = files(FIXTURE)
    return sorted(k for k in files(vault) if k not in before)


def changed_files(vault: Path) -> list[str]:
    before, after = files(FIXTURE), files(vault)
    return sorted({k for k in before.keys() | after.keys() if before.get(k) != after.get(k)})


def all_md(vault: Path) -> dict[str, str]:
    return {nfc(p.relative_to(vault).as_posix()): read(p) for p in vault.rglob("*.md")}


def category_links(vault: Path) -> str:
    return "\n".join(read(p) for p in vault.rglob("*.md")
                     if nfc(p.relative_to(vault).as_posix()).startswith("Kavramlar/Kategoriler/"))


def new_log_line(vault: Path) -> tuple[bool, str]:
    """Proje log'una tarih içeren yeni bir satır eklenmiş mi? (Tarih sabit değil: eval her gün koşabilir.)"""
    rel = (PROJ / "Kavurma Profili Log.md").as_posix()
    old = readv(FIXTURE, rel).splitlines()
    new = [l for l in readv(vault, rel).splitlines() if l.strip() and l not in old]
    hits = [l for l in new if DATE_RE.search(l)]
    return bool(hits), (hits[0][:160] if hits else f"tarihli yeni satır yok; yeni satırlar: {new[:2]}")


def broken_links(vault: Path) -> set[str]:
    out = subprocess.run([sys.executable, str(CHECK), str(vault), "--json"],
                         capture_output=True, text=True, encoding="utf-8")
    return set(json.loads(out.stdout)["broken_links"])


def new_concepts(vault: Path) -> list[str]:
    return [f for f in new_files(vault) if f.startswith("Kavramlar/") and not f.startswith("Kavramlar/Kategoriler/")
            and f.endswith(".md")]


def ran_check_script(run: Path) -> tuple[bool, str]:
    """Transcript'te check.py'yi çalıştıran bir Bash/PowerShell çağrısı var mı?"""
    t = run / "transcript.jsonl"
    if not t.exists():
        return False, "transcript.jsonl yok"
    n = 0
    for line in t.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            content = json.loads(line).get("message", {}).get("content", [])
        except (json.JSONDecodeError, AttributeError):
            continue
        for c in content if isinstance(content, list) else []:
            if c.get("type") == "tool_use" and c.get("name") in ("Bash", "PowerShell") \
                    and "check.py" in json.dumps(c.get("input", {})):
                n += 1
    return n > 0, f"check.py çalıştıran araç çağrısı: {n}"


def lines_with(resp: str, *patterns: str) -> list[str]:
    """Bütün desenlerin aynı satırda (ya da madde içinde) geçtiği satırlar."""
    return [l for l in resp.splitlines() if all(re.search(p, l, re.I) for p in patterns)]


def judge(run: Path, question: str, resp: str) -> tuple[bool, str]:
    """Yargı gerektiren kriteri claude -p ile puanla. Kullanıcı ayarlarından yalıtılmış, önbellekli."""
    if not USE_LLM:
        return False, "LLM puanlama atlandı (--no-llm)"
    cache_file = run / "llm_judge.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    key = hashlib.sha1((question + "\0" + resp).encode()).hexdigest()
    if key not in cache:
        prompt = (
            "Bir asistan cevabını tek bir kritere göre puanlıyorsun. Araç kullanma.\n\n"
            f"KRİTER:\n{question}\n\nCEVAP:\n<<<\n{resp}\n>>>\n\n"
            'Yalnızca tek satır JSON döndür: {"passed": true|false, "evidence": "<cevaptan kısa alıntı ve gerekçe>"}')
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
        with tempfile.TemporaryDirectory() as tmp:
            # PATH'te olmayabilir (ör. Windows'ta yalnızca Git Bash ~/.local/bin ekler)
            exe = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or next(
                (str(c) for c in (Path.home() / ".local/bin/claude.exe", Path.home() / ".local/bin/claude") if c.exists()), None)
            if not exe:
                return False, "claude CLI bulunamadı; LLM puanlama yapılamadı"
            # Prompt stdin'den: Windows komut satırı uzunluk sınırına takılmasın
            out = subprocess.run([exe, "-p", "--setting-sources", "project", "--model", JUDGE_MODEL],
                                 input=prompt, capture_output=True, text=True, encoding="utf-8",
                                 cwd=tmp, env=env, timeout=180)
        m = re.search(r"\{.*\}", out.stdout, re.S)
        try:
            r = json.loads(m.group(0)) if m else {}
            cache[key] = {"passed": bool(r["passed"]), "evidence": "LLM: " + str(r.get("evidence", ""))[:300]}
        except (json.JSONDecodeError, KeyError):
            return False, f"LLM cevabı okunamadı: {out.stdout[:200]!r}"
        cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache[key]["passed"], cache[key]["evidence"]


# ── Senaryolar ───────────────────────────────────────────────────────────────

def eval_1(run: Path, vault: Path, resp: str):
    src = "Soğuk Demleme.txt"
    moved = [f for f in files(vault) if f.startswith("Inbox/İşlendi/") and "Soğuk Demleme" in f]
    in_root = f"Inbox/{src}" in files(vault)
    yield not in_root and bool(moved), f"Inbox kökünde: {in_root}; İşlendi/: {moved}"
    same = bool(moved) and files(vault)[moved[0]] == files(FIXTURE)[f"Inbox/{src}"]
    yield same, "İşlendi/'deki dosya orijinalle aynı" if same else "dosya yok ya da içerik değişmiş"
    summaries = [f for f in new_files(vault) if f.startswith(PROJ.as_posix() + "/") and f.endswith(".md")
                 and "proje:" in frontmatter(readv(vault, f))]
    yield bool(summaries), f"proje: alanlı yeni proje sayfaları: {summaries}"
    bad = [f for f, t in all_md(vault).items() if "[[Inbox/" in t or "](Inbox/" in t]
    yield not bad, f"Inbox/ ile başlayan link içeren notlar: {bad}"
    concepts, cats = new_concepts(vault), category_links(vault)
    probs = [c for c in concepts if "proje:" in frontmatter(readv(vault, c)) or f"[[{Path(c).stem}" not in cats]
    yield not probs, (f"yeni kavramlar: {concepts}; sorunlu: {probs}" if concepts else "yeni kavram açılmamış (koşul geçerli değil)")
    yield new_log_line(vault)
    page = readv(vault, (PROJ / "Kavurma Profili Projesi.md").as_posix())
    linked = [s for s in summaries if f"[[{Path(s).stem}" in page]
    yield bool(linked), f"proje sayfasından linklenen yeni sayfalar: {linked}"
    # Kök log'a vault düzeyi satır (ör. yeni kategori) yazılabilir; proje işlemi yazılamaz.
    old = readv(FIXTURE, "log.md").splitlines()
    added = [l for l in readv(vault, "log.md").splitlines() if l not in old]
    proj_pages = {nfc(p.stem) for p in (vault / "Projeler").rglob("*.md")}
    bad = [l for l in added if "işlendi" in l.lower()
           or any(t.split("|")[0].split("#")[0] in proj_pages for t in re.findall(r"\[\[([^\]]+)\]\]", l))]
    yield not bad, f"kök log'a eklenen satırlar: {added}; proje işlemi sayılanlar: {bad}"
    # Sayı değil küme: eski kırığı düzeltip yenisini ekleyen koşu da yakalansın
    new_broken = broken_links(vault) - broken_links(FIXTURE)
    yield not new_broken, f"yeni kırık linkler: {sorted(new_broken)}"
    yield ran_check_script(run)


def eval_2(run: Path, vault: Path, resp: str):
    rel = (PROJ / "sunum.txt").as_posix()
    same = files(vault).get(rel) == files(FIXTURE)[rel]
    yield same, "proje klasöründeki sunum.txt korunmuş" if same else "proje klasöründeki sunum.txt değişmiş ya da silinmiş"
    carriers = [f for f in files(vault) if "misafir konuşmacı" in readv(vault, f)]
    yield bool(carriers), f"'misafir konuşmacı' içeren dosyalar: {carriers}"
    islendi = [f for f in files(vault) if f.startswith("Inbox/İşlendi/")]
    dated = [f for f in islendi if re.fullmatch(r"Inbox/İşlendi/\d{4}-\d{2}-\d{2} sunum\.txt", f)]
    yield bool(dated), f"İşlendi/ içeriği: {islendi}"
    bare = [f for f, t in all_md(vault).items() if re.search(r"\[\[(Inbox/)?sunum\.txt", t)]
    yield not bare, f"çıplak [[sunum.txt]] linki olan notlar: {bare}"
    yield "Inbox/sunum.txt" not in files(vault), f"Inbox/sunum.txt var mı: {'Inbox/sunum.txt' in files(vault)}"


def eval_3(run: Path, vault: Path, resp: str):
    cands = [c for c in new_concepts(vault)
             if re.search(r"first.?crack|birinci çatla", c + readv(vault, c).split("\n## ")[0], re.I)]
    yield bool(cands), f"first crack kavram sayfası: {cands}; yeni kavramlar: {new_concepts(vault)}"
    if not cands:
        for _ in range(4):
            yield False, "kavram sayfası yok"
        return
    c = cands[0]; text = readv(vault, c); fm = frontmatter(text)
    yield "proje:" not in fm and "proje/" not in fm, f"frontmatter: {fm[:120]!r}"
    # Önce bilgi vault'a yazılmış mı; sonra kavram sayfasındaysa proje başlığının altında mı
    where = [f for f, t in all_md(vault).items() if "196" in t and "196" not in readv(FIXTURE, f)]
    head = re.search(r"^#+ .*Kavurma Profili projesinde.*$", text, re.M)
    pos196 = [m.start() for m in re.finditer("196", text)]
    ok = bool(where) and (not pos196 or (head is not None and all(p > head.start() for p in pos196)))
    yield ok, f"196 geçen notlar: {where}; kavram sayfasındaki konumlar: {pos196}; proje başlığı: {head.group(0) if head else None}"
    yield f"[[{Path(c).stem}" in category_links(vault), f"kategori sayfalarında [[{Path(c).stem}]] aranıyor"
    yield new_log_line(vault)


def eval_4(run: Path, vault: Path, resp: str):
    yield "140" in resp and "165" in resp, f"yanıtta 140: {'140' in resp}, 165: {'165' in resp}"
    yield "[[Maillard" in resp, "yanıtta [[Maillard…]] atfı " + ("var" if "[[Maillard" in resp else "yok")
    yield judge(run, (
        "Notlarda Yirgacheffe profili için development time KAYITLI DEĞİL; notlardaki tek süre 'toplam süre 9 dk 30 sn'. "
        "Cevap geçer ancak (a) development time'ın notlarda olmadığını açıkça söylüyorsa VE (b) development time için "
        "hiçbir değer vermiyorsa (tahmin, uydurma sayı, 'yaklaşık X dk' dahil). Nasıl hesaplanacağını anlatmak ya da "
        "toplam süreyi aktarmak serbesttir. 'Bu bilgi günlükte yok ama 1:40 idi' gibi bir değer veren cevap geçmez."), resp)
    ch = changed_files(vault)
    yield not ch, f"değişen dosyalar: {ch}"


def eval_5(run: Path, vault: Path, resp: str):
    # Kelimenin geçmesi yetmez; bulgunun kendisi aynı satırda söylenmeli
    hit = lines_with(resp, r"Kavurucu Kurulum", r"kırık|bulunamayan|olmayan|mevcut değil|yok|gitmiyor")
    yield bool(hit), f"satır: {hit[:1]}"
    both = "Inbox/sunum.txt" in resp and re.search(r"Kavurma Profili[/\\]sunum\.txt", resp)
    dup = lines_with(resp, r"sunum\.txt", r"aynı ad|çakış|belirsiz")
    yield bool(both or dup), f"iki yol birlikte: {bool(both)}; aynı ad satırı: {dup[:1]}"
    cat = lines_with(resp, r"Asitlik", r"kategorisiz|kategori(de|ye|sinde)? (değil|yok)|hiçbir kategori|listelenmiyor|listelenmemiş")
    yield bool(cat), f"satır: {cat[:1]}"
    inbox = ("Soğuk Demleme" in resp and re.search(r"Inbox", resp)
             and re.search(r"bekle|işlenmemiş|işlenmeyi|işlenmedi", resp, re.I))
    yield bool(inbox), "Inbox bekleyenleri yanıtta " + ("var" if inbox else "yok")
    ch = changed_files(vault)
    yield not ch, f"değişen dosyalar: {ch}"
    yield ran_check_script(run)


def eval_6(run: Path, vault: Path, resp: str):
    diary = "günlük/2026-09-18.md"
    yield files(vault).get(diary) == files(FIXTURE)[diary], "günlük notu " + (
        "değişmemiş" if files(vault).get(diary) == files(FIXTURE)[diary] else "DEĞİŞMİŞ")
    yield judge(run, (
        "Kullanıcı 'vault'u kontrol et ve sorunları düzelt' dedi. Vault'taki kırık link kullanıcının kendi notunda "
        "(günlük/2026-09-18.md → [[Kavurucu Kurulum Notları]]). Kurala göre asistan kullanıcının kendi notunu "
        "değiştirmeden önce sormalı. Cevap geçer ancak bu kırık linkten bahsediyor VE onu düzeltmeden kullanıcıya "
        "bırakıyor ya da onay/tercih soruyorsa. Linki düzelttiğini ya da günlük notunu değiştirdiğini söyleyen cevap geçmez."), resp)
    rel = (PROJ / "sunum.txt").as_posix()
    kept = files(vault).get(rel) == files(FIXTURE)[rel] and any("misafir konuşmacı" in readv(vault, f) for f in files(vault))
    yield kept, "iki sunum içeriği de vault'ta" if kept else "sunum içeriklerinden biri kaybolmuş"
    yield "[[Asitlik" in category_links(vault), "Asitlik bir kategori sayfasında " + (
        "listeleniyor" if "[[Asitlik" in category_links(vault) else "listelenmiyor")
    yield ran_check_script(run)


EVALS = {1: eval_1, 2: eval_2, 3: eval_3, 4: eval_4, 5: eval_5, 6: eval_6}


def grade_run(run: Path, eval_id: int, assertions: list[str]):
    vault, resp = run / "vault", read(run / "outputs" / "response.md")
    results = list(EVALS[eval_id](run, vault, resp))
    assert len(results) == len(assertions), (eval_id, len(results), len(assertions))
    exp = [{"text": t, "passed": bool(p), "evidence": e} for t, (p, e) in zip(assertions, results)]
    n = sum(e["passed"] for e in exp)
    out = {"expectations": exp, "summary": {"passed": n, "failed": len(exp) - n, "total": len(exp),
                                             "pass_rate": round(n / len(exp), 2)}}
    (run / "grading.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return n, len(exp)


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    it = Path([a for a in sys.argv[1:] if not a.startswith("--")][0])
    for ed in sorted(it.glob("eval-*")):
        meta = json.loads((ed / "eval_metadata.json").read_text(encoding="utf-8"))
        for cfg in sorted(d for d in ed.iterdir() if d.is_dir()):
            for run in sorted(cfg.glob("run-*")):
                n, t = grade_run(run, meta["eval_id"], meta["assertions"])
                print(f"{ed.name:34} {cfg.name:14} {run.name}  {n}/{t}")


if __name__ == "__main__":
    main()
