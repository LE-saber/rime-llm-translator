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
  <method name="Begin"><arg type="s" direction="in"/><arg type="b" direction="out"/><arg type="s" direction="out"/></method>
  <method name="Restore"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
  <method name="Retarget"><arg type="s" direction="in"/><arg type="b" direction="out"/><arg type="s" direction="out"/></method>
  <method name="Submit"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
  <method name="End"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
  <signal name="TargetLost"><arg type="s"/></signal>
  <signal name="TargetChanged"><arg type="s"/><arg type="s"/></signal>
</interface></node>`;

function isPanel(window) {
    return window && (window.get_gtk_application_id() === 'im.rime.LLMTranslator.Panel' ||
        window.get_wm_class()?.toLowerCase() === 'rime-llm-panel' ||
        window.get_wm_class_instance() === 'rime-llm-panel');
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
            const lease = this._lease;
            if (!lease || !window)
                return;
            if (lease.restoring && window !== lease.window && !isPanel(window)) {
                this._lose();
            } else if (!isPanel(window) && !lease.restoring && !lease.sent) {
                // Wait for the client to enable its actual text widget. Merely
                // focusing an application with no text caret is not a target.
                if (this._settleSource)
                    GLib.source_remove(this._settleSource);
                this._settleSource = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 60, () => {
                    this._settleSource = 0;
                    if (this._lease === lease && global.display.focus_window === window)
                        this._capture(window);
                    return GLib.SOURCE_REMOVE;
                });
            }
        });
        // Changing fields/caret inside one Wayland window need not change the
        // Meta.Window or InputFocus object. The client supplies a fresh text
        // context here. Panel and settings windows are explicitly excluded.
        this._surroundingSignal = Main.inputMethod.connect('surrounding-text-set', () => {
            this._capture(global.display.focus_window);
        });
        this._mapSignal = global.window_manager.connect('map', (_wm, actor) => {
            const window = actor.meta_window;
            if (isPanel(window) && window.get_title() === 'Rime Translator · 长文本') {
                window.make_above();
                Main.activateWindow(window);
                // GTK supplies the X11 utility/skip-taskbar hints, including on
                // Xwayland. Wayland native windows get compositor-level above.
            }
        });
        this._lockSignal = Main.sessionMode.connect('updated', () => {
            if (Main.sessionMode.isLocked)
                this._lose();
        });
    }

    _end() {
        if (this._settleSource) {
            GLib.source_remove(this._settleSource);
            this._settleSource = 0;
        }
        if (this._lease?.destroySignal)
            this._lease.window.disconnect(this._lease.destroySignal);
        this._lease = null;
    }

    _capture(window, ibusConfirmed = false) {
        const lease = this._lease;
        const im = Main.inputMethod;
        if (!lease || lease.restoring || lease.sent || !window || isPanel(window) ||
            Main.overview.visible || Main.modalCount > 0 || Main.sessionMode.isLocked ||
            (!im.currentFocus && !ibusConfirmed))
            return false;
        if (im._purpose === IBus.InputPurpose.PASSWORD || im._purpose === IBus.InputPurpose.PIN) {
            this._lose();
            return false;
        }
        if (lease.destroySignal)
            lease.window.disconnect(lease.destroySignal);
        lease.window = window;
        lease.focus = im.currentFocus;
        lease.surrounding = im.getSurroundingText();
        lease.destroySignal = window.connect('unmanaged', () => this._lose());
        this._object.emit_signal('TargetChanged', new GLib.Variant('(ss)', [lease.token, window.get_title() ?? '']));
        return true;
    }

    _lose() {
        if (this._lease)
            this._object.emit_signal('TargetLost', new GLib.Variant('(s)', [this._lease.token]));
        this._end();
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
            this._lease.destroySignal = window.connect('unmanaged', () => this._lose());
        }
        invocation.return_value(new GLib.Variant('(bs)', [Boolean(valid), valid ? window.get_title() ?? '' : '']));
    }

    RetargetAsync([token], invocation) {
        const valid = this._valid(token, invocation) && this._capture(global.display.focus_window, true);
        invocation.return_value(new GLib.Variant('(bs)', [Boolean(valid), valid ? this._lease.window.get_title() ?? '' : '']));
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
                this._lose();
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
                        this._lose();
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
        this._lose();
        global.display.disconnect(this._focusSignal);
        Main.inputMethod.disconnect(this._surroundingSignal);
        global.window_manager.disconnect(this._mapSignal);
        Main.sessionMode.disconnect(this._lockSignal);
        this._object.unexport();
        Gio.bus_unown_name(this._name);
        this._object = null;
    }
}
