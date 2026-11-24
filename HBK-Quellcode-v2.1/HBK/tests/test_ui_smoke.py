"""Headless-Test der UI-Logik: Tkinter wird durch Stubs ersetzt, Datenbank und Rechenkern sind echt."""
import os, sys, tempfile, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class Stub:
    def __init__(self, *a, **k): pass
    def __getattr__(self, n): return lambda *a, **k: Stub()
    def get(self, *a): return ""
    def __iter__(self): return iter(())


class Var:
    def __init__(self, *a, value="", **k): self.v = value
    def get(self): return self.v
    def set(self, v): self.v = v
    def trace_add(self, *a): pass


class FakeTreeview(Stub):
    def __init__(self, *a, **k):
        self.nodes, self.order, self.sel = {}, {"": []}, ()
    def insert(self, parent, index, iid=None, text="", values=(), tags=(), open=False, **k):
        self.nodes[iid] = {"text": text, "values": tuple(values), "tags": tags, "open": open, "parent": parent}
        self.order.setdefault(parent, []).append(iid); self.order.setdefault(iid, [])
        return iid
    def delete(self, *ids):
        for i in ids:
            if i in self.nodes:
                n = self.nodes.pop(i); self.order[n["parent"]].remove(i)
                for c in list(self.order.get(i, [])): self.delete(c)
                self.order.pop(i, None)
    def get_children(self, item=""): return tuple(self.order.get(item, []))
    def item(self, iid, opt=None): return self.nodes[iid][opt]
    def exists(self, iid): return iid in self.nodes
    def selection(self): return self.sel
    def selection_set(self, i): self.sel = (i,)
    def see(self, i): pass


def install_stubs():
    tk = types.ModuleType("tkinter"); ttk = types.ModuleType("tkinter.ttk"); font = types.ModuleType("tkinter.font")
    fd = types.ModuleType("tkinter.filedialog"); mb = types.ModuleType("tkinter.messagebox")
    for n in ("Toplevel", "Tk", "Text", "Listbox", "Menu"): setattr(tk, n, type(n, (Stub,), {}))
    tk.StringVar = tk.BooleanVar = Var
    for n in ("Frame", "Label", "Button", "Entry", "Combobox", "Notebook", "LabelFrame", "Scrollbar", "Style", "Checkbutton"):
        setattr(ttk, n, type(n, (Stub,), {}))
    ttk.Treeview = FakeTreeview
    font.Font = Stub
    mb.showinfo = mb.showerror = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: True
    fd.asksaveasfilename = fd.askopenfilename = lambda **k: None
    tk.ttk, tk.font, tk.filedialog, tk.messagebox = ttk, font, fd, mb
    sys.modules.update({"tkinter": tk, "tkinter.ttk": ttk, "tkinter.font": font, "tkinter.filedialog": fd, "tkinter.messagebox": mb})


install_stubs()
from hbk import ui, ui_leistung, ui_projekt, ui_stamm, widgets, auth  # noqa: E402
from hbk.db import DB, seed_demo  # noqa: E402
import tkinter  # noqa: E402


class FakeApp:
    def __init__(self, db): self.db, self.root, self.opened = db, Stub(), []
    def refresh_all(self): pass
    def open_projekt(self, pid): self.opened.append(pid)


