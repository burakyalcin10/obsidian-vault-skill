#!/usr/bin/env python3
"""evals.json'daki kriterleri dosya sistemine bakarak programatik olarak puanlar.

Kullanım: python3 evals/grade.py <iteration klasörü>
Beklenen yapı: <iteration>/eval-<id>-<ad>/<config>/run-1/{vault/, outputs/response.md}
Her run klasörüne grading.json yazar (skill-creator viewer biçimi).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture-vault"
CHECK = HERE.parent / "skills" / "vault" / "scripts" / "check.py"
TODAY = "2026-09-25"
PROJ = Path("Projeler/Kavurma Profili")


# ── Yardımcılar ──────────────────────────────────────────────────────────────

def files(root: Path) -> dict[str, str]:
    """göreli yol → içerik özeti"""
    return {p.relative_to(root).as_posix(): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and ".obsidian" not in p.parts}


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace") if p.exists() else ""


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
    return {p.relative_to(vault).as_posix(): read(p) for p in vault.rglob("*.md")}


def category_links(vault: Path) -> str:
    return "\n".join(read(p) for p in (vault / "Kavramlar/Kategoriler").glob("*.md"))


def new_log_line(vault: Path) -> tuple[bool, str]:
    old = read(FIXTURE / PROJ / "Kavurma Profili Log.md").splitlines()
    new = [l for l in read(vault / PROJ / "Kavurma Profili Log.md").splitlines() if l not in old]
    hits = [l for l in new if TODAY in l]
    return bool(hits), (hits[0][:160] if hits else f"yeni satırlar: {new[:2]}")


def broken_count(vault: Path) -> int:
    out = subprocess.run([sys.executable, str(CHECK), str(vault), "--json"],
                         capture_output=True, text=True, encoding="utf-8")
    return len(json.loads(out.stdout)["broken_links"])


def new_concepts(vault: Path) -> list[str]:
    return [f for f in new_files(vault) if f.startswith("Kavramlar/") and not f.startswith("Kavramlar/Kategoriler/")
            and f.endswith(".md")]


# ── Değerlendirmeler ─────────────────────────────────────────────────────────

def eval_1(vault: Path, resp: str):
    src = "Soğuk Demleme.txt"
    moved = [p for p in (vault / "Inbox/İşlendi").glob("*.txt") if "Soğuk Demleme" in p.name]
    yield (not (vault / "Inbox" / src).exists() and bool(moved),
           f"Inbox kökünde: {(vault / 'Inbox' / src).exists()}; İşlendi/: {[p.name for p in moved]}")
    same = bool(moved) and moved[0].read_bytes() == (FIXTURE / "Inbox" / src).read_bytes()
    yield same, "İşlendi/'deki dosya orijinalle aynı" if same else "dosya yok ya da içerik değişmiş"
    summaries = [f for f in new_files(vault) if f.startswith(PROJ.as_posix() + "/") and f.endswith(".md")
                 and "proje:" in frontmatter(read(vault / f))]
    yield bool(summaries), f"proje: alanlı yeni proje sayfaları: {summaries}"
    bad = [f for f, t in all_md(vault).items() if "[[Inbox/" in t or "](Inbox/" in t]
    yield not bad, f"Inbox/ ile başlayan link içeren notlar: {bad}"
    concepts, cats = new_concepts(vault), category_links(vault)
    probs = [c for c in concepts if "proje:" in frontmatter(read(vault / c)) or f"[[{Path(c).stem}" not in cats]
    yield not probs, (f"yeni kavramlar: {concepts}; sorunlu: {probs}" if concepts else "yeni kavram açılmamış (koşul geçerli değil)")
    ok, ev = new_log_line(vault)
    yield ok, ev
    page = read(vault / PROJ / "Kavurma Profili Projesi.md")
    linked = [s for s in summaries if f"[[{Path(s).stem}" in page]
    yield bool(linked), f"proje sayfasından linklenen yeni sayfalar: {linked}"
    # Kök log'a vault düzeyi satır (ör. yeni kategori) yazılabilir; proje işlemi yazılamaz:
    # yeni satır "işlendi" içermemeli ve Projeler/ altındaki bir sayfaya link vermemeli.
    old = read(FIXTURE / "log.md").splitlines()
    added = [l for l in read(vault / "log.md").splitlines() if l not in old]
    proj_pages = {p.stem for p in (vault / "Projeler").rglob("*.md")}
    bad = [l for l in added if "işlendi" in l.lower()
           or any(t.split("|")[0].split("#")[0] in proj_pages for t in re.findall(r"\[\[([^\]]+)\]\]", l))]
    yield not bad, f"kök log'a eklenen satırlar: {added}; proje işlemi sayılanlar: {bad}"
    n = broken_count(vault)
    yield n <= 1, f"kırık link sayısı: {n} (başlangıç 1)"


def eval_2(vault: Path, resp: str):
    orig = FIXTURE / PROJ / "sunum.txt"
    same = (vault / PROJ / "sunum.txt").exists() and (vault / PROJ / "sunum.txt").read_bytes() == orig.read_bytes()
    yield same, "proje klasöründeki sunum.txt korunmuş" if same else "proje klasöründeki sunum.txt değişmiş ya da silinmiş"
    carriers = [p.relative_to(vault).as_posix() for p in vault.rglob("*") if p.is_file() and "misafir konuşmacı" in read(p)]
    yield bool(carriers), f"'misafir konuşmacı' içeren dosyalar: {carriers}"
    dated = [p.name for p in (vault / "Inbox/İşlendi").glob("*") if re.fullmatch(r"\d{4}-\d{2}-\d{2} sunum\.txt", p.name)]
    yield bool(dated), f"İşlendi/ içeriği: {[p.name for p in (vault / 'Inbox/İşlendi').glob('*')]}"
    bare = [f for f, t in all_md(vault).items() if re.search(r"\[\[(Inbox/)?sunum\.txt", t)]
    yield not bare, f"çıplak [[sunum.txt]] linki olan notlar: {bare}"
    yield not (vault / "Inbox/sunum.txt").exists(), f"Inbox/sunum.txt var mı: {(vault / 'Inbox/sunum.txt').exists()}"


def eval_3(vault: Path, resp: str):
    cands = [c for c in new_concepts(vault)
             if re.search(r"first.?crack|birinci çatla", c + read(vault / c).split("\n## ")[0], re.I)]
    yield bool(cands), f"first crack kavram sayfası: {cands}; yeni kavramlar: {new_concepts(vault)}"
    if not cands:
        for _ in range(4):
            yield False, "kavram sayfası yok"
        return
    c = cands[0]; text = read(vault / c); fm = frontmatter(text)
    yield "proje:" not in fm and "proje/" not in fm, f"frontmatter: {fm[:120]!r}"
    head = re.search(r"^#+ .*Kavurma Profili projesinde.*$", text, re.M)
    pos196 = [m.start() for m in re.finditer("196", text)]
    ok = not pos196 or (head is not None and all(p > head.start() for p in pos196))
    yield ok, f"196 konumları: {pos196}; proje başlığı: {head.group(0) if head else None}"
    yield f"[[{Path(c).stem}" in category_links(vault), f"kategori sayfalarında [[{Path(c).stem}]] aranıyor"
    ok, ev = new_log_line(vault)
    yield ok, ev


def eval_4(vault: Path, resp: str):
    yield "140" in resp and "165" in resp, f"yanıtta 140: {'140' in resp}, 165: {'165' in resp}"
    yield "[[Maillard" in resp, "yanıtta [[Maillard…]] atfı " + ("var" if "[[Maillard" in resp else "yok")
    neg = re.search(r"development[^.\n]{0,200}(yok|bulunmuyor|geçmiyor|yer almıyor|kayıtlı değil|not edilmemiş|bulunamadı|bulamadım)"
                    r"|(yok|bulunmuyor|geçmiyor|yer almıyor|kayıtlı değil|not edilmemiş|bulunamadı)[^.\n]{0,120}development", resp, re.I)
    yield bool(neg), f"eşleşme: {neg.group(0)[:160]!r}" if neg else "development time'ın notlarda olmadığı söylenmemiş"
    ch = changed_files(vault)
    yield not ch, f"değişen dosyalar: {ch}"


def eval_5(vault: Path, resp: str):
    yield "Kavurucu Kurulum" in resp, "kırık link yanıtta " + ("geçiyor" if "Kavurucu Kurulum" in resp else "geçmiyor")
    yield "sunum.txt" in resp, "sunum.txt yanıtta " + ("geçiyor" if "sunum.txt" in resp else "geçmiyor")
    yield "Asitlik" in resp and re.search(r"kategori", resp, re.I) is not None, "Asitlik + kategori yanıtta"
    yield "Soğuk Demleme" in resp and "Inbox" in resp, "Inbox bekleyenleri yanıtta"
    ch = changed_files(vault)
    yield not ch, f"değişen dosyalar: {ch}"


EVALS = {1: eval_1, 2: eval_2, 3: eval_3, 4: eval_4, 5: eval_5}


def grade_run(run: Path, eval_id: int, assertions: list[str]):
    vault, resp = run / "vault", read(run / "outputs" / "response.md")
    results = list(EVALS[eval_id](vault, resp))
    assert len(results) == len(assertions), (eval_id, len(results), len(assertions))
    exp = [{"text": t, "passed": bool(p), "evidence": e} for t, (p, e) in zip(assertions, results)]
    n = sum(e["passed"] for e in exp)
    out = {"expectations": exp, "summary": {"passed": n, "failed": len(exp) - n, "total": len(exp),
                                             "pass_rate": round(n / len(exp), 2)}}
    (run / "grading.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return n, len(exp)


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    it = Path(sys.argv[1])
    for ed in sorted(it.glob("eval-*")):
        meta = json.loads((ed / "eval_metadata.json").read_text(encoding="utf-8"))
        for cfg in sorted(d for d in ed.iterdir() if d.is_dir()):
            for run in sorted(cfg.glob("run-*")):
                n, t = grade_run(run, meta["eval_id"], meta["assertions"])
                print(f"{ed.name:34} {cfg.name:14} {n}/{t}")


if __name__ == "__main__":
    main()
