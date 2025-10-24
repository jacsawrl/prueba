#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
logout_to_greeter.py

Intenta cerrar la sesión del usuario y volver a la pantalla de login (greeter)
usando varios métodos, ordenados de menos a más intrusivos.
Requiere --execute para realizar acciones reales (por seguridad).

Usar solo en sistemas donde tengas permiso.
"""

import os
import sys
import shutil
import subprocess
import getpass
import time

def cmd_exists(cmd):
    return shutil.which(cmd) is not None

def run_cmd_list(cmd_list, capture_output=False):
    try:
        if capture_output:
            proc = subprocess.run(cmd_list, capture_output=True, text=True)
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        else:
            proc = subprocess.run(cmd_list)
            return proc.returncode, "", ""
    except Exception as e:
        return 1, "", str(e)

def run_shell(cmd, capture_output=False):
    # fallback: run through shell (used only if needed)
    try:
        if capture_output:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        else:
            proc = subprocess.run(cmd, shell=True)
            return proc.returncode, "", ""
    except Exception as e:
        return 1, "", str(e)

def get_current_user():
    return getpass.getuser()

def get_xdg_session_id():
    return os.environ.get("XDG_SESSION_ID") or os.environ.get("WAYLAND_DISPLAY")

def find_session_for_uid(uid):
    """Intenta encontrar sesión asociada al UID usando loginctl (si está disponible)."""
    if not cmd_exists("loginctl"):
        return None
    rc, out, err = run_shell("loginctl list-sessions --no-legend", capture_output=True)
    if rc != 0 or not out:
        return None
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        session = parts[0]
        rc2, out2, err2 = run_shell(f"loginctl show-session {session} -p User --no-pager", capture_output=True)
        if rc2 != 0 or not out2:
            continue
        for l in out2.splitlines():
            if l.startswith("User="):
                val = l.split("=",1)[1].strip()
                if val == str(uid):
                    return session
    return None

def try_dm_tool_switch():
    # LightDM: dm-tool switch-to-greeter (no root)
    if cmd_exists("dm-tool"):
        return ["dm-tool", "switch-to-greeter"]
    return None

def try_gnome_session_quit():
    # GNOME: gnome-session-quit --logout --no-prompt (tries to logout cleanly)
    if cmd_exists("gnome-session-quit"):
        return ["gnome-session-quit", "--logout", "--no-prompt"]
    return None

def try_loginctl_terminate_session(xdg_session):
    # loginctl terminate-session <id>  (may not require root if user owns session)
    if cmd_exists("loginctl") and xdg_session:
        return ["loginctl", "terminate-session", str(xdg_session)]
    return None

def try_loginctl_found_session(uid):
    if not cmd_exists("loginctl"):
        return None
    session = find_session_for_uid(uid)
    if session:
        return ["loginctl", "terminate-session", session]
    return None

def try_loginctl_terminate_user(user):
    # more aggressive: terminate-user (kills all processes of user)
    if cmd_exists("loginctl"):
        return ["loginctl", "terminate-user", user]
    return None

def try_kill_user_pkill(user):
    # very aggressive: pkill -KILL -u user
    if cmd_exists("pkill"):
        return ["pkill", "-KILL", "-u", user]
    return None

def try_systemctl_restart_via_pkexec(dm_service):
    # attempt to restart DM via pkexec (will open auth dialog in GUI)
    # dm_service e.g. 'gdm', 'sddm', 'lightdm'
    if cmd_exists("pkexec") and cmd_exists("systemctl"):
        return ["pkexec", "systemctl", "restart", dm_service]
    return None

def best_guess_dm():
    # heurística simple para adivinar display manager / entorno
    # Prioriza variables de entorno y existencia de binarios
    env = os.environ.get("XDG_CURRENT_DESKTOP", "") + " " + os.environ.get("DESKTOP_SESSION", "") + " " + os.environ.get("XDG_SESSION_DESKTOP", "")
    env = env.lower()
    if "gnome" in env or cmd_exists("gdm") or cmd_exists("gdm3"):
        return "gdm"
    if "kde" in env or cmd_exists("sddm"):
        return "sddm"
    if "xfce" in env or cmd_exists("lightdm"):
        return "lightdm"
    # fallback: check common binaries
    if cmd_exists("gdm") or cmd_exists("gdm3"):
        return "gdm"
    if cmd_exists("sddm"):
        return "sddm"
    if cmd_exists("lightdm") or cmd_exists("dm-tool"):
        return "lightdm"
    return None

def attempt_method(cmd_list, description, capture_output=False, allow_wait=True):
    print(f"[>] Intentando: {description} -> {' '.join(cmd_list)}")
    rc, out, err = run_cmd_list(cmd_list, capture_output=capture_output)
    if rc == 0:
        print(f"[+] OK: {description}")
        if capture_output:
            if out:
                print(out)
            if err:
                print("stderr:", err)
        # darle un pequeño tiempo para que el display manager responda antes de terminar el script
        if allow_wait:
            time.sleep(2)
        return True
    else:
        # algunos comandos, especialmente logout, devuelven rc != 0 aunque inicien proceso de logout.
        # mostramos stderr para diagnóstico.
        if capture_output:
            print(f"[-] Falló (rc={rc}). stdout: {out} stderr: {err}")
        else:
            print(f"[-] Falló (rc={rc}).")
        return False

def main():
    if "--execute" not in sys.argv:
        print("Por seguridad este script requiere --execute para realizar acciones reales.")
        print("Ejemplo: python3 logout_to_greeter.py --execute")
        sys.exit(1)

    user = get_current_user()
    uid = os.getuid()
    xdg_session = get_xdg_session_id()
    guessed_dm = best_guess_dm()

    print(f"[i] Usuario detectado: {user} (uid {uid})")
    if xdg_session:
        print(f"[i] XDG_SESSION_ID / WAYLAND_DISPLAY detectado: {xdg_session}")
    if guessed_dm:
        print(f"[i] Display manager sugerido: {guessed_dm}")
    else:
        print("[i] No se pudo determinar claramente el display manager.")

    # Lista de métodos por orden preferente
    methods = []

    # 1) dm-tool switch-to-greeter (LightDM) - no root
    m = try_dm_tool_switch()
    if m:
        methods.append((m, "dm-tool switch-to-greeter (LightDM greeter)"))

    # 2) gnome-session-quit --logout --no-prompt (intento limpio para GNOME)
    m = try_gnome_session_quit()
    if m:
        methods.append((m, "gnome-session-quit --logout --no-prompt (GNOME safe logout)"))

    # 3) loginctl terminate-session XDG_SESSION_ID (systemd way) - suele funcionar en muchos DMs
    m = try_loginctl_terminate_session(xdg_session)
    if m:
        methods.append((m, "loginctl terminate-session <XDG_SESSION_ID> (systemd)"))

    # 4) loginctl terminate-session <found session by UID>
    m = try_loginctl_found_session(uid)
    if m:
        methods.append((m, "loginctl terminate-session <session found by UID> (systemd)"))

    # 5) loginctl terminate-user (agresivo)
    m = try_loginctl_terminate_user(user)
    if m:
        methods.append((m, "loginctl terminate-user <user> (kills all user processes)"))

    # 6) pkill -KILL -u user (muy agresivo)
    m = try_kill_user_pkill(user)
    if m:
        methods.append((m, "pkill -KILL -u <user> (muy drástico)"))

    # 7) commandos para reiniciar el DM via pkexec (necesitarán auth GUI)
    # Solo añadimos el comando apropiado si conocemos el DM o si los binarios existen.
    dm = guessed_dm
    if dm is None:
        # probar varios servicios si no sabemos cuál hay
        for svc in ("gdm", "gdm3", "sddm", "lightdm"):
            cmd = try_systemctl_restart_via_pkexec(svc)
            if cmd:
                methods.append((cmd, f"pkexec systemctl restart {svc} (reinicia el display manager, requerirá autenticación)"))
    else:
        cmd = try_systemctl_restart_via_pkexec(dm)
        if cmd:
            methods.append((cmd, f"pkexec systemctl restart {dm} (reinicia el display manager, requerirá autenticación)"))

    if not methods:
        print("[-] No se detectó ningún método disponible en este sistema para volver al greeter.")
        print("    Comprobaciones realizadas: dm-tool, gnome-session-quit, loginctl, pkill, pkexec/systemctl.")
        sys.exit(2)

    # Ejecutar métodos en orden hasta que uno funcione
    for cmd_list, desc in methods:
        # métodos que no devuelven salida útil al captura a veces rompen; intentamos sin capture en primera instancia.
        # Para los que sabemos pueden dar salida, usamos capture_output para diagnosticar.
        capture = True if ("loginctl" in desc or "pkexec" in desc) else False
        ok = attempt_method(cmd_list, desc, capture_output=capture)
        # Si el método fue exitoso, salimos del script. Aunque el logout real normalmente terminará este proceso,
        # en algunos entornos el proceso continúa y por eso hacemos sys.exit(0).
        if ok:
            print("[i] Si todo fue correcto, deberías ver ahora la pantalla de inicio de sesión (greeter).")
            sys.exit(0)
        else:
            # esperar un poco antes de intentar el siguiente (evita spam)
            time.sleep(1)

    print("[-] Ningún método tuvo éxito. Revisa permisos, si hay autenticación necesaria o bloqueos por antivirus/VirtualBox.")
    print("Sugerencias:")
    print(" - Prueba ejecutar desde una terminal dentro de la sesión y ver mensajes de error.")
    print(" - Si el comando requiere reiniciar el display manager (pkexec/systemctl), se te pedirá autenticación gráfica.")
    print(" - En VirtualBox confirma que el guest additions / drivers gráficos están funcionando correctamente.")
    sys.exit(3)

if __name__ == "__main__":
    main()
