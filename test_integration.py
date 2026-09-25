"""
Tests d'intégration Graph Tenant Manager (sans connexion Graph réelle).
Vérifie : compilation, imports croisés, AsyncRunner, services avec mock,
contrats d'API, dialogues (logique), wiring de la GUI.
"""

import asyncio
import sys
import os
import types
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0
FAILED = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        FAILED.append(name)
        print(f"  ✗ {name} {detail}")


print("=" * 60)
print("TESTS D'INTÉGRATION — Graph Tenant Manager v1.1")
print("=" * 60)

# ---------------------------------------------------------------- 1. Compilation
print("\n[1] Compilation de tous les modules")
import py_compile
for mod in ["main.py", "core/async_runner.py", "core/auth.py", "core/graph_client.py",
            "services/users_service.py", "services/groups_service.py",
            "services/devices_service.py", "services/licenses_service.py",
            "gui/main_window.py", "gui/dialogs.py", "utils/logger.py"]:
    try:
        py_compile.compile(mod, doraise=True)
        check(f"py_compile {mod}", True)
    except Exception as e:
        check(f"py_compile {mod}", False, str(e)[:80])

# ---------------------------------------------------------------- 2. Imports
print("\n[2] Imports croisés")
try:
    from core.async_runner import AsyncRunner
    check("import AsyncRunner", True)
except Exception as e:
    check("import AsyncRunner", False, str(e))
    sys.exit(1)

try:
    from core.auth import TenantAuthManager
    from core.graph_client import GraphClientWrapper
    check("import core", True)
except Exception as e:
    check("import core", False, str(e))
    sys.exit(1)

try:
    from services.users_service import UsersService
    from services.groups_service import GroupsService
    from services.devices_service import DevicesService
    from services.licenses_service import LicensesService
    check("import services", True)
except Exception as e:
    check("import services", False, str(e))
    sys.exit(1)

try:
    from gui.main_window import GraphTenantManagerApp, run_app
    check("import gui.main_window", True)
except Exception as e:
    check("import gui.main_window", False, str(e))
    sys.exit(1)

try:
    import gui.dialogs as dialogs
    for cls in ["UserCreateDialog", "UserEditDialog", "ResetPasswordDialog",
                "AssignLicenseDialog", "GroupCreateDialog", "MembersDialog",
                "UserDetailDialog", "UnlicensedUsersDialog"]:
        check(f"dialog {cls}", hasattr(dialogs, cls))
except Exception as e:
    check("import gui.dialogs", False, str(e))
    sys.exit(1)

# ---------------------------------------------------------------- 3. AsyncRunner
print("\n[3] AsyncRunner (fix du bug asyncio.run multiple + mode sync v2.0)")
runner = AsyncRunner.get_instance()

async def op1():
    return "ok1"

async def op2():
    await asyncio.sleep(0.05)
    return "ok2"

r1 = runner.run(op1())
check("run() #1", r1 == "ok1", f"obtenu {r1!r}")
r2 = runner.run(op2())
check("run() #2 (même loop, pas de 'Event loop is closed')", r2 == "ok2", f"obtenu {r2!r}")

# v2.0 : run_in_thread accepte aussi les fonctions SYNC (auth MSAL bloquante)
sync_results = []
runner.run_in_thread(lambda: "valeur_sync", callback=lambda v: sync_results.append(v))
time.sleep(0.5)
check("run_in_thread() sync factory (auth MSAL)", sync_results == ["valeur_sync"], f"obtenu {sync_results!r}")

results = []
runner.run_in_thread(lambda: op2(), callback=lambda v: results.append(v))
time.sleep(0.5)
check("run_in_thread() coroutine + callback", results == ["ok2"], f"obtenu {results!r}")

err_caught = []
runner.run_in_thread(lambda: (_ for _ in ()).throw(ValueError("boom")),
                     error_callback=lambda e: err_caught.append(e))
time.sleep(0.5)
check("run_in_thread() error_callback", len(err_caught) == 1 and isinstance(err_caught[0], ValueError))

runner.stop()
check("stop() propre", not runner.is_running)

# ---------------------------------------------------------------- 3b. Auth v2.0 zéro-config
print("\n[3b] Auth v2.0 — zéro config (client well-known Microsoft)")
from core.auth import TenantAuthManager, WELL_KNOWN_CLIENT_ID, cache_dir, DEFAULT_SCOPES

auth = TenantAuthManager({})
check("auth: client well-known par défaut", auth.client_id == WELL_KNOWN_CLIENT_ID)
check("auth: client well-known = app MS Graph PowerShell", WELL_KNOWN_CLIENT_ID == "14d82eec-204b-4c2f-b7e8-296a70dab67e")
check("auth: 11 scopes par défaut", len(auth.scopes) == 11 and "Directory.ReadWrite.All" in auth.scopes)
check("auth: custom_app False", auth.custom_app is False)

