"""Real native Wayland text field, separate from the Xwayland editor process."""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

app = Gtk.Application(application_id="im.rime.WaylandTestTarget")


def activate(app):
    window = Gtk.ApplicationWindow(application=app, title="Wayland translation target")
    window.set_default_size(520, 200)
    text = Gtk.TextView()
    second = Gtk.Entry()
    layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    layout.pack_start(text, True, True, 0)
    layout.pack_start(second, False, False, 0)
    window.add(layout)
    xml = """<node><interface name='im.rime.WaylandTestTarget'>
      <method name='Text'><arg type='s' direction='out'/></method>
      <method name='Other'><arg type='s' direction='out'/></method>
      <method name='OtherText'><arg type='s' direction='out'/></method>
      <method name='First'><arg type='s' direction='out'/></method>
      <method name='Seed'><arg type='s' direction='in'/><arg type='i' direction='in'/><arg type='s' direction='out'/></method>
      <method name='Second'><arg type='s' direction='out'/></method>
      <method name='SecondText'><arg type='s' direction='out'/></method>
    </interface></node>"""
    other_text = None
    def method(connection, sender, path, interface, name, args, invocation):
        nonlocal other_text
        if name == "First":
            text.grab_focus()
            invocation.return_value(GLib.Variant("(s)", ("focused",)))
            return
        if name == "OtherText":
            invocation.return_value(GLib.Variant("(s)", (other_text.get_text() if other_text else "",)))
            return
        if name == "Seed":
            value, cursor = args.unpack()
            buffer = text.get_buffer()
            buffer.set_text(value)
            buffer.place_cursor(buffer.get_iter_at_offset(cursor))
            invocation.return_value(GLib.Variant("(s)", ("seeded",)))
            return
        if name in ("Second", "SecondText"):
            if name == "Second":
                second.grab_focus()
            invocation.return_value(GLib.Variant("(s)", (second.get_text(),)))
            return
        if name == "Other":
            other = Gtk.ApplicationWindow(application=app, title="Unrelated text target")
            other.set_default_size(300, 160)
            other_text = Gtk.Entry()
            other.add(other_text)
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
