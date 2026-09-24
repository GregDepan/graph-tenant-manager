"""
Dialogues de l'application Graph Tenant Manager.

Tous les dialogues sont des Toplevel transient + grab_set, centrés sur la
fenêtre parente, intégralement en français et construits en ttk (thème
hérité de la fenêtre principale). Chaque dialogue retourne un résultat
via l'attribut `result` après fermeture :

    UserCreateDialog.result      -> dict | None
    UserEditDialog.result       -> dict | None
    ResetPasswordDialog.result  -> (password, force_change) | None
    AssignLicenseDialog.result  -> (sku_id, action) | None
    GroupCreateDialog.result    -> dict | None
    UserDetailDialog.result     -> None (lecture seule)
    MembersDialog.result        -> None (opérations via callbacks)

Les dialogues ne contiennent AUCUNE logique Graph : toute opération est
déclenchée par callback vers la fenêtre principale (qui passe par
AsyncRunner). Les membres d'un groupe sont fournis/rafraîchis via les
callbacks `on_refresh_members` / `on_add_member` / `on_remove_member`.
"""

import secrets
import string
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Tuple


# =====================================================================
# Génération de mot de passe temporaire (complexité Microsoft)
# =====================================================================

_TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_=+?"


def generate_temp_password(length: int = 14) -> str:
    """
    Génère un mot de passe temporaire robuste (≥ 1 majuscule, 1 minuscule,
    1 chiffre, 1 caractère spécial), mélangé de façon cryptographiquement
    sûre.
    """
    specials = "!@#$%^&*-_=+?"
    parts = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(specials),
    ]
    parts += [secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(max(length - 4, 0))]
    secrets.SystemRandom().shuffle(parts)
    return "".join(parts)


def center_dialog(dialog: tk.Toplevel, parent: Optional[tk.Misc] = None) -> None:
    """Centre un dialogue sur son parent (ou à l'écran si pas de parent)."""
    dialog.update_idletasks()
    width = dialog.winfo_width()
    height = dialog.winfo_height()
    if parent is not None and parent.winfo_exists():
        px = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    else:
        px = (dialog.winfo_screenwidth() - width) // 2
        py = (dialog.winfo_screenheight() - height) // 2
    dialog.geometry(f"+{max(px, 0)}+{max(py, 0)}")


