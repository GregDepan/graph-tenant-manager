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
            "core/app_info.py", "core/updater.py",
            "services/users_service.py", "services/groups_service.py",
            "services/devices_service.py", "services/licenses_service.py",
            "services/sharepoint_service.py", "services/onedrive_service.py",
            "services/exchange_service.py", "services/teams_service.py",
            "gui/main_window.py", "gui/dialogs.py", "gui/workload_panels.py",
            "utils/logger.py"]:
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
check("auth: 17 scopes par défaut (v2.1 workloads)",
      len(auth.scopes) == 17 and "Directory.ReadWrite.All" in auth.scopes
      and "Sites.Read.All" in auth.scopes and "Team.ReadBasic.All" in auth.scopes
      and "Reports.Read.All" in auth.scopes and "Files.Read.All" in auth.scopes
      and "Channel.ReadBasic.All" in auth.scopes and "TeamMember.Read.All" in auth.scopes)
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


# ---- Fakes workloads v2.1 -------------------------------------------

class FakeSite:
    def __init__(self, i, personal=False):
        self.id = f"site{i}"
        self.display_name = f"Site {i}"
        self.web_url = f"https://contoso.sharepoint.com/sites/site{i}"
        self.is_personal_site = personal
        self.created_date_time = "2026-01-15T10:00:00Z"
        self.last_modified_date_time = "2026-09-20T12:00:00Z"


class FakeDrive:
    def __init__(self, i, used, total, dtype="business"):
        self.id = f"drive{i}"
        self.name = f"Documents {i}"
        self.drive_type = dtype
        self.web_url = f"https://contoso.sharepoint.com/doc{i}"
        self.quota = types.SimpleNamespace(
            used=used, total=total, remaining=total - used, state="normal")


class FakeTeamGroup:
    def __init__(self, i, archived=False):
        self.id = f"team{i}"
        self.display_name = f"Équipe {i}"
        self.mail = f"team{i}@contoso.com"
        self.proxy_addresses = [f"SMTP:team{i}@contoso.com"]
        self.visibility = "Private" if i == 0 else "Public"
        self.created_date_time = "2026-02-01T09:00:00Z"
        self.description = f"Équipe {i} du tenant"
        self.is_archived = archived


