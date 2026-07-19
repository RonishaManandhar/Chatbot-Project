import ast
import tokenize
from pathlib import Path

from jinja2 import TemplateSyntaxError

from tests.BaseTestCase import BaseTestCase


class AppIntegrityTests(BaseTestCase):

    def test_home_redirects_to_login(self):
        response = self.client.get("/")

        self.assertEqual(
            302,
            response.status_code
        )

        self.assertIn(
            "/login",
            response.headers["Location"]
        )

    def test_required_endpoints_exist(self):
        endpoints = {
            rule.endpoint
            for rule in self.app.url_map.iter_rules()
        }

        required = {
            "auth.login",
            "auth.signup",
            "customer.dashboard",
            "customer.my_profile",
            "agent.dashboard",
            "admin.dashboard",
            "admin.email_logs",
        }

        missing = required - endpoints

        self.assertTrue(
            required.issubset(endpoints),
            f"Missing endpoints: {missing}"
        )

    def test_all_python_files_compile(self):
        project = Path(
            self.app.root_path
        ).parent

        for path in project.rglob("*.py"):
            if (
                "env" in path.parts
                or ".git" in path.parts
                or "__pycache__" in path.parts
            ):
                continue

            with self.subTest(
                path=str(path)
            ):
                # tokenize.open() correctly handles UTF-8 BOM
                # and Python source encoding declarations.
                with tokenize.open(path) as source_file:
                    source = source_file.read()

                ast.parse(
                    source,
                    filename=str(path)
                )

    def test_all_jinja_templates_parse(self):
        templates = (
            Path(self.app.root_path)
            / "templates"
        )

        for path in templates.rglob("*.html"):
            with self.subTest(
                path=str(path)
            ):
                try:
                    content = path.read_text(
                        encoding="utf-8-sig"
                    )

                    self.app.jinja_env.parse(
                        content
                    )

                except TemplateSyntaxError as error:
                    self.fail(
                        f"{path}: {error}"
                    )