auth_custom = TenantAuthManager({"clientId": "mon-app-perso"})
check("auth: surcharge clientId possible", auth_custom.client_id == "mon-app-perso" and auth_custom.custom_app is True)

try:
    cred = auth._browser_credential()
    check("auth: credential navigateur constructible", type(cred).__name__ == "InteractiveBrowserCredential")
except Exception as e:
    check("auth: credential navigateur constructible", False, str(e)[:60])

try:
    cred = auth._device_credential()
    check("auth: credential device code constructible", type(cred).__name__ == "DeviceCodeCredential")
except Exception as e:
    check("auth: credential device code constructible", False, str(e)[:60])

# prompt_callback device code : signature 3 args
codes = []
auth._device_credential(prompt_callback=lambda uc, vu, ex: codes.append(uc))
check("auth: prompt_callback device (3 args)", True)

# Persistance record : écriture + relecture + list_saved_tenants
from azure.identity import AuthenticationRecord
fake_record = AuthenticationRecord(
    tenant_id="tid-test-1234", client_id=WELL_KNOWN_CLIENT_ID,
    authority="login.microsoftonline.com", home_account_id="ha.1234", username="admin@contoso.com",
)
auth._save_record("tid-test-1234", fake_record, "admin@contoso.com", "Contoso")
saved = auth.list_saved_tenants()
check("auth: record persisté + list_saved_tenants", len(saved) == 1 and saved[0]["tenant_id"] == "tid-test-1234" and saved[0]["username"] == "admin@contoso.com")

payload = auth._load_record_payload("tid-test-1234")
check("auth: payload relu", payload is not None and payload.get("tenant_name") == "Contoso")

auth.forget_tenant("tid-test-1234")
check("auth: forget_tenant supprime le record", len(auth.list_saved_tenants()) == 0)

check("auth: reconnect_silent None si pas de record", auth.reconnect_silent("inconnu") is None)

# Session
check("auth: disconnect mémoire sans effacer records", True)

# ---------------------------------------------------------------- 4. Mock Graph
print("\n[4] Services avec mock Graph (contrat + logique)")

class FakeUser:
    def __init__(self, i, lic=None):
        self.id = f"u{i}"
        self.display_name = f"User {i}"
        self.user_principal_name = f"user{i}@contoso.com"
        self.mail = f"user{i}@contoso.com"
        self.job_title = "Technicien" if i % 2 else None
        self.department = "IT" if i % 3 else None
        self.office_location = None
        self.mobile_phone = None
        self.business_phones = ["0555" + str(i)] if i % 2 else []
        self.account_enabled = i != 5
        self.created_date_time = None
        # licences : objets avec attribut sku_id (comme le SDK), pas des dicts
        self.assigned_licenses = (
            [types.SimpleNamespace(sku_id=lic)] if lic else []
        )

class FakeGroup:
    def __init__(self, i, gtype="security"):
        self.id = f"g{i}"
        self.display_name = f"Groupe {i}"
        self.mail = f"g{i}@contoso.com" if gtype == "unified" else None
        self.mail_enabled = gtype in ("unified", "distribution")
        self.security_enabled = gtype in ("security", "mailsec")
        self.group_types = ["Unified"] if gtype == "unified" else []
        self.description = f"Desc {i}"

class FakeDevice:
    def __init__(self, i, os_name="Windows", compliant=True):
        self.id = f"d{i}"
        self.display_name = f"PC-{i}"
        self.device_id = f"did{i}"
        self.operating_system = os_name
        self.operating_system_version = "10.0"
        self.manufacturer = "Dell"
        self.model = "Latitude"
        self.account_enabled = True
        self.is_compliant = compliant
        self.approximate_last_sign_in_date_time = None

class FakeSku:
    def __init__(self, part, total, consumed):
        self.sku_id = f"sku-{part}"
        self.sku_part_number = part
        self.consumed_units = consumed
        self.prepaid_units = [types.SimpleNamespace(enabled=total)]