class UI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = DB(os.path.join(self.tmp, "u.db")); seed_demo(self.db)
        self.app = FakeApp(self.db)
        self.pid = self.db.one("SELECT id FROM projekte")["id"]
        self.lid = self.db.one("SELECT id FROM leistungen WHERE nr='L-001'")["id"]

    def answers(self, *vals):
        it = iter(vals)
        f = lambda *a, **k: next(it)
        for m in (ui, ui_stamm, ui_leistung, ui_projekt, widgets):
            m.ask = f

    def files(self, path):
        tkinter.filedialog.asksaveasfilename = tkinter.filedialog.askopenfilename = lambda **k: path

    def test_ordnerbaum_und_suche(self):
        v = ui_stamm.ArtikelView(Stub(), self.app); v.refresh()
        t = v.ft.tree
        self.assertEqual({"f1", "f2", "f3"}, {i for i in t.get_children()})                  # Holz, Dämmung, Befestigung
        self.assertEqual(t.nodes["f1"]["text"], "Holz"); self.assertEqual(t.get_children("f1"), ("i1",))
        self.assertIn("KVH", t.nodes["i1"]["text"])
        v.ft.suche.set("zellulose"); v.refresh()
        self.assertEqual(t.get_children(), ("f2",))                                           # leere Ordner ausgeblendet
        v.ft.suche.set(""); v.refresh()
        t.selection_set("f1"); self.assertEqual(v.ft.target_folder(), 1)
        t.selection_set("i1"); self.assertEqual(v.ft.sel_item(), 1)
        self.answers({"name": "Konstruktionsholz"}); t.selection_set("f1"); v.ordner_neu(); v.refresh()
        self.assertIn("Holz / Konstruktionsholz", dict((p, i) for i, p in self.db.ordner_pfade("artikel")))
        self.answers({"ordner": "Holz / Konstruktionsholz"}); t.selection_set("i1"); v.verschieben()
        self.assertEqual(self.db.one("SELECT ordner_id FROM artikel WHERE id=1")["ordner_id"], self.db.ordner_id_per_pfad("artikel", "Holz / Konstruktionsholz"))

    def test_artikel_neu_in_leistung(self):
        base = {"nr": "", "bezeichnung": "Spezialplatte", "einheit": "m²", "ordner": ui_stamm.KEIN_ORDNER, "lieferant": "X", "preis": "10,00",
                "ab": "01.11.2026", "pa": "12", "kategorie": "", "gewicht": "", "volumen": "", "lager": ""}
        self.answers({**base, "stamm": True})
        a1 = ui_stamm.artikel_neu(self.app, Stub(), None, in_leistung=True)
        r = self.db.one("SELECT * FROM artikel WHERE id=?", (a1,))
        self.assertEqual((r["stamm"], r["quelle"], r["preisaufschlag"]), (1, "Leistung", 12.0)); self.assertTrue(r["nr"].startswith("A-"))
        self.answers({**base, "bezeichnung": "Nur lokal", "stamm": False})
        a2 = ui_stamm.artikel_neu(self.app, Stub(), None, in_leistung=True)
        self.assertEqual(self.db.one("SELECT stamm FROM artikel WHERE id=?", (a2,))["stamm"], 0)
        texte = [i[2] for i in ui_stamm.artikel_items(self.db, "")]
        self.assertTrue(any("Spezialplatte" in t and "★" in t for t in texte))               # in Stammdaten gekennzeichnet
        self.assertFalse(any("Nur lokal" in t for t in texte))                               # nicht in Stammdaten
        w = ui_leistung.LeistungWindow(self.app, self.lid)
        w.mat_neu() if False else w._material_einfuegen(a2)
        self.assertEqual(self.db.one("SELECT COUNT(*) c FROM leistung_material WHERE artikel_id=?", (a2,))["c"], 1)

    def test_klick_bearbeitung_leistung(self):
        w = ui_leistung.LeistungWindow(self.app, self.lid)
        t = w.tree
        self.assertEqual(t.nodes["L"]["values"][6], "01 h 48 min")                           # Gesamtzeit 1,8 h
        mid = self.db.one("SELECT id FROM leistung_material WHERE leistung_id=? ORDER BY id", (self.lid,))["id"]
        lid2 = self.db.one("SELECT id FROM leistung_lohn WHERE leistung_id=?", (self.lid,))["id"]
        self.assertEqual(w._rohwert(f"m{mid}", "menge"), "0,045"); self.assertEqual(w._rohwert(f"m{mid}", "pa"), "8")
        self.assertIsNone(w._rohwert(f"m{mid}", "ek"))                                      # EK nicht direkt änderbar
        w._commit(f"m{mid}", "pa", "10 %"); w._commit(f"m{mid}", "ma", "5"); w._commit(f"m{mid}", "menge", "0,05")
        r = self.db.one("SELECT * FROM leistung_material WHERE id=?", (mid,))
        self.assertEqual((r["preisaufschlag"], r["verschnitt"], r["menge"]), (10.0, 5.0, "0,05"))
        self.assertIn("*", t.nodes[f"m{mid}"]["values"][3])                                   # abweichender Aufschlag markiert
        w._commit(f"m{mid}", "pa", "")                                                       # leeren -> wieder Artikelwert
        self.assertIsNone(self.db.one("SELECT preisaufschlag FROM leistung_material WHERE id=?", (mid,))["preisaufschlag"])
        w._commit(f"m{mid}", "#0", "KVH Sonderprofil")
        self.assertIn("KVH Sonderprofil", t.nodes[f"m{mid}"]["text"])
        w._commit(f"l{lid2}", "zeit", "02 h 00 min"); self.assertEqual(self.db.one("SELECT zeit_h FROM leistung_lohn WHERE id=?", (lid2,))["zeit_h"], 2.0)
        w._commit(f"l{lid2}", "vk", "60"); self.assertEqual(self.db.one("SELECT satz FROM leistung_lohn WHERE id=?", (lid2,))["satz"], 60.0)
        w._commit("L", "#0", "Wand neu"); w._commit("L", "menge", "lfm")
        l = self.db.one("SELECT * FROM leistungen WHERE id=?", (self.lid,))
        self.assertEqual((l["bezeichnung"], l["einheit"]), ("Wand neu", "lfm"))
        w._commit(f"m{mid}", "menge", "Quatsch+")                                           # ungültig: Fehlerdialog, keine Änderung
        self.assertEqual(self.db.one("SELECT menge FROM leistung_material WHERE id=?", (mid,))["menge"], "0,05")

    def test_lohnanteil_dialog_und_analyse(self):
        w = ui_leistung.LeistungWindow(self.app, self.lid)
        self.answers({"bez": "Aufmaß", "zeit": "00 h 30 min", "einheit": "Psch", "menge": "1", "art": "– Standardsatz –", "satz": "", "fix": True})
        self.assertTrue(ui_leistung.LohnDialog(self.app, w, self.lid).ok)
        o = self.db.one("SELECT * FROM leistung_lohn WHERE bezeichnung='Aufmaß'")
        self.assertEqual((o["zeit_h"], o["menge_fix"], o["satz"], o["lohnart_id"]), (0.5, 1, None, None))
        self.answers({"bez": "Aufmaß", "zeit": "1:00", "einheit": "Psch", "menge": "1", "art": "Helfer (38,00 €/h)", "satz": "", "fix": True})
        self.assertTrue(ui_leistung.LohnDialog(self.app, w, self.lid, o["id"]).ok)
        o = self.db.one("SELECT * FROM leistung_lohn WHERE id=?", (o["id"],))
        self.assertEqual((o["zeit_h"], self.db.one("SELECT bezeichnung FROM lohnarten WHERE id=?", (o["lohnart_id"],))["bezeichnung"]), (1.0, "Helfer"))
        w.v_menge.set("10"); w.analyse()
        self.assertEqual(w.kz.__class__.__name__, "FakeTreeview")
        kz = {w.kz.nodes[i]["text"]: w.kz.nodes[i]["values"][0] for i in w.kz.get_children()}
        self.assertEqual(kz["Feste Zeiten (Menge fix)"], "01 h 00 min")                       # Aufmaß 1 h fix
        self.assertEqual(kz["Zeit je Einheit (ohne feste Zeiten)"], "01 h 48 min je m²")
        w.tree.selection_set(f"l{o['id']}"); w.entfernen()
        self.assertIsNone(self.db.one("SELECT 1 FROM leistung_lohn WHERE id=?", (o["id"],)))

    def test_leistungen_tab_ordner_export(self):
        tab = ui_leistung.LeistungenTab(Stub(), self.app); tab.refresh()
        t = tab.ft.tree
        self.assertEqual({"f4", "f5"}, {i for i in t.get_children() if i[0] == "f"}); self.assertEqual(t.get_children("f4"), (f"i{self.lid}",))
        self.assertIn("m²", t.nodes[f"i{self.lid}"]["values"][2])
        self.answers({"nr": "L-050", "bezeichnung": "Neue Leistung", "einheit": "lfm", "ordner": "Dach"}); tab.neu()
        self.assertEqual(self.db.one("SELECT ordner_id FROM leistungen WHERE nr='L-050'")["ordner_id"], self.db.ordner_id_per_pfad("leistung", "Dach"))
        t.selection_set(f"i{self.lid}"); tab.dupl(); self.assertEqual(self.db.one("SELECT COUNT(*) c FROM leistung_lohn")["c"], 4)
        pfad = os.path.join(self.tmp, "kwp.csv"); self.files(pfad)
        self.answers({"format": "CSV (Tabelle)", "umfang": "Alle Leistungen", "trenner": "Semikolon ;", "kod": "Windows-1252 (Excel / ERP)", "dez": "Komma ,", "bst": True})
        ui_leistung.ExportDialog(self.app, None, None)
        self.assertTrue(os.path.exists(pfad) and os.path.exists(pfad[:-4] + "_Bausteine.csv"))
        t.selection_set("f4")
        self.answers({"format": "CSV (Tabelle)", "umfang": "Gewählter Ordner (inkl. Unterordner)", "trenner": "Komma ,", "kod": "UTF-8", "dez": "Punkt .", "bst": False})
        ui_leistung.ExportDialog(self.app, None, 4)
        self.assertEqual(len(open(pfad, encoding="utf-8-sig").read().strip().splitlines()), 1 + 2)  # Kopf + Wand-Leistung + Kopie
        dn = os.path.join(self.tmp, "DATANORM.001"); self.files(dn)
        self.answers({"format": "Datanorm 4.0 (für KWP)", "umfang": "Alle Leistungen", "trenner": "Semikolon ;", "kod": "UTF-8", "dez": "Komma ,", "bst": False})
        ui_leistung.ExportDialog(self.app, None, None)
        self.assertTrue(open(dn, "rb").read().startswith(b"V;"))

    def test_loehne(self):
        v = ui_stamm.LoehneView(Stub(), self.app); v.refresh()
        self.answers({"nr": "LA-9", "bez": "Meister", "satz": "70,00"}); v.neu()
        self.assertEqual(self.db.one("SELECT satz FROM lohnarten WHERE nr='LA-9'")["satz"], 70.0)
        self.answers({"satz": "52,50"}); v.std_aendern(); self.assertEqual(self.db.get_setting("lohnsatz"), "52.5")
        v.t.tree.selection_set(str(self.db.one("SELECT id FROM lohnarten WHERE nr='LA-1'")["id"])); v.loeschen()
        self.assertIsNone(self.db.one("SELECT lohnart_id FROM leistung_lohn WHERE leistung_id=?", (self.lid,))["lohnart_id"])

    def test_import_dialog(self):
        p = os.path.join(self.tmp, "s.csv")
        open(p, "w", encoding="utf-8").write("Artikelnummer;Bezeichnung;Einheit;Preis;Hersteller\nZ-1;Dachlatte 40x60;lfm;1,85;Sägewerk\nZ-2;Konterlatte;lfm;2,10;Sägewerk\n")
        d = ui_stamm.ImportDialog(self.app); self.files(p); d.datei()
        self.assertEqual(d.combos["preis"].get(), "Preis")
        d.v_neu.set("Holz / Latten"); d.start()
        a = self.db.one("SELECT * FROM artikel WHERE nr='Z-1'")
        self.assertEqual(self.db.ordner_pfad("artikel", a["ordner_id"]), "Holz / Latten")

    def test_picker_und_projekt(self):
        pk = ui_stamm.ArtikelPicker(self.app, Stub()); pk.ft.tree.selection_set("i2"); pk.ok(); self.assertEqual(pk.result, 2)
        w = ui_projekt.ProjektWindow(self.app, self.pid)
        self.assertEqual(len(w.tp.tree.get_children()), 6); self.assertEqual(len(w.to.tree.get_children()), 3)
        self.assertIn("h", w.to.tree.nodes[w.to.tree.get_children()[0]]["values"][6])
        self.answers({"titel": "v1"}); w.snap(); self.assertEqual(len(w.ts.tree.get_children()), 1)
        self.answers({"nr": "P-DEMO-001", "bezeichnung": "Haus", "kunde": "K", "ort": "O", "status": "Angebot", "datum": "15.10.2025",
                      "stichtag": "15.10.2025", "aufschlag": "15"}); w.stamm()
        self.assertEqual(self.db.one("SELECT aufschlag_override FROM projekte")["aufschlag_override"], 15.0)
        self.assertGreater(w.result["summen"]["material"], w.result["summen"]["material_ek"] * 1.14)
        pdf = os.path.join(self.tmp, "x.pdf"); self.files(pdf); w.pdf(); self.assertTrue(os.path.exists(pdf))
        w.ts.tree.selection_set(w.ts.tree.get_children()[0]); w.s_pdf(); w.s_show()

    def test_passwort_dialog_und_dashboard(self):
        self.answers({"pw1": "geheim1", "pw2": "geheim2"}, {"pw1": "geheim1", "pw2": "geheim1"})
        self.assertTrue(ui.passwort_dialog(Stub(), self.db)); self.assertTrue(auth.check_password(self.db, "geheim1"))
        self.answers({"pw": "falsch"}, {"pw": "geheim1"}); self.assertTrue(ui.passwort_dialog(Stub(), self.db))
        self.answers(None); self.assertFalse(ui.passwort_dialog(Stub(), self.db))
        d = ui.DashboardTab(Stub(), self.app); d.refresh()
        for c in (ui_projekt.ProjekteTab, ui_stamm.StammdatenTab):
            c(Stub(), self.app).refresh()


if __name__ == "__main__":
    unittest.main()
