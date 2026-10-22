"""Real native Wayland text field, separate from the Xwayland editor process."""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

app = Gtk.Application(application_id="im.rime.WaylandTestTarget")


def activate(app):
    window = Gtk.ApplicationWindow(application=app, title="Wayland translation target")
    window.set_default_size(520, 200)
    text = Gtk.TextView()
    window.add(text)
    xml = """<node><interface name='im.rime.WaylandTestTarget'>
      <method name='Text'><arg type='s' direction='out'/></method>
      <method name='Other'><arg type='s' direction='out'/></method>
    </interface></node>"""
    def method(connection, sender, path, interface, name, args, invocation):
        if name == "Other":
            other = Gtk.ApplicationWindow(application=app, title="Unrelated text target")
            other.set_default_size(300, 160)
            other.add(Gtk.Entry())
            other.show_all()
            invocation.return_value(GLib.Variant("(s)", ("opened",)))
            return
        buffer = text.get_buffer()
        invocation.return_value(GLib.Variant("(s)", (
            buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True),)))
    info = Gio.DBusNodeInfo.new_for_xml(xml)
    app.get_dbus_connection().register_object("/im/rime/WaylandTestTarget", info.interfaces[0], method, None, None)
    window.show_all()
    text.grab_focus()


app.connect("activate", activate)
app.run([])