class BaseDialog(tk.Toplevel):
    """
    Dialogue de base : Toplevel transient, grab_set, centré, fermeture
    par Échap, attribut `result` initialisé à None.

    Les sous-classes construisent l'UI dans _build_ui() et appellent
    _validate() pour vérifier les saisies avant d'accepter.
    """

    def __init__(self, parent: tk.Misc, title: str, width: int = 480, height: Optional[int] = None):
        try:
            super().__init__(parent)
        except Exception:
            # Parent déjà détruit (rare) : dialogue autonome
            super().__init__()
        self.title(title)
        self.result: Any = None
        self._accepted = False
        self._geom_set = False

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda e: self._on_cancel())

        # Contenu
        container = ttk.Frame(self, padding=15)
        container.pack(fill=tk.BOTH, expand=True)
        self.body = container

        self._build_ui(container)

        # Taille : hauteur auto ou fixée
        self.update_idletasks()
        req_h = height or self.winfo_reqheight()
        self.geometry(f"{width}x{req_h}")
        center_dialog(self, parent)
        self._geom_set = True

        # Boutons Annuler / Valider en bas
        btn_frame = ttk.Frame(container)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(15, 0))
        self.cancel_btn = ttk.Button(btn_frame, text="Annuler", command=self._on_cancel)
        self.cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
        self.ok_btn = ttk.Button(btn_frame, text="Valider", command=self._on_ok)
        self.ok_btn.pack(side=tk.RIGHT)

        self.ok_btn.focus_set()
        self.wait_visibility()
        self.grab_set()

    # --- à surcharger ------------------------------------------------
    def _build_ui(self, parent: ttk.Frame) -> None:
        """Construit le corps du dialogue. À surcharger."""
        pass

    def _validate(self) -> Optional[str]:
        """Retourne un message d'erreur si saisie invalide, sinon None."""
        return None

    def _build_result(self) -> Any:
        """Construit self.result après validation. À surcharger."""
        return None

    # --- helpers -----------------------------------------------------
    def _make_form(self, parent: ttk.Frame) -> ttk.Frame:
        """Crée un formulaire avec grille pour champs label + widget."""
        form = ttk.Frame(parent)
        form.pack(fill=tk.BOTH, expand=True)
        return form

    def _add_field(self, form: ttk.Frame, label: str, row: int,
                   widget: Optional[tk.Widget] = None, widget_type: type = ttk.Entry,
                   **widget_kwargs) -> tk.Widget:
        """
        Ajoute un champ (label + widget) sur la ligne `row` du formulaire.
        Retourne le widget pour que l'appelant puisse lire la valeur.
        """
        ttk.Label(form, text=label).grid(row=row, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        if widget is None:
            widget = widget_type(form, **widget_kwargs)
        widget.grid(row=row, column=1, sticky=tk.EW, pady=4)
        form.columnconfigure(1, weight=1)
        return widget

    def _notify_error(self, message: str) -> None:
        """Affiche un message d'erreur en haut du dialogue."""
        if hasattr(self, "error_label") and self.error_label.winfo_exists():
            self.error_label.config(text=message, foreground="red")
        else:
            from tkinter import messagebox
            messagebox.showerror("Erreur de saisie", message, parent=self)

    # --- cycle de vie ------------------------------------------------
    def _on_ok(self):
        error = self._validate()
        if error:
            self._notify_error(error)
            return
        try:
            self.result = self._build_result()
        except Exception as e:
            self._notify_error(str(e))
            return
        self._accepted = True
        self._close()

    def _on_cancel(self):
        self.result = None
        self._accepted = False
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


# =====================================================================
# Utilisateurs
# =====================================================================

class UserCreateDialog(BaseDialog):
    """
    Dialogue de création d'utilisateur.

    Champs : Nom affiché*, UPN*, mot de passe (auto 🔑), changer à la 1re
    connexion, département, poste.

    result -> dict(camelCase) :
        {
            "displayName": str, "userPrincipalName": str,
            "password": str, "forceChangePassword": bool,
            "department": str, "jobTitle": str
        }
    """

    def __init__(self, parent: tk.Misc, default_domain: str = ""):
        self.default_domain = default_domain
        super().__init__(parent, "➕ Créer un utilisateur", width=520)

    def _build_ui(self, parent: ttk.Frame):
        form = self._make_form(parent)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Nom affiché *:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(form, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=1, sticky=tk.EW, pady=4)

        ttk.Label(form, text="UPN (identifiant) *:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        upn_frame = ttk.Frame(form)
        upn_frame.grid(row=1, column=1, sticky=tk.EW, pady=4)
        self.upn_var = tk.StringVar()
        self.upn_local = ttk.Entry(upn_frame, textvariable=self.upn_var)
        self.upn_local.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if self.default_domain:
            ttk.Label(upn_frame, text=f"@{self.default_domain}").pack(side=tk.LEFT, padx=(4, 0))
        else:
            self.domain_entry = ttk.Entry(upn_frame, width=18)
            ttk.Label(upn_local, text="@").pack(side=tk.LEFT, padx=(4, 0))
            ttk.Label(upn_frame, text="@").pack(side=tk.LEFT, padx=(4, 0))
            self.domain_entry.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(form, text="Mot de passe:").grid(row=2, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        pwd_frame = ttk.Frame(form)
        pwd_frame.grid(row=2, column=1, sticky=tk.EW, pady=4)
        self.pwd_var = tk.StringVar(value=generate_temp_password())
        self.pwd_entry = ttk.Entry(pwd_frame, textvariable=self.pwd_var)
        self.pwd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(pwd_frame, text="🔑 Auto", width=6,
                   command=lambda: self.pwd_var.set(generate_temp_password())).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(pwd_frame, text="(lisible)", foreground="gray").pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(form, text="").grid(row=3, column=0)
        self.force_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            pwd_frame,
            text="Changer le mot de passe à la 1re connexion",
            variable=self.force_var
        ).pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(form, text="Département:").grid(row=4, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        self.dept_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.dept_var).grid(row=4, column=1, sticky=tk.EW, pady=4)

        ttk.Label(form, text="Poste:").grid(row=5, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        self.job_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.job_var).grid(row=5, column=1, sticky=tk.EW, pady=4)

        ttk.Label(
            form, text="* champs obligatoires — le mot de passe est généré automatiquement",
            foreground="gray"
        ).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))

        # Message d'erreur de saisie
        self.error_label = ttk.Label(form, text="", foreground="red")
        self.error_label.grid(row=7, column=0, columnspan=2, sticky=tk.W)

        self.name_entry.focus_set()

    def _validate(self) -> Optional[str]:
        if not self.name_var.get().strip():
            return "Le nom affiché est obligatoire."
        local = self.upn_var.get().strip()
        domain = self._current_domain().strip()
        if not local or not domain:
            return "L'UPN (identifiant et domaine) est obligatoire."
        if "@" in local or " " in local:
            return "L'UPN local ne doit contenir ni '@' ni espaces."
        return None

    def _current_domain(self) -> str:
        if self.default_domain:
            return self.default_domain
        return self.domain_entry.get().strip()

    def _build_result(self) -> Dict[str, Any]:
        upn = f"{self.upn_var.get().strip()}@{self._current_domain().strip()}"
        return {
            "displayName": self.name_var.get().strip(),
            "userPrincipalName": upn,
            "password": self.pwd_var.get().strip() or generate_temp_password(),
            "forceChangePassword": bool(self.force_var.get()),
            "department": self.dept_var.get().strip(),
            "jobTitle": self.job_var.get().strip(),
        }