class FakeChannel:
    def __init__(self, i, ctype="standard"):
        self.id = f"ch{i}"
        self.display_name = f"Canal {i}"
        self.description = f"Desc canal {i}"
        self.membership_type = ctype
        self.email = f"ch{i}@contoso.com"
        self.created_date_time = "2026-02-05T09:00:00Z"

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
    # ---- Workloads v2.1 ----
    async def get_all_sites(self, limit=None):
        return [FakeSite(1), FakeSite(2), FakeSite(3, personal=True)]
    async def get_site_drives(self, site_id):
        return [FakeDrive(1, 5 * 1024**3, 100 * 1024**3),
                FakeDrive(2, 0, 100 * 1024**3)]
    async def get_user_drive(self, user_id):
        if user_id in ("u5", "u6"):
            return None  # pas de OneDrive provisionné
        return FakeDrive(int(user_id[1:]), 2 * 1024**3, 1024 * 1024**3,
                         dtype="personal")
    async def get_all_teams(self, limit=None):
        return [FakeTeamGroup(0), FakeTeamGroup(1, archived=True)]
    async def get_team_channels(self, team_id):
        return [FakeChannel(0), FakeChannel(1, ctype="private")]
    async def get_team_member_count(self, team_id):
        return 12
    async def get_mailbox_usage_report(self, period="D30"):
        return (
            "Report Refresh Date,User Principal Name,Display Name,Is Deleted,"
            "Storage Used (Byte),Item Count,Last Activity Date\r\n"
            "2026-09-25,alice@contoso.com,Alice Martin,False,1073741824,1200,2026-09-24\r\n"
            "2026-09-25,bob@contoso.com,Bob Dupont,True,536870912,300,2026-09-10\r\n"
            "2026-09-25,carole@contoso.com,Carole Bernard,False,2147483648,3400,\r\n"
        ).encode("utf-8")

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

    # ---- Workloads v2.1 : SharePoint / OneDrive / Exchange / Teams ----
    from services.sharepoint_service import SharePointService
    from services.onedrive_service import OneDriveService
    from services.exchange_service import ExchangeService
    from services.teams_service import TeamsService

    # SharePoint
    sps = SharePointService(fw)
    sites = await sps.get_sites()
    check("sharepoint: 2 sites (perso exclu)", len(sites) == 2)
    check("sharepoint: champs du contrat",
          all(k in sites[0] for k in ("id", "name", "url", "created",
                                      "last_modified", "personal")))
    libs = await sps.get_libraries("site1")
    check("sharepoint: 2 bibliothèques", len(libs) == 2)
    check("sharepoint: quota lu", libs[0]["storage_quota"] == 100 * 1024**3)
    all_sites = await sps.get_sites(include_personal=True)
    check("sharepoint: include_personal=True → 3", len(all_sites) == 3)
    tmp3 = os.path.join(tempfile.gettempdir(), "gtm_test_sites.csv")
    ok = sps.export_to_csv(sites, tmp3)
    check("sharepoint: export CSV", ok and "SharePoint" in open(tmp3, encoding="utf-8").read())

    # OneDrive
    ods = OneDriveService(fw)
    drives = await ods.get_drives()
    check("onedrive: 5 lecteurs (2 sans drive)", len(drives) == 5)
    check("onedrive: tri par propriétaire",
          drives[0]["owner"] == "User 0")
    check("onedrive: quota/remaining lus",
          drives[0]["storage_used"] == 2 * 1024**3 and
          drives[0]["storage_remaining"] == 1022 * 1024**3)
    tmp4 = os.path.join(tempfile.gettempdir(), "gtm_test_od.csv")
    ok = ods.export_to_csv(drives, tmp4)
    check("onedrive: export CSV", ok and "Go" in open(tmp4, encoding="utf-8").read())

    # Exchange
    exs = ExchangeService(fw)
    boxes = await exs.get_mailbox_usage()
    check("exchange: 2 boîtes (supprimée exclue)", len(boxes) == 2)
    alice = [b for b in boxes if b["upn"] == "alice@contoso.com"][0]
    check("exchange: parsing tailles/activité",
          alice["storage_used"] == 1024**3 and alice["item_count"] == 1200
          and alice["last_activity"] == "2026-09-24")
    carole = [b for b in boxes if b["upn"] == "carole@contoso.com"][0]
    check("exchange: activité vide tolérée", carole["last_activity"] == "")
    tmp5 = os.path.join(tempfile.gettempdir(), "gtm_test_ex.csv")
    ok = exs.export_to_csv(boxes, tmp5)
    check("exchange: export CSV", ok and "Alice" in open(tmp5, encoding="utf-8").read())

    # Teams
    ts = TeamsService(fw)
    teams = await ts.get_all_teams_formatted()
    check("teams: 2 équipes", len(teams) == 2)
    check("teams: champs du contrat",
          all(k in teams[0] for k in ("id", "name", "mail", "visibility",
                                      "archived", "created", "member_count")))
    check("teams: archivée détectée", teams[1]["archived"] is True)
    chans = await ts.get_team_channels("team0")
    check("teams: 2 canaux", len(chans) == 2)
    check("teams: type privé détecté",
          chans[1]["type"] == "private")
    cnt = await ts.get_team_member_count("team0")
    check("teams: member count", cnt == 12)
    tmp6 = os.path.join(tempfile.gettempdir(), "gtm_test_teams.csv")
    ok = ts.export_to_csv(teams, tmp6)
    check("teams: export CSV", ok and "Oui" in open(tmp6, encoding="utf-8").read())

    # ---- Mises à jour automatiques (v2.1) ----
    from core.app_info import APP_VERSION, parse_version
    from core import updater

    check("updater: APP_VERSION définie", APP_VERSION == "2.1.1")
    check("updater: parse_version v2.1.0", parse_version("v2.1.0") == (2, 1, 0))
    check("updater: parse_version robuste", parse_version("v10.2.3-beta") == (10, 2, 3))
    check("updater: comparaison stricte",
          updater.compare_versions("v99.0.0")[0] is True and
          updater.compare_versions("v2.1.0")[0] is False and
          updater.compare_versions("v2.0.9")[0] is False and
          updater.compare_versions("v2.1.1")[0] is True)
    check("updater: padding implicite (2,1) < (2,1,0)",
          updater.compare_versions("v2.1")[0] is False)

    # Mock réseau : API GitHub injoignable → None silencieux
    orig_fetch = updater.fetch_latest_release
    updater.fetch_latest_release = lambda timeout=120: None
    check("updater: GitHub injoignable → None", updater.check_update() is None)

    # Mock réseau : release plus récente avec asset .exe → dict d'update
    updater.fetch_latest_release = lambda timeout=120: {
        "tag_name": "v9.9.9",
        "assets": [{"name": "GraphTenantManager.exe",
                    "browser_download_url": "https://x/GraphTenantManager.exe",
                    "url": "https://api.x/asset", "size": 12345}],
        "body": "notes",
    }
    info = updater.check_update()
    check("updater: release détectée", info is not None and
          info["version"] == "9.9.9" and info["size"] == 12345)

    # Release sans asset .exe → None
    updater.fetch_latest_release = lambda timeout=120: {
        "tag_name": "v9.9.9", "assets": [], "body": ""}
    check("updater: sans asset .exe → None", updater.check_update() is None)
    updater.fetch_latest_release = orig_fetch

    # Téléchargement vers fichier temporaire (serveur HTTP local mocké)
    import http.server, threading
    payload = b"FAKEEXE" * 1000
    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *a, **k):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/GraphTenantManager.exe"
        progress_calls = []
        path = updater.download_update(url, progress_cb=lambda r, t: progress_calls.append((r, t)))
        check("updater: téléchargement complet",
              path is not None and os.path.exists(path) and
              os.path.getsize(path) == len(payload))
        check("updater: progression rapportée",
              len(progress_calls) > 0 and progress_calls[-1][0] == len(payload))
    finally:
        srv.shutdown()
    # Mode script : apply_update refuse proprement (pas un .exe)
    check("updater: apply_update no-op en mode script",
          updater.apply_update("/tmp/whatever.exe") is False)

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
    # Neutralise le réseau de l'updater : le check auto planifié par
    # l'app (after 800ms) trouvera fetch_latest_release patché → None
    # silencieux, aucun appel réel vers GitHub pendant le test headless.
    from core import updater as _upd
    _orig_fetch = _upd.fetch_latest_release
    _upd.fetch_latest_release = lambda timeout=120: None
    config = {
        "clientId": "test", "tenantId": "common",
        "graphUserScopes": "User.Read.All", "theme": "clam",
        "language": "fr", "refresh_interval": 300, "log_level": "INFO", "log_file": "",
    }
    app = GraphTenantManagerApp(root, config)

    # L'app a bien 9 onglets (5 historiques + 4 workloads v2.1)
    check("gui: 9 onglets", len(app.notebook.tabs()) == 9, f"{len(app.notebook.tabs())}")
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

    # ---- Workloads v2.1 : panneaux construits + rendus mockés ----
    check("gui: 4 panneaux workload instanciés",
          all(hasattr(app, n) and getattr(app, n) is not None
              for n in ("sharepoint_panel", "onedrive_panel",
                        "exchange_panel", "teams_panel")))
    app.sharepoint_panel.renderer([
        {"id": "site1", "name": "Site 1", "url": "https://x", "created": "",
         "last_modified": "", "personal": False}])
    check("gui: rendu SharePoint", len(app.sharepoint_panel.tree.get_children()) == 1)
    app.teams_panel.renderer([
        {"id": "team0", "name": "Équipe 0", "mail": "t@c.com",
         "visibility": "Public", "archived": False, "created": ""}])
    check("gui: rendu Teams", len(app.teams_panel.tree.get_children()) == 1)
    # _workload_panel : mapping index → panneau
    check("gui: mapping _workload_panel",
          app._workload_panel(5) is app.sharepoint_panel and
          app._workload_panel(8) is app.teams_panel and
          app._workload_panel(2) is None)
    # _init_services instancie aussi les services workload
    check("gui: _init_services → 8 services",
          app.sharepoint_service is not None and app.onedrive_service is not None
          and app.exchange_service is not None and app.teams_service is not None)
    # déconnexion : _clear_all_data vide les panneaux
    app._clear_all_data()
    check("gui: _clear_all_data vide les panneaux",
          len(app.sharepoint_panel.tree.get_children()) == 0 and
          app.sharepoint_panel.data == [])
    # Mise à jour : le check planifié au démarrage ne crashe pas (méthode
    # présente + runner branché) ; pas d'appel réseau réel en test.
    check("gui: _check_for_updates existe", callable(app._check_for_updates))
    check("gui: version au titre", "v2.1" in app.root.title())
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
    _upd.fetch_latest_release = _orig_fetch  # restaure le vrai fetcher
    check("gui: destroy propre", True)

# ---------------------------------------------------------------- Résultat
print("\n" + "=" * 60)
print(f"RÉSULTAT : {PASS} PASS / {FAIL} FAIL")
if FAILED:
    print("Échecs :", ", ".join(FAILED))
print("=" * 60)
sys.exit(1 if FAIL else 0)