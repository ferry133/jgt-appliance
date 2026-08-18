#!/usr/bin/env python3
"""Check the gate in front of claude-code before anything is rendered.

Every cluster runs a claude-code instance: a root shell with cluster-admin
RBAC that the Cloudflare tunnel exposes to the internet the moment it connects
— no port forward, no firewall change — and whose hostname enters Certificate
Transparency logs as soon as cert-manager issues for it. There is no obscurity
to fall back on, and `replicas: 0` is a posture rather than a control: anything
that scales it up removes it.

Two modes, so two checks:

  Auth0 (the default)   auth0.json must supply the shared application's domain,
                        client_id and client_secret. Absent, the render dies
                        partway through with a traceback; empty, it deploys an
                        oauth2-proxy that cannot start — and OIDC mode gives
                        ttyd no fallback, so that is a terminal nobody reaches.

  claudecode_auth0:     ttyd basic auth is the whole gate, so the credential
  false                 must exist and must not be guessable. Before this
                        check, an unset one rendered an empty --credential and
                        published an unauthenticated shell.

The strength rules live here rather than in cluster.schema.cue because a CUE
constraint prints the offending value in its error message. A check that leaks
the credential into a terminal and a CI log in order to complain about it is
worse than no check, so nothing below ever prints the value — only what is
wrong with it.

Usage: check-claudecode-auth.py [cluster.yaml]
Exit 0 if acceptable, 1 otherwise.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

MIN_PASSWORD = 20

# Names and passwords that show up when someone is "just testing" and then ships.
WEAK = {
    "admin", "administrator", "test", "tester", "user", "demo", "guest",
    "root", "changeme", "password", "passw0rd", "letmein", "secret",
    "123456", "12345678", "qwerty", "claude", "ttyd",
}

AUTH0_FIELDS = ("domain", "client_id", "client_secret")


def yq(expression: str, path: Path) -> str:
    """Read one value via yq rather than by hand-parsing the line.

    The ttyd credential contains a colon by definition, and any line may carry
    an inline comment or quoting. Splitting on the first colon produced a value
    several characters longer than the real one, which silently changes what the
    length check decides — a checker that mis-reads the thing it is checking is
    worse than useless here.
    """
    result = subprocess.run(
        ["yq", "-r", expression, str(path)], capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"could not read {path}: {result.stderr.strip()}")
    return result.stdout.strip()


def auth0_enabled(path: Path) -> bool:
    """Mirrors the render-time default in templates/scripts/plugin.py.

    Read bare, not as `.claudecode_auth0 // true`: yq's alternative operator
    falls through on `false` as well as on null, so the opt-out read back as
    opted in and this checked the wrong mode.
    """
    return yq('.claudecode_auth0', path) != "false"


def check_auth0(config: Path) -> list[str]:
    """Whatever cluster.yaml does not override has to come from auth0.json.

    allowed_emails counts among those: OIDC mode renders the allowlist into a
    ConfigMap, and an absent one fails the render rather than defaulting open.
    """
    from_config = {
        field: yq(f'.claudecode_auth0_{field} // ""', config)
        for field in AUTH0_FIELDS
    }
    emails = yq('.claudecode_allowed_emails // ""', config)
    if all(from_config.values()) and emails:
        return []

    auth0 = config.parent / "auth0.json"
    if not auth0.is_file():
        return [
            "auth0.json not found — claude-code defaults to Auth0 login",
            "copy it from another cluster directory (it is the same shared "
            "Auth0 application everywhere, and gitignored in all of them)",
            "or set `claudecode_auth0: false` in cluster.yaml for ttyd basic auth",
        ]
    try:
        data = json.loads(auth0.read_text())
    except json.JSONDecodeError as e:
        return [f"auth0.json is not valid JSON: {e}"]

    missing = [f for f in AUTH0_FIELDS if not (data.get(f) or from_config[f])]
    if not (data.get("allowed_emails") or emails):
        missing.append("allowed_emails")
    if missing:
        return [f"auth0.json is missing or empty: {', '.join(missing)}"]
    return []


def callback_urls(config: Path) -> list[str]:
    """The Auth0 registrations a render cannot perform on the operator's behalf.

    Rendering succeeds without them and the terminal still fails to open, with
    an Auth0 error page rather than anything pointing back here — so print them
    every time instead of waiting for someone to hit it.
    """
    domain = yq('.cloudflare_domain // ""', config)
    instances = yq('.claude_instances // ["im"] | .[]', config).split()
    if not domain:
        return []
    return [f"https://{i}.{domain}/oauth2/callback" for i in instances]


def credential_problems(credential: str) -> list[str]:
    found: list[str] = []
    user, sep, password = credential.partition(":")
    if not sep:
        return ["not in user:password form"]
    if not user:
        found.append("username is empty")
    elif user.lower() in WEAK:
        found.append(f"username {user!r} is a default that gets guessed first")
    if len(password) < MIN_PASSWORD:
        found.append(f"password is {len(password)} characters, needs {MIN_PASSWORD}")
    lowered = password.lower()
    for weak in sorted(WEAK):
        if weak in lowered:
            found.append(f"password contains {weak!r}")
            break
    if password and re.fullmatch(r"(.)\1*", password):
        found.append("password is a single repeated character")
    return found


def check_basic_auth(config: Path) -> list[str]:
    credential = yq('.ttyd_credential // ""', config)
    if not credential:
        return [
            "claudecode_auth0 is false and ttyd_credential is unset",
            "that renders ttyd with no --credential at all: an unauthenticated "
            "root shell on a public hostname",
        ]
    return credential_problems(credential)


def main() -> int:
    config = Path(sys.argv[1] if len(sys.argv) > 1 else "cluster.yaml")
    if not config.is_file():
        sys.exit(f"not found: {config}")

    auth0 = auth0_enabled(config)
    if auth0:
        label, problems = "claudecode auth (Auth0)", check_auth0(config)
        remedy = []
    else:
        label, problems = "claudecode auth (ttyd basic)", check_basic_auth(config)
        remedy = [
            "Generate one with:",
            "  python3 -c \"import secrets;"
            " print('ops:' + secrets.token_urlsafe(24))\"",
            "then update cluster.yaml and re-run `task configure`.",
        ]

    if problems:
        print(f"FAIL  {label}", file=sys.stderr)
        for problem in problems:
            print(f"        {problem}", file=sys.stderr)
        if remedy:
            print(file=sys.stderr)
            print("      This guards an internet-reachable shell.", file=sys.stderr)
            for line in remedy:
                print(f"      {line}", file=sys.stderr)
        return 1

    print(f"ok    {label}")
    if auth0:
        for url in callback_urls(config):
            print(f"        Auth0 app must allow callback: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