class UserEditDialog(BaseDialog):
    """
    Dialogue de modification d'utilisateur (champs d'identité/profil).

    result -> dict(snake_case, clés uniquement si valeur renseignée) :
        {"display_name": str, "department": str, "job_title": str,
         "office_location": str, "mobile_phone": str}
    """

    def __init__(self, parent: tk.Misc, user: Dict[str, Any]):
        self.user = user
        super().__init__(parent, "✏️ Modifier l'utilisateur", width=500)

    def _build_ui(self, parent: ttk.Frame):
        form = self._make_form(parent)
        form.columnconfigure(1, weight=1)

        header = f"{self.user.get('display_name', '')}  ({self.user.get('user_principal_name', '')})"
        ttk.Label(form, text=header, style="Subtitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(form, text="Nom affiché:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        self.name_var = tk.StringVar(value=self.user.get("display_name", ""))
        ttk.Entry(form, textvariable=self.name_var).grid(row=1, column=1, sticky=tk.EW, pady=4)

        ttk.Label(form, text="Département:").grid(row=2, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        self.dept_var = tk.StringVar(value=self.user.get("department", "") or "")
        ttk.Entry(form, textvariable=self.dept_var).grid(row=2, column=1, sticky=tk.EW, pady=4)

        ttk.Label(form, text="Poste:").grid(row=3, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        self.job_var = tk.StringVar(value=self.user.get("job_title", "") or "")
        ttk.Entry(form, textvariable=self.job_var).grid(row=3, column=1, sticky=tk.EW, pady=4)

        ttk.Label(form, text="Bureau:").grid(row=4, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        self.office_var = tk.StringVar(value=self.user.get("office_location", "") or "")
        ttk.Entry(form, textvariable=self.office_var).grid(row=4, column=1, sticky=tk.EW, pady=4)

        ttk.Label(form, text="Téléphone mobile:").grid(row=5, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        self.mobile_var = tk.StringVar(value=self.user.get("mobile_phone", "") or "")
        ttk.Entry(form, textvariable=self.mobile_var).grid(row=5, column=1, sticky=tk.EW, pady=4)

        self.error_label = ttk.Label(form, text="", foreground="red")
        self.error_label.grid(row=6, column=0, columnspan=2, sticky=tk.W)

    def _validate(self) -> Optional[str]:
        if not self.name_var.get().strip():
            return "Le nom affiché ne peut pas être vide."
        return None

    def _build_result(self) -> Dict[str, Any]:
        updates: Dict[str, Any] = {}
        if self._changed("display_name", self.name_var.get().strip()):
            updates["display_name"] = self.name_var.get().strip()
        if self._changed("department", self.dept_var.get().strip()):
            updates["department"] = self.dept_var.get().strip()
        if self._changed("job_title", self.job_var.get().strip()):
            updates["job_title"] = self.job_var.get().strip()
        if self._changed("office_location", self.office_var.get().strip()):
            updates["office_location"] = self.office_var.get().strip()
        if self._changed("mobile_phone", self.mobile_var.get().strip()):
            updates["mobile_phone"] = self.mobile_var.get().strip()
        return updates

    def _changed(self, key: str, new_value: str) -> bool:
        old = self.user.get(key, None) or ""
        return new_value != old


class ResetPasswordDialog(BaseDialog):
    """
    Dialogue de réinitialisation de mot de passe.

    result -> (password: str, force_change: bool) ou None
    """

    def __init__(self, parent: tk.Misc, user: Dict[str, Any]):
        self.user = user
        super().__init__(parent, "🔒 Réinitialiser le mot de passe", width=480)

    def _build_ui(self, parent: ttk.Frame):
        form = self._make_form(parent)
        form.columnconfigure(1, weight=1)

        ttk.Label(
            form, text=f"Réinitialiser le mot de passe de :",
            style="Subtitle.TLabel"
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        ttk.Label(
            form, text=f"{self.user.get('display_name', '')} ({self.user.get('user_principal_name', '')})",
            font=("Segoe UI", 10, "bold")
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 15))

        ttk.Label(form, text="Nouveau mot de passe:").grid(row=2, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        pwd_frame = ttk.Frame(form)
        pwd_frame.grid(row=2, column=1, sticky=tk.EW, pady=4)
        self.pwd_var = tk.StringVar(value=generate_temp_password())
        self.pwd_entry = ttk.Entry(pwd_frame, textvariable=self.pwd_var)
        self.pwd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(pwd_frame, text="🔑 Auto", width=6,
                   command=lambda: self.pwd_var.set(generate_temp_password())).pack(side=tk.LEFT, padx=(5, 0))

        self.force_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            form, text="Obliger le changement au prochain sign-in",
            variable=self.force_var
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))

        ttk.Label(
            form, text="Le mot de passe temporaire robuste est généré automatiquement (12+ caractères).",
            foreground="gray"
        ).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))

        self.error_label = ttk.Label(form, text="", foreground="red")
        self.error_label.grid(row=5, column=0, columnspan=2, sticky=tk.W)

    def _validate(self) -> Optional[str]:
        pwd = self.pwd_var.get()
        if not pwd or len(pwd) < 8:
            return "Le mot de passe doit contenir au moins 8 caractères."
        has_upper = any(c.isupper() for c in pwd)
        has_lower = any(c.islower() for c in pwd)
        has_digit = any(c.isdigit() for c in pwd)
        has_special = any(c in "!@#$%^&*-_=+?" for c in pwd)
        if not (has_upper and has_lower and has_digit and has_special):
            return "Le mot de passe doit contenir majuscule, minuscule, chiffre et caractère spécial."
        return None

    def _build_result(self) -> Tuple[str, bool]:
        return (self.pwd_var.get(), bool(self.force_var.get()))


class AssignLicenseDialog(BaseDialog):
    """
    Dialogue d'assignation/retrait de licence.

    Args:
        skus: liste de dicts (clés sku_id, display_name/part_number)
        current_skus: ensemble des SKU déjà assignés à l'utilisateur
        remove_mode: ouvrir directement en mode retrait

    result -> (sku_id: str, action: str) avec action in {"add", "remove"}
    """

    def __init__(self, parent: tk.Misc, skus: List[Dict[str, Any]],
                 current_skus: Optional[List[str]] = None,
                 remove_mode: bool = False):
        self.skus = skus or []
        self.current_skus = set(current_skus or [])
        self.remove_mode = remove_mode
        super().__init__(parent, "🔑 Gérer les licences", width=520)

    def _build_ui(self, parent: ttk.Frame):
        form = self._make_form(parent)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Action:", ).grid(row=0, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        self.action_var = tk.StringVar(value="remove" if self.remove_mode else "add")
        action_frame = ttk.Frame(form)
        action_frame.grid(row=0, column=1, sticky=tk.W, pady=4)
        self.add_radio = ttk.Radiobutton(
            action_frame, text="Ajouter", value="add", variable=self.action_var,
            command=self._refresh_availability
        )
        self.add_radio.pack(side=tk.LEFT, padx=(0, 15))
        self.remove_radio = ttk.Radiobutton(
            action_frame, text="Retirer", value="remove", variable=self.action_var,
            command=self._refresh_availability
        )
        self.remove_radio.pack(side=tk.LEFT)

        ttk.Label(form, text="Licence:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        list_frame = ttk.Frame(form)
        list_frame.grid(row=1, column=1, sticky=tk.NSEW, pady=4)
        form.rowconfigure(1, weight=1)

        # Treeview avec scrollbar pour les licences disponibles
        self.sku_tree = ttk.Treeview(
            list_frame, columns=("name", "status"), show="tree headings", height=8, selectmode="browse"
        )
        self.sku_tree.heading("#0", text="Produit")
        self.sku_tree.heading("name", text="Référence SKU")
        self.sku_tree.column("#0", width=240, stretch=True)
        self.sku_tree.column("name", width=140, anchor=tk.W)
        self.sku_tree.heading("status", text="Statut")
        self.ssku_tree_col = self.sku_tree.column("status", width=110, anchor=tk.W)

        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.sku_tree.yview)
        self.sku_tree.configure(yscrollcommand=scroll.set)
        self.sku_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._load_skus("remove" if self.remove_mode else "add")

        ttk.Label(
            form,
            text="Sélectionnez une licence puis choisissez Ajouter ou Retirer.",
            foreground="gray"
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))

        self.error_label = ttk.Label(form, text="", foreground="red")
        self.error_label.grid(row=3, column=0, columnspan=2, sticky=tk.W)

    def _load_skus(self, action: str):
        """Charge la liste des SKUs (retirables vs assignables)."""
        for item in self.sku_tree.get_children():
            self.sku_tree.delete(item)
        for sku in self.skus:
            sku_id = sku.get("sku_id", "")
            assigned = sku_id in self.current_skus
            # En mode ajout : toutes les licences non assignées ;
            # en mode retrait : uniquement les licences assignées.
            if action == "add" and assigned:
                continue
            name = sku.get("display_name") or sku.get("part_number") or sku_id
            status = "Assignée" if assigned else f"Disponible ({sku.get('available', '?')} restantes)"
            self.sku_tree.insert("", tk.END, iid=sku_id, text=name, values=(sku.get("part_number", ""), status))

    def _refresh_availability(self):
        self._load_skus(self.action_var.get())

    def _validate(self) -> Optional[str]:
        selection = self.sku_tree.selection()
        if not selection:
            return "Sélectionnez une licence dans la liste."
        return None

    def _build_result(self) -> Tuple[str, str]:
        sku_id = self.sku_tree.selection()[0]
        return (sku_id, self.action_var.get())


class UserDetailDialog(BaseDialog):
    """
    Dialogue en lecture seule présentant les détails d'un utilisateur,
    avec un bouton pour copier l'UPN dans le presse-papiers.
    """

    def __init__(self, parent: tk.Misc, user: Dict[str, Any]):
        self.user = user
        super().__init__(parent, "👤 Détails de l'utilisateur", width=560)

    def _build_ui(self, parent: ttk.Frame):
        form = self._make_form(parent)
        form.columnconfigure(1, weight=1)

        display = self.user.get("display_name", "")
        upn = self.user.get("user_principal_name", "")
        ttk.Label(form, text=display, style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W)
        ttk.Label(form, text=upn, style="Subtitle.TLabel", foreground="gray").grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 12))

        fields = [
            ("Email", self.user.get("email", "")),
            ("Poste", self.user.get("job_title", "")),
            ("Département", self.user.get("department", "")),
            ("Bureau", self.user.get("screen_office", self.user.get("office_location", ""))),
            ("Téléphone mobile", self.user.get("mobile_phone", "")),
            ("Téléphone pro", self.user.get("business_phone", "")),
            ("Licence", "✔ Oui" if self.user.get("has_license") else "✖ Non"),
            ("Compte actif", "Oui" if self.user.get("account_enabled") else "Non"),
            ("Créé le", (self.user.get("created_date_time", "") or "")[:19].replace("T", " ")),
        ]
        row = 2
        for label, value in fields:
            ttk.Label(form, text=f"{label} :").grid(row=row, column=0, sticky=tk.W, padx=(0, 10), pady=3)
            ttk.Label(form, text=str(value) if value not in (None, "") else "—").grid(
                row=row, column=1, sticky=tk.W, pady=3)
            row += 1

        skus = self.user.get("license_skus") or []
        if skus:
            ttk.Label(form, text="Licences assignées :").grid(
                row=row, column=0, sticky=tk.W, padx=(0, 10), pady=3)
            ttk.Label(form, text=", ".join(str(s) for s in skus), wraplength=380).grid(
                row=row, column=1, sticky=tk.W, pady=3)
            row += 1

        copy_frame = ttk.Frame(form)
        copy_frame.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(12, 0))
        ttk.Button(
            copy_frame, text="📋 Copier l'UPN",
            command=lambda: self._copy_to_clipboard(self.user.get("user_principal_name", ""))
        ).pack(side=tk.LEFT)

        # Remplacer le bouton Valider par un simple bouton Fermer
        self.ok_btn and None
        self.cancel_btn and None

    def _build_result(self) -> Any:
        return None

    def _copy_to_clipboard(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self._notify_copied()

    def _notify_copied(self):
        if hasattr(self, "copy_feedback") and self.copy_feedback.winfo_exists():
            self.copy_feedback.config(text="✔ UPN copié !", foreground="green")
        else:
            from tkinter import messagebox
            messagebox.showinfo("Copié", "UPN copié dans le presse-papiers.", parent=self)


# =====================================================================
# Groupes
# =====================================================================

class GroupCreateDialog(BaseDialog):
    """
    Dialogue de création de groupe.

    Champs : Nom*, type (radio Microsoft 365 / Sécurité / Distribution),
    description.

    result -> dict(camelCase) :
        {"displayName": str, "mailEnabled": bool, "securityEnabled": bool,
         "groupTypes": list, "mailNickname": str, "description": str}
    """

    def __init__(self, parent: tk.Misc):
        super().__init__(parent, "➕ Créer un groupe", width=480)

    def _build_ui(self, parent: ttk.Frame):
        form = self._make_form(parent)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Nom du groupe *:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10), pady=4)
        self.name_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.name_var).grid(row=0, column=1, sticky=tk.EW, pady=4)

        ttk.Label(form, text="Type de groupe:").grid(row=1, column=0, sticky=tk.N, padx=(0, 10), pady=4)
        type_frame = ttk.Frame(form)
        type_frame.grid(row=1, column=1, sticky=tk.W, pady=4)
        self.type_var = tk.StringVar(value="m365")
        ttk.Radiobutton(type_frame, text="Microsoft 365", value="m365", variable=self.type_var).pack(anchor=tk.W)
        ttk.Radiobutton(type_frame, text="Sécurité", value="security", variable=self.type_var).pack(anchor=tk.W)
        ttk.Radiobutton(type_frame, text="Distribution", value="distribution", variable=self.type_var).pack(anchor=tk.W)

        ttk.Label(form, text="Description:").grid(row=2, column=0, sticky=tk.N, padx=(0, 10), pady=4)
        self.desc_text = tk.Text(form, height=3, width=36, relief="solid", borderwidth=1)
        self.desc_text.grid(row=2, column=1, ok_to_place=True, sticky=tk.EW, pady=4)
        self.desc_text.grid_remove()

        self.error_label = ttk.Label(form, text="", foreground="row=0")
        self.error_label = ttk.Label(form, text="", foreground="red")
        self.error_label.grid(row=4, column=0, columnspan=2, sticky=tk.W)

        ttk.Label(
            form, text="* champ obligatoire — mailNickname déduit automatiquement du nom",
            foreground="gray"
        ).grid(row=5, column=0, description_cspan=True, columnspan=2, sticky=tk.W, pady=(10, 0))

    def _validate(self) -> Optional[str]:
        if not self.name_var.get().strip():
            return "Le nom du groupe est obligatoire."
        return None

    def _build_result(self) -> Dict[str, Any]:
        name = self.name_var.get().strip()
        gtype = self.type_var.get()
        group_types: List[str] = []
        mail_enabled = False
        security_enabled = False
        if gtype == "m365":
            group_types = ["Unified"]
            mail_enabled = True
            security_enabled = False
        elif gtype == "security":
            group_types = []
            mail_enabled = False
            security_enabled = True
        else:  # distribution
            group_types = []
            mail_enabled = True
            security_enabled = False
        return {
            "displayName": name,
            "mailEnabled": mail_enabled,
            "securityEnabled": security_enabled,
            "groupTypes": group_types,
            "mailNickname": name.replace(" ", ""),
            "description": self.desc_text.get("1.0", tk.END).strip(),
        }