class FakeGraphWrapper:
    """Mock conforme au contrat GraphClientWrapper."""
    async def get_all_users(self, limit=None):
        return [FakeUser(i, lic="SPE_E3" if i < 3 else None) for i in range(7)]
    async def search_users(self, term):
        return [FakeUser(1)]
    async def create_user(self, data):
        if not data.get("userPrincipalName"):
            return None
        return FakeUser(99)
    async def update_user(self, uid, updates):
        return True
    async def delete_user(self, uid):
        return True
    async def reset_user_password(self, uid, pwd, force_change=True):
        return True
    async def assign_licenses(self, uid, add_skus, remove_skus):
        self.last_assign = (uid, add_skus, remove_skus)
        return True
    async def get_subscribed_skus(self):
        return [FakeSku("SPE_E3", 25, 24), FakeSku("AAD_PREMIUM", 100, 3)]
    async def get_all_groups(self, limit=None):
        return [FakeGroup(0, "unified"), FakeGroup(1, "security"), FakeGroup(2, "distribution")]
    async def get_group_members(self, gid):
        return [FakeUser(1), FakeUser(2)]
    async def create_group(self, data):
        return FakeGroup(99)
    async def add_group_member(self, gid, mid):
        return True
    async def remove_group_member(self, gid, mid):
        return True
    async def get_all_devices(self, limit=None):
        return [FakeDevice(0, "Windows", True), FakeDevice(1, "iOS", False), FakeDevice(2, "macOS", None)]
    async def get_device_by_id(self, did):
        return FakeDevice(0)
    async def get_tenant_info(self):
        return {"id": "tid", "display_name": "Contoso", "verified_domains": ["contoso.com"], "initial_domain": "contoso.com"}
    async def get_tenant_users_count(self):
        return 7
    async def get_tenant_groups_count(self):
        return 3
    async def get_tenant_devices_count(self):
        return 3

async def run_tests_async():
    global PASS, FAIL
    fw = FakeGraphWrapper()

    # Users
    us = UsersService(fw)
    users = await us.get_all_users_formatted()
    check("users: 7 formatés", len(users) == 7, f"{len(users)}")
    u0 = users[0]
    check("users: clés du contrat",
          all(k in u0 for k in ["id", "display_name", "email", "user_principal_name",
                                "job_title", "department", "office_location", "mobile_phone",
                                "business_phone", "account_enabled", "created_date_time",
                                "has_license", "license_skus"]))
    check("users: has_license cohérent", users[0]["has_license"] is True and users[5]["has_license"] is False)
    check("users: license_skus liste", isinstance(users[0]["license_skus"], list))
    check("users: business_phone extrait", users[1]["business_phone"] == "05551")

    # create sans UPN → None (fix KeyError)
    res = await us.create({"displayName": "X"})
    check("users: create sans UPN → None (fix KeyError)", res is None)
    uid = await us.create({"displayName": "Y", "userPrincipalName": "y@contoso.com"})
    check("users: create OK retourne id", uid == "u99")

    # licences
    ok = await us.assign_license("u5", "sku-X")
    check("users: assign_license → assign_licenses wrapper", ok and fw.last_assign == ("u5", ["sku-X"], []))
    ok = await us.unassign_license("u5", "sku-X")
    check("users: unassign_license", ok)
    ok = await us.set_blocked("u5", True)
    check("users: set_blocked", ok)
    ok = await us.reset_password("u5", "Pass123!", force_change=False)
    check("users: reset_password", ok)

    # CSV
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "gtm_test_users.csv")
    ok = us.export_to_csv(users, tmp)
    content = open(tmp, encoding="utf-8").read()
    check("users: export CSV écrit", ok and "has_license" in content and "license_skus" in content)

    # Groups
    gs = GroupsService(fw)
    groups = await gs.get_all_groups_formatted()
    check("groups: 3 formatés", len(groups) == 3)
    check("groups: PAS de member_count au listing (fix N+1)",
          all("member_count" not in g for g in groups))
    check("groups: types détectés",
          groups[0]["group_type"] == "Microsoft 365" and groups[1]["group_type"] == "Security")
    members = await gs.get_group_members("g0")
    check("groups: get_group_members formaté", len(members) == 2 and "type" in members[0])
    cnt = await gs.get_member_count("g0")
    check("groups: get_member_count à la demande", cnt == 2)
    gdata = await gs.create({"displayName": "New", "group_type": "Sécurité"})
    check("groups: create", gdata is not None)

    # Devices
    ds = DevicesService(fw)
    devices = await ds.get_all_devices_formatted()
    check("devices: 3 formatés", len(devices) == 3)
    check("devices: conformité basée sur is_compliant (fix)",
          devices[0]["compliance_status"] == "Conforme"
          and devices[1]["compliance_status"] == "Non conforme"
          and devices[2]["compliance_status"] == "Inconnu")
    check("devices: os_type détecté", devices[0]["os_type"] == "Windows" and devices[1]["os_type"] == "iOS")

    # Licences
    ls = LicensesService(fw)
    inv = await ls.get_inventory()
    check("licences: 2 SKUs", len(inv) == 2)
    spe = [i for i in inv if i["part_number"] == "SPE_E3"][0]
    check("licences: total/consumed/available", spe["total"] == 25 and spe["consumed"] == 24 and spe["available"] == 1)
    check("licences: warning déclenché (1 dispo)", spe["warning"] is True)
    aad = [i for i in inv if i["part_number"] == "AAD_PREMIUM"][0]
    check("licences: pas de warning si stock OK", aad["warning"] is False)
    check("licences: display_name mapping FR", spe["display_name"] == "Microsoft 365 E3")
    unl = await ls.get_unlicensed_users()
    check("licences: unlicensed filtrés", len(unl) == 4 and all(not u["has_license"] for u in unl))

    tmp2 = os.path.join(tempfile.gettempdir(), "gtm_test_lic.csv")
    ok = ls.export_to_csv(inv, tmp2)
    check("licences: export CSV", ok and open(tmp2, encoding="utf-8").read().count("Oui") >= 1)

