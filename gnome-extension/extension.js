// GNOME 46: shared Wayland IBus contexts cannot identify the destination window.
// Check and commit inside the compositor, without clipboard or synthetic keys.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import IBus from 'gi://IBus';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const NAME = 'im.rime.LLMTranslator.Shell';
const PATH = '/im/rime/LLMTranslator/Shell';
const XML = `<node><interface name="${NAME}">
  <method name="Begin"><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
  <method name="Restore"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
  <method name="Submit"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
  <method name="End"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
</interface></node>`;

function isPanel(window) {
    return window && (window.get_gtk_application_id() === 'im.rime.LLMTranslator.Panel' ||
        window.get_wm_class() === 'rime-llm-panel');
}

export default class RimeTranslator extends Extension {
    enable() {
        this._lease = null;
        this._object = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._object.export(Gio.DBus.session, PATH);
        this._name = Gio.bus_own_name_on_connection(Gio.DBus.session, NAME,
            Gio.BusNameOwnerFlags.NONE, null, null);
        this._focusSignal = global.display.connect('notify::focus-window', () => {
            const window = global.display.focus_window;
            if (this._lease && window && window !== this._lease.window && !isPanel(window))
                this._end();
        });
        this._mapSignal = global.window_manager.connect('map', (_wm, actor) => {
            const window = actor.meta_window;
            if (isPanel(window) && window.get_title() === 'Rime Translator · 长文本') {
                window.make_above();
                // GTK supplies the X11 utility/skip-taskbar hints, including on
                // Xwayland. Wayland native windows get compositor-level above.
            }
        });
        this._lockSignal = Main.sessionMode.connect('updated', () => {
            if (Main.sessionMode.isLocked)
                this._end();
        });
    }

    _end() {
        if (this._lease?.destroySignal)
            this._lease.window.disconnect(this._lease.destroySignal);
        this._lease = null;
    }

    _valid(token, invocation) {
        return this._lease && this._lease.token === token &&
            this._lease.owner === invocation.get_sender() && !Main.sessionMode.isLocked;
    }

    BeginAsync([token], invocation) {
        // Only the actual IBus bridge owner may create a lease. A public bus
        // method must not become an arbitrary cross-application typing API.
        let owner = null;
        try {
            [owner] = Gio.DBus.session.call_sync('org.freedesktop.DBus',
                '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'GetNameOwner',
                new GLib.Variant('(s)', ['im.rime.LLMTranslator.Bridge']),
                null, Gio.DBusCallFlags.NONE, 1000, null).deepUnpack();
        } catch (_) { /* No live frontend. */ }
        const window = global.display.focus_window;
        const valid = owner === invocation.get_sender() && token.length === 36 &&
            window && !isPanel(window) && !Main.overview.visible && !Main.sessionMode.isLocked;
        if (valid) {
            this._end();
            this._lease = {token, owner, window, focus: Main.inputMethod.currentFocus,
                surrounding: Main.inputMethod.getSurroundingText(), sent: false, restoring: false};
            this._lease.destroySignal = window.connect('unmanaged', () => this._end());
        }
        invocation.return_value(new GLib.Variant('(b)', [Boolean(valid)]));
    }

    RestoreAsync([token], invocation) {
        let status = 'cancelled';
        if (this._valid(token, invocation)) {
            const window = global.display.focus_window;
            if (!window || window === this._lease.window || isPanel(window)) {
                this._lease.restoring = true;
                this._lease.deadline = GLib.get_monotonic_time() + 8000000;
                Main.activateWindow(this._lease.window);
                status = 'waiting';
            } else {
                this._end();
            }
        }
        invocation.return_value(new GLib.Variant('(s)', [status]));
    }

    SubmitAsync([token, text], invocation) {
        let status = 'cancelled';
        if (this._valid(token, invocation)) {
            const lease = this._lease;
            const im = Main.inputMethod;
            if (lease.sent) {
                status = 'sent'; // A lost reply must never duplicate text.
            } else if (lease.restoring && GLib.get_monotonic_time() < lease.deadline) {
                status = 'waiting';
                if (global.display.focus_window === lease.window && im.currentFocus) {
                    const purpose = im._purpose;
                    const surrounding = im.getSurroundingText();
                    // Refuse a changed widget/caret when surrounding text is
                    // available. Never store these strings on disk or log them.
                    const changed = lease.surrounding[0] != null && surrounding[0] != null &&
                        JSON.stringify(lease.surrounding) !== JSON.stringify(surrounding);
                    if ((lease.focus && im.currentFocus !== lease.focus) || changed ||
                        purpose === IBus.InputPurpose.PASSWORD || purpose === IBus.InputPurpose.PIN ||
                        !text || new TextEncoder().encode(text).length > 262144) {
                        status = 'cancelled';
                        this._end();
                    } else {
                        im.commit(text);
                        lease.sent = true;
                        status = 'sent';
                    }
                }
            }
        }
        invocation.return_value(new GLib.Variant('(s)', [status]));
    }

    EndAsync([token], invocation) {
        if (this._valid(token, invocation))
            this._end();
        invocation.return_value(new GLib.Variant('(s)', ['closed']));
    }

    disable() {
        this._end();
        global.display.disconnect(this._focusSignal);
        global.window_manager.disconnect(this._mapSignal);
        Main.sessionMode.disconnect(this._lockSignal);
        this._object.unexport();
        Gio.bus_unown_name(this._name);
        this._object = null;
    }
}
