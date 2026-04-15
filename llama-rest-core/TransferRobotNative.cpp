#include "PipelineService.h"

#include <algorithm>
#include <regex>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "PipelineInternal.h"

using pipeline_internal::chat_completion;
using pipeline_internal::contains_any_lowered;
using pipeline_internal::ensure_object;
using pipeline_internal::extract_json_text;
using pipeline_internal::json;
using pipeline_internal::json_bool;
using pipeline_internal::json_string;
using pipeline_internal::make_request_id;
using pipeline_internal::normalize_whitespace;
using pipeline_internal::parse_json_body;
using pipeline_internal::trace_entry;
using pipeline_internal::to_lower_ascii;
using pipeline_internal::truncate_normalized;

namespace {

const std::vector<std::pair<std::string, std::string>> kTransferRobotCorrections = {
    {"리푸트", "리프트"},
    {"리프투", "리프트"},
    {"대나", "되나"},
    {"데나", "되나"},
    {"출바", "출발"},
    {"멈처", "멈춰"},
    {"올려조", "올려줘"},
};

const std::vector<std::string> kTransferLiftKeywords = {
    "lift", "리프트", "올려", "올려줘", "내려", "내려줘",
};
const std::vector<std::string> kTransferDepartureKeywords = {
    "depart", "departure", "start", "go", "move", "출발", "이동", "가자", "가도", "출발해",
};
const std::vector<std::string> kTransferStopKeywords = {
    "stop", "halt", "freeze", "멈춰", "정지", "멈추", "멈처",
};
const std::vector<std::string> kTransferHardwareStateKeywords = {
    "state", "status", "check", "confirm", "확인", "상태", "센서", "안전", "리프트", "출발", "정지",
};

std::string transfer_replace_all(std::string text, const std::string& from, const std::string& to) {
    if (from.empty()) {
        return text;
    }
    std::size_t start = 0;
    while ((start = text.find(from, start)) != std::string::npos) {
        text.replace(start, from.size(), to);
        start += to.size();
    }
    return text;
}

json normalize_transfer_robot_request(const json& request) {
    const auto metadata = ensure_object(request.value("metadata", json::object()));
    std::string request_id = truncate_normalized(json_string(request, "request_id"));
    if (request_id.empty()) {
        request_id = truncate_normalized(json_string(metadata, "request_id"));
    }
    if (request_id.empty()) {
        request_id = make_request_id();
    }

    std::string stt_text = truncate_normalized(json_string(request, "stt_text"));
    if (stt_text.empty()) {
        stt_text = truncate_normalized(json_string(request, "transcript"));
    }
    if (stt_text.empty()) {
        stt_text = truncate_normalized(json_string(request, "user_message"));
    }
    if (stt_text.empty()) {
        throw std::runtime_error("stt_text must not be blank");
    }

    return json{
        {"request_id", request_id},
        {"stt_text", stt_text},
        {"metadata", metadata},
    };
}

std::string corrected_transcript_fallback(const std::string& raw_text) {
    std::string corrected = normalize_whitespace(raw_text);
    for (const auto& correction : kTransferRobotCorrections) {
        corrected = transfer_replace_all(corrected, correction.first, correction.second);
    }

    corrected = std::regex_replace(corrected, std::regex(R"(\b대나\??$)"), "되나?");
    corrected = std::regex_replace(corrected, std::regex(R"(\b되나$)"), "되나?");
    corrected = std::regex_replace(corrected, std::regex(R"(\b해도 되나\??$)"), "해도 되나?");
    return truncate_normalized(corrected, 240);
}

std::string detect_transfer_intent(const std::string& text) {
    const std::string lowered = to_lower_ascii(text);
    const bool lift_related = contains_any_lowered(lowered, kTransferLiftKeywords);
    const bool departure_related = contains_any_lowered(lowered, kTransferDepartureKeywords);
    const bool stop_related = contains_any_lowered(lowered, kTransferStopKeywords);

    if (lift_related && departure_related) {
        return "lift_request_and_departure_question";
    }
    if (stop_related) {
        return "stop_request";
    }
    if (lift_related) {
        return "lift_request";
    }
    if (departure_related) {
        return "departure_question";
    }
    return "general_robot_guidance";
}

bool detect_hardware_check_needed(const std::string& corrected_text, const std::string& intent) {
    if (intent == "general_robot_guidance") {
        return contains_any_lowered(to_lower_ascii(corrected_text), kTransferHardwareStateKeywords);
    }
    return true;
}

std::string fallback_reply_for_tts(const std::string& intent, bool needs_hardware_check) {
    if (intent == "lift_request_and_departure_question") {
        return "현재 상태를 확인한 뒤 출발 여부를 안내하겠습니다.";
    }
    if (intent == "lift_request") {
        return "리프트 상태를 확인한 뒤 안내하겠습니다.";
    }
    if (intent == "departure_question") {
        return "주행 가능 상태를 확인한 뒤 안내하겠습니다.";
    }
    if (intent == "stop_request") {
        return "정지 상태를 우선 확인하겠습니다.";
    }
    if (needs_hardware_check) {
        return "현재 장비 상태를 확인한 뒤 안내하겠습니다.";
    }
    return "짧게 다시 말씀해 주세요.";
}

json build_transfer_robot_user_prompt_payload(const json& normalized_request) {
    return json{
        {"request_id", normalized_request.at("request_id")},
        {"stt_text", normalized_request.at("stt_text")},
        {"task", "Correct the noisy STT transcript, infer likely user intent, and return TTS-ready JSON only."},
        {"output_schema", {
            {"corrected_transcript", "string"},
            {"intent", "string"},
            {"reply_for_tts", "string"},
            {"needs_hardware_check", true},
        }},
    };
}

json build_transfer_robot_fallback_result(const json& normalized_request) {
    const std::string corrected_transcript = corrected_transcript_fallback(json_string(normalized_request, "stt_text"));
    const std::string intent = detect_transfer_intent(corrected_transcript);
    const bool needs_hardware_check = detect_hardware_check_needed(corrected_transcript, intent);
    return json{
        {"corrected_transcript", corrected_transcript},
        {"intent", intent},
        {"reply_for_tts", fallback_reply_for_tts(intent, needs_hardware_check)},
        {"needs_hardware_check", needs_hardware_check},
    };
}

json sanitize_transfer_robot_result(const json& normalized_request, const json& parsed) {
    const json fallback = build_transfer_robot_fallback_result(normalized_request);
    const std::string corrected_transcript = truncate_normalized(
        json_string(parsed, "corrected_transcript", json_string(fallback, "corrected_transcript")),
        240
    );
    std::string intent = truncate_normalized(
        json_string(parsed, "intent", json_string(fallback, "intent")),
        80
    );
    if (intent.empty()) {
        intent = json_string(fallback, "intent");
    }

    std::string reply_for_tts = truncate_normalized(
        json_string(parsed, "reply_for_tts", json_string(fallback, "reply_for_tts")),
        120
    );
    if (reply_for_tts.empty()) {
        reply_for_tts = json_string(fallback, "reply_for_tts");
    }

    const bool needs_hardware_check =
        parsed.contains("needs_hardware_check") && parsed.at("needs_hardware_check").is_boolean()
            ? parsed.at("needs_hardware_check").get<bool>()
            : json_bool(fallback, "needs_hardware_check", true);

    return json{
        {"corrected_transcript", corrected_transcript},
        {"intent", intent},
        {"reply_for_tts", reply_for_tts},
        {"needs_hardware_check", needs_hardware_check},
    };
}

}  // namespace

