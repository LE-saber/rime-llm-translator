/* The IBus thread owns target identity and submission. No simulated keys/paste. */
#include "rime_panel.h"
#include <glib/gstdio.h>
#include <rime_api.h>
#include <sys/stat.h>
#include <string.h>
extern RimeApi* rime_api;
extern RimeSessionId rime_engine_session(IBusEngine* engine);

#define BRIDGE "im.rime.LLMTranslator.Bridge"
#define PATH "/im/rime/LLMTranslator/Bridge"
static GDBusConnection* connection;
static IBusBus* ibus;
static guint focus_epoch;
static IBusEngine* focused;
static gchar *focus_id, *focus_client, *target_id, *token, *peer, *pending;
static const gchar* status = "closed";
static gint64 expires;
static gint64 alt_down, alt_last;
static guint alt_count;

static void cancel(void) {
  g_clear_pointer(&pending, g_free);
  status = "cancelled";
}

static gboolean submit(gpointer unused) {
  if (!pending) return G_SOURCE_CONTINUE;
  if (g_get_monotonic_time() > expires) {
    g_clear_pointer(&pending, g_free);
    status = "expired";
  } else if (focused && !g_strcmp0(focus_id, target_id)) {
    /* Initial IBus FocusId discovery is asynchronous. Require a confirmed
       FocusInId after the editor yields focus, never submit using a guess. */
    if (!g_strcmp0(focus_client, "unknown")) return G_SOURCE_CONTINUE;
    if (!g_strcmp0(focus_client, "gnome-shell") || !g_strcmp0(focus_client, "fake")) {
      cancel(); status = "unsupported";
      return G_SOURCE_CONTINUE;
    }
    guint purpose = 0, hints = 0;
    ibus_engine_get_content_type(focused, &purpose, &hints);
    if (purpose == IBUS_INPUT_PURPOSE_PASSWORD || purpose == IBUS_INPUT_PURPOSE_PIN) {
      cancel();
      return G_SOURCE_CONTINUE;
    }
    ibus_engine_commit_text(focused, ibus_text_new_from_string(pending));
    g_clear_pointer(&pending, g_free);
    status = "sent";
  }
  return G_SOURCE_CONTINUE;
}

void rime_panel_focus(IBusEngine* engine, const char* context, const char* client) {
  ++focus_epoch;
  focused = engine;
  g_free(focus_id); focus_id = g_strdup(context);
  g_free(focus_client); focus_client = g_strdup(client);
  alt_count = 0; alt_down = 0; alt_last = 0;
  /* Never submit into an unrelated context, even if the user returns later. */
  if (pending && g_strcmp0(target_id, context) &&
      !g_str_has_suffix(client, ":rime-llm-panel")) cancel();
}

void rime_panel_blur(IBusEngine* engine) {
  ++focus_epoch;
  if (focused == engine) focused = NULL;
  alt_count = 0; alt_down = 0;
}

typedef struct { IBusEngine* engine; guint epoch; } InitialFocus;
static void initial_focus_ready(GObject* object, GAsyncResult* result, gpointer data) {
  InitialFocus* initial = data;
  GError* error = NULL;
  gchar* id = ibus_bus_current_input_context_async_finish(IBUS_BUS(object), result, &error);
  if (id && initial->epoch == focus_epoch && focused == initial->engine) {
    g_free(focus_id); focus_id = g_strdup(id);
  }
  g_free(id); g_clear_error(&error);
  g_object_unref(initial->engine); g_free(initial);
}

void rime_panel_legacy_focus(IBusEngine* engine) {
  if (!ibus || (focused == engine && focus_id)) return;
  ++focus_epoch;
  focused = engine;
  g_clear_pointer(&focus_id, g_free);
  g_free(focus_client); focus_client = g_strdup("unknown");
  InitialFocus* initial = g_new0(InitialFocus, 1);
  initial->engine = g_object_ref(engine); initial->epoch = focus_epoch;
  ibus_bus_current_input_context_async(ibus, 1000, NULL, initial_focus_ready, initial);
}

void rime_panel_destroy(IBusEngine* engine) {
  rime_panel_blur(engine);
}

