"""check.py için regresyon testleri. Çalıştırma: python3 -m unittest discover tests"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "vault" / "scripts" / "check.py"
spec = importlib.util.spec_from_file_location("check", SCRIPT)
assert spec and spec.loader
check = importlib.util.module_from_spec(spec)
sys.modules["check"] = check
spec.loader.exec_module(check)


class VaultTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel: str, text: str = "x", raw: bytes | None = None):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if raw is not None:
            p.write_bytes(raw)
        else:
            p.write_text(text, encoding="utf-8")

    def run_checks(self):
        v = check.Vault(self.root)
        return {key: fn(v) for key, _, fn in check.CHECKS}

    # ── Unicode ──────────────────────────────────────────────────────────────

    def test_nfd_filename_resolves_nfc_link(self):
        """macOS dosya adını NFD verir; nottaki [[Öğrenme]] NFC yazılır."""
        self.write(unicodedata.normalize("NFD", "Kavramlar/Öğrenme.md"))
        self.write("Projeler/X/X Projesi.md", "[[Öğrenme]]")
        self.assertEqual(self.run_checks()["broken_links"], [])

    def test_nfd_link_resolves_nfc_filename(self):
        self.write("Kavramlar/Öğrenme.md")
        self.write("Projeler/X/X Projesi.md", unicodedata.normalize("NFD", "[[Öğrenme]]"))
        self.assertEqual(self.run_checks()["broken_links"], [])

    def test_nfd_islendi_folder_counts_as_processed(self):
        self.write(unicodedata.normalize("NFD", "Inbox/İşlendi/eski.pdf"))
        self.assertEqual(self.run_checks()["inbox_pending"], [])

    def test_turkish_dotted_capital_matches_obsidian(self):
        """Obsidian düz toLowerCase kullanır: İşlem.md'ye [[işlem]] çözülmez, [[İşlem]] çözülür."""
        self.write("Kavramlar/İşlem.md")
        self.write("Projeler/X/X Projesi.md", "[[İşlem]] [[İŞLEM]] [[işlem]]")
        broken = self.run_checks()["broken_links"]
        self.assertEqual(broken, ["Projeler/X/X Projesi.md → [[işlem]]"])

    # ── Aynı ad ve kategoriler ───────────────────────────────────────────────

    def test_duplicate_attachment_names(self):
        self.write("Inbox/İşlendi/slides.pdf")
        self.write("Projeler/B/slides.pdf")
        self.assertEqual(self.run_checks()["duplicate_names"],
                         ["Inbox/İşlendi/slides.pdf | Projeler/B/slides.pdf"])

    def test_concept_in_two_categories(self):
        self.write("Kavramlar/K.md")
        self.write("Kavramlar/Kategoriler/A Kavramları.md", "- [[K]]")
        self.write("Kavramlar/Kategoriler/B Kavramları.md", "- [[K]]")
        self.assertEqual(self.run_checks()["category_listing"],
                         ["birden fazla kategoride: Kavramlar/K.md (A Kavramları, B Kavramları)"])

    def test_uncategorized_concept(self):
        self.write("Kavramlar/K.md")
        self.assertEqual(self.run_checks()["category_listing"], ["kategorisiz: Kavramlar/K.md"])

    # ── Frontmatter ──────────────────────────────────────────────────────────

    def test_bom_frontmatter_is_parsed(self):
        """BOM'lu dosyada proje: alanı taşıyan kavram yine yakalanmalı."""
        self.write("Kavramlar/K.md", raw="﻿---\nproje: \"[[X Projesi]]\"\n---\n# K\n".encode("utf-8"))
        self.assertEqual(self.run_checks()["concepts_with_project"], ["Kavramlar/K.md"])

    def test_crlf_frontmatter_is_parsed(self):
        self.write("Kavramlar/K.md", raw=b"---\r\nproje: x\r\n---\r\n# K\r\n")
        self.assertEqual(self.run_checks()["concepts_with_project"], ["Kavramlar/K.md"])

    # ── Markdown linkleri ────────────────────────────────────────────────────

    def test_markdown_link_counts_as_incoming(self):
        self.write("Kavramlar/Gömme.md")
        self.write("Projeler/X/X Projesi.md", "[metin](Gömme.md)")
        r = self.run_checks()
        self.assertEqual(r["orphans"], [])
        self.assertEqual(r["broken_links"], [])

    def test_markdown_link_url_encoded_and_relative(self):
        self.write("Kavramlar/Vektör Veritabanları.md")
        self.write("Projeler/X/X Projesi.md",
                   "[a](../../Kavramlar/Vekt%C3%B6r%20Veritabanlar%C4%B1.md) "
                   "[b](<../../Kavramlar/Vektör Veritabanları.md#Başlık>)")
        v = check.Vault(self.root)
        targets = [t for _, t in v.links[Path("Projeler/X/X Projesi.md")]]
        self.assertEqual(targets, [Path("Kavramlar/Vektör Veritabanları.md")] * 2)

    def test_markdown_link_broken_is_reported(self):
        self.write("Projeler/X/X Projesi.md", "[metin](Yok.md)")
        self.assertEqual(len(self.run_checks()["broken_links"]), 1)

    def test_external_and_anchor_links_ignored(self):
        self.write("Projeler/X/X Projesi.md",
                   "[w](https://example.com) [m](mailto:a@b.c) [h](#başlık) [o](obsidian://open?x)")
        self.assertEqual(self.run_checks()["broken_links"], [])

    def test_markdown_image_embed(self):
        self.write("resim.png")
        self.write("Projeler/X/X Projesi.md", "![alt](resim.png)")
        self.assertEqual(self.run_checks()["broken_links"], [])

    # ── Kod blokları ─────────────────────────────────────────────────────────

    def test_tilde_fence_ignored(self):
        self.write("Projeler/X/X Projesi.md", "~~~\n[[Yok]]\n~~~\n")
        self.assertEqual(self.run_checks()["broken_links"], [])

    def test_backtick_fence_ignored(self):
        self.write("Projeler/X/X Projesi.md", "```md\n[[Yok]]\n```\n")
        self.assertEqual(self.run_checks()["broken_links"], [])

    def test_longer_fence_contains_shorter(self):
        """```` ile açılan blok içindeki ``` bloğu kapatmaz."""
        self.write("Projeler/X/X Projesi.md", "````\n```\n[[Yok]]\n```\n[[Yok2]]\n````\n[[Var]]")
        self.write("Kavramlar/Var.md")
        self.assertEqual(self.run_checks()["broken_links"], [])

    def test_link_after_fence_still_counted(self):
        self.write("Projeler/X/X Projesi.md", "~~~\nkod\n~~~\n[[Yok]]")
        self.assertEqual(len(self.run_checks()["broken_links"]), 1)

    # ── Inbox ────────────────────────────────────────────────────────────────

    def test_inbox_subfolders(self):
        self.write("Inbox/alt/derin.pdf")
        self.write("Inbox/İşlendi/alt/eski.pdf")
        self.assertEqual(self.run_checks()["inbox_pending"], ["Inbox/alt/derin.pdf"])

    def test_processed_source_link_survives_move(self):
        self.write("Inbox/İşlendi/kaynak.pdf")
        self.write("Projeler/X/X Projesi.md", "[[kaynak.pdf]]")
        self.assertEqual(self.run_checks()["broken_links"], [])


if __name__ == "__main__":
    unittest.main()
