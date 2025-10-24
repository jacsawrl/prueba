#!/usr/bin/env python3
"""
logout_universal.py

Cierra la sesión del usuario actual intentando varios métodos.
Diseñado para ser ejecutado desde un .desktop con --execute (doble click).

Usar solo en sistemas donde tengas permiso.
"""

import os
import shutil
import subprocess
import getpass
import sys

def cmd_exists(name):
    return shutil.which(name) is not None

def run(cmd):
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def get_current_user():
    return getpass.getuser()

def get_xdg_session_id():
    return os.environ.get("XDG_SESSION_ID") or os.environ.get("WAYLAND_DISPLAY")

def find_session_for_uid(uid):
    if not cmd_exists("loginctl"):
        return None
    rc, out, err = run("loginctl list-sessions --no-legend")
    if rc != 0 or not out:
        return None
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        session = parts[0]
        rc2, out2, err2 = run(f"loginctl show-session {session} -p User --no-pager")
        if rc2 != 0 or not out2:
            continue
        for l in out2.splitlines():
            if l.startswith("User="):
                val = l.split("=",1)[1].strip()
                if val == str(uid):
                    return session
    return None

def try_gnome():
    if cmd_exists("gnome-session-quit") and ("DISPLAY" in os.environ or "WAYLAND_DISPLAY" in os.environ):
        return "gnome-session-quit --logout --no-prompt"
    return None

def try_loginctl_session(xdg):
    if cmd_exists("loginctl") and xdg:
        return f"loginctl terminate-session {xdg}"
    return None

def try_loginctl_found(uid):
    if not cmd_exists("loginctl"):
        return None
    session = find_session_for_uid(uid)
    if session:
        return f"loginctl terminate-session {session}"
    return None

def try_loginctl_terminate_user(user):
    if cmd_exists("loginctl"):
        return f"loginctl terminate-user {user}"
    return None

def try_pkill(user):
    if cmd_exists("pkill"):
        return f"pkill -KILL -u {user}"
    return None

def main():
    # Si no pasas --execute aborta: protección ante doble clic accidental.
    if "--execute" not in sys.argv:
        print("Este script requiere el flag --execute para realizar el logout.")
        print("Por seguridad, se debe usar el .desktop que llame al script con --execute.")
        sys.exit(1)

    user = get_current_user()
    uid = os.getuid()
    xdg = os.environ.get("XDG_SESSION_ID")

    methods = []
    g = try_gnome()
    if g:
        methods.append(("gnome", g))
    s1 = try_loginctl_session(xdg)
    if s1:
        methods.append(("loginctl_session_xdg", s1))
    s2 = try_loginctl_found(uid)
    if s2:
        methods.append(("loginctl_session_found", s2))
    s3 = try_loginctl_terminate_user(user)
    if s3:
        methods.append(("loginctl_terminate_user", s3))
    p = try_pkill(user)
    if p:
        methods.append(("pkill_kill_user", p))

    if not methods:
        print("No se detectaron métodos disponibles para cerrar sesión en este sistema.")
        sys.exit(2)

    for key, cmd in methods:
        print(f"Intentando método {key}: {cmd}")
        rc, out, err = run(cmd)
        if rc == 0:
            print(f"Método '{key}' ejecutado con éxito. El sistema debería volver a la pantalla de login.")
            # Es probable que el proceso actual sea terminado por el logout; sólo salimos.
            sys.exit(0)
        else:
            print(f"Fallo en método '{key}' (rc={rc}). stderr: {err}")

    print("Ningún método fue exitoso. Revisa permisos o ejecuta desde terminal para más información.")
    sys.exit(3)

if __name__ == "__main__":
    main()
