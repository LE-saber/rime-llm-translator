// Native CPU-only translation worker. Third-party code is pinned in engine.lock.
#include <iostream>
#include <map>
#include <memory>
#include <string>
#include <nlohmann/json.hpp>
#include <opencc/SimpleConverter.hpp>
#include "translator/service.h"

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  // This binary's baseline is x86-64. intgemm dispatches its own kernels.
  __builtin_cpu_init();
  if (!__builtin_cpu_supports("sse4.1")) {
    std::cerr << "rime-mt: CPU requires SSE4.1\n";
    return 2;
  }
  using namespace marian::bergamot;
  using json = nlohmann::json;
  BlockingService::Config config;
  config.cacheSize = 0;
  BlockingService service(config);
  opencc::SimpleConverter converter("/usr/share/opencc/t2s.json");
  std::map<std::string, std::shared_ptr<TranslationModel>> models;
  std::string line;
  // Parent writes bounded messages; reject protocol misuse before inference.
  while (std::getline(std::cin, line)) {
    if (line.size() > 65536) return 2;
    try {
      auto request = json::parse(line);
      auto direction = request.at("direction").get<std::string>();
      auto input = request.at("text").get<std::string>();
      if ((direction != "zh-en" && direction != "en-ja") || input.empty() || input.size() > 16384)
        throw std::runtime_error("invalid request");
      if (direction == "zh-en") input = converter.Convert(input);
      auto& model = models[direction];
      if (!model) {
        auto options = parseOptionsFromFilePath(std::string(argv[1]) + "/" + direction + "/config.yml");
        model = std::make_shared<TranslationModel>(options, 1);
      }
      auto responses = service.translateMultiple(model, {std::move(input)}, {ResponseOptions()});
      auto output = responses.at(0).target.text;
      if (output.empty() || output.size() > 32768) throw std::runtime_error("invalid output");
      std::cout << json({{"text", output}}).dump() << std::endl;
    } catch (const std::exception&) {
      // Do not log user input, model output, or parser exceptions containing input.
      std::cout << "{\"error\":\"offline translation failed\"}" << std::endl;
    }
  }
}