# =====================================================================
# Membres
# =====================================================================

class MembersDialog(BaseDialog):
    """
    Dialogue de gestion des membres d'un groupe.

    La liste des membres est fournie initialement par la fenêtre
    principale puis rafraîchie via `on_refresh_members` (callback appelé
    dans un thread Graph par la fenêtre principale).

    Callbacks (tous optionnels) :
        on_refresh_members(group_id) -> liste de membres
        on_add_member(group_id, member_id) -> bool
        on_remove_member(group_id, member_id) -> bool
    """

    def __init__(self, parent: tk.Misc, group_name: str, group_id: str,
                 members: List[Dict[str, Any]],
                 on_refresh_members: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
                 on_add_member: Optional[Callable[[str, str], bool]] = None,
                 on_remove_member: Optional[Callable[[str, str], bool]] = None):
        self.group_name = group_name
        self.group_id = group_id
        self.members = members or []
        self.on_refresh_members = on_refresh_members
        self.on_add_member = on_add_member
        self.on_remove_member = on_remove_member
        super().__init__(parent, f"👥 Membres — {group_name}", width=640)
        self.geometry(f"{640}x{520}")

    def _build_ui(self, parent: ttk.Frame):
        main = ttk.Frame(parent)
        main.pack(fill=tk.BOTH, expand=True)

        # Info + boutons
        top_frame = ttk.Frame(main)
        top_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(top_frame, text=f"Membres du groupe « {self.group_name} »", style="Subtitle.TLabel").pack(side=tk.LEFT)
        self.count_label = ttk.Label(top_frame, text=f"({len(self.members)})")
        self.count_label.pack(side=tk.LEFT, padx=6)

        ttk.Button(top_frame, text="🔄 Actualiser", command=self._on_refresh).pack(side=tk.RIGHT)
        ttk.Button(top_frame, text="➖ Retirer", command=self._on_remove).pack(side=tk.RIGHT, padx=5)
        ttk.Button(top_frame, text="➕ Ajouter", command=self._on_add).pack(side=tk.RIGHT)

        # Treeview membres
        tree_frame = ttk.Frame(main)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.members_tree = ttk.Treeview(
            tree_frame, columns=("email", "type"), show="tree headings", height=14, selectmode="browse"
        )
        self.members_tree.heading("#0", text="Nom")
        self.members_tree.column("#0", width=240, stretch=True)
        self.members_tree.heading("email", text="Email")
        self.members_tree.column("email", width=220, anchor=tk.W)
        self.members_tree.heading("type", text="Type")
        self.members_tree.column("type", width=110, anchor=tk.W)

        scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.members_tree.yview)
        self.members_tree.configure(yscrollcommand=scroll.set)
        self.members_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._render_members()

        # Bandeau de statut local au dialogue
        self.status_label = ttk.Label(main, text="", foreground="gray")
        self.status_label.pack(fill=tk.X, pady=(8, 0))

        # Cacher les boutons Annuler/Valider standard
        self.ok_btn.pack_forget()
        self.cancel_btn.config(text="Fermer")

    def _render_members(self):
        for item in self.members_tree.get_children():
            self.members_tree.delete(item)
        for m in self.members:
            name = m.get("display_name", "N/A")
            self.members_tree.insert("", tk.END, iid=m.get("id"), text=name,
                                     values=(m.get("email", ""), m.get("type", "")))
        self.count_label.config(text=f"({len(self.members)})")

    def _set_local_status(self, message: str, error: bool = False):
        self.status_label.config(text=message, foreground="red" if error else "gray")
        self.status_label.update_idletasks()

    def _on_refresh(self):
        if not self.on_refresh_members:
            self._set_local_status("Actualisation non disponible.")
            return
        self._set_local_status("Actualisation des membres...")
        try:
            members = self.on_refresh_members(self.group_id)
            if members is None:
                members = []
            self.members = members
            self._render_members()
            self._set_local_status(f"✔ {len(members)} membres.")
        except Exception as e:
            self._set_local_status(f"❌ Erreur : {e}", error=True)

    def _on_add(self):
        if not self.on_add_member:
            self._set_local_status("Ajout non disponible (connectez un tenant).")
            return
        # Petit dialogue de saisie de l'ID/email du membre à ajouter
        dlg = _MemberPickDialog(self, self.members, self.on_pick_member)
        if dlg.result:
            self._set_local_status(f"✔ Membre ajouté.", error=False)

    def _on_add_picked(self, candidate: Dict[str, Any]):
        """Ajoute un membre sélectionné depuis la liste des utilisateurs du tenant."""
        self._set_local_status(f"Ajout de {candidate.get('display_name', '')}...")
        try:
            ok = self.on_add_member(self.group_id, candidate.get("id"))
            if ok:
                self._set_local_status(f"✔ Membre ajouté.")
                self._on_refresh()
            else:
                self._set_local_status(f"❌ Échec de l'ajout (Graph a refusé l'opération).", error=True)
        except Exception as e:
            self._set_local_status(f"❌ Erreur : {e}", error=True)

    def on_pick_member(self, candidate: Dict[str, Any]):
        self._on_add_picked(candidate)

    def _on_remove(self):
        selection = self.members_tree.selection()
        if not selection:
            self._set_local_status("Sélectionnez un membre à retirer.")
            return
        member_id = selection[0]
        member_name = self.members_tree.item(selection[0], "text")
        if not self.on_remove_member:
            self._set_local_status("Retrait non disponible (connectez un tenant).")
            return
        if not messagebox_askyesno_delete(self, f"Retirer « {member_name} » du groupe ?"):
            return
        self._set_local_status(f"Retrait de {member_name}...")
        try:
            ok = self._on_remove_call(member_id)
            if ok:
                self._set_local_status(f"✔ Membre retiré.")
                self._on_refresh()
            else:
                self._set_local_status(f"❌ Échec du retrait.", error=True)
        except Exception as e:
            self._set_local_status(f"❌ Erreur : {e}", error=True)

    def _on_remove_call(self, member_id: str) -> bool:
        return self.on_remove_member(self.group_id, member_id)



