// Native CPU-only translation worker. Third-party code is pinned in engine.lock.
#include <iostream>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <nlohmann/json.hpp>
#include <opencc/SimpleConverter.hpp>
#include "translator/service.h"

// Use the model's real tokenizer, split on sentence/word boundaries, and never
// discard a suffix. Each piece stays below the backend's 64-token wrap limit.
std::vector<std::string> chunks(const std::string& input,
    const std::shared_ptr<marian::bergamot::TranslationModel>& model) {
  std::vector<std::string> output;
  size_t start = 0, previous = 0, boundary = 0;
  for (size_t end = 0; end < input.size();) {
    size_t begin = end;
    do { ++end; } while (end < input.size() && (static_cast<unsigned char>(input[end]) & 0xc0) == 0x80);
    auto character = input.substr(begin, end - begin);
    if (model->sourceTokenCount(input.substr(start, end - start)) > 48 && previous > start) {
      size_t cut = boundary > start ? boundary : previous;
      auto part = input.substr(start, cut - start);
      if (part.find_first_not_of(" \r\n\t") != std::string::npos) output.push_back(part);
      start = end = cut;
      boundary = previous = start;
      continue;
    }
    previous = end;
    if (character == " " || character == "\t" || character == "," || character == "，") boundary = end;
    if (character == "。" || character == "！" || character == "？" || character == "\n" ||
        ((character == "." || character == "!" || character == "?") &&
         (end == input.size() || input[end] == ' '))) {
      auto part = input.substr(start, end - start);
      if (part.find_first_not_of(" \r\n\t") != std::string::npos) output.push_back(part);
      start = boundary = previous = end;
    }
  }
  if (start < input.size() && input.substr(start).find_first_not_of(" \r\n\t") != std::string::npos)
    output.push_back(input.substr(start));
  return output;
}

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  // This binary's baseline is x86-64. intgemm dispatches its own kernels.
  __builtin_cpu_init();
  if (!__builtin_cpu_supports("sse4.1")) {
    std::cerr << "rime-mt: CPU requires SSE4.1\n";
    return 2;
  }
  if (std::strcmp(argv[1], "--check-cpu") == 0) return 0;
  using namespace marian::bergamot;
  using json = nlohmann::json;
  BlockingService::Config config;
  config.cacheSize = 0;
  config.logger.level = "error";
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
      std::string output;
      for (auto& part : chunks(input, model)) {
        auto responses = service.translateMultiple(model, {std::move(part)}, {ResponseOptions()});
        auto translated = responses.at(0).target.text;
        if (translated.empty()) throw std::runtime_error("empty segment translation");
        if (!output.empty() && direction == "zh-en") output += ' ';
        output += translated;
      }
      if (output.empty() || output.size() > 32768) throw std::runtime_error("invalid output");
      std::cout << json({{"text", output}}).dump() << std::endl;
    } catch (const std::exception&) {
      // Do not log user input, model output, or parser exceptions containing input.
      std::cout << "{\"error\":\"offline translation failed\"}" << std::endl;
    }
  }
}