nlohmann::json PipelineService::transfer_robot_stt_internal(const nlohmann::json& request) const {
    const json normalized_request = normalize_transfer_robot_request(request);
    json trace = json::array();
    trace.push_back(trace_entry(
        "normalize",
        "passed",
        "Transfer-robot STT request was normalized.",
        json{{"request_id", normalized_request.at("request_id")}, {"stt_text", normalized_request.at("stt_text")}}
    ));

    json structured;
    std::string decision_source = "fallback";

    if (config_.transfer_robot_model_enabled) {
        try {
            const std::string raw_response = chat_completion(
                config_.transfer_robot_model_endpoint,
                config_.transfer_robot_model_name,
                config_.transfer_robot_system_prompt,
                build_transfer_robot_user_prompt_payload(normalized_request).dump(2, ' ', false, json::error_handler_t::replace),
                config_.transfer_robot_temperature,
                config_.transfer_robot_max_tokens,
                config_.transfer_robot_reasoning_mode,
                config_.transfer_robot_reasoning_budget,
                config_.transfer_robot_request_timeout
            );
            structured = sanitize_transfer_robot_result(
                normalized_request,
                parse_json_body(extract_json_text(raw_response))
            );
            decision_source = "model";
            trace.push_back(trace_entry(
                "model",
                "generated",
                "Transfer-robot local model produced structured STT correction output.",
                json{{"model_name", config_.transfer_robot_model_name}}
            ));
        } catch (const std::exception& exc) {
            structured = build_transfer_robot_fallback_result(normalized_request);
            trace.push_back(trace_entry(
                "model",
                "failed",
                "Transfer-robot model output was invalid and deterministic fallback was used.",
                json{{"error", exc.what()}}
            ));
        }
    } else {
        structured = build_transfer_robot_fallback_result(normalized_request);
        trace.push_back(trace_entry(
            "fallback",
            "applied",
            "Transfer-robot deterministic fallback handled the STT request.",
            json::object()
        ));
    }

    const json result = {
        {"response", structured},
        {"decision_source", decision_source},
        {"normalized_input", normalized_request},
        {"trace", trace},
    };
    return result;
}

nlohmann::json PipelineService::transfer_robot_stt(const nlohmann::json& request, bool debug) const {
    const json result = transfer_robot_stt_internal(request);
    if (debug) {
        return result;
    }
    return result.at("response");
}