def messagebox_askyesno_delete(parent, message: str) -> bool:
    """Confirmation de suppression (helper pour garder l'import local)."""
    from tkinter import messagebox
    return messagebox.askyesno("Confirmation", message, parent=parent)


class _MemberPickDialog(BaseDialog):
    """
    Dialogue interne de choix d'un membre à ajouter : liste des
    utilisateurs du tenant (chargée par la fenêtre principale) dans
    laquelle on sélectionne l'utilisateur à ajouter au groupe.
    """

    def __init__(self, parent: tk.Misc, current_members: List[Dict[str, Any]],
                 on_ok: Optional[Callable[[Dict[str, Any]], None]] = None,
                 load_users: Optional[Callable[[], List[Dict[str, Any]]]] = None):
        self.current_members = current_members or []
        self.on_ok = on_ok
        self.load_users = load_users
        self.candidates: List[Dict[str, AsyncRunner_result_placeholder]] = []
        super().__init__(parent, "➕ Ajouter un membre", width=580)
        self.geometry(f"{580}x{480}")

    def _build_ui(self, parent: ttk.Frame):
        main = ttk.Frame(parent)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="Sélectionnez l'utilisateur à ajouter :", style="Subtitle.TLabel").pack(anchor=tk.W, pady=(0, 8))

        tree_frame = ttk.Frame(main)
        tree_frame.pack(fill=tk.BOKH, expand=True)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.users_tree = ttk.Treeview(
            tree_frame, columns=("email", "type"), show="tree headings", height=12, selectmode="browse"
        )
        self.users_tree.heading("#0", text="Nom")
        self.users_tree.column("#0", width=200, stretch=True)
        self.users_tree.heading("email", text="Email")
        self.users_users_tree_col = None
        self.users_tree.column("email", width=200, anchor=tk.W)
        self.users_tree.heading("type", text="Type")
        self.users_tree.column("type", width=90, anchor=tk.W)

        scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.users_tree.yview)
        self.users_tree.configure(yscrollcommand=scroll.set)
        self.users_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Statut
        self.status_label = ttk.Label(main, text="Chargement des utilisateurs...", foreground="gray")
        self.status_label.pack(fill=tk.X, pady=(8, 0))

        self.ok_btn.config(text="Ajouter")
        self.cancel_btn.config(text="Annuler")

        # Chargement des utilisateurs (blocant local, léger : cache de la fenêtre principale)
        if self.load_users:
            try:
                users = self.load_users()
                self.candidates = [u for u in users
                                   if u.get("id") not in {m.get("id") for m in self.current_members}]
                self._render_users()
                self.status_label.config(text=f"{len(self.candidates)} utilisateurs disponibles (hors membres actuels)")
            except Exception as e:
                self.status_label.config(text=f"❌ Erreur de chargement : {e}", foreground="red")
        else:
            self.status_label.config(text="Liste des utilisateurs indisponible.")

    def _render_users(self):
        for item in self.users_tree.get_children():
            self.users_tree.delete(item)
        for u in self.candidates:
            self.users_tree.insert("", tk.END, iid=u.get("id"), text=u.get("display_name", "N/A"),
                                   values=(u.get("email", "") or u.get("user_principal_name", ""),
                                           u.get("type", "Utilisateur")))

    def _validate(self) -> Optional[str]:
        if not self.users_tree.selection():
            return "Sélectionnez un utilisateur."
        return None

    def _build_result(self) -> Dict[str, Any]:
        uid = self.users_tree.selection()[0]
        for u in self.candidates:
            if u.get("id") == uid:
                return u
        return None