void rime_panel_open(IBusEngine* engine) {
  if (!connection || !focused || !focus_id ||
      g_str_has_suffix(focus_client, ":rime-llm-panel")) return;
  guint purpose = 0, hints = 0;
  ibus_engine_get_content_type(engine, &purpose, &hints);
  if (purpose == IBUS_INPUT_PURPOSE_PASSWORD || purpose == IBUS_INPUT_PURPOSE_PIN) return;
  cancel();
  g_free(target_id); target_id = g_strdup(focus_id);
  g_free(token); token = g_uuid_string_random();
  g_clear_pointer(&peer, g_free);
  /* Generic shell contexts are shared across foreign applications on Wayland. */
  status = (!g_strcmp0(focus_client, "gnome-shell") || !g_strcmp0(focus_client, "fake"))
           ? "unsupported" : "editing";
  RimeSessionId session = rime_engine_session(engine);
  RIME_STRUCT(RimeContext, ctx);
  const char* seed = "";
  if (rime_api->get_context(session, &ctx)) {
    int i = ctx.menu.highlighted_candidate_index;
    if (ctx.composition.length && i >= 0 && i < ctx.menu.num_candidates)
      seed = ctx.menu.candidates[i].text;
  }
  gchar* directory = g_build_filename(g_get_home_dir(), ".cache", "rime-llm-translator", NULL);
  g_mkdir_with_parents(directory, 0700);
  gchar* file = g_build_filename(directory, "panel-open", NULL);
  gchar* body = g_strconcat(token, "\n", seed, NULL);
  /* Private and atomic, never put composed user text in process arguments. */
  gchar* temporary = g_strconcat(file, ".tmp", NULL);
  g_file_set_contents_full(temporary, body, -1, G_FILE_SET_CONTENTS_CONSISTENT, 0600, NULL);
  g_rename(temporary, file);
  g_free(temporary); g_free(body); g_free(file); g_free(directory);
  rime_api->free_context(&ctx);
  rime_api->clear_composition(session);
  ibus_engine_hide_preedit_text(engine);
  ibus_engine_hide_lookup_table(engine);
  gchar* argv[] = {"/usr/bin/rime-llm-translator", "panel", token, NULL};
  GError* error = NULL;
  if (!g_spawn_async(NULL, argv, NULL, G_SPAWN_DEFAULT, NULL, NULL, NULL, &error)) {
    status = "failed";
    g_warning("Cannot start long-text editor: %s", error->message);
    g_error_free(error);
  }
}

gboolean rime_panel_key(IBusEngine* engine, guint keyval, guint state) {
  if (keyval == IBUS_KEY_space && (state & IBUS_CONTROL_MASK) && g_getenv("RIME_LLM_TEST_DIAGNOSTICS"))
    g_printerr("Panel chord: focused=%d client=%s state=%u\n", focused != NULL,
               focus_client ? focus_client : "none", state);
  if (!focused || g_str_has_suffix(focus_client ? focus_client : "", ":rime-llm-panel"))
    return FALSE;
  GKeyFile* cfg = g_key_file_new();
  gchar* path = g_build_filename(g_get_home_dir(), ".config", "rime-llm-translator", "config.ini", NULL);
  g_key_file_load_from_file(cfg, path, G_KEY_FILE_NONE, NULL);
  gchar* binding = g_key_file_get_string(cfg, "panel", "open_hotkey", NULL);
  if (!binding) binding = g_strdup("Alt+space");
  gboolean match = FALSE;
  guint mods = state & (IBUS_CONTROL_MASK | IBUS_SHIFT_MASK | IBUS_MOD1_MASK | IBUS_SUPER_MASK);
  if (!strcmp(binding, "DoubleAlt") || !strcmp(binding, "TripleAlt")) {
    gint64 now = g_get_monotonic_time();
    gboolean is_alt = keyval == IBUS_KEY_Alt_L || keyval == IBUS_KEY_Alt_R;
    if (!is_alt || (mods & ~IBUS_MOD1_MASK)) { alt_count = 0; alt_down = 0; }
    else if (!(state & IBUS_RELEASE_MASK)) {
      if (alt_down) { alt_count = 0; alt_down = -1; }
      else alt_down = now;
    } else {
      if (alt_down > 0 && now - alt_down < 400000) {
        alt_count = now - alt_last < 400000 ? alt_count + 1 : 1;
        alt_last = now;
        match = alt_count == (!strcmp(binding, "DoubleAlt") ? 2u : 3u);
      } else alt_count = 0;
      alt_down = 0;
    }
  } else if (!(state & IBUS_RELEASE_MASK)) {
    gchar** parts = g_strsplit(binding, "+", -1);
    guint expected = 0, key = 0;
    for (int i = 0; parts[i]; ++i) {
      if (!strcmp(parts[i], "Control")) expected |= IBUS_CONTROL_MASK;
      else if (!strcmp(parts[i], "Alt")) expected |= IBUS_MOD1_MASK;
      else if (!strcmp(parts[i], "Shift")) expected |= IBUS_SHIFT_MASK;
      else if (!strcmp(parts[i], "Super")) expected |= IBUS_SUPER_MASK;
      else key = ibus_keyval_from_name(parts[i]);
    }
    match = key && ibus_keyval_to_lower(keyval) == ibus_keyval_to_lower(key) && mods == expected;
    if (keyval == IBUS_KEY_space && (state & IBUS_CONTROL_MASK) && g_getenv("RIME_LLM_TEST_DIAGNOSTICS"))
      g_printerr("Panel binding: %s key=%u expected=%u match=%d\n", binding, key, expected, match);
    g_strfreev(parts);
  }
  g_free(binding); g_free(path); g_key_file_unref(cfg);
  if (match) { rime_panel_open(engine); return TRUE; }
  return FALSE;
}

