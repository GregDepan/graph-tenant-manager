"""
Script de test rapide pour Graph Tenant Manager
Vérifie que les modules s'importent correctement
"""

import sys
import os

print("🧪 Tests Graph Tenant Manager")
print("=" * 50)

# Ajouter le dossier courant
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Tester les imports
tests_passed = 0
tests_failed = 0

def test_import(module_name, module_path=None):
    """Teste l'import d'un module"""
    global tests_passed, tests_failed
    
    try:
        if module_path:
            module = __import__(module_path, fromlist=[''])
        else:
            module = __import__(module_name)
        
        print(f"✓ {module_name}")
        tests_passed += 1
        return True
    except Exception as e:
        print(f"✗ {module_name}: {e}")
        tests_failed += 1
        return False

print("\n📦 Testing core modules...")
test_import('core.auth', 'core.auth')
test_import('core.graph_client', 'core.graph_client')

print("\n📦 Testing services...")
test_import('services.users_service', 'services.users_service')
test_import('services.groups_service', 'services.groups_service')
test_import('services.devices_service', 'services.devices_service')

print("\n📦 Testing gui...")
test_import('gui.main_window', 'gui.main_window')

print("\n📦 Testing utils...")
test_import('utils.logger', 'utils.logger')

print("\n" + "=" * 50)
print(f"Résultats: {tests_passed} passed, {tests_failed} failed")

if tests_failed > 0:
    print("\n⚠️  Certains tests ont échoué.")
    print("Exécutez: install.bat pour installer les dépendances.")
    sys.exit(1)
else:
    print("\n✅ Tous les tests sont passés!")
    print("\nL'application est prête à être utilisée.")
    print("Lancez: python main.py")
    sys.exit(0)
