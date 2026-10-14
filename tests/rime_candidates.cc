// Integration smoke test against the real Ubuntu librime and librime-lua.
#include <rime_api.h>
#include <cstring>
#include <iostream>
#include <string>
#include <cstdlib>
#include <fstream>

int main(int argc, char** argv) {
  if (argc < 3 || argc > 5) {
    std::cerr << "usage: rime-candidates USER_DATA_DIR SHARED_DATA_DIR [EXPECTED_CANDIDATE [AI_REQUEST_PATH]]\n";
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
  bool has_translation = argc == 3;
  bool labeled_translation = argc == 3;
  bool valid = rime->get_context(session, &ctx);
  bool has_candidates = valid && ctx.menu.num_candidates > 0;
  if (valid) {
    std::cout << "preedit: " << (ctx.composition.preedit ? ctx.composition.preedit : "(none)") << "\n";
    std::cout << "candidate count: " << ctx.menu.num_candidates << "\n";
    for (int i = 0; i < ctx.menu.num_candidates; ++i) {
      if (ctx.menu.candidates[i].text)
        std::cout << "candidate " << i << ": " << ctx.menu.candidates[i].text << "\n";
    }
    if (argc >= 4) {
      for (int i = 0; i < ctx.menu.num_candidates; ++i) {
        if (ctx.menu.candidates[i].text &&
            std::string(ctx.menu.candidates[i].text) == argv[3]) {
          has_translation = true;
          std::string label = std::string(argv[3]).find("Offline") != std::string::npos ? "MT" : "AI";
          const char* comment = ctx.menu.candidates[i].comment;
          labeled_translation = comment && std::string(comment).find(label) != std::string::npos;
        }
      }
    }
    rime->free_context(&ctx);
  }
  if (argc >= 5) {
    // X11 Return keysym; ShiftMask | ControlMask.
    rime->process_key(session, 0xff0d, 5);
    std::ifstream request(argv[4]);
    if (!request.good()) {
      std::cerr << "FAIL: AI hotkey did not enqueue an explicit request\n";
      rime->destroy_session(session);
      rime->finalize();
      return 1;
    }
    std::cout << "PASS: AI hotkey wrote one explicit request\n";
  }
  rime->destroy_session(session);
  rime->finalize();
  if (!has_candidates) {
    std::cerr << "FAIL: Chinese candidate menu disappeared\n";
    return 1;
  }
  if (!has_translation || !labeled_translation) {
    std::cerr << "FAIL: translation candidate or its MT/AI annotation missing\n";
    return 1;
  }
  std::cout << "PASS: native Chinese candidates survived and expected translation was visible\n";
  return 0;
}
