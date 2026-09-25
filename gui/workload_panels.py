"""
Panneaux GUI des workloads v2.1 : SharePoint, OneDrive, Exchange, Teams.

Construits sur le même pattern que les onglets existants (barre de
boutons + Treeview via MainWindow._make_tree) mais regroupés ici pour
ne pas alourdir main_window.py. Chaque classe expose build(tab_frame)
qui rend le panneau inactif tant qu'aucun tenant n'est connecté (les
boutons vérifient la présence du service).
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from services.sharepoint_service import SharePointService, _gb
from services.onedrive_service import OneDriveService
from services.exchange_service import ExchangeService
from services.teams_service import TeamsService

if TYPE_CHECKING:  # pragma: no cover
    from gui.main_window import GraphTenantManagerApp


class WorkloadPanel:
    """
    Socle commun des panneaux workload.

    Un panneau = barre de boutons + Treeview + data cache. Le panneau
    ne connaît ni le runner ni le root : il reçoit des callbacks
    (set_busy, set_idle, run, error) branchés par la fenêtre principale.
    """

    def __init__(self, app: "GraphTenantManagerApp"):
        self.app = app
        self.data: List[Dict[str, Any]] = []
        self.tree: Optional[ttk.Treeview] = None

    # -- helpers fournis par la fenêtre principale ---------------------

    REFRESH_MSG = ""
    LABEL = ""

    # loader/renderer : méthodes concrètes par sous-classe
    # (refresh() les résout dynamiquement — pas de déclaration abstraite)

    @property
    def service(self):
        """Service métier du panneau (None si non connecté)."""
        raise NotImplementedError

    def set_busy(self, msg: str) -> None:
        self.app._set_busy(msg)

    def set_idle(self, msg: str) -> None:
        self.app._set_idle(msg)

    def run(self, factory: Callable, on_ok: Callable, label: str) -> None:
        """Exécute une coroutine (ou fonction) en arrière-plan."""
        self.app.runner.run_in_thread(
            factory,
            callback=lambda result: self.app.root.after(0, lambda: on_ok(result)),
            error_callback=self.app._make_error_cb(label),
        )

    def ask_csv_path(self, default: str) -> Optional[str]:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=default,
            filetypes=[("Fichier CSV", "*.csv")])
        return path or None

    def _tree(self) -> ttk.Treeview:
        """Treeview du panneau (toujours construit par build())."""
        assert self.tree is not None
        return self.tree

    # -- cycle commun ---------------------------------------------------

    def refresh(self) -> None:
        if self.service is None:
            messagebox.showinfo("Non connecté",
                                "Connectez-vous à un tenant d'abord.")
            return
        self.set_busy(self.REFRESH_MSG)
        self.run(self.loader, self.renderer, self.LABEL)


class SharePointPanel(WorkloadPanel):
    """Onglet SharePoint : inventaire des sites + bibliothèques."""

    REFRESH_MSG = "Chargement des sites SharePoint..."
    LABEL = "Chargement des sites SharePoint"

    @property
    def service(self) -> Optional[SharePointService]:
        return self.app.sharepoint_service

    @property
    def loader(self):
        return self.service.get_sites

    def build(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, pady=(0, 6))
        self.btn_refresh = ttk.Button(top, text="🔄 Actualiser",
                                      command=self.refresh)
        self.btn_refresh.pack(side=tk.LEFT, padx=2)
        self.btn_libraries = ttk.Button(top, text="📚 Bibliothèques",
                                        command=self.show_libraries)
        self.btn_libraries.pack(side=tk.LEFT, padx=2)
        self.btn_export = ttk.Button(top, text="📊 Export CSV",
                                     command=self.export_csv)
        self.btn_export.pack(side=tk.LEFT, padx=2)

        self.tree = self.app._make_tree(
            parent,
            ["Site", "URL", "Créé le", "Modifié le", "Type"],
            widths=[220, 300, 90, 90, 90],
        )
        self.tree.bind("<Double-1>", lambda e: self.show_libraries())

    def renderer(self, sites: List[Dict[str, Any]]) -> None:
        self.data = sites
        self.tree.delete(*self.tree.get_children())
        for s in sites:
            self.tree.insert("", tk.END, iid=s.get("id"), values=(
                s.get("name", ""),
                s.get("url", ""),
                s.get("created", ""),
                s.get("last_modified", ""),
                "Perso" if s.get("personal") else "SharePoint",
            ))
        self.set_idle(f"✓ {len(sites)} sites listés")

    def show_libraries(self) -> None:
        site = self._selected()
        if not site:
            messagebox.showinfo("Sélection", "Sélectionnez un site d'abord.")
            return
        self.set_busy("Chargement des bibliothèques...")
        self.run(lambda: self.service.get_libraries(site["id"]),
                 self._render_libraries(site),
                 "Chargement des bibliothèques")

    def _render_libraries(self, site: Dict) -> Callable:
        def apply(drives: List[Dict[str, Any]]) -> None:
            lines = [f"Bibliothèques de « {site['name']} » :",
                     f"{'Nom':<28}{'Type':<14}{'Utilisé':>10}{'Quota':>10}"]
            for d in drives:
                lines.append(
                    f"{(d.get('name') or '')[:26]:<28}"
                    f"{(d.get('type') or '')[:12]:<14}"
                    f"{_gb(d.get('storage_used')) or '-':>10}"
                    f"{_gb(d.get('storage_quota')) or '-':>10}")
            messagebox.showinfo("Bibliothèques", "\n".join(lines))
            self.set_idle(f"✓ {len(drives)} bibliothèque(s)")
        return apply

    def export_csv(self) -> None:
        if not self.data:
            messagebox.showinfo("Export", "Aucune donnée à exporter.")
            return
        path = self.ask_csv_path("sites_sharepoint.csv")
        if not path:
            return
        if self.service.export_to_csv(self.data, path):
            self.set_idle(f"✓ Export écrit : {path}")
        else:
            messagebox.showerror("Export", "Échec de l'export CSV.")

    def _selected(self) -> Optional[Dict[str, Any]]:
        sel = self.tree.selection()
        if not sel:
            return None
        item = self.tree.item(sel[0])
        name = item["values"][0] if item["values"] else ""
        for s in self.data:
            if s.get("id") == sel[0]:
                return s
        return next((s for s in self.data if s.get("name") == name), None)


class OneDrivePanel(WorkloadPanel):
    """Onglet OneDrive : lecteurs personnels + quotas."""

    REFRESH_MSG = "Chargement des lecteurs OneDrive..."
    LABEL = "Chargement des lecteurs OneDrive"

    @property
    def service(self) -> Optional[OneDriveService]:
        return self.app.onedrive_service

    @property
    def loader(self):
        return self.service.get_drives

    def build(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, pady=(0, 6))
        self.btn_refresh = ttk.Button(top, text="🔄 Actualiser",
                                      command=self.refresh)
        self.btn_refresh.pack(side=tk.LEFT, padx=2)
        self.btn_export = ttk.Button(top, text="📊 Export CSV",
                                     command=self.export_csv)
        self.btn_export.pack(side=tk.LEFT, padx=2)

        self.tree = self.app._make_tree(
            parent,
            ["Propriétaire", "Email", "Utilisé", "Quota", "Disponible"],
            widths=[200, 220, 90, 90, 100],
        )

    def renderer(self, drives: List[Dict[str, Any]]) -> None:
        self.data = drives
        self.tree.delete(*self.tree.get_children())
        for d in drives:
            remaining = d.get("storage_remaining")
            warn = remaining is not None and remaining < 5 * 1024 ** 3
            self.tree.insert("", tk.END, iid=d.get("id"), values=(
                d.get("owner", ""),
                d.get("owner_email", ""),
                _gb(d.get("storage_used")),
                _gb(d.get("storage_quota")),
                _gb(remaining),
            ), tags=("warning",) if warn else ())
        self.tree.tag_configure("warning", foreground="#cc0000")
        self.set_idle(f"✓ {len(drives)} lecteur(s) listé(s)")

    def export_csv(self) -> None:
        if not self.data:
            messagebox.showinfo("Export", "Aucune donnée à exporter.")
            return
        path = self.ask_csv_path("onedrive.csv")
        if not path:
            return
        if self.service.export_to_csv(self.data, path):
            self.set_idle(f"✓ Export écrit : {path}")
        else:
            messagebox.showerror("Export", "Échec de l'export CSV.")


class ExchangePanel(WorkloadPanel):
    """Onglet Exchange : utilisation des boîtes (rapport D30 par défaut)."""

    REFRESH_MSG = "Chargement de l'utilisation des boîtes (D30)..."
    LABEL = "Chargement du rapport Exchange"

    @property
    def service(self) -> Optional[ExchangeService]:
        return self.app.exchange_service

    @property
    def loader(self):
        return self.service.get_mailbox_usage

    def build(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, pady=(0, 6))
        self.btn_refresh = ttk.Button(top, text="🔄 Actualiser",
                                      command=self.refresh)
        self.btn_refresh.pack(side=tk.LEFT, padx=2)
        self.btn_export = ttk.Button(top, text="📊 Export CSV",
                                     command=self.export_csv)
        self.btn_export.pack(side=tk.LEFT, padx=2)

        self.tree = self.app._make_tree(
            parent,
            ["Boîte", "UPN", "Taille", "Nb éléments", "Dernière activité"],
            widths=[200, 230, 90, 100, 120],
        )

    def renderer(self, mailboxes: List[Dict[str, Any]]) -> None:
        self.data = mailboxes
        self.tree.delete(*self.tree.get_children())
        for m in mailboxes:
            self.tree.insert("", tk.END, values=(
                m.get("display_name", ""),
                m.get("upn", ""),
                _gb(m.get("storage_used")),
                m.get("item_count", ""),
                m.get("last_activity", ""),
            ))
        self.set_idle(f"✓ {len(mailboxes)} boîte(s) en activité")

    def export_csv(self) -> None:
        if not self.data:
            messagebox.showinfo("Export", "Aucune donnée à exporter.")
            return
        path = self.ask_csv_path("exchange_boites.csv")
        if not path:
            return
        if self.service.export_to_csv(self.data, path):
            self.set_idle(f"✓ Export écrit : {path}")
        else:
            messagebox.showerror("Export", "Échec de l'export CSV.")


class TeamsPanel(WorkloadPanel):
    """Onglet Teams : équipes + canaux + effectifs à la demande."""

    REFRESH_MSG = "Chargement des équipes..."
    LABEL = "Chargement des équipes"

    @property
    def service(self) -> Optional[TeamsService]:
        return self.app.teams_service

    @property
    def loader(self):
        return self.service.get_all_teams_formatted

    def build(self, parent) -> None:
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, pady=(0, 6))
        self.btn_refresh = ttk.Button(top, text="🔄 Actualiser",
                                      command=self.refresh)
        self.btn_refresh.pack(side=tk.LEFT, padx=2)
        self.btn_channels = ttk.Button(top, text="📺 Canaux",
                                       command=self.show_channels)
        self.btn_channels.pack(side=tk.LEFT, padx=2)
        self.btn_export = ttk.Button(top, text="📊 Export CSV",
                                     command=self.export_csv)
        self.btn_export.pack(side=tk.LEFT, padx=2)

        self.tree = self.app._make_tree(
            parent,
            ["Équipe", "Email", "Visibilité", "Archivée", "Créée le"],
            widths=[220, 230, 100, 80, 90],
        )
        self.tree.bind("<Double-1>", lambda e: self.show_channels())

    def renderer(self, teams: List[Dict[str, Any]]) -> None:
        self.data = teams
        self.tree.delete(*self.tree.get_children())
        for t in teams:
            self.tree.insert("", tk.END, iid=t.get("id"), values=(
                t.get("name", ""),
                t.get("mail", ""),
                t.get("visibility", ""),
                "Oui" if t.get("archived") else "Non",
                t.get("created", ""),
            ))
        self.set_idle(f"✓ {len(teams)} équipe(s) listée(s)")

    def show_channels(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Sélection", "Sélectionnez une équipe d'abord.")
            return
        team = next((t for t in self.data if t.get("id") == sel[0]), None)
        if not team:
            return
        self.set_busy("Chargement des canaux...")
        self.run(
            lambda: self.service.get_team_channels(team["id"]),
            self._render_channels(team),
            "Chargement des canaux",
        )

    def _render_channels(self, team: Dict) -> Callable:
        def apply(channels: List[Dict[str, Any]]) -> None:
            lines = [f"Canaux de « {team['name']} » :"]
            for c in channels:
                typ = {"standard": "Std", "private": "Privé",
                       "shared": "Partagé"}.get(c.get("type"), c.get("type"))
                lines.append(f"  • {c.get('name')}  [{typ}]")
            messagebox.showinfo("Canaux", "\n".join(lines) or "Aucun canal.")
            self.set_idle(f"✓ {len(channels)} canal/canaux")
        return apply

    def export_csv(self) -> None:
        if not self.data:
            messagebox.showinfo("Export", "Aucune donnée à exporter.")
            return
        path = self.ask_csv_path("teams.csv")
        if not path:
            return
        if self.service.export_to_csv(self.data, path):
            self.set_idle(f"✓ Export écrit : {path}")
        else:
            messagebox.showerror("Export", "Échec de l'export CSV.")