#!/usr/bin/env python3
"""
logout_universal.py

Script para intentar cerrar la sesión del usuario actual en Linux usando
varios métodos (GNOME, systemd/logind, pkill). Por seguridad, POR DEFECTO
es un dry-run: muestra lo que haría. Use --execute para que realice la acción.

Usar solo en sistemas en los que tengas permiso.
"""

import os
import shutil
import subprocess
import getpass
import argparse
import sys

def cmd_exists(name):
    return shutil.which(name) is not None

def run(cmd, check=False):
    """Ejecuta comando; devuelve (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def get_current_user():
    return getpass.getuser()

def get_xdg_session_id():
    return os.environ.get("XDG_SESSION_ID")

def find_session_for_uid(uid):
    # intenta mapear la sesión actual usando loginctl (si disponible)
    if not cmd_exists("loginctl"):
        return None
    rc, out, err = run("loginctl list-sessions --no-legend")
    if rc != 0:
        return None
    # líneas: "  2 user1  seat0   1.2.3.4"
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        session = parts[0]
        try:
            # obtener UID de la sesión
            rc2, out2, err2 = run(f"loginctl show-session {session} -p Remote -p Name -p Display -p State -p Id -p User --no-pager")
            # prefijado: "User=1000"
            for l in out2.splitlines():
                if l.startswith("User="):
                    uid_line = l.split("=",1)[1].strip()
                    if uid_line == str(uid):
                        return session
        except Exception:
            continue
    return None

def gnome_logout_command():
    # comando estándar para GNOME
    return "gnome-session-quit --logout --no-prompt"

def loginctl_terminate_session_command(session):
    return f"loginctl terminate-session {session}"

def loginctl_terminate_user_command(user):
    return f"loginctl terminate-user {user}"

def pkill_kill_user_command(user):
    return f"pkill -KILL -u {user}"

def choose_method_dryrun():
    user = get_current_user()
    xdg = get_xdg_session_id()
    methods = []

    # método GNOME (si existe binario y hay DISPLAY)
    if cmd_exists("gnome-session-quit") and ("DISPLAY" in os.environ or "WAYLAND_DISPLAY" in os.environ):
        methods.append(("gnome", gnome_logout_command()))

    # systemd/logind method using XDG_SESSION_ID first
    if cmd_exists("loginctl"):
        if xdg:
            methods.append(("loginctl_session_xdg", loginctl_terminate_session_command(xdg)))
        # intentar encontrar sesión por UID
        try:
            uid = os.getuid()
            session = find_session_for_uid(uid)
            if session:
                methods.append(("loginctl_session_found", loginctl_terminate_session_command(session)))
        except Exception:
            pass
        # terminate-user (agresivo)
        methods.append(("loginctl_terminate_user", loginctl_terminate_user_command(user)))

    # pkill (último recurso)
    if cmd_exists("pkill"):
        methods.append(("pkill_kill_user", pkill_kill_user_command(user)))

    return methods

def perform_method(method_cmd):
    rc, out, err = run(method_cmd)
    return rc, out, err

def main():
    parser = argparse.ArgumentParser(description="Cerrar sesión de usuario (modo por defecto: simulación). Usar --execute para realmente cerrar la sesión.")
    parser.add_argument("--execute", action="store_true", help="Ejecuta el método seleccionado en lugar de simular.")
    parser.add_argument("--force-method", choices=["gnome","loginctl_session_xdg","loginctl_session_found","loginctl_terminate_user","pkill_kill_user"], help="Forzar un método concreto (opcional).")
    args = parser.parse_args()

    user = get_current_user()
    print(f"[+] Usuario detectado: {user}")
    xdg = get_xdg_session_id()
    if xdg:
        print(f"[+] XDG_SESSION_ID = {xdg}")

    methods = choose_method_dryrun()

    if args.force_method:
        # filtrar por la clave solicitada
        methods = [m for m in methods if m[0] == args.force_method]
        if not methods:
            print(f"[-] Método solicitado '{args.force_method}' no disponible en este sistema.")
            sys.exit(2)

    if not methods:
        print("[-] No se detectó ningún método disponible para cerrar sesión en este sistema.")
        print("    Comandos disponibles comprobados: gnome-session-quit, loginctl, pkill.")
        sys.exit(3)

    print("\n[+] Métodos detectados (ordenados por preferencia):")
    for key, cmd in methods:
        print(f"    - {key}: {cmd}")

    if not args.execute:
        print("\n[!] MODO SIMULACIÓN: no se hizo ningún cambio real.")
        print("    Para ejecutar realmente uno de los métodos, vuelve a ejecutar con la opción --execute.")
        print("    Si deseas forzar un método en particular usa --force-method <nombre>.")
        sys.exit(0)

    # En execute: intentamos cada método en orden hasta que uno funcione
    print("\n[!] Ejecutando (modo real) — ten cuidado, esto cerrará la sesión si tiene éxito.")
    for key, cmd in methods:
        print(f"[>] Intentando método {key}: {cmd}")
        rc, out, err = perform_method(cmd)
        if rc == 0:
            print(f"[+] Método '{key}' ejecutado con éxito. Resultado:\n{out}")
            # Si el logout se inició, lo mas probable es que el proceso actual termine; salir del script.
            sys.exit(0)
        else:
            print(f"[-] Método '{key}' falló (rc={rc}). stderr:\n{err}")
    print("[-] Ningún método tuvo éxito. Revisa permisos y comandos disponibles.")
    sys.exit(4)

if __name__ == "__main__":
    main()
