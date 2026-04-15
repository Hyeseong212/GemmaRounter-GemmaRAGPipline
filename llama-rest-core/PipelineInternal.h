#ifndef PIPELINE_INTERNAL_H
#define PIPELINE_INTERNAL_H

#include <filesystem>
#include <string>
#include <utility>
#include <vector>

#include "external/nlohmann/json.hpp"

namespace pipeline_internal {

using json = nlohmann::json;

struct ParsedUrl {
    std::string base;
    std::string path;
};

struct DetectedSignals {
    std::vector<std::string> error_codes;
    bool asks_manual_or_sop = false;
    bool asks_error_meaning = false;
    bool asks_steps_or_procedure = false;
    bool asks_specs_or_policy = false;
    bool organization_specific = false;
    bool reference_grounding_likely = false;
    bool open_ended_reasoning = false;

    json to_json() const {
        return json{
            {"error_codes", error_codes},
            {"asks_manual_or_sop", asks_manual_or_sop},
            {"asks_error_meaning", asks_error_meaning},
            {"asks_steps_or_procedure", asks_steps_or_procedure},
            {"asks_specs_or_policy", asks_specs_or_policy},
            {"organization_specific", organization_specific},
            {"reference_grounding_likely", reference_grounding_likely},
            {"open_ended_reasoning", open_ended_reasoning},
        };
    }
};

struct NormalizedRouterInput {
    std::string request_id;
    std::string user_message;
    json metadata = json::object();
    DetectedSignals detected_signals;

    json to_json() const {
        return json{
            {"request_id", request_id},
            {"user_message", user_message},
            {"metadata", metadata},
            {"detected_signals", detected_signals.to_json()},
        };
    }
};

struct RouterDecision {
    std::string route;
    bool needs_rag = false;
    std::string confidence = "medium";
    std::vector<std::string> reason_codes;
    std::string summary_for_handoff;
    std::string retrieval_query;

    json to_json() const {
        return json{
            {"route", route},
            {"needs_rag", needs_rag},
            {"confidence", confidence},
            {"reason_codes", reason_codes},
            {"summary_for_handoff", summary_for_handoff},
            {"retrieval_query", retrieval_query},
        };
    }
};

struct ScoreBreakdown {
    int routing_confidence = 0;
    int evidence_quality = 0;
    int safety = 0;
    int answer_quality = 0;
    int format_quality = 0;

    int total() const {
        return routing_confidence + evidence_quality + safety + answer_quality + format_quality;
    }

    json to_json() const {
        return json{
            {"routing_confidence", routing_confidence},
            {"evidence_quality", evidence_quality},
            {"safety", safety},
            {"answer_quality", answer_quality},
            {"format_quality", format_quality},
        };
    }
};

std::string getenv_or_default(const char* key, const std::string& default_value);
bool getenv_or_default_bool(const char* key, bool default_value);
double getenv_or_default_double(const char* key, double default_value);
int getenv_or_default_int(const char* key, int default_value);

std::filesystem::path repo_root();
std::string load_text_file(const std::filesystem::path& path);
std::string normalize_whitespace(const std::string& input);
std::string to_lower_ascii(const std::string& input);
std::string truncate_normalized(const std::string& input, std::size_t limit = 240);
bool contains_any_lowered(const std::string& lowered, const std::vector<std::string>& keywords);
json ensure_object(const json& value);
json ensure_array(const json& value);
std::vector<std::string> json_string_array(const json& value);
json json_array_from_strings(const std::vector<std::string>& values);
std::string json_string(const json& obj, const std::string& key, const std::string& default_value = "");
bool json_bool(const json& obj, const std::string& key, bool default_value = false);
std::string make_request_id();
json trace_entry(
    const std::string& stage,
    const std::string& status,
    const std::string& detail,
    const json& data = json::object()
);

ParsedUrl parse_url(const std::string& url);
json parse_json_body(const std::string& body);
std::string extract_json_text(const std::string& raw_text);
std::string post_json(const std::string& url, const json& payload, double timeout_seconds);
std::string chat_completion(
    const std::string& endpoint,
    const std::string& model_name,
    const std::string& system_prompt,
    const std::string& user_prompt,
    double temperature,
    int max_tokens,
    const std::string& reasoning_mode,
    int reasoning_budget,
    double timeout_seconds
);

std::pair<std::string, std::vector<std::string>> split_legacy_rag_answer(const std::string& raw_answer);
std::string extract_warning(const std::string& answer_text);

}  // namespace pipeline_internal

#endif