static void method(GDBusConnection* conn, const gchar* sender, const gchar* path,
                   const gchar* iface, const gchar* name, GVariant* args,
                   GDBusMethodInvocation* invocation, gpointer unused) {
  const gchar *supplied, *text;
  if (!strcmp(name, "Focus")) {
    gchar* info = g_strdup_printf("focused=%d client=%s id=%s target-match=%d state=%s", focused != NULL,
                                 focus_client ? focus_client : "none", focus_id ? focus_id : "none",
                                 target_id && !g_strcmp0(target_id, focus_id), status);
    g_dbus_method_invocation_return_value(invocation, g_variant_new("(s)", info));
    g_free(info);
    return;
  }
  if (!strcmp(name, "Open")) {
    if (focused) rime_panel_open(focused);
    g_dbus_method_invocation_return_value(invocation, g_variant_new("(s)", token ? token : ""));
    return;
  }
  if (!strcmp(name, "Queue")) g_variant_get(args, "(&s&s)", &supplied, &text);
  else g_variant_get(args, "(&s)", &supplied);
  if (!token || strcmp(token, supplied) || (peer && strcmp(peer, sender))) {
    g_dbus_method_invocation_return_dbus_error(invocation, BRIDGE ".InvalidTarget", "Target expired");
    return;
  }
  if (!peer) peer = g_strdup(sender);
  if (!strcmp(name, "Queue")) {
    if (strcmp(status, "editing") || !*text || strlen(text) > 262144 || !g_utf8_validate(text, -1, NULL)) {
      g_dbus_method_invocation_return_dbus_error(invocation, BRIDGE ".NotReady", "Target unavailable or send already queued");
      return;
    }
    pending = g_strdup(text);
    expires = g_get_monotonic_time() + 8000000;
    status = "waiting";
  } else if (!strcmp(name, "Cancel")) cancel();
  g_dbus_method_invocation_return_value(invocation, g_variant_new("(s)", status));
}

void rime_panel_init(IBusBus* bus) {
  ibus = bus;
  const gchar* xml = "<node><interface name='" BRIDGE "'>"
    "<method name='Focus'><arg type='s' direction='out'/></method>"
    "<method name='Open'><arg type='s' direction='out'/></method>"
    "<method name='State'><arg type='s' direction='in'/><arg type='s' direction='out'/></method>"
    "<method name='Cancel'><arg type='s' direction='in'/><arg type='s' direction='out'/></method>"
    "<method name='Queue'><arg type='s' direction='in'/><arg type='s' direction='in'/><arg type='s' direction='out'/></method>"
    "</interface></node>";
  GError* error = NULL;
  connection = g_bus_get_sync(G_BUS_TYPE_SESSION, NULL, &error);
  if (!connection) { g_clear_error(&error); return; }
  GDBusNodeInfo* info = g_dbus_node_info_new_for_xml(xml, NULL);
  static const GDBusInterfaceVTable vtable = {method, NULL, NULL, {0}};
  g_dbus_connection_register_object(connection, PATH, info->interfaces[0], &vtable, NULL, NULL, NULL);
  g_bus_own_name_on_connection(connection, BRIDGE, G_BUS_NAME_OWNER_FLAGS_NONE, NULL, NULL, NULL, NULL);
  g_dbus_node_info_unref(info);
  g_timeout_add(50, submit, NULL);
}
