"""
Fenêtre principale de l'application Graph Tenant Manager.

v1.1 — Réécriture complète :
- Threading via AsyncRunner (fix du gel UI + bug 'Event loop is closed')
- 5 onglets complets : Dashboard, Utilisateurs, Groupes, Appareils, Licences
- Exports CSV, dialogues de gestion, alertes licences
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.async_runner import AsyncRunner
from core.auth import TenantAuthManager
from core.graph_client import GraphClientWrapper
from core import local_db
from services.users_service import UsersService
from services.groups_service import GroupsService
from services.devices_service import DevicesService
from services.licenses_service import LicensesService
from services.sharepoint_service import SharePointService
from services.onedrive_service import OneDriveService
from services.exchange_service import ExchangeService
from services.teams_service import TeamsService
from gui.dialogs import (
    UserCreateDialog,
    UserEditDialog,
    ResetPasswordDialog,
    AssignLicenseDialog,
    GroupCreateDialog,
    MembersDialog,
    UserDetailDialog,
    UnlicensedUsersDialog,
)

APP_TITLE = "🏢 Graph Tenant Manager"

# v2.1 : version applicative (affichée + comparée aux releases GitHub)
from core.app_info import APP_VERSION as APP_VERSION_LOCAL  # noqa: E402


def _looks_like_guid(s: str) -> bool:
    """True si la chaîne ressemble à un GUID (36 chars, 4 tirets)."""
    s = str(s)
    if len(s) != 36 or s.count("-") != 4:
        return False
    try:
        parts = s.split("-")
        return all(len(p) in (8, 4, 4, 4, 12) and all(c in "0123456789abcdefABCDEF" for c in p)
                   for p in [parts[0], parts[1], parts[2], parts[3], parts[4]])
    except Exception:
        return False


def _fmt_age(seconds: float) -> str:
    """v2.1.8 : âge lisible d'un cache (« 3 min », « 2 h », « 5 j »)."""
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return "?"
    if seconds < 0:
        return "?"
    if seconds < 60:
        return f"{int(seconds)} s"
    if seconds < 3600:
        return f"{int(seconds // 60)} min"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h"
    return f"{int(seconds // 86400)} j"


