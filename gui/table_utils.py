"""
Utilitaires de tableaux intelligents (v2.1.5) : tri au clic + filtre live.

Fonctionnement :
- TableEnhancer s'attache à un ttk.Treeview EXISTANT (aucun changement
  de code côté rendu : il détecte lui-même les rechargements via un
  wrapper sur insert/delete).
- Tri : clic sur un en-tête → type détecté automatiquement par colonne
  (nombres — y compris « 24 Go » / « 95 % », dates dd/mm/yyyy ou ISO,
  texte insensible aux accents/casse). Second clic = ordre inverse,
  flèche ▲/▼ dans l'en-tête.
- Filtre : saisie instantanée, insensible accents/casse, multi-termes
  (séparés par espaces = ET logique) sur TOUTES les colonnes.
  Compteur « X / Y » affiché pendant le filtrage. Échap = efface.

API :
- enhance_tree(tree, filter_entry=None, count_label=None) -> TableEnhancer
  (créé par MainWindow._make_tree ; les panneaux/dialogues en profitent
  automatiquement)
- make_sortable(tree) : tri seul (dialogues modaux)
- TableEnhancer.sort_by(col) / set_filter(term) / refresh_view()
"""

import re
import tkinter as tk
import unicodedata
from tkinter import ttk
from typing import Any, List, Optional, Tuple

_ARROW_ASC = " ▲"
_ARROW_DESC = " ▼"

_NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_FR_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
# Multiplicateurs d'unités courantes (insensible casse) — pour trier
# « 980 Mo » < « 15 Go » intelligemment plutôt que 980 > 15 en brut.
_UNIT_FACTORS = {
    "mo": 1.0, "mb": 1.0, "mio": 1.048576,
    "go": 1024.0, "gb": 1024.0, "gio": 1073.741824,
    "ko": 1.0 / 1024.0, "kb": 1.0 / 1024.0,
}


def normalize(text: Any) -> str:
    """Minuscules + accents supprimés (é→e) — comparaison naturelle FR."""
    s = str(text if text is not None else "").casefold()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _leading_number(s: str) -> Optional[float]:
    """Premier nombre d'une cellule (« 24 Go » → 24576 en Mo, « 95 % » → 95)."""
    m = _NUM_RE.search(s)
    if not m:
        return None
    value = float(m.group().replace(",", "."))
    # Unité juste après le nombre ? (Go, Mo, ko, GB...)
    rest = s[m.end():].strip().casefold()
    for unit, factor in _UNIT_FACTORS.items():
        if rest.startswith(unit):
            return value * factor
    return value


def _fr_date(s: str):
    """Date dd/mm/yyyy → tuple triable ; None si pas une date."""
    m = _FR_DATE_RE.match(s.strip())
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return (y, mo, d)


def _key_factory(samples: List[str]):
    """
    Construit la fonction de tri d'une colonne à partir d'un échantillon
    de ses valeurs. Détection : nombre > date FR > texte normalisé.
    Cellules vides toujours rejetées en fin de tri asc.
    """
    non_empty = [str(v).strip() for v in samples
                 if str(v or "").strip() and str(v).strip() != "—"]
    if non_empty:
        nums = [_leading_number(v) for v in non_empty]
        if all(n is not None for n in nums):
            def num_key(v: str):
                n = _leading_number(str(v))
                return (0, n, normalize(v)) if n is not None else (1, 0.0, "")
            return num_key
        dates = [_fr_date(v) for v in non_empty]
        if all(d is not None for d in dates):
            def date_key(v: str):
                d = _fr_date(str(v))
                return (0, d) if d else (1, ())
            return date_key

    def text_key(v: str):
        s = str(v or "").strip()
        return (1, "") if not s or s == "—" else (0, normalize(s))
    return text_key


