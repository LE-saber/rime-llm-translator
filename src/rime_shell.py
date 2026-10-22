"""Per-user GNOME 46 bridge installation; never change other extensions."""
import os
from pathlib import Path
import shutil
import subprocess

UUID = "rime-llm-translator@le-saber"
SOURCE = Path("/usr/share/rime-llm-translator/gnome-extension")


def install():
    if not SOURCE.is_dir():
        return
    destination = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "gnome-shell/extensions" / UUID
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("metadata.json", "extension.js"):
        shutil.copy2(SOURCE / name, destination / name)
    if "gnome" not in os.environ.get("XDG_CURRENT_DESKTOP", "").lower():
        return
    from gi.repository import Gio
    schemas = Gio.SettingsSchemaSource.get_default()
    if not schemas or not schemas.lookup("org.gnome.shell", True):
        return
    settings = Gio.Settings.new("org.gnome.shell")
    enabled = list(settings.get_strv("enabled-extensions"))
    if UUID not in enabled:
        settings.set_strv("enabled-extensions", enabled + [UUID])
    disabled = list(settings.get_strv("disabled-extensions"))
    if UUID in disabled:
        settings.set_strv("disabled-extensions", [item for item in disabled if item != UUID])
    Gio.Settings.sync()
    if shutil.which("gnome-extensions"):
        subprocess.run(["gnome-extensions", "enable", UUID], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("GNOME floating-panel bridge installed. Log out/in to load this version.")
    if settings.get_boolean("disable-user-extensions"):
        print("User extensions are disabled globally. Enable extensions in GNOME Extensions, then log out/in.")


def status():
    try:
        from gi.repository import Gio, GLib
        reply = Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner",
            GLib.Variant("(s)", ("im.rime.LLMTranslator.Shell",)), None,
            Gio.DBusCallFlags.NONE, 1000, None)
        return "active" if reply.unpack()[0] else "inactive (sync + enable, then log out/in)"
    except (ImportError, RuntimeError) as exc:
        return "unavailable: " + str(exc)
    except Exception:
        return "inactive (no desktop session bus)"
