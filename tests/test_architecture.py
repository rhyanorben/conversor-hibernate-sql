import ast
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1] / 'hibernate_sql'
ALLOWED_DEPENDENCIES = {
    'domain': {'domain'},
    'application': {'application', 'domain'},
    'infrastructure': {'infrastructure', 'domain'},
    'presentation': {'presentation', 'application'},
}


class ArchitectureTests(unittest.TestCase):
    def test_dependencies_point_to_inner_layers(self):
        for layer, allowed in ALLOWED_DEPENDENCIES.items():
            for path in (PROJECT / layer).rglob('*.py'):
                tree = ast.parse(path.read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    modules = []
                    if isinstance(node, ast.ImportFrom) and node.module:
                        modules.append(node.module)
                    elif isinstance(node, ast.Import):
                        modules.extend(alias.name for alias in node.names)
                    for module in modules:
                        if module.startswith('hibernate_sql.'):
                            dependency = module.split('.')[1]
                            with self.subTest(path=path, dependency=dependency):
                                self.assertIn(dependency, allowed)
