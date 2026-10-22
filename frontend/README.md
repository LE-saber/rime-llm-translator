This frontend is derived from rime/ibus-rime 1.5.0, commit
`d525f18b45123869af0055cc8402d459ebdbb9e3`:
https://github.com/rime/ibus-rime/tree/d525f18b45123869af0055cc8402d459ebdbb9e3

Copyright Rime Developers. Licensed under GPLv3 or later; see LICENSE.
All modified frontend source is distributed here and in the Debian package.

Local changes: register a separate `rime-llm` IBus engine and private user data
directory, watch the active translation cache in the frontend main loop, refresh
Rime and publish the IBus lookup table without another physical key, preserve
the highlighted candidate, implement reset, and clean up timers on destruction.
The stock IBus Rime engine is not replaced.