class GraphTenantManagerApp:
    """Application principale de gestion multi-tenants Microsoft Graph."""

    def __init__(self, root: tk.Tk, config: Dict):
        self.root = root
        self.config = config
        self.auth_manager = TenantAuthManager(config)
        self.runner = AsyncRunner.get_instance()

        self.graph_wrapper: Optional[GraphClientWrapper] = None
        self.users_service: Optional[UsersService] = None
        self.groups_service: Optional[GroupsService] = None
        self.devices_service: Optional[DevicesService] = None
        self.licenses_service: Optional[LicensesService] = None
        # Workloads v2.1
        self.sharepoint_service: Optional[SharePointService] = None
        self.onedrive_service: Optional[OneDriveService] = None
        self.exchange_service: Optional[ExchangeService] = None
        self.teams_service: Optional[TeamsService] = None

        self.current_tenant_id: Optional[str] = None
        self.tenant_info: Optional[Dict[str, Any]] = None
        # v2.1.5 : enhancers tri/filtre par treeview (id(tree) -> enhancer)
        self._tree_enhancers: Dict[int, Any] = {}

        # Caches de données par onglet
        self._users_data: List[Dict] = []
        self._groups_data: List[Dict] = []
        self._devices_data: List[Dict] = []
        self._licenses_data: List[Dict] = []
        # v2.1.7 : récapitulatif multi-tenant du dashboard
        self._portfolio_data: List[Dict[str, Any]] = []

        self.root.title(APP_TITLE)
        self.root.geometry("1280x800")
        self.root.minsize(1080, 700)
        # v2.1 : version affichée dans la barre de titre
        self.root.title(f"{APP_TITLE} — v{APP_VERSION_LOCAL}")

        self._setup_styles()
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()

        self._show_welcome()
        # v2.0 : propose la reconnexion silencieuse aux tenants déjà autorisés
        self.root.after(300, self._try_silent_reconnect)
        # v2.1 : vérification non bloquante des mises à jour GitHub
        self.root.after(800, self._check_for_updates)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # MISES À JOUR AUTOMATIQUES (v2.1)
    # ------------------------------------------------------------------

    def _check_for_updates(self, manual: bool = False):
        """Interroge GitHub en arrière-plan ; propose la mise à jour le cas échéant.

        manual=True (menu Aide, v2.1.6) : notifie TOUJOURS le résultat —
        « à jour », « injoignable » ou « disponible ». L'auto-check au
        démarrage reste silencieux s'il n'y a rien à dire.
        """
        import core.updater as updater

        if manual:
            self._set_busy("Vérification des mises à jour...")

        def check():
            return updater.check_update(verbose=manual)

        def on_result(info):
            def apply():
                if manual:
                    self._set_idle()
                if info:
                    self._offer_update(info)
                elif manual:
                    # v2.1.6 : confirmation explicite quand on force le check
                    messagebox.showinfo(
                        "✓ À jour",
                        f"Aucune mise à jour disponible.\n"
                        f"Vous utilisez déjà la version la plus récente "
                        f"(v{APP_VERSION_LOCAL}).",
                        parent=self.root,
                    )
            self.root.after(0, apply)

        def on_error(e):
            def apply():
                if manual:
                    self._set_idle()
                    messagebox.showerror(
                        "Vérification impossible",
                        f"La vérification des mises à jour a échoué :\n\n{e}\n\n"
                        f"Réessayez plus tard, ou consultez "
                        f"https://github.com/GregDepan/graph-tenant-manager/releases",
                        parent=self.root,
                    )
            self.root.after(0, apply)

        self.runner.run_in_thread(check, callback=on_result, error_callback=on_error)

    def _offer_update(self, info):
        """Affiche la notification de mise à jour disponible."""
        from tkinter import messagebox
        size_mo = info.get("size", 0) / (1024 * 1024)
        msg = (
            f"Une nouvelle version est disponible !\n\n"
            f"Version actuelle : {APP_VERSION_LOCAL}\n"
            f"Nouvelle version : v{info['version']}\n"
            f"Taille : {size_mo:.1f} Mo\n\n"
            f"Mettre à jour maintenant ?\n"
            f"(L'application redémarrera automatiquement)"
        )
        answer = messagebox.askyesno(
            "🔄 Mise à jour disponible", msg, icon="question", parent=self.root)
        if answer:
            self._apply_update(info)

    def _apply_update(self, info):
        """Télécharge et applique la mise à jour, avec barre de progression."""
        import core.updater as updater

        # Fenêtre de progression
        win = tk.Toplevel(self.root)
        win.title("Mise à jour en cours")
        win.geometry("380x120")
        win.resizable(False, False)
        win.transient(self.root)
        ttk.Label(win, text=f"Téléchargement v{info['version']}...",
                  padding=(15, 10)).pack()
        bar = ttk.Progressbar(win, length=340, mode="determinate", maximum=100)
        bar.pack(padx=15)
        pct_label = ttk.Label(win, text="0 %", padding=(15, 5))
        pct_label.pack()
        win.grab_set()

        def on_progress(received, total):
            def apply():
                pct = int(received * 100 / total)
                bar["value"] = pct
                pct_label.config(text=f"{pct} %")
            self.root.after(0, apply)

        def do_download():
            return updater.download_update(info["url"], progress_cb=on_progress)

        def on_done(path):
            def apply():
                if not path:
                    messagebox.showerror(
                        "Mise à jour",
                        "Le téléchargement a échoué.\n"
                        "Réessayez plus tard ou téléchargez manuellement\n"
                        "depuis https://github.com/GregDepan/graph-tenant-manager/releases",
                        parent=self.root)
                    win.destroy()
                    return
                # v2.1.9 : apply_update ne fait plus sys.exit() (le thread
                # worker n'y meurt que lui-même). Quand il rend True, le
                # nouvel exe est déjà relancé : on ferme CETTE instance
                # proprement depuis le main thread.
                if updater.apply_update(path):
                    win.destroy()
                    self._set_idle("✓ Mise à jour appliquée — relance...")
                    self.root.after(200, self._exit_after_update)
                else:
                    messagebox.showerror(
                        "Mise à jour",
                        "L'application de la mise à jour a échoué.",
                        parent=self.root)
                    win.destroy()
            self.root.after(0, apply)

        def on_error(exc):
            def apply():
                messagebox.showerror(
                    "Mise à jour", f"Téléchargement impossible : {exc}",
                    parent=self.root)
                win.destroy()
            self.root.after(0, apply)

        self.runner.run_in_thread(do_download, callback=on_done, error_callback=on_error)

    def _exit_after_update(self):
        """v2.1.9 : fermeture propre après mise à jour appliquée.

        Le nouvel exe est déjà relancé par apply_update() : on arrête le
        runner asyncio puis on détruit la fenêtre — depuis le MAIN
        thread (avant : sys.exit() dans le worker n'y tuait que le
        thread, l'ancienne app restait ouverte en doublon).
        """
        try:
            self.runner.stop()
        except Exception:
            pass
        self.root.destroy()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Title.TLabel', font=('Segoe UI', 16, 'bold'))
        style.configure('Subtitle.TLabel', font=('Segoe UI', 12))
        style.configure('Status.TLabel', font=('Segoe UI', 9))
        style.configure('Success.TLabel', foreground='green')
        style.configure('Error.TLabel', foreground='red')
        style.configure('Warning.TLabel', foreground='orange')
        style.configure('Treeview', rowheight=25)
        style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'))

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Fichier", menu=file_menu)
        file_menu.add_command(label="Connecter un tenant", command=self._connect_tenant)
        file_menu.add_command(label="Déconnecter", command=self._disconnect)
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self._on_close)

        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Affichage", menu=view_menu)
        view_menu.add_command(label="Dashboard", command=lambda: self.notebook.select(0))
        view_menu.add_command(label="Utilisateurs", command=self._show_users)
        view_menu.add_command(label="Groupes", command=self._show_groups)
        view_menu.add_command(label="Appareils", command=self._show_devices)
        view_menu.add_command(label="Licences", command=self._show_licenses)
        view_menu.add_command(label="SharePoint", command=lambda: self._show_workload_tab(5))
        view_menu.add_command(label="OneDrive", command=lambda: self._show_workload_tab(6))
        view_menu.add_command(label="Exchange", command=lambda: self._show_workload_tab(7))
        view_menu.add_command(label="Teams", command=lambda: self._show_workload_tab(8))

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Aide", menu=help_menu)
        help_menu.add_command(label="Documentation", command=self._show_help)
        help_menu.add_separator()
        help_menu.add_command(label="🔄 Vérifier les mises à jour",
                              command=lambda: self._check_for_updates(manual=True))
        help_menu.add_command(label="À propos", command=self._show_about)

    def _create_main_layout(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(main_frame)
        header.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(header, text=APP_TITLE, style='Title.TLabel').pack(side=tk.LEFT)

        tenant_frame = ttk.Frame(header)
        tenant_frame.pack(side=tk.RIGHT)

        ttk.Label(tenant_frame, text="Tenant:").pack(side=tk.LEFT, padx=(0, 5))
        self.tenant_var = tk.StringVar()
        self.tenant_combo = ttk.Combobox(
            tenant_frame, textvariable=self.tenant_var, width=40, state='readonly'
        )
        self.tenant_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.tenant_combo.bind('<<ComboboxSelected>>', self._on_tenant_selected)

        self.connect_btn = ttk.Button(header, text="🔐 Connecter", command=self._connect_tenant)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        self.refresh_btn = ttk.Button(header, text="🔄 Actualiser", command=self._refresh_data)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.dashboard_tab = ttk.Frame(self.notebook)
        self.users_tab = ttk.Frame(self.notebook)
        self.groups_tab = ttk.Frame(self.notebook)
        self.devices_tab = ttk.Frame(self.notebook)
        self.licenses_tab = ttk.Frame(self.notebook)
        # Workloads v2.1
        self.sharepoint_tab = ttk.Frame(self.notebook)
        self.onedrive_tab = ttk.Frame(self.notebook)
        self.exchange_tab = ttk.Frame(self.notebook)
        self.teams_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.dashboard_tab, text="📊 Dashboard")
        self.notebook.add(self.users_tab, text="👥 Utilisateurs")
        self.notebook.add(self.groups_tab, text="👥 Groupes")
        self.notebook.add(self.devices_tab, text="📱 Appareils")
        self.notebook.add(self.licenses_tab, text="🔑 Licences")
        self.notebook.add(self.sharepoint_tab, text="🗂️ SharePoint")
        self.notebook.add(self.onedrive_tab, text="☁️ OneDrive")
        self.notebook.add(self.exchange_tab, text="📧 Exchange")
        self.notebook.add(self.teams_tab, text="💬 Teams")

        self._build_users_tab()
        self._build_groups_tab()
        self._build_devices_tab()
        self._build_licenses_tab()
        # Workloads v2.1 — panneaux auto-contenus
        from gui.workload_panels import (
            SharePointPanel, OneDrivePanel, ExchangePanel, TeamsPanel,
        )
        self.sharepoint_panel = SharePointPanel(self)
        self.onedrive_panel = OneDrivePanel(self)
        self.exchange_panel = ExchangePanel(self)
        self.teams_panel = TeamsPanel(self)
        self.sharepoint_panel.build(self.sharepoint_tab)
        self.onedrive_panel.build(self.onedrive_tab)
        self.exchange_panel.build(self.exchange_tab)
        self.teams_panel.build(self.teams_tab)

    def _create_status_bar(self):
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_label = ttk.Label(
            self.status_frame, text="Statut: Non connecté", style='Status.TLabel', padding=5
        )
        self.status_label.pack(side=tk.LEFT)
        self.connection_label = ttk.Label(
            self.status_frame, text="", style='Status.TLabel', padding=5
        )
        self.connection_label.pack(side=tk.RIGHT)

    def _make_tree(self, parent, columns, widths=None, filterable=True):
        """Treeview standard + scrollbar, triable et filtrable (v2.1.5).

        filterable=True : ajoute une entrée de filtre instantané au-dessus
        du tableau (multi-termes, insensible aux accents) + compteur de
        lignes. Le tri par clic sur en-tête est TOUJOURS actif.
        """
        from gui.table_utils import TableEnhancer

        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True)

        enhancer_vars = {}
        if filterable:
            filter_bar = ttk.Frame(frame)
            filter_bar.pack(fill=tk.X, pady=(0, 2))
            filter_var = tk.StringVar()
            count_label = ttk.Label(filter_bar, text="", foreground="gray")
            entry = ttk.Entry(filter_bar, textvariable=filter_var)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            count_label.pack(side=tk.LEFT, padx=(8, 0))
            enhancer_vars = {"var": filter_var, "label": count_label}

        tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        for i, col in enumerate(columns):
            tree.heading(col, text=col)
            tree.column(col, width=(widths[i] if widths else 120), anchor=tk.W)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        enh = TableEnhancer(
            tree,
            filter_var=enhancer_vars.get("var"),
            count_label=enhancer_vars.get("label"),
        )
        self._tree_enhancers[id(tree)] = enh
        return tree

    def _set_busy(self, msg):
        self.status_label.config(text="⏳ " + msg, foreground='orange')
        self.root.config(cursor='watch')
        for btn in self._collect_action_buttons():
            btn.state(['disabled'])
        self.root.update_idletasks()

    def _set_idle(self, msg_ok=None):
        self.root.config(cursor='arrow')
        for btn in self._collect_action_buttons():
            btn.state(['!disabled'])
        if msg_ok:
            green = ('✓' in msg_ok) or ('✔' in msg_ok)
            self.status_label.config(
                text="Statut: " + msg_ok,
                foreground='green' if green else 'black',
            )

    def _collect_action_buttons(self):
        btns = []
        if hasattr(self, 'users_btns'):
            btns += list(self.users_btns.values())
        if hasattr(self, 'groups_btns'):
            btns += list(self.groups_btns.values())
        if hasattr(self, 'btn_refresh_devices'):
            btns += [self.btn_refresh_devices, self.btn_export_devices]
        if hasattr(self, 'btn_refresh_licenses'):
            btns += [self.btn_refresh_licenses, self.btn_unlicensed, self.btn_export_licenses]
        # Workloads v2.1 : boutons des panneaux
        for pname in ('sharepoint_panel', 'onedrive_panel',
                      'exchange_panel', 'teams_panel'):
            panel = getattr(self, pname, None)
            if panel is not None:
                btns += [b for b in (
                    getattr(panel, 'btn_refresh', None),
                    getattr(panel, 'btn_libraries', None),
                    getattr(panel, 'btn_channels', None),
                    getattr(panel, 'btn_export', None),
                ) if b is not None]
        if hasattr(self, 'connect_btn'):
            btns += [self.connect_btn, self.refresh_btn]
        return [b for b in btns if b is not None]

    def _on_tab_changed(self, event):
        if not self.graph_wrapper:
            return
        tab = self.notebook.index(self.notebook.select())
        if tab == 1 and not self._users_data:
            self._load_users()
        elif tab == 2 and not self._groups_data:
            self._load_groups()
        elif tab == 3 and not self._devices_data:
            self._load_devices()
        elif tab == 4 and not self._licenses_data:
            self._load_licenses()
        elif 5 <= tab <= 8:
            if self.current_tenant_id and not self.auth_manager.has_workload_scopes(self.current_tenant_id):
                self._set_idle("⚠️ Permissions réduites : onglet workload indisponible "
                               "jusqu'au consentement admin des nouveaux scopes.")
                return
            panel = self._workload_panel(tab)
            if panel is not None and not panel.data:
                panel.refresh()

    # Workloads v2.1 : sélecteur d'onglet + helpers ---------------------

    def _workload_panel(self, tab_index: int):
        """Retourne le panel workload pour l'index d'onglet (5-8), sinon None."""
        mapping = {5: "sharepoint_panel", 6: "onedrive_panel",
                   7: "exchange_panel", 8: "teams_panel"}
        attr = mapping.get(tab_index)
        return getattr(self, attr, None) if attr else None

    def _show_workload_tab(self, index: int):
        self.notebook.select(index)
        panel = self._workload_panel(index)
        if panel is not None and self.graph_wrapper and not panel.data:
            panel.refresh()

    def _show_welcome(self):
        for widget in self.dashboard_tab.winfo_children():
            widget.destroy()
        wf = ttk.Frame(self.dashboard_tab)
        wf.pack(fill=tk.BOTH, expand=True, padx=50, pady=50)
        ttk.Label(wf, text="Bienvenue dans Graph Tenant Manager", style='Title.TLabel').pack(pady=20)
        ttk.Label(
            wf,
            text="Connectez-vous à un tenant Microsoft 365 pour commencer",
            style='Subtitle.TLabel',
        ).pack(pady=10)
        ttk.Label(
            wf,
            text=(
                "• Gérer plusieurs tenants clients\n"
                "• Administrer utilisateurs, groupes, appareils\n"
                "• Inventaire des licences et alertes\n"
                "• Exports CSV pour tes rapports clients"
            ),
            justify=tk.LEFT,
        ).pack(pady=20)

    # ================================================================
    # ONGLET UTILISATEURS
    # ================================================================

    def _build_users_tab(self):
        top = ttk.Frame(self.users_tab)
        top.pack(fill=tk.X, pady=(0, 6))

        self.user_search_var = tk.StringVar()
        search_entry = ttk.Entry(top, textvariable=self.user_search_var, width=28)
        search_entry.pack(side=tk.LEFT, padx=(0, 5))
        search_entry.bind("<Return>", lambda e: self._search_users_action())

        search_btn = ttk.Button(top, text="🔍", command=self._search_users_action)
        search_btn.pack(side=tk.LEFT, padx=(0, 15))

        self.users_btns = {}
        self.users_btns['create'] = ttk.Button(top, text="➕ Créer", command=self._user_create)
        self.users_btns['create'].pack(side=tk.LEFT, padx=2)
        self.users_btns['edit'] = ttk.Button(top, text="✏️ Modifier", command=self._user_edit)
        self.users_btns['edit'].pack(side=tk.LEFT, padx=2)
        self.users_btns['reset'] = ttk.Button(top, text="🔒 Réinit. MDP", command=self._user_reset_password)
        self.users_btns['reset'].pack(side=tk.LEFT, padx=2)
        self.users_btns['license'] = ttk.Button(top, text="🔑 Licences", command=self._user_license)
        self.users_btns['license'].pack(side=tk.LEFT, padx=2)
        self.users_btns['block'] = ttk.Button(top, text="⛔ Bloquer/Débloquer", command=self._user_block)
        self.users_btns['block'].pack(side=tk.LEFT, padx=2)
        self.users_btns['delete'] = ttk.Button(top, text="🗑️ Supprimer", command=self._user_delete)
        self.users_btns['delete'].pack(side=tk.LEFT, padx=2)
        self.users_btns['export'] = ttk.Button(top, text="📊 Export CSV", command=self._export_users_csv)
        self.users_btns['export'].pack(side=tk.LEFT, padx=2)

        self.users_tree = self._make_tree(
            self.users_tab,
            ["Nom", "Email", "Poste", "Département", "Licences", "Actif", "UPN"],
            widths=[200, 240, 130, 130, 220, 60, 220],
        )
        self.users_tree.bind("<Double-1>", lambda e: self._user_details())
        self.users_tree.tag_configure('disabled_account', foreground='#888888')

    def _load_users(self, force_refresh: bool = False):
        users_service = self.users_service
        licenses_service = self.licenses_service
        if not users_service:
            return
        tid = self.current_tenant_id
        # v2.1.8 : cache-aside — affiche le cache immédiatement si dispo
        # (bascule de tenant / retour d'onglet instantanés), puis
        # rafraîchit en arrière-plan.
        cached = local_db.load_collection(tid, "users") if tid else None
        if cached and (self._users_data or []).__len__() == 0:
            self._render_users(cached, from_cache=True)

        self._set_busy("Chargement des utilisateurs...")

        def factory():
            # v2.1.3 : charge aussi l'inventaire licences si absent —
            # nécessaire pour afficher les noms de licences par utilisateur.
            async def inner():
                users = await users_service.get_all_users_formatted()
                if not self._licenses_data and licenses_service:
                    try:
                        self._licenses_data = await licenses_service.get_inventory()
                    except Exception:
                        pass  # l'affichage retombe sur les part numbers
                return users
            return inner()

        def on_fresh(users):
            def apply():
                if tid:
                    local_db.save_collection(tid, "users", users)
                self._render_users(users)
            self.root.after(0, apply)

        self.runner.run_in_thread(
            factory,
            callback=on_fresh,
            error_callback=self._make_error_cb("Chargement des utilisateurs"),
        )

    def _license_names_map(self) -> Dict[str, str]:
        """
        Map {sku_id GUID -> nom commercial} pour afficher les licences par
        utilisateur (v2.1.3). Se base sur l'inventaire chargé ; sinon vide.
        """
        m: Dict[str, str] = {}
        for lic in (self._licenses_data or []):
            sid = lic.get("sku_id") or ""
            if sid:
                m[str(sid)] = lic.get("display_name") or lic.get("part_number") or ""
        return m

    def _user_license_cell(self, u: Dict) -> str:
        """Cellule « Licences » pour le tableau Utilisateurs : noms lisibles."""
        skus = u.get("license_skus") or []
        if not skus:
            return "✖ Aucune"
        m = self._license_names_map()
        names = []
        for s in skus:
            s = str(s)
            name = m.get(s)
            if not name and s and not _looks_like_guid(s):
                # part number inconnu de l'inventaire → nom FR si mappé
                from services.licenses_service import _sku_display_name
                name = _sku_display_name(s)
            names.append(name or s)
        return "✔ " + ", ".join(names)

    def _render_users(self, users, from_cache: bool = False):
        self._users_data = users
        self.users_tree.delete(*self.users_tree.get_children())
        for u in users:
            enabled = u.get('account_enabled', True)
            self.users_tree.insert("", tk.END, iid=u.get('id'), values=(
                u.get('display_name', ''),
                u.get('email', ''),
                u.get('job_title', ''),
                u.get('department', ''),
                self._user_license_cell(u),
                "Oui" if enabled else "Non",
                u.get('user_principal_name', ''),
            ), tags=('disabled_account',) if not enabled else ())
        if from_cache:
            # v2.1.8 : cache affiché — le refresh réseau arrive derrière
            age = local_db.collection_age_seconds(self.current_tenant_id or "", "users")
            if age is not None:
                self._set_idle(f"✓ {len(users)} utilisateurs (cache local, "
                               f"rafraîchi il y a {_fmt_age(age)})")
        else:
            self._set_idle(f"✓ {len(users)} utilisateurs chargés")

    def _search_users_action(self):
        term = self.user_search_var.get().strip()
        if not self.users_service:
            return
        if len(term) >= 3:
            self._set_busy(f"Recherche « {term} »...")
            self.runner.run_in_thread(
                lambda: self.users_service.search(term),
                callback=lambda result: self.root.after(0, lambda: self._render_users(result)),
                error_callback=self._make_error_cb("Recherche"),
            )
        elif not term:
            self._load_users()
        else:
            self._render_users([
                u for u in self._users_data
                if term.lower() in ((u.get('display_name') or '')
                                    + (u.get('email') or '')
                                    + (u.get('user_principal_name') or '')).lower()
            ])

    def _selected_user(self):
        sel = self.users_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Sélectionnez d'abord un utilisateur dans la liste.")
            return None
        uid = sel[0]
        for u in self._users_data:
            if u.get('id') == uid:
                return u
        return None

    def _make_error_cb(self, label):
        def error_cb(e):
            def apply():
                self._set_idle()
                messagebox.showerror("Erreur", f"{label} : {e}")
            self.root.after(0, apply)
        return error_cb

    def _run_action(self, factory, msg_ok, reload=True):
        """Exécute une action Graph en thread + recharge les utilisateurs."""
        self.runner.run_in_thread(
            factory,
            callback=lambda ok: self.root.after(0, lambda: self._after_action(ok, msg_ok, reload)),
            error_callback=self._make_error_cb(msg_ok),
        )

    def _after_action(self, ok, msg_ok, reload=True):
        self._set_idle()
        if ok:
            if reload:
                self._load_users()
            self.status_label.config(text="Statut: " + msg_ok, foreground='green')
        else:
            messagebox.showerror("Erreur", "L'opération a échoué (Graph a refusé ou erreur API).")

    def _user_details(self):
        user = self._selected_user()
        if user:
            UserDetailDialog(self.root, user, license_names=self._license_names_map())

    def _user_create(self):
        if not self.users_service:
            return
        domain = ""
        if self.tenant_info and self.tenant_info.get('verified_domains'):
            domains = [d for d in self.tenant_info['verified_domains'] if d]
            domain = domains[0] if domains else ""
        dlg = UserCreateDialog(self.root, default_domain=domain)
        if not dlg.result:
            return
        data = dlg.result
        self._set_busy("Création de l'utilisateur...")
        self._run_action(lambda: self.users_service.create(data), "Utilisateur créé ✓")

    def _user_edit(self):
        if not self.users_service:
            return
        user = self._selected_user()
        if not user:
            return
        dlg = UserEditDialog(self.root, user)
        if not dlg.result:
            return
        updates = dlg.result
        self._set_busy("Modification en cours...")
        self._run_action(lambda: self.users_service.update(user['id'], updates), "Utilisateur modifié ✓")

    def _user_reset_password(self):
        if not self.users_service:
            return
        user = self._selected_user()
        if not user:
            return
        dlg = ResetPasswordDialog(self.root, user)
        if not dlg.result:
            return
        password, force_change = dlg.result
        self._set_busy("Réinitialisation du mot de passe...")

        def factory():
            return self.users_service.reset_password(user['id'], password, force_change)

        def on_ok(ok):
            def apply():
                self._set_idle()
                if ok:
                    messagebox.showinfo(
                        "Succès",
                        "Mot de passe réinitialisé ✓\n\n"
                        f"Nouveau mot de passe :\n{password}\n\n"
                        "Communiquez-le à l'utilisateur de façon sécurisée.",
                    )
                else:
                    messagebox.showerror("Erreur", "La réinitialisation a échoué.")
            self.root.after(0, apply)

        self.runner.run_in_thread(
            factory,
            callback=on_ok,
            error_callback=self._make_error_cb("Réinitialisation du mot de passe"),
        )

    def _user_license(self):
        if not self.users_service or not self.licenses_service:
            return
        user = self._selected_user()
        if not user:
            return
        self._set_busy("Chargement des licences...")
        self.runner.run_in_thread(
            lambda: self.licenses_service.get_inventory(),
            callback=lambda skus: self.root.after(0, lambda: self._open_assign_license(user, skus)),
            error_callback=self._make_error_cb("Chargement des licences"),
        )

    def _open_assign_license(self, user, skus):
        self._set_idle()
        dlg = AssignLicenseDialog(self.root, skus, current_skus=user.get('license_skus'))
        if not dlg.result:
            return
        sku_id, action = dlg.result
        self._set_busy("Application de la licence...")

        def factory():
            if action == 'add':
                return self.users_service.assign_license(user['id'], sku_id)
            return self.users_service.unassign_license(user['id'], sku_id)

        self._run_action(factory, "Licence appliquée ✓")

    def _user_block(self):
        if not self.users_service:
            return
        user = self._selected_user()
        if not user:
            return
        blocked = not user.get('account_enabled', True)
        verb = "débloquer" if blocked else "bloquer"
        if not messagebox.askyesno("Confirmation", f"Voulez-vous {verb} « {user.get('display_name')} » ?"):
            return
        self._set_busy(f"{verb.capitalize()} en cours...")
        self._run_action(
            lambda: self.users_service.set_blocked(user['id'], blocked),
            f"Utilisateur {'débloqué' if blocked else 'bloqué'} ✓",
        )

    def _user_delete(self):
        if not self.users_service:
            return
        user = self._selected_user()
        if not user:
            return
        if not messagebox.askyesno(
            "Confirmation",
            f"Supprimer « {user.get('display_name')} » ({user.get('user_principal_name')}) ?\n\n"
            "Suppression réversible : récupérable 30 jours dans Entra ID.",
        ):
            return
        self._set_busy("Suppression en cours...")
        self._run_action(lambda: self.users_service.delete(user['id']), "Utilisateur supprimé ✓")

    # ================================================================
    # ONGLET GROUPES
    # ================================================================

    def _build_groups_tab(self):
        top = ttk.Frame(self.groups_tab)
        top.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(top, text="Type:").pack(side=tk.LEFT, padx=(0, 4))
        self.group_type_var = tk.StringVar(value="Tous")
        self.group_type_combo = ttk.Combobox(
            top, textvariable=self.group_type_var, state='readonly', width=22,
            values=["Tous", "Microsoft 365", "Sécurité", "Distribution", "Mail-Enabled Security"],
        )
        self.group_type_combo.pack(side=tk.LEFT, padx=(0, 15))
        self.group_type_combo.bind("<<ComboboxSelected>>", lambda e: self._render_groups())

        self.groups_btns = {}
        self.groups_btns['create'] = ttk.Button(top, text="➕ Créer", command=self._group_create)
        self.groups_btns['create'].pack(side=tk.LEFT, padx=2)
        self.groups_btns['members'] = ttk.Button(top, text="👥 Membres", command=self._group_members)
        self.groups_btns['members'].pack(side=tk.LEFT, padx=2)
        self.groups_btns['delete'] = ttk.Button(top, text="🗑️ Supprimer", command=self._group_delete)
        self.groups_btns['delete'].pack(side=tk.LEFT, padx=2)
        self.groups_btns['export'] = ttk.Label()  # placeholder pour éviter crash _collect_action_buttons
        self.groups_btns['export'].destroy()
        btn = ttk.Button(top, text="📊 Export CSV", command=self._export_groups_csv)
        btn.pack(side=tk.LEFT, padx=2)
        self.groups_btns['export'] = btn

        self.groups_tree = self._make_tree(
            self.groups_tab,
            ["Nom", "Type", "Email", "Description"],
            widths=[220, 160, 240, 340],
        )

    def _load_groups(self):
        if not self.groups_service:
            return
        # v2.1.8 : cache-aside — affichage instantané depuis le cache local
        cached = local_db.load_collection(self.current_tenant_id or "", "groups")
        if cached and not self._groups_data:
            self._groups_data = cached
            self._render_groups()
            age = local_db.collection_age_seconds(self.current_tenant_id or "", "groups")
            if age is not None:
                self._set_idle(f"✓ {len(cached)} groupes (cache, il y a {_fmt_age(age)})")
        self._set_busy("Chargement des groupes...")

        def on_fresh(groups):
            def apply():
                if self.current_tenant_id:
                    local_db.save_collection(self.current_tenant_id, "groups", groups)
                self._apply_groups(groups)
            self.root.after(0, apply)

        self.runner.run_in_thread(
            lambda: self.groups_service.get_all_groups_formatted(),
            callback=on_fresh,
            error_callback=self._make_error_cb("Chargement des groupes"),
        )

    def _apply_groups(self, groups):
        self._groups_data = groups
        self._render_groups()
        self._set_idle(f"✓ {len(groups)} groupes chargés")

    def _render_groups(self):
        ftype = self.group_type_var.get()
        self.groups_tree.delete(*self.groups_tree.get_children())
        for g in self._groups_data:
            if ftype != "Tous" and g.get('group_type') != ftype:
                continue
            self.groups_tree.insert("", tk.END, iid=g.get('id'), values=(
                g.get('display_name', ''),
                g.get('group_type', ''),
                g.get('mail', ''),
                (g.get('description') or '')[:80],
            ))

    def _selected_group(self):
        sel = self.groups_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Sélectionnez d'abord un groupe.")
            return None
        gid = sel[0]
        for g in self._groups_data:
            if g.get('id') == gid:
                return g
        return None

    def _group_create(self):
        if not self.groups_service:
            return
        dlg = GroupCreateDialog(self.root)
        if not dlg.result:
            return
        data = dlg.result
        self._set_busy("Création du groupe...")

        def factory():
            return self.groups_service.create(data)

        def on_ok(gid):
            def apply():
                self._set_idle()
                if gid:
                    self._load_groups()
                    self.status_label.config(text="Statut: Groupe créé ✓", foreground='green')
                else:
                    messagebox.showerror("Erreur", "La création a échoué.")
            self.root.after(0, apply)

        self.runner.run_in_thread(factory, callback=on_ok, error_callback=self._make_error_cb("Création du groupe"))

    def _group_members(self):
        if not self.groups_service:
            return
        group = self._selected_group()
        if not group:
            return
        self._set_busy("Chargement des membres...")

        def load_members():
            return self.runner.run(self.groups_service.get_group_members(group['id']))

        def on_ok(members):
            def apply():
                self._set_idle()
                MembersDialog(
                    self.root,
                    group_name=group['display_name'],
                    group_id=group['id'],
                    members=members or [],
                    on_refresh_members=self._members_refresh_cb,
                    on_add_member=self._members_add_cb,
                    on_remove_member=self._members_remove_cb,
                )
            self.root.after(0, apply)

        self.runner.run_in_thread(load_members, callback=on_ok, error_callback=self._make_error_cb("Chargement des membres"))

    def _members_refresh_cb(self, group_id):
        return self.runner.run(self.groups_service.get_group_members(group_id))

    def _members_add_cb(self, group_id, member_id):
        return self.runner.run(self.groups_service.add_member(group_id, member_id))

    def _members_remove_cb(self, group_id, member_id):
        return self.runner.run(self.groups_service.remove_member(group_id, member_id))

    def _group_delete(self):
        if not self.groups_service:
            return
        group = self._selected_group()
        if not group:
            return
        if not messagebox.askyesno("Confirmation", f"Supprimer le groupe « {group.get('display_name')} » ?"):
            return
        self._set_busy("Suppression du groupe...")
        self._run_group_action(lambda: self.groups_service.delete(group['id']), "Groupe supprimé ✓")

    def _run_group_action(self, factory, msg_ok):
        def on_ok(ok):
            def apply():
                self._set_idle()
                if ok:
                    self._load_groups()
                    self.status_label.config(text="Statut: " + msg_ok, foreground='green')
                else:
                    messagebox.showerror("Erreur", "L'opération a échoué.")
            self.root.after(0, apply)

        self.runner.run_in_thread(factory, callback=on_ok, error_callback=self._make_error_cb(msg_ok))

    # ================================================================
    # ONGLET APPAREILS
    # ================================================================

    def _build_devices_tab(self):
        top = ttk.Frame(self.devices_tab)
        top.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(top, text="OS:").pack(side=tk.LEFT, padx=(0, 4))
        self.device_os_var = tk.StringVar(value="Tous")
        self.device_os_combo = ttk.Combobox(
            top, textvariable=self.device_os_var, state='readonly', width=14,
            values=["Tous", "Windows", "macOS", "iOS", "Android", "Linux", "Autre"],
        )
        self.device_os_combo.pack(side=tk.LEFT, padx=(0, 15))
        self.device_os_combo.bind("<<ComboboxSelected>>", lambda e: self._render_devices())

        self.btn_refresh_devices = ttk.Button(top, text="🔄 Actualiser", command=self._load_devices)
        self.btn_refresh_devices.pack(side=tk.LEFT, padx=2)
        self.btn_export_devices = ttk.Button(top, text="📊 Export CSV", command=self._export_devices_csv)
        self.btn_export_devices.pack(side=tk.LEFT, padx=2)

        self.devices_tree = self._make_tree(
            self.devices_tab,
            ["Nom", "OS", "Version", "Fabricant", "Modèle", "Conformité", "Dernière connexion"],
            widths=[200, 100, 110, 140, 140, 110, 160],
        )
        self.devices_tree.tag_configure('noncompliant', foreground='#cc0000')

    def _load_devices(self):
        if not self.devices_service:
            return
        # v2.1.8 : cache-aside — affichage instantané depuis le cache local
        cached = local_db.load_collection(self.current_tenant_id or "", "devices")
        if cached and not self._devices_data:
            self._devices_data = cached
            self._render_devices()
            age = local_db.collection_age_seconds(self.current_tenant_id or "", "devices")
            if age is not None:
                self._set_idle(f"✓ {len(cached)} appareils (cache, il y a {_fmt_age(age)})")
        self._set_busy("Chargement des appareils...")

        def on_fresh(devices):
            def apply():
                if self.current_tenant_id:
                    local_db.save_collection(self.current_tenant_id, "devices", devices)
                self._apply_devices(devices)
            self.root.after(0, apply)

        self.runner.run_in_thread(
            lambda: self.devices_service.get_all_devices_formatted(),
            callback=on_fresh,
            error_callback=self._make_error_cb("Chargement des appareils"),
        )

    def _apply_devices(self, devices):
        self._devices_data = devices
        self._render_devices()
        self._set_idle(f"✓ {len(devices)} appareils chargés")

    def _render_devices(self):
        fos = self.device_os_var.get()
        self.devices_tree.delete(*self.devices_tree.get_children())
        for d in self._devices_data:
            if fos != "Tous" and d.get('os_type') != fos:
                continue
            compliance = d.get('compliance_status', 'Inconnu')
            tag = ('noncompliant',) if compliance == 'Non conforme' else ()
            self.devices_tree.insert("", tk.END, iid=d.get('id'), values=(
                d.get('display_name', ''),
                d.get('operating_system', ''),
                d.get('os_version', ''),
                d.get('manufacturer', ''),
                d.get('model', ''),
                compliance,
                d.get('approximate_last_sign_in_date_time', ''),
            ), tags=tag)

    # ================================================================
    # ONGLET LICENCES
    # ================================================================

    def _build_licenses_tab(self):
        top = ttk.Frame(self.licenses_tab)
        top.pack(fill=tk.X, pady=(0, 6))

        self.btn_refresh_licenses = ttk.Button(top, text="🔄 Actualiser", command=self._load_licenses)
        self.btn_refresh_licenses.pack(side=tk.LEFT, padx=2)
        self.btn_unlicensed = ttk.Button(top, text="👤 Utilisateurs sans licence", command=self._show_unlicensed_users)
        self.btn_unlicensed.pack(side=tk.LEFT, padx=2)
        self.btn_export_licenses = ttk.Button(top, text="📊 Export CSV", command=self._export_licenses_csv)
        self.btn_export_licenses.pack(side=tk.LEFT, padx=2)

        self.licenses_tree = self._make_tree(
            self.licenses_tab,
            ["Produit", "Référence SKU", "Consommées", "Total", "Disponibles", "Alerte"],
            widths=[260, 160, 100, 80, 100, 70],
        )
        self.licenses_tree.tag_configure('warning', foreground='#cc0000')

    def _load_licenses(self):
        if not self.licenses_service:
            return
        # v2.1.8 : cache-aside — affichage instantané depuis le cache local
        cached = local_db.load_collection(self.current_tenant_id or "", "licenses")
        if cached and not self._licenses_data:
            self._render_licenses(cached, from_cache=True)
        self._set_busy("Chargement des licences...")

        def on_fresh(inventory):
            def apply():
                if self.current_tenant_id:
                    local_db.save_collection(self.current_tenant_id, "licenses", inventory)
                self._render_licenses(inventory)
            self.root.after(0, apply)

        self.runner.run_in_thread(
            lambda: self.licenses_service.get_inventory(),
            callback=on_fresh,
            error_callback=self._make_error_cb("Chargement des licences"),
        )

    def _render_licenses(self, inventory, from_cache: bool = False):
        self._licenses_data = inventory
        self.licenses_tree.delete(*self.licenses_tree.get_children())
        for lic in inventory:
            self.licenses_tree.insert("", tk.END, iid=lic.get('sku_id'), values=(
                lic.get('display_name', ''),
                lic.get('part_number', ''),
                lic.get('consumed', 0),
                lic.get('total', 0),
                lic.get('available', 0),
                "⚠️" if lic.get('warning') else "OK",
            ), tags=('warning',) if lic.get('warning') else ())
        if from_cache:
            age = local_db.collection_age_seconds(self.current_tenant_id or "", "licenses")
            if age is not None:
                self._set_idle(f"✓ {len(inventory)} licences (cache, il y a {_fmt_age(age)})")
        else:
            self._set_idle(f"✓ {len(inventory)} licences listées")

    def _show_unlicensed_users(self):
        if not self.licenses_service:
            return
        self._set_busy("Recherche des utilisateurs sans licence...")
        self.runner.run_in_thread(
            lambda: self.licenses_service.get_unlicensed_users(),
            callback=lambda users: self.root.after(0, lambda: self._open_unlicensed(users)),
            error_callback=self._make_error_cb("Recherche des utilisateurs sans licence"),
        )

    def _open_unlicensed(self, users):
        self._set_idle()
        UnlicensedUsersDialog(self.root, users)
        self.status_label.config(
            text=f"Statut: {len(users)} utilisateur(s) sans licence",
            foreground='orange' if users else 'green',
        )

    # ================================================================
    # DASHBOARD
    # ================================================================

    def _load_dashboard(self):
        if not self.graph_wrapper:
            return
        # v2.1.7 : dashboard PORTFOLIO — récapitulatif de TOUS les
        # tenants connectés (pas seulement le courant). Le tenant courant
        # est scanné en premier ; chaque tenant est indépendant (une
        # erreur de token sur l'un ne casse pas le récap des autres).
        tenants = [self.current_tenant_id] + [
            t for t in self.auth_manager.list_connected_tenants()
            if t != self.current_tenant_id
        ]
        # v2.1.8 : affiche d'abord le DERNIER portefeuille connu (cache
        # local, instantané) puis rafraîchit en arrière-plan — fini
        # l'écran vide à chaque bascule/actualisation.
        cached_pf = local_db.load_collection(self.current_tenant_id or "", "portfolio")
        if cached_pf:
            self._display_dashboard(cached_pf, from_cache=True)
            age = local_db.collection_age_seconds(self.current_tenant_id or "", "portfolio")
            if age is not None:
                self._set_idle(f"✓ {len(cached_pf)} tenants (cache, il y a {_fmt_age(age)}) — "
                               f"rafraîchissement en cours...")
        else:
            self._set_busy("Chargement du portefeuille multi-tenant...")

        def factory():
            import asyncio as _a

            async def scan_tenant(tid: str) -> Dict[str, Any]:
                info: Dict[str, Any] = {
                    "tenant_id": tid,
                    "label": self._tenant_label(tid),
                    "users": None, "groups": None, "devices": None,
                    "licenses_total": 0, "licenses_consumed": 0,
                    "alerts": [], "reduced": not self.auth_manager.has_workload_scopes(tid),
                    "error": None,
                    # v2.1.9 : distingo membres / invités / bloqués
                    "members": 0, "guests": 0, "blocked": 0,
                    # v2.1.9 : stockage OneDrive (None si perms réduites)
                    "storage": None,
                }
                try:
                    if tid == self.current_tenant_id:
                        wrapper = self.graph_wrapper
                        if wrapper is None:
                            raise RuntimeError("aucun tenant courant connecté")
                    else:
                        client = self.auth_manager.get_client(tid)
                        if client is None:
                            raise RuntimeError("client Graph absent (reconnectez-vous)")
                        wrapper = GraphClientWrapper(client)
                    # v2.1.9 : breakdown users (membres/invités/bloqués) +
                    # quotas stockage OneDrive en parallèle du reste.
                    has_workloads = self.auth_manager.has_workload_scopes(tid)
                    users, groups, devices, licenses, tenant_info, breakdown = await _a.gather(
                        wrapper.get_tenant_users_count(),
                        wrapper.get_tenant_groups_count(),
                        wrapper.get_tenant_devices_count(),
                        LicensesService(wrapper).get_inventory(),
                        wrapper.get_tenant_info(),
                        wrapper.get_users_breakdown(),
                    )
                    if has_workloads:
                        try:
                            info["storage"] = await wrapper.get_storage_quota()
                        except Exception as se:
                            print(f"[Dashboard] Stockage indisponible pour {tid}: {se}")
                    info["users"] = users
                    info["groups"] = groups
                    info["devices"] = devices
                    info["tenant_info"] = tenant_info
                    info["members"] = breakdown.get("members", 0)
                    info["guests"] = breakdown.get("guests", 0)
                    info["blocked"] = breakdown.get("blocked", 0)
                    info["licenses_total"] = sum(l.get('total', 0) for l in licenses or [])
                    info["licenses_consumed"] = sum(l.get('consumed', 0) for l in licenses or [])
                    info["alerts"] = [
                        {"name": l.get("display_name") or l.get("part_number") or "?",
                         "available": l.get("available", 0)}
                        for l in licenses or [] if l.get("warning")
                    ]
                except Exception as e:
                    info["error"] = str(e)[:140]
                return info

            async def inner():
                tasks = [scan_tenant(t) for t in tenants if t]
                return await _a.gather(*tasks)
            return inner()

        def on_ok(portfolio):
            def apply():
                self._portfolio_data = list(portfolio or [])
                # v2.1.8 : persiste le portefeuille pour le prochain
                # affichage instantané (clé = tenant courant)
                if self.current_tenant_id:
                    local_db.save_collection(self.current_tenant_id, "portfolio", self._portfolio_data)
                # tenant_info du tenant COURANT conservé (domaine par défaut
                # de la création d'utilisateur)
                for p in self._portfolio_data:
                    if p.get("tenant_id") == self.current_tenant_id:
                        self.tenant_info = p.get("tenant_info")
                        self._licenses_data = []
                        break
                self._display_dashboard(self._portfolio_data)
                self._set_idle("✓ Portefeuille actualisé")
            self.root.after(0, apply)

        self.runner.run_in_thread(factory, callback=on_ok, error_callback=self._make_error_cb("Chargement du dashboard"))

    def _display_dashboard(self, portfolio, from_cache: bool = False):
        """v2.1.7 : récap multi-tenant (liste de dicts issus de _load_dashboard)."""
        self._portfolio_data = list(portfolio or [])
        portfolio = self._portfolio_data
        for widget in self.dashboard_tab.winfo_children():
            widget.destroy()

        main = ttk.Frame(self.dashboard_tab, padding="20")
        main.pack(fill=tk.BOTH, expand=True)

        if not portfolio:
            if not from_cache:
                ttk.Label(main, text="Aucun tenant connecté.",
                          style='Subtitle.TLabel').pack(pady=20)
            return

        # ---- Cartes de synthèse globales ----
        ok_rows = [p for p in portfolio if p.get("error") is None]
        total_users = sum(p.get("users") or 0 for p in ok_rows)
        total_members = sum(p.get("members") or 0 for p in ok_rows)
        total_guests = sum(p.get("guests") or 0 for p in ok_rows)
        total_blocked = sum(p.get("blocked") or 0 for p in ok_rows)
        total_consumed = sum(p.get("licenses_consumed") or 0 for p in ok_rows)
        total_licenses = sum(p.get("licenses_total") or 0 for p in ok_rows)
        st_total = sum((p.get("storage") or {}).get("total", 0) for p in ok_rows if p.get("storage"))
        st_used = sum((p.get("storage") or {}).get("used", 0) for p in ok_rows if p.get("storage"))
        reduced_count = sum(1 for p in portfolio if p.get("reduced"))
        errors_count = len(portfolio) - len(ok_rows)

        def _human_bytes(n: float) -> str:
            for unit, factor in (("To", 1024**4), ("Go", 1024**3), ("Mo", 1024**2)):
                if n >= factor:
                    v = n / factor
                    return f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " " + unit
            return f"{int(n)} o"

        stats = ttk.Frame(main)
        stats.pack(fill=tk.X, pady=(0, 15))
        cards = [
            ("🏢 Tenants", f"{len(portfolio)}"),
            ("👥 Comptes", f"{total_users}"
                           + (f"\n({total_members} membres, {total_guests} invités)" if total_users else "")),
            ("🔑 Licences", f"{total_consumed} / {total_licenses}"),
            ("💾 Stockage OneDrive", f"{_human_bytes(st_used)} / {_human_bytes(st_total)}"
                                    if st_total else "—"),
        ]
        for title, value in cards:
            card = ttk.LabelFrame(stats, text=title, padding=20)
            card.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.BOTH)
            ttk.Label(card, text=value, font=('Segoe UI', 16, 'bold'), justify=tk.CENTER).pack()
            if title == "👥 Comptes" and total_blocked:
                ttk.Label(card, text=f"⛔ {total_blocked} bloqué(s)", foreground='red').pack()
            if title == "🏢 Tenants" and errors_count:
                ttk.Label(card, text=f"⚠️ {errors_count} en erreur", foreground='red').pack()

        # ---- Tableau récapitulatif par tenant ----
        recap = ttk.LabelFrame(main, text="📋 Récapitulatif par tenant", padding=10)
        recap.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        columns = ["Membres", "Invités", "Bloqués", "Groupes", "Appareils",
                   "Licences", "Stockage", "Statut"]
        widths = [80, 70, 70, 80, 80, 110, 150, 150]
        tree = ttk.Treeview(recap, columns=columns, show='tree headings', height=max(6, len(portfolio)))
        tree.heading("#0", text="Tenant")
        tree.column("#0", width=200, stretch=True)
        for i, col in enumerate(columns):
            tree.heading(col, text=col)
            tree.column(col, width=widths[i], anchor=tk.W)
        scroll = ttk.Scrollbar(recap, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        from gui.table_utils import make_sortable
        make_sortable(tree)

        def _fmt_storage(p) -> str:
            """v2.1.9 : « 1,2 / 5 To » — Go/Mo si petit, « — » si perms réduites."""
            s = p.get("storage")
            if not s:
                return "—"
            def human(n: float) -> str:
                for unit, factor in (("To", 1024**4), ("Go", 1024**3), ("Mo", 1024**2)):
                    if n >= factor:
                        v = n / factor
                        return f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " " + unit
                return f"{int(n)} o"
            return f"{human(s.get('used', 0))} / {human(s.get('total', 0))}"

        for p in portfolio:
            if p.get("error"):
                lic_txt, statut, sto_txt = "—", f"❌ Erreur : {p['error'][:60]}", "—"
            else:
                lic_txt = f"{p.get('licenses_consumed', 0)} / {p.get('licenses_total', 0)}"
                n_alerts = len(p.get("alerts") or [])
                statut = "⚠️ Permissions réduites" if p.get("reduced") else (
                    f"🔴 {n_alerts} alerte(s)" if n_alerts else "🟢 OK"
                )
                sto_txt = _fmt_storage(p)
            tree.insert("", tk.END, text=p.get("label") or p.get("tenant_id", "?"), values=(
                p.get("members") if p.get("members") is not None else "—",
                p.get("guests") if p.get("guests") is not None else "—",
                p.get("blocked") if p.get("blocked") is not None else "—",
                p.get("groups") if p.get("groups") is not None else "—",
                p.get("devices") if p.get("devices") is not None else "—",
                lic_txt,
                sto_txt,
                statut,
            ))
        tree.tag_configure('cur', font=('Segoe UI', 9, 'bold'))
        try:
            tree.item(tree.get_children()[0], tags=('cur',))  # tenant courant en gras
        except (tk.TclError, IndexError):
            pass

        # ---- Détail quotas de stockage par tenant (v2.1.9) ----
        storage = ttk.LabelFrame(main, text="💾 Quotas de stockage OneDrive (par tenant)", padding=10)
        storage.pack(fill=tk.X)
        rows = [p for p in portfolio if p.get("error") is None]
        any_storage = any(p.get("storage") for p in rows)
        if any_storage:
            for p in rows:
                s = p.get("storage")
                if not s:
                    continue
                total, used = s.get("total", 0), s.get("used", 0)
                pct = (used * 100 / total) if total else 0
                color = 'red' if pct >= 90 else ('orange' if pct >= 75 else 'green')
                ttk.Label(
                    storage,
                    text=f"• {p.get('label') or '?'} : {_fmt_storage(p)} utilisés ({pct:.0f} %)",
                    foreground=color,
                ).pack(anchor=tk.W)
        elif rows and all(p.get("reduced") for p in rows):
            ttk.Label(storage, text="Quotas indisponibles : permissions réduites "
                                    "(consentement admin des scopes workloads requis).",
                      foreground='orange').pack(anchor=tk.W)
        else:
            ttk.Label(storage, text="Aucune donnée de stockage disponible.",
                      foreground='gray').pack(anchor=tk.W)

    # ================================================================
    # CONNEXION / TENANTS — v2.0 clé en main
    # ================================================================

    def _connect_tenant(self):
        """Connexion directe : navigateur → compte → tenant déduit. Zéro saisie."""
        self._set_busy("Connexion — le navigateur va s'ouvrir...")

        def show_device_code(user_code, verification_uri, expires_on):
            def apply():
                messagebox.showinfo(
                    "Connexion sans navigateur",
                    f"Sur un autre appareil, ouvrez :\n\n{verification_uri}\n\n"
                    f"et saisissez le code :\n\n{user_code}\n\n"
                    "(le code expire dans 15 minutes)",
                )
            self.root.after(0, apply)

        def on_ok(client):
            def apply():
                tid = self.auth_manager.get_current_tenant()
                self._register_connected_tenant(tid)
                self._set_idle(f"✓ Connecté : {self._tenant_label(tid)}")
                self.connection_label.config(text="🟢 En ligne")
            self.root.after(0, apply)

        def on_err(e):
            def apply():
                self._set_idle()
                messagebox.showerror(
                    "Erreur de connexion",
                    f"{e}\n\nVérifiez que le compte utilisé est bien un compte "
                    "admin du tenant client, puis réessayez.",
                )
            self.root.after(0, apply)

        self.runner.run_in_thread(
            lambda: self.auth_manager.connect_interactive(prompt_callback=show_device_code),
            callback=on_ok,
            error_callback=on_err,
        )

    def _tenant_label(self, tid: str) -> str:
        """Libellé lisible du tenant (nom > username > GUID)."""
        info = self.auth_manager.account_info(tid)
        if info.get('tenant_name'):
            return info['tenant_name']
        if info.get('username'):
            return info['username']
        if tid:
            return tid
        return "tenant inconnu"

    def _register_connected_tenant(self, tid: str):
        """Après connexion : wiring complet + affichage."""
        client = self.auth_manager.get_client(tid)
        if client is None:
            # reconnect_silent peut retourner None (cache expiré) :
            # ne jamais enregistrer un tenant sans client Graph.
            self._set_idle()
            messagebox.showerror(
                "Connexion",
                "Le tenant n'a pas pu être initialisé (cache d'authentification "
                "expiré). Utilisez « Connecter » pour une nouvelle connexion.",
            )
            return
        self.graph_wrapper = GraphClientWrapper(client)
        self.current_tenant_id = tid
        self._init_services()
        self._update_tenant_list()
        self.tenant_var.set(self._tenant_label(tid))
        self._clear_all_data()
        reduced = not self.auth_manager.has_workload_scopes(tid)
        if reduced:
            self.connection_label.config(
                text="🟢 En ligne (permissions réduites — onglets workloads indisponibles "
                     "jusqu'au consentement admin des nouveaux scopes)",
            )
        else:
            self.connection_label.config(text="🟢 En ligne")
        # v2.1.7 : recharge l'onglet COURANT (l'ancien code forçait le
        # dashboard ; depuis un autre onglet, la liste restait vide
        # jusqu'au prochain clic d'onglet après un changement de tenant).
        self._reload_current_tab()

    def _reload_current_tab(self):
        """Recharge les données de l'onglet visible (après connexion ou
        bascule de tenant). Dashboard → stats ; sinon lazy-load du
        contenu via _on_tab_changed."""
        if not self.graph_wrapper:
            return
        try:
            tab = self.notebook.index(self.notebook.select())
        except Exception:
            tab = 0
        if tab == 0:
            self._load_dashboard()
        else:
            self._on_tab_changed(None)

    def _try_silent_reconnect(self):
        """
        Au démarrage : si des tenants sont déjà autorisés sur ce poste,
        propose leur reconnexion en un clic (cache de tokens).

        v2.1.5 : propose TOUS les tenants sauvegardés (l'ancien code ne
        rebranchait que le premier) ; chacun reçoit un bouton.
        """
        saved = self.auth_manager.list_saved_tenants()
        if not saved:
            return

        def ask():
            names = "\n".join(
                f"• {s['tenant_name'] or s['username'] or s['tenant_id']}"
                for s in saved[:10]
            )
            answer = messagebox.askyesno(
                "Reconnexion",
                f"Tenants déjà autorisés sur ce poste :\n\n{names}\n\n"
                "Les reconnecter silencieusement maintenant ?\n"
                "(aucune fenêtre de connexion ne s'ouvrira — ils seront "
                "tous disponibles dans le sélecteur)",
                icon='question',
            )
            if answer:
                for s in saved:
                    self._do_silent_reconnect(s['tenant_id'])
        self.root.after(200, ask)

    def _do_silent_reconnect(self, tid: str):
        self._set_busy("Reconnexion silencieuse...")

        def on_ok(client):
            def apply():
                self._register_connected_tenant(tid)
                self._set_idle(f"✓ Reconnecté : {self._tenant_label(tid)}")
                self.connection_label.config(text="🟢 En ligne")
            self.root.after(0, apply)

        def on_err(e):
            def apply():
                self._set_idle()
                messagebox.showerror(
                    "Reconnexion impossible",
                    f"Le cache d'authentification a expiré pour ce tenant.\n"
                    f"Utilisez « Connecter » pour une nouvelle connexion.\n\n({e})",
                )
            self.root.after(0, apply)

        self.runner.run_in_thread(
            lambda: self.auth_manager.reconnect_silent(tid),
            callback=on_ok,
            error_callback=on_err,
        )

    def _init_services(self):
        self.users_service = UsersService(self.graph_wrapper)
        self.groups_service = GroupsService(self.graph_wrapper)
        self.devices_service = DevicesService(self.graph_wrapper)
        self.licenses_service = LicensesService(self.graph_wrapper)
        # Workloads v2.1
        self.sharepoint_service = SharePointService(self.graph_wrapper)
        self.onedrive_service = OneDriveService(self.graph_wrapper)
        self.exchange_service = ExchangeService(self.graph_wrapper)
        self.teams_service = TeamsService(self.graph_wrapper)

    def _clear_all_data(self):
        self._users_data = []
        self._groups_data = []
        self._devices_data = []
        self._licenses_data = []
        self.tenant_info = None
        # v2.1.7 : vider AUSSI les treeviews principaux — l'ancien code
        # ne vidait que les caches : après un changement de tenant, les
        # tableaux affichaient encore les données du tenant précédent.
        for tree in (getattr(self, 'users_tree', None),
                     getattr(self, 'groups_tree', None),
                     getattr(self, 'devices_tree', None),
                     getattr(self, 'licenses_tree', None)):
            if tree is not None:
                try:
                    tree.delete(*tree.get_children())
                except tk.TclError:
                    pass
        # Reset des recherches/filtres (recherche du tenant précédent)
        if getattr(self, 'user_search_var', None) is not None:
            self.user_search_var.set("")
        if getattr(self, 'group_type_var', None) is not None:
            self.group_type_var.set("Tous")
        # v2.1.7 : filtres instantanés des 9 tableaux (vars internes des
        # TableEnhancer) — sinon l'ancien filtre masquerait les nouvelles
        # données du tenant fraîchement chargées.
        for enh in list(getattr(self, '_tree_enhancers', {}).values()):
            if getattr(enh, 'filter_var', None) is not None:
                try:
                    enh.filter_var.set("")
                except tk.TclError:
                    pass
        # Workloads v2.1 : vider les treeviews + caches des panneaux
        for panel in (self.sharepoint_panel, self.onedrive_panel,
                      self.exchange_panel, self.teams_panel):
            panel.data = []
            if panel.tree is not None:
                panel.tree.delete(*panel.tree.get_children())

    def _disconnect(self):
        if self.current_tenant_id:
            self.auth_manager.disconnect(self.current_tenant_id)
        self.graph_wrapper = None
        self.current_tenant_id = None
        self.tenant_var.set("")
        self._clear_all_data()
        self.connect_btn.config(text="🔐 Connecter")
        self.status_label.config(text="Statut: Déconnecté", foreground='black')
        self.connection_label.config(text="")
        self._show_welcome()

    def _update_tenant_list(self):
        """Met à jour le dropdown des tenants connectés.

        v2.1.5 : affiche les libellés lisibles (nom > username > GUID)
        au lieu des GUID bruts, et ne change PLUS la sélection courante
        (l'ancien current(0) écrasait la bascule vers un autre tenant).
        """
        tenants = self.auth_manager.list_connected_tenants()
        # Libellé unique par tenant (suffixe si collision de noms)
        labels = {}
        used = set()
        for tid in tenants:
            label = self._tenant_label(tid) or tid
            base = label
            n = 2
            while label in used:
                label = f"{base} ({n})"
                n += 1
            used.add(label)
            labels[tid] = label
        self._tenant_labels = labels
        self.tenant_combo['values'] = [labels[tid] for tid in tenants]
        # Sélection = tenant courant, sans le changer
        current_label = labels.get(self.current_tenant_id or "")
        if current_label:
            self.tenant_var.set(current_label)

    def _on_tenant_selected(self, event):
        """Bascule vers un tenant déjà connecté.

        v2.1.7 : rebranchement COMPLET (wrapper Graph, services, vidage
        des tableaux, rechargement de l'onglet courant). L'ancien code ne
        basculait qu'en mémoire : les listes continuaient d'afficher le
        tenant précédent et les services appelaient l'ancien client.
        """
        if not getattr(self, "_tenant_labels", None):
            return
        label = self.tenant_var.get()
        # Résolution libellé -> GUID via la map interne (fiable, même
        # si deux tenants portent le même nom)
        rev = {v: k for k, v in self._tenant_labels.items()}
        tid = rev.get(label)
        if not tid:
            return
        if tid == self.current_tenant_id:
            return
        try:
            if not self.auth_manager.set_current_tenant(tid):
                raise RuntimeError(f"Tenant {tid} non connecté")
            self._register_connected_tenant(tid)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de basculer: {e}")

    # ================================================================
    # EXPORTS CSV
    # ================================================================

    def _ask_csv_path(self, initialfile):
        return filedialog.asksaveasfilename(
            defaultextension='.csv',
            filetypes=[('Fichier CSV', '*.csv')],
            initialfile=initialfile,
        )

    def _export_generic(self, label, loader, exporter, initialfile, apply_cache):
        """Export CSV générique : charge si besoin, écrit, confirme."""
        path = self._ask_csv_path(initialfile)
        if not path:
            return
        self._set_busy(f"Export {label}...")

        def factory():
            data = apply_cache()
            if data:
                ok = exporter(data, path)
                return data, ok
            data = loader()
            return data, exporter(data, path)

        def on_ok(result):
            data, ok = result

            def apply():
                self._set_idle()
                if ok:
                    messagebox.showinfo("Succès", f"Export réussi ✓\n{len(data)} {label} → {path}")
                else:
                    messagebox.showerror("Erreur", "L'export a échoué.")
            self.root.after(0, apply)

        self.runner.run_in_thread(factory, callback=on_ok, error_callback=self._make_error_cb(f"Export {label}"))

    def _export_users_csv(self):
        if not self.users_service:
            return
        self._export_generic(
            "utilisateurs",
            lambda: self.runner.run(self.users_service.get_all_users_formatted()),
            self.users_service.export_to_csv,
            "utilisateurs.csv",
            lambda: self._users_data,
        )

    def _export_groups_csv(self):
        if not self.groups_service:
            return
        self._export_generic(
            "groupes",
            lambda: self.runner.run(self.groups_service.get_all_groups_formatted()),
            self.groups_service.export_to_csv,
            "groupes.csv",
            lambda: self._groups_data,
        )

    def _export_devices_csv(self):
        if not self.devices_service:
            return
        self._export_generic(
            "appareils",
            lambda: self.runner.run(self.devices_service.get_all_devices_formatted()),
            self.devices_service.export_to_csv,
            "appareils.csv",
            lambda: self._devices_data,
        )

    def _export_licenses_csv(self):
        if not self.licenses_service:
            return
        self._export_generic(
            "licences",
            lambda: self.runner.run(self.licenses_service.get_inventory()),
            self.licenses_service.export_to_csv,
            "licences.csv",
            lambda: self._licenses_data,
        )

    # ================================================================
    # NAVIGATION / DIVERS
    # ================================================================

    def _show_users(self):
        self.notebook.select(1)
        if not self._users_data:
            self._load_users()

    def _show_groups(self):
        self.notebook.select(2)
        if not self._groups_data:
            self._load_groups()

    def _show_devices(self):
        self.notebook.select(3)
        if not self._devices_data:
            self._load_devices()

    def _show_licenses(self):
        self.notebook.select(4)
        if not self._licenses_data:
            self._load_licenses()

    def _refresh_data(self):
        if not self.graph_wrapper:
            messagebox.showinfo("Info", "Connectez-vous d'abord à un tenant.")
            return
        self._clear_all_data()
        self._load_dashboard()
        tab = self.notebook.index(self.notebook.select())
        if tab == 1:
            self._load_users()
        elif tab == 2:
            self._load_groups()
        elif tab == 3:
            self._load_devices()
        elif tab == 4:
            self._load_licenses()

    def _show_help(self):
        messagebox.showinfo("Aide", (
            "Graph Tenant Manager - Aide\n\n"
            "1. Connectez-vous à un tenant (ID + navigateur)\n"
            "2. Utilisez les onglets pour gérer utilisateurs, groupes, appareils et licences\n"
            "3. Double-cliquez un utilisateur pour ses détails\n"
            "4. Exports CSV disponibles sur chaque onglet\n\n"
            "Astuce : la reconnexion à un tenant déjà autorisé est silencieuse (cache)."
        ))

    def _show_about(self):
        messagebox.showinfo("À propos", (
            f"Graph Tenant Manager v{APP_VERSION_LOCAL}\n\n"
            "Outil de gestion multi-tenants Microsoft Graph\n"
            "pour administrateurs / MSP.\n\n"
            "Python 3.10+ · Microsoft Graph SDK · Tkinter"
        ))

    def _on_close(self):
        try:
            self.runner.stop()
        except Exception:
            pass
        self.root.destroy()


def run_app(config):
    """Point d'entrée appelé par main.py"""
    root = tk.Tk()
    app = GraphTenantManagerApp(root, config)
    root.mainloop()
