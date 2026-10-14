// Integration smoke test against the real Ubuntu librime and librime-lua.
#include <rime_api.h>
#include <cstring>
#include <iostream>
#include <string>
#include <cstdlib>

int main(int argc, char** argv) {
  if (argc != 3) {
    std::cerr << "usage: rime-candidates USER_DATA_DIR SHARED_DATA_DIR\n";
    return 2;
  }
  RimeApi* rime = rime_get_api();
  RIME_STRUCT(RimeTraits, traits);
  traits.shared_data_dir = argv[2];
  traits.user_data_dir = argv[1];
  traits.app_name = "rime.candidate.integration";
  rime->setup(&traits);
  rime->initialize(&traits);
  if (rime->start_maintenance(True)) rime->join_maintenance_thread();
  RimeSessionId session = rime->create_session();
  if (!session) {
    std::cerr << "Could not create Rime session\n";
    rime->finalize();
    return 1;
  }
  if (!rime->select_schema(session, "luna_pinyin")) {
    std::cerr << "Could not select Luna Pinyin\n";
    rime->destroy_session(session);
    rime->finalize();
    return 1;
  }
  rime->set_option(session, "ascii_mode", False);
  for (const char c : std::string("nihao")) {
    rime->process_key(session, c, 0);
  }
  RIME_STRUCT(RimeContext, ctx);
  bool valid = rime->get_context(session, &ctx);
  bool has_candidates = valid && ctx.menu.num_candidates > 0;
  if (valid) {
    std::cout << "preedit: " << (ctx.composition.preedit ? ctx.composition.preedit : "(none)") << "\n";
    std::cout << "candidate count: " << ctx.menu.num_candidates << "\n";
    for (int i = 0; i < ctx.menu.num_candidates; ++i) {
      if (ctx.menu.candidates[i].text)
        std::cout << "candidate " << i << ": " << ctx.menu.candidates[i].text << "\n";
    }
    rime->free_context(&ctx);
  }
  rime->destroy_session(session);
  rime->finalize();
  if (!has_candidates) {
    std::cerr << "FAIL: Chinese candidate menu disappeared\n";
    return 1;
  }
  std::cout << "PASS: Native Chinese candidates survived Rime filter\n";
  return 0;
}
