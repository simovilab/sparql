"""Isolated official-image integration test; no IMDb download or public ports."""

import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[1]
PROJECT = f"sparql-test-{uuid.uuid4().hex[:10]}"


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


with tempfile.TemporaryDirectory(prefix="sparql-test-") as directory:
    temporary = Path(directory)
    data = temporary / "data"
    data.mkdir()
    key = temporary / "ui_secret_key"
    key.write_text(secrets.token_hex(32))
    key.chmod(0o600)
    override = temporary / "compose.test.json"
    override.write_text(json.dumps({
        "services": {
            "qlever": {
                "labels": {"traefik.enable": "false"},
                "healthcheck": {"interval": "3s", "start_period": "10s"},
            },
            "qlever-ui": {
                "labels": {"traefik.enable": "false"},
                "healthcheck": {"interval": "3s", "start_period": "10s"},
            },
        },
        "networks": {
            "traefik_proxy": {"external": False, "name": f"{PROJECT}-proxy"},
        },
        "secrets": {"ui_secret_key": {"file": str(key)}},
    }))
    environment = {
        **os.environ,
        "QLEVER_DATA_DIR": str(data),
        "QLEVER_UID": str(os.getuid()),
        "QLEVER_GID": str(os.getgid()),
        "QLEVER_MEMORY_LIMIT": "2g",
        "QLEVER_MEMORY_FOR_QUERIES": "512M",
        "QLEVER_CACHE_MAX_SIZE": "128M",
        "QLEVER_CACHE_SINGLE_ENTRY": "64M",
        "QLEVER_UI_BACKEND": "imdb",
        "SPARQL_DOMAIN": "sparql.simovi.org",
    }
    compose = [
        "docker", "compose", "--project-name", PROJECT,
        "--env-file", str(ROOT / ".env.example"),
        "-f", str(ROOT / "compose.yaml"), "-f", str(override),
    ]

    def compose_run(*args, **kwargs):
        return run([*compose, *args], env=environment, **kwargs)

    try:
        compose_run("config", "--quiet")
        compose_run("run", "--rm", "qlever-manage", "setup-imdb")
        assert "imdb" in (data / "Qleverfile").read_text()
        # A second setup must refuse to overwrite the existing configuration.
        result = subprocess.run(
            [*compose, "run", "--rm", "qlever-manage", "setup-imdb"],
            env=environment,
        )
        assert result.returncode != 0
        (data / "Qleverfile").write_text(
            "[data]\nNAME = imdb\nDESCRIPTION = Smoke test\nFORMAT = ttl\n"
            "[index]\nINPUT_FILES = imdb.ttl\n"
            "CAT_INPUT_FILES = cat ${INPUT_FILES}\n"
            "PARALLEL_PARSING = false\nTEXT_INDEX = from_literals\n"
            "[runtime]\nSYSTEM = native\n"
        )
        (data / "imdb.ttl").write_text(
            '<https://example.org/movie> <https://www.imdb.com/title> "Test movie" .\n'
        )
        compose_run("run", "--rm", "qlever-manage", "index")
        compose_run("up", "-d", "--wait", "--wait-timeout", "180")
        compose_run("exec", "-T", "qlever-ui", "python", "/deploy/check-ui.py")
        compose_run(
            "exec", "-T", "qlever-ui", "python", "-c",
            "import json, urllib.parse, urllib.request; "
            "url='http://qlever:7001/?'+urllib.parse.urlencode("
            "{'query':'SELECT ?s WHERE { ?s ?p ?o } LIMIT 1'}); "
            "request=urllib.request.Request(url, headers="
            "{'Accept':'application/sparql-results+json'}); "
            "data=json.load(urllib.request.urlopen(request)); "
            "assert data['results']['bindings'][0]['s']['value']"
            " == 'https://example.org/movie'; print('SPARQL query passed')",
        )
        compose_run(
            "exec", "-T", "qlever-ui", "python", "manage.py", "shell", "-c",
            "from django.contrib.staticfiles.storage import staticfiles_storage; "
            "from urllib.request import Request, urlopen; "
            "path=staticfiles_storage.url('/wasm/formatter/index.js'); "
            "request=Request('http://127.0.0.1:7000'+path, "
            "headers={'Host':'sparql.simovi.org'}); "
            "assert urlopen(request).status == 200; "
            "print('Production formatter asset passed')",
        )
        compose_run(
            "exec", "-T", "qlever-ui", "python", "-c",
            """import urllib.parse
import urllib.request
from urllib.error import HTTPError

def rejected(parameters):
    url = "http://qlever:7001/?" + urllib.parse.urlencode(parameters)
    try:
        urllib.request.urlopen(url)
    except HTTPError as error:
        return error.code, error.read().decode()
    raise AssertionError("Restricted request unexpectedly succeeded")

code, body = rejected({"cmd": "clear-cache", "access-token": "imdb"})
assert code == 403, (code, body)
code, body = rejected({"query": "SELECT * WHERE { SERVICE <http://127.0.0.1:7001/> { ?s ?p ?o } }"})
assert "not allowed" in body.lower(), (code, body)
print("Public API restrictions passed")
""",
        )
        checks = (
            "from django.conf import settings; "
            "from django.contrib.auth import get_user_model; "
            "from backend.models import Backend; "
            "assert not settings.DEBUG; "
            "assert settings.SESSION_COOKIE_SECURE; "
            "assert not get_user_model().objects.exclude(username='smoke-admin')"
            ".filter(is_active=True).exists(); "
            "backend=Backend.objects.get(slug='imdb'); "
            "assert backend.baseUrl == 'https://sparql.simovi.org/api'; "
            "assert backend.isDefault; "
            "assert not Backend.objects.exclude(pk=backend.pk).filter(sortKey__gt=0).exists(); "
            "print('UI production configuration passed')"
        )
        compose_run("exec", "-T", "qlever-ui", "python", "manage.py", "shell", "-c", checks)
        compose_run(
            "exec", "-T", "qlever-ui", "python", "manage.py", "shell", "-c",
            "from django.contrib.auth import get_user_model; "
            "get_user_model().objects.create_superuser(username='smoke-admin', "
            "email='smoke@example.invalid', password=None)",
        )
        compose_run("restart", "qlever-ui")
        compose_run("up", "-d", "--wait", "--wait-timeout", "180")
        compose_run("exec", "-T", "qlever-ui", "python", "manage.py", "shell", "-c", checks)
        compose_run(
            "exec", "-T", "qlever-ui", "python", "manage.py", "shell", "-c",
            "from django.contrib.auth import get_user_model; "
            "assert get_user_model().objects.get(username='smoke-admin').is_active; "
            "print('Administrator survives restart')",
        )
        # Exercise the documented custom-data path without a text index.
        compose_run("stop", "qlever-ui", "qlever")
        config = data / "Qleverfile"
        config.write_text(
            config.read_text().replace("NAME = imdb", "NAME = custom")
            .replace("TEXT_INDEX = from_literals", "TEXT_INDEX = none")
        )
        compose_run("run", "--rm", "qlever-manage", "index")
        compose_run("up", "-d", "--wait", "--wait-timeout", "180")
        compose_run("exec", "-T", "qlever-ui", "python", "/deploy/check-ui.py")
        print("Smoke test passed.")
    except BaseException:
        subprocess.run([*compose, "logs", "--tail", "100"], env=environment)
        raise
    finally:
        compose_run("--profile", "tools", "down", "--volumes", "--remove-orphans")