class TableEnhancer:
    """Tri + filtre pour un Treeview plat (show='headings')."""

    def __init__(self, tree: ttk.Treeview, filter_var: Optional[tk.StringVar] = None,
                 count_label: Optional[Any] = None):
        self.tree = tree
        self.filter_var = filter_var
        self.count_label = count_label
        self._all_items: List[Tuple[str, Tuple, Tuple]] = []
        self._dirty = True
        self._applying = False
        self._sort_col: Optional[str] = None
        self._sort_desc = False
        self._refresh_pending = None
        self._orig_headings = {}
        self._wrap_mutators()
        if filter_var is not None:
            filter_var.trace_add("write", lambda *_: self.refresh_view())
        # Échap = vider le filtre
        if filter_var is not None:
            tree.bind("<Escape>", lambda e: (filter_var.set(""), "break")[1])
        # Tri par clic sur les en-têtes
        for col in tree["columns"]:
            self._orig_headings[col] = tree.heading(col, "text")
            tree.heading(col, command=lambda c=col: self.sort_by(c))

    # -- détection des rechargements -----------------------------------
    def _wrap_mutators(self):
        tree = self.tree
        orig_insert, orig_delete = tree.insert, tree.delete

        def insert(*a, **k):
            if not self._applying:
                self._dirty = True
                self._schedule_refresh()
            return orig_insert(*a, **k)

        def delete(*a, **k):
            if not self._applying:
                self._dirty = True
                self._schedule_refresh()
            return orig_delete(*a, **k)

        tree.insert = insert
        tree.delete = delete

    def _schedule_refresh(self):
        """Après un rechargement : ré-applique filtre/tri si actifs."""
        has_filter = bool(self.filter_var is not None and self.filter_var.get().strip())
        if not (has_filter or self._sort_col):
            return  # vue brute : rien à ré-appliquer
        if self._refresh_pending is None:
            def _do():
                self._refresh_pending = None
                self.refresh_view()
            self._refresh_pending = self.tree.after_idle(_do)

    # -- API -------------------------------------------------------------
    def sort_by(self, col: str) -> None:
        """Clic sur l'en-tête d'une colonne : tri asc, re-clic = desc."""
        if col == self._sort_col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = False
        self._update_heading_arrows()
        self.refresh_view()

    def set_filter(self, term: str) -> None:
        if self.filter_var is not None:
            self.filter_var.set(term)
        else:
            self._pending_filter = term
            self.refresh_view()

    def refresh_view(self) -> None:
        """Réapplique filtre + tri sur l'état actuel (re-snapshot si besoin)."""
        term = (self.filter_var.get() if self.filter_var is not None
                else getattr(self, "_pending_filter", ""))
        has_filter = bool(term.strip())
        if not self._dirty and not has_filter and not self._sort_col:
            return
        if self._dirty:
            self._snapshot()
        rows = self._all_items
        if has_filter:
            terms = [normalize(t) for t in term.split()]
            rows = [
                r for r in rows
                if all(t in normalize(" ".join(str(v) for v in r[1])) for t in terms)
            ]
        if self._sort_col:
            col_idx = list(self.tree["columns"]).index(self._sort_col)
            samples = [r[1][col_idx] for r in rows] or [""]
            key = _key_factory(samples)
            rows = sorted(rows, key=lambda r: key(r[1][col_idx]),
                          reverse=self._sort_desc)
        # Réinsérer (iids stables → sélection/détails conservés)
        self._applying = True
        try:
            self.tree.delete(*self.tree.get_children())
            for iid, values, tags in rows:
                self.tree.insert("", tk.END, iid=iid, values=values,
                                 tags=tags if tags else ())
        finally:
            self._applying = False
        if self.count_label is not None:
            total = len(self._all_items)
            if has_filter and total:
                self.count_label.config(text=f"{len(rows)} / {total} lignes")
            else:
                self.count_label.config(text="")

    # -- interne -----------------------------------------------------------
    def _snapshot(self):
        self._all_items = [
            (iid,
             tuple(self.tree.item(iid, "values")),
             tuple(self.tree.item(iid, "tags") or ()))
            for iid in self.tree.get_children()
        ]
        self._dirty = False

    def _update_heading_arrows(self):
        for col, text in self._orig_headings.items():
            if col == self._sort_col:
                arrow = _ARROW_DESC if self._sort_desc else _ARROW_ASC
                self.tree.heading(col, text=text + arrow)
            else:
                self.tree.heading(col, text=text)


def make_sortable(tree) -> TableEnhancer:
    """Tri seul (clic en-têtes) pour un Treeview de dialogue."""
    return TableEnhancer(tree)


def enhance_tree(tree, filter_var=None, count_label=None) -> TableEnhancer:
    """Tri + filtre complets — utilisé par MainWindow._make_tree."""
    return TableEnhancer(tree, filter_var=filter_var, count_label=count_label)