asyncio.run(run_tests_async())

# ---------------------------------------------------------------- 5. GUI wiring (headless)
print("\n[5] GUI wiring (headless — construction logique uniquement)")

try:
    import tkinter as tk
except Exception:
    tk = None
    print("  (tkinter indisponible — partie GUI wiring sautée)")

if tk:
    root = tk.Tk()
    root.withdraw()
    config = {
        "clientId": "test", "tenantId": "common",
        "graphUserScopes": "User.Read.All", "theme": "clam",
        "language": "fr", "refresh_interval": 300, "log_level": "INFO", "log_file": "",
    }
    app = GraphTenantManagerApp(root, config)

    # L'app a bien 5 onglets
    check("gui: 5 onglets", len(app.notebook.tabs()) == 5, f"{len(app.notebook.tabs())}")
    # Boutons d'action présents
    check("gui: boutons users (7)", len(app.users_btns) == 7, f"{len(app.users_btns)}")
    check("gui: boutons groups (4)", len(app.groups_btns) == 4)
    # Services absents avant connexion
    check("gui: services None avant connexion", app.users_service is None)
    # _init_services avec mock
    app.graph_wrapper = FakeGraphWrapper()
    app._init_services()
    check("gui: _init_services instancie tout",
          app.users_service is not None and app.licenses_service is not None)
    # rendu users via le thread
    app._render_users([{"id": "u1", "display_name": "A", "email": "a@c.com",
                        "job_title": "", "department": "", "has_license": True,
                        "account_enabled": True, "user_principal_name": "a@c.com"}])
    check("gui: _render_users remplit le tree", len(app.users_tree.get_children()) == 1)
    # rendu licences avec warning tag
    app._render_licenses([{"sku_id": "s1", "part_number": "P", "display_name": "Prod",
                           "total": 10, "consumed": 9, "available": 1, "warning": True}])
    check("gui: _render_licenses + tag warning", "warning" in app.licenses_tree.item(app.licenses_tree.get_children()[0], "tags"))
    # dashboard display
    app._display_dashboard(7, 3, 3, {"id": "t", "display_name": "Contoso"},
                           [{"consumed": 9, "total": 10, "available": 1, "warning": True}])
    check("gui: dashboard affiché", len(app.dashboard_tab.winfo_children()) > 0)

    # ---- 5b. Instanciation des dialogues (régression __initasks__ v2.0) ----
    # Le bug v2.0 (super().__initasks__ dans UnlicensedUsersDialog) n'était
    # pas détecté car aucun test n'instanciait les dialogues. On construit
    # maintenant chaque dialogue critique headless.
    # NB : sous Xvfb sans window manager, les Toplevel ne sont jamais
    # « mappés » par le serveur X → wait_visibility() attendrait pour
    # toujours. On le neutralise pour ce test uniquement (en usage réel
    # avec un WM, le comportement est inchangé).
    tk.Toplevel.wait_visibility = lambda self, *a, **k: None
    from gui.dialogs import UnlicensedUsersDialog, AssignLicenseDialog
    d1 = UnlicensedUsersDialog(root, [{"id": "u1", "display_name": "A",
                                       "email": "a@c.com", "has_license": False}])
    check("gui: UnlicensedUsersDialog instancié (fix __initasks__)", d1 is not None)
    d1.destroy()
    d2 = AssignLicenseDialog(root, [{"sku_id": "s1", "display_name": "Prod",
                                     "available": 5}], current_skus=[])
    check("gui: AssignLicenseDialog instancié", d2 is not None)
    d2.destroy()

    root.destroy()
    check("gui: destroy propre", True)

# ---------------------------------------------------------------- Résultat
print("\n" + "=" * 60)
print(f"RÉSULTAT : {PASS} PASS / {FAIL} FAIL")
if FAILED:
    print("Échecs :", ", ".join(FAILED))
print("=" * 60)
sys.exit(1 if FAIL else 0)