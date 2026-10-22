#ifndef RIME_PANEL_H
#define RIME_PANEL_H
#include <ibus.h>
void rime_panel_init(void);
void rime_panel_focus(IBusEngine* engine, const char* context, const char* client);
void rime_panel_blur(IBusEngine* engine);
void rime_panel_destroy(IBusEngine* engine);
gboolean rime_panel_key(IBusEngine* engine, guint keyval, guint state);
void rime_panel_open(IBusEngine* engine);
#endif