# =====================================================================
# Licences : utilisateurs sans licence
# =====================================================================

class UnlicensedUsersDialog(BaseDialog):
    """
    Dialogue listant les utilisateurs sans licence (résultat de
    LicensesService.get_unlicensed_users()), avec bouton d'export CSV.

    La liste est fournie déjà chargée par la fenêtre principale.
    """

    def __user__(self): pass
    def __init__(self, parent: tk.Misc, users: List[Dict[str, Any]],
                 on_export: Optional[Callable[[List[Dict[str, Any]]], None]] = None):
        self.users = users or []
        self.on_export = on_export
        super().__initasks__(parent, "👤 Utilisateurs sans licence", width=640)
        self.geometry(f"{640}x{520}")

    def _build_ui(self, parent: ttk.Frame):
        main = ttk.Frame(parent)
        main.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(main)
        top.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(top, text=f"{len(self.users)} utilisateur(s) sans licence",
                  style="Subtitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(top, text="📊 Export CSV", command=self._on_export).pack(side=tk.RIGHT)

        tree_frame = ttk.Frame(main)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.users_tree = ttk.Treeview(
            tree_frame, columns=("email", "dept", "job"), show="tree headings", height=14
        )
        self.users_tree.heading("#0", text="Nom")
        self.users_tree.column("#0", width=200, stretch=True)
        self.users_tree.heading("email", text="Email")
        self.users_tree.column("email", width=220, anchor=tk.W)
        self.users_tree.heading("dept", text="Département")
        self.users_tree.column("de pt", width=130, anchor=tk.W)
        self.users_tree.column("dept", width=130, anchor=tk.W)
        self.users_tree.heading("job", text="Poste")
        self.users_tree.column("job", width=130, anchor=tk.W)

        scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.users_tree.yview)
        self.users_tree.configure(yscrollcommand=scroll.set)
        self.users_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for u in self.users:
            self.users_tree.insert("", tk.END, iid=u.get("id"), text=u.get("display_name", "N/A"),
                                   values=(u.get("email", "") or u.get("user_principal_name", ""),
                                           u.get("department", ""), u.get("job_title", "")))

        self.ok_btn.config(text="Fermer")
        self.cancel_btn.pack_forget()

    def _on_export(self):
        if self.on_export:
            self.on_export(self.users)

    def _build_result(self) -> Any:
        return None


# =====================================================================
# Helpers
# =====================================================================

def asksaveasfilename_csv(title: str, suggested_name: str = "export.csv") -> Optional[str]:
    """Ouvre un dialogue de sauvegarde CSV et retourne le chemin ou None."""
    from tkinter import filedialog
    path = filedialog.asksaveasfilename(
        title=title,
        defaultextension=".csv",
        filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")],
        initialfile=suggested_name,
    )
    return path or None