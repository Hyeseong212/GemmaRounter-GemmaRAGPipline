#include "PipelineService.h"

#include <algorithm>
#include <map>
#include <regex>
#include <string>
#include <vector>

#include "PipelineInternal.h"

using pipeline_internal::DetectedSignals;
using pipeline_internal::NormalizedRouterInput;
using pipeline_internal::RouterDecision;
using pipeline_internal::ScoreBreakdown;
using pipeline_internal::chat_completion;
using pipeline_internal::contains_any_lowered;
using pipeline_internal::ensure_array;
using pipeline_internal::ensure_object;
using pipeline_internal::extract_json_text;
using pipeline_internal::extract_warning;
using pipeline_internal::json;
using pipeline_internal::json_bool;
using pipeline_internal::json_string;
using pipeline_internal::json_string_array;
using pipeline_internal::make_request_id;
using pipeline_internal::parse_json_body;
using pipeline_internal::post_json;
using pipeline_internal::split_legacy_rag_answer;
using pipeline_internal::trace_entry;
using pipeline_internal::to_lower_ascii;
using pipeline_internal::truncate_normalized;

namespace {

const std::regex kErrorCodePattern(R"(\b[Ee]\d{2,4}\b)");

const std::vector<std::string> kManualKeywords = {
    "manual", "sop", "procedure", "guide", "document", "reference",
    "매뉴얼", "절차", "문서", "가이드", "설명서", "사용설명서", "레퍼런스",
};
const std::vector<std::string> kDeviceKeywords = {
    "device", "equipment", "instrument", "robot",
    "장비", "기기", "기계", "제품", "분석기", "측정기", "검사지", "로봇",
};
const std::vector<std::string> kOperationalReferenceKeywords = {
    "charge", "charging", "measure", "measurement", "clean", "cleaning", "disinfect", "storage",
    "replace", "insert", "remove", "reuse", "expiration", "expiry", "strip",
    "충전", "측정", "세척", "소독", "보관", "교체", "삽입", "제거", "재사용", "유효기간", "검사지",
    "주의사항", "확인사항", "사용방법", "사용법", "사용전", "사용중", "사용후",
};
const std::vector<std::string> kPermissionKeywords = {
    "can i", "can we", "is it ok", "allowed", "safe to", "should i",
    "해도", "써도", "되나", "되나요", "가능", "괜찮", "금지", "주의", "확인해야",
};
const std::vector<std::string> kErrorMeaningKeywords = {
    "error", "meaning", "뜻", "의미", "에러", "알람", "경고",
};
const std::vector<std::string> kStepKeywords = {
    "step", "steps", "procedure", "sequence", "how should",
    "조치", "순서", "절차", "단계", "어떻게",
};
const std::vector<std::string> kSpecKeywords = {
    "spec", "specs", "policy", "policies", "rule",
    "규격", "사양", "정책", "기준", "요건",
};
const std::vector<std::string> kOrgSpecificKeywords = {
    "우리 프로젝트", "우리 장비", "이 장비", "이 제품", "내부 문서", "사내", "프로젝트 문서",
};
const std::vector<std::string> kOpenReasoningKeywords = {
    "compare", "comparison", "difference", "tradeoff", "pros and cons",
    "why", "brainstorm", "analyze",
    "비교", "차이", "장단점", "왜", "분석", "정리", "설명",
};
const std::vector<std::string> kReferenceKeywords = {
    "manual", "sop", "procedure", "guide", "document", "reference",
    "spec", "specs", "policy", "policies",
    "매뉴얼", "절차", "문서", "가이드", "설명서", "사용설명서",
    "레퍼런스", "규격", "사양", "정책", "기준",
};
const std::vector<std::string> kRiskyContentKeywords = {
    "진단", "치료", "처방", "투약", "복용", "용량", "수술", "약을", "약물",
};
const std::vector<std::string> kUnsafeOverrideKeywords = {
    "무시", "우회", "강제로", "비활성", "해제", "override", "bypass",
};
const std::vector<std::string> kHumanReviewMarkers = {
    "사람 검토", "의사와 상의", "전문가와 상의", "담당자에게 문의", "추가 확인 필요", "환자별 판단",
};
const std::vector<std::string> kInsufficientMarkers = {
    "근거가 부족", "정보가 부족", "직접 확인할 수 없", "문서에서 확인할 수 없", "충분한 근거가 없",
};
const std::vector<std::string> kReferenceMarkers = {
    "문서", "매뉴얼", "SOP", "절차", "기준", "출처",
};

bool upstream_prefers_rag(const json& metadata) {
    if (!metadata.is_object()) {
        return false;
    }
    if (json_string(metadata, "upstream_route") == "server_rag") {
        return true;
    }
    const auto first_router_display = ensure_object(metadata.value("first_router_display", json::object()));
    if (json_string(first_router_display, "route") == "server_rag") {
        return true;
    }
    const auto first_router_handoff = ensure_object(metadata.value("first_router_handoff", json::object()));
    if (json_string(first_router_handoff, "route") == "server_rag") {
        return true;
    }
    const auto handoff_metadata = ensure_object(first_router_handoff.value("metadata", json::object()));
    return json_bool(handoff_metadata, "needs_rag", false);
}

DetectedSignals extract_signals(const std::string& message) {
    const std::string lowered = to_lower_ascii(message);
    std::vector<std::string> error_codes;

    for (std::sregex_iterator iter(message.begin(), message.end(), kErrorCodePattern), end; iter != end; ++iter) {
        std::string code = to_lower_ascii(iter->str());
        std::transform(code.begin(), code.end(), code.begin(), [](unsigned char ch) {
            return static_cast<char>(std::toupper(ch));
        });
        if (std::find(error_codes.begin(), error_codes.end(), code) == error_codes.end()) {
            error_codes.push_back(code);
        }
    }

    const bool asks_manual_or_sop = contains_any_lowered(lowered, kManualKeywords);
    const bool device_related =
        contains_any_lowered(lowered, kDeviceKeywords) ||
        contains_any_lowered(lowered, kOperationalReferenceKeywords);
    const bool operational_reference_question =
        device_related && contains_any_lowered(lowered, kPermissionKeywords);
    const bool asks_error_meaning = !error_codes.empty() || contains_any_lowered(lowered, kErrorMeaningKeywords);
    const bool asks_steps_or_procedure = contains_any_lowered(lowered, kStepKeywords);
    const bool asks_specs_or_policy = contains_any_lowered(lowered, kSpecKeywords);
    const bool organization_specific = contains_any_lowered(lowered, kOrgSpecificKeywords);
    const bool open_ended_reasoning = contains_any_lowered(lowered, kOpenReasoningKeywords) || message.size() >= 120;
    const bool reference_grounding_likely =
        !error_codes.empty() ||
        asks_manual_or_sop ||
        operational_reference_question ||
        asks_steps_or_procedure ||
        asks_specs_or_policy ||
        (organization_specific && !open_ended_reasoning);

    return DetectedSignals{
        error_codes,
        asks_manual_or_sop,
        asks_error_meaning,
        asks_steps_or_procedure,
        asks_specs_or_policy,
        organization_specific,
        reference_grounding_likely,
        open_ended_reasoning,
    };
}

std::vector<std::string> rag_reason_codes(const DetectedSignals& signals) {
    std::vector<std::string> reasons;
    if (!signals.error_codes.empty() || signals.asks_error_meaning) {
        reasons.push_back("error_code_reference");
    }
    if (signals.asks_manual_or_sop || signals.asks_steps_or_procedure) {
        reasons.push_back("manual_or_sop_reference");
    }
    if (signals.asks_specs_or_policy) {
        reasons.push_back("spec_or_policy_reference");
    }
    if (signals.organization_specific) {
        reasons.push_back("organization_specific_reference");
    }
    if (reasons.empty()) {
        reasons.push_back("manual_or_sop_reference");
    }
    return reasons;
}

RouterDecision fallback_decision(const NormalizedRouterInput& request) {
    if (request.detected_signals.reference_grounding_likely || upstream_prefers_rag(request.metadata)) {
        std::string summary = truncate_normalized(request.user_message);
        std::string retrieval_query = summary;
        if (!request.detected_signals.error_codes.empty()) {
            retrieval_query.clear();
            for (const auto& code : request.detected_signals.error_codes) {
                if (!retrieval_query.empty()) {
                    retrieval_query += " ";
                }
                retrieval_query += code;
            }
            retrieval_query += " " + summary;
        }
        auto reasons = rag_reason_codes(request.detected_signals);
        if (upstream_prefers_rag(request.metadata)) {
            reasons.push_back("upstream_first_router_rag");
        }
        reasons.push_back("fallback_reference_bias");
        return RouterDecision{
            "server_rag",
            true,
            "medium",
            reasons,
            summary,
            truncate_normalized(retrieval_query),
        };
    }

    return RouterDecision{
        "server_llm",
        false,
        "medium",
        {"general_reasoning_ok", "fallback_general_reasoning"},
        truncate_normalized(request.user_message),
        "",
    };
}

json build_router_user_prompt_payload(const NormalizedRouterInput& request) {
    return json{
        {"request_id", request.request_id},
        {"user_message", request.user_message},
        {"detected_signals", request.detected_signals.to_json()},
        {"route_rules", {
            {"server_rag", "Use when the answer should be grounded in manuals, SOPs, error-code tables, specs, policies, or internal project references."},
            {"server_llm", "Use when a strong general model can answer directly without document retrieval grounding."},
        }},
        {"task", "Return only the routing JSON for whether this request needs RAG grounding."},
    };
}

RouterDecision decision_from_model_output(const NormalizedRouterInput& request, const json& parsed) {
    const std::string route = json_string(parsed, "route");
    if (route != "server_rag" && route != "server_llm") {
        throw std::runtime_error("Invalid model route");
    }

    std::string confidence = json_string(parsed, "confidence", "medium");
    if (confidence != "high" && confidence != "medium" && confidence != "low") {
        confidence = "medium";
    }

    const std::string summary = truncate_normalized(json_string(parsed, "summary_for_handoff", request.user_message));
    const std::string retrieval_query = truncate_normalized(json_string(parsed, "retrieval_query", ""));

    if (route == "server_rag") {
        return RouterDecision{
            "server_rag",
            true,
            confidence,
            rag_reason_codes(request.detected_signals),
            summary,
            retrieval_query.empty() ? summary : retrieval_query,
        };
    }

    return RouterDecision{
        "server_llm",
        false,
        confidence,
        {"general_reasoning_ok"},
        summary,
        "",
    };
}

json build_router_display(const RouterDecision& decision) {
    return json{
        {"route", decision.route},
        {"needs_rag", decision.needs_rag},
        {"confidence", decision.confidence},
        {"brief", decision.route == "server_rag" ? "문서 근거가 필요해 RAG로 전달" : "일반 서버 LLM 답변으로 처리"},
        {"reason_codes", decision.reason_codes},
    };
}

json build_router_handoff(const NormalizedRouterInput& request, const RouterDecision& decision) {
    const std::string summary = decision.summary_for_handoff.empty() ? request.user_message : decision.summary_for_handoff;

    if (decision.route == "server_rag") {
        std::string retrieval_query = decision.retrieval_query;
        if (retrieval_query.empty()) {
            retrieval_query = summary;
            if (!request.detected_signals.error_codes.empty()) {
                retrieval_query.clear();
                for (const auto& code : request.detected_signals.error_codes) {
                    if (!retrieval_query.empty()) {
                        retrieval_query += " ";
                    }
                    retrieval_query += code;
                }
                retrieval_query += " " + summary;
            }
        }

        return json{
            {"route", "server_rag"},
            {"target_system", "rag_reference_api"},
            {"task_type", "grounded_reference_lookup"},
            {"summary", summary},
            {"required_inputs", json::array({"user_message", "retrieved_context"})},
            {"metadata", {
                {"needs_rag", true},
                {"retrieval_query", truncate_normalized(retrieval_query)},
                {"question", request.user_message},
            }},
        };
    }

    return json{
        {"route", "server_llm"},
        {"target_system", "server_large_llm"},
        {"task_type", "general_answer_generation"},
        {"summary", summary},
        {"required_inputs", json::array({"user_message"})},
        {"metadata", {
            {"needs_rag", false},
            {"question", request.user_message},
        }},
    };
}

std::string metadata_text(const json& metadata, const std::string& key) {
    if (!metadata.is_object()) {
        return "";
    }
    return truncate_normalized(json_string(metadata, key));
}

NormalizedRouterInput normalize_router_input(const json& request) {
    const auto metadata = ensure_object(request.contains("metadata") ? request.at("metadata") : json::object());
    std::string request_id = truncate_normalized(json_string(request, "request_id"));
    if (request_id.empty()) {
        request_id = truncate_normalized(json_string(metadata, "request_id"));
    }
    if (request_id.empty()) {
        request_id = make_request_id();
    }

    const std::string user_message = truncate_normalized(json_string(request, "user_message"));
    if (user_message.empty()) {
        throw std::runtime_error("user_message must not be blank");
    }

    return NormalizedRouterInput{
        request_id,
        user_message,
        metadata,
        extract_signals(user_message),
    };
}

json adapt_first_router_input(const json& request) {
    const auto first_router = ensure_object(request.at("first_router"));
    const auto display = ensure_object(first_router.at("display"));
    const auto handoff = ensure_object(first_router.at("handoff"));
    const std::string display_route = json_string(display, "route");
    const std::string handoff_route = json_string(handoff, "route");
    if (display_route != handoff_route) {
        throw std::runtime_error("first_router.display.route must match first_router.handoff.route");
    }
    if (handoff_route != "server_rag" && handoff_route != "server_llm") {
        throw std::runtime_error("Only server-bound first-router routes can be forwarded to server routing");
    }

    const auto request_metadata = ensure_object(request.contains("metadata") ? request.at("metadata") : json::object());
    const auto handoff_metadata = ensure_object(handoff.contains("metadata") ? handoff.at("metadata") : json::object());

    std::string resolved_question = truncate_normalized(json_string(request, "original_question"));
    if (resolved_question.empty()) {
        resolved_question = metadata_text(handoff_metadata, "original_question");
    }
    if (resolved_question.empty()) {
        resolved_question = metadata_text(handoff_metadata, "question");
    }
    if (resolved_question.empty()) {
        throw std::runtime_error("original_question must be provided explicitly or in first_router.handoff.metadata");
    }

    auto metadata = request_metadata;
    metadata["source"] = "first_router";
    metadata["original_question"] = resolved_question;
    metadata["first_router_display"] = display;
    metadata["first_router_handoff"] = handoff;
    if (!metadata.contains("upstream_route")) {
        metadata["upstream_route"] = display_route;
    }
    if (!metadata.contains("upstream_target_system")) {
        metadata["upstream_target_system"] = json_string(handoff, "target_system");
    }
    if (!metadata.contains("upstream_task_type")) {
        metadata["upstream_task_type"] = json_string(handoff, "task_type");
    }
    if (!metadata.contains("upstream_summary")) {
        metadata["upstream_summary"] = json_string(handoff, "summary");
    }

    return json{
        {"request_id", json_string(request, "request_id")},
        {"user_message", resolved_question},
        {"metadata", metadata},
    };
}

int routing_points(const json& second_router) {
    if (!second_router.is_object()) {
        return 14;
    }
    const std::string confidence = json_string(second_router, "confidence", "medium");
    if (confidence == "high") {
        return 20;
    }
    if (confidence == "low") {
        return 8;
    }
    return 14;
}

bool is_reference_like(const std::string& question) {
    if (std::regex_search(question, kErrorCodePattern)) {
        return true;
    }
    return contains_any_lowered(to_lower_ascii(question), kReferenceKeywords);
}

json build_score_display(const json& decision) {
    static const std::map<std::string, std::string> brief_map = {
        {"release", "최종 점수 기준을 만족해 답변 출고"},
        {"reroute_to_rag", "문서 근거가 필요해 RAG로 재분기"},
        {"retry_generation", "출력 품질이 부족해 재생성 필요"},
        {"human_review", "안전 또는 근거 이슈로 사람 검토 필요"},
        {"block", "위험한 우회/무시 성격이 보여 차단"},
    };

    return json{
        {"final_score", decision.at("final_score")},
        {"action", decision.at("action")},
        {"brief", brief_map.at(decision.at("action").get<std::string>())},
        {"reasons", decision.at("reasons")},
    };
}

json build_score_decision(
    const std::string& route_used,
    const std::string& action,
    const std::vector<std::string>& reasons,
    const ScoreBreakdown& breakdown,
    const std::string& final_answer
) {
    std::vector<std::string> unique_reasons;
    for (const auto& reason : reasons) {
        if (std::find(unique_reasons.begin(), unique_reasons.end(), reason) == unique_reasons.end()) {
            unique_reasons.push_back(reason);
        }
    }
    int total = breakdown.total();
    total = std::max(0, std::min(100, total));

    return json{
        {"route_used", route_used},
        {"final_score", total},
        {"action", action},
        {"reasons", unique_reasons},
        {"breakdown", breakdown.to_json()},
        {"final_answer", final_answer.empty() ? json(nullptr) : json(final_answer)},
    };
}

json score_rag_path(const json& request) {
    std::vector<std::string> reasons;
    ScoreBreakdown breakdown;
    breakdown.routing_confidence = routing_points(request.value("second_router", json::object()));
    breakdown.safety = 25;
    std::string action = "retry_generation";
    std::string final_answer;

    const auto rag_result = request.value("rag_result", json(nullptr));
    if (!rag_result.is_object()) {
        reasons.push_back("missing_rag_result");
        return build_score_decision("server_rag", action, reasons, breakdown, final_answer);
    }

    const std::string answer = truncate_normalized(json_string(rag_result, "answer"));
    if (!answer.empty()) {
        breakdown.answer_quality = answer.size() >= 20 ? 18 : 10;
        breakdown.format_quality += 4;
    } else {
        reasons.push_back("empty_answer");
    }

    const bool answerable = json_bool(rag_result, "answerable", false);
    const auto used_chunk_ids = ensure_array(rag_result.value("used_chunk_ids", json::array()));
    const auto retrieved_scores = ensure_array(rag_result.value("retrieved_scores", json::array()));

    if (answerable) {
        breakdown.evidence_quality = 18;
        if (!used_chunk_ids.empty()) {
            breakdown.evidence_quality += 7;
            breakdown.format_quality += 6;
        } else {
            reasons.push_back("missing_chunk_ids");
        }

        if (!retrieved_scores.empty()) {
            double total = 0.0;
            int count = 0;
            for (const auto& score : retrieved_scores) {
                if (score.is_number()) {
                    total += score.get<double>();
                    ++count;
                }
            }
            if (count > 0) {
                const double average = total / static_cast<double>(count);
                if (average >= 0.85) {
                    breakdown.evidence_quality = std::min(25, breakdown.evidence_quality + 2);
                } else if (average < 0.45) {
                    breakdown.evidence_quality = std::max(0, breakdown.evidence_quality - 4);
                    reasons.push_back("low_retrieval_scores");
                }
            }
        }
    } else {
        breakdown.evidence_quality = 4;
        reasons.push_back("unsupported_by_context");
    }

    const bool needs_human_review = json_bool(rag_result, "needs_human_review", false);
    const std::string warning = truncate_normalized(json_string(rag_result, "warning"));
    if (needs_human_review) {
        breakdown.safety = 0;
        reasons.push_back("rag_requested_human_review");
    } else if (!warning.empty()) {
        breakdown.safety = 18;
        reasons.push_back("warning_present");
    }

    if (needs_human_review || !answerable) {
        action = "human_review";
    } else if (answer.empty()) {
        action = "retry_generation";
    } else if (used_chunk_ids.empty()) {
        action = "retry_generation";
    } else {
        const int tentative = breakdown.total();
        if (tentative >= 75) {
            action = "release";
            final_answer = answer;
        } else if (tentative >= 55) {
            action = "retry_generation";
        } else {
            action = "human_review";
        }
    }

    return build_score_decision("server_rag", action, reasons, breakdown, final_answer);
}

json score_server_llm_path(const json& request) {
    std::vector<std::string> reasons;
    ScoreBreakdown breakdown;
    breakdown.routing_confidence = routing_points(request.value("second_router", json::object()));
    breakdown.evidence_quality = 12;
    breakdown.safety = 25;
    std::string action = "retry_generation";
    std::string final_answer;

    const auto server_llm_result = request.value("server_llm_result", json(nullptr));
    if (!server_llm_result.is_object()) {
        reasons.push_back("missing_server_llm_result");
        breakdown.evidence_quality = 0;
        return build_score_decision("server_llm", action, reasons, breakdown, final_answer);
    }

    const std::string answer = truncate_normalized(json_string(server_llm_result, "answer"));
    bool reference_like_question = is_reference_like(json_string(request, "original_question"));
    const std::string answer_lowered = to_lower_ascii(answer);
    const bool risky_content = contains_any_lowered(answer_lowered, kRiskyContentKeywords);
    const bool unsafe_override = contains_any_lowered(answer_lowered, kUnsafeOverrideKeywords);

    const auto second_router = request.value("second_router", json::object());
    if (second_router.is_object() && json_string(second_router, "route") == "server_rag") {
        reference_like_question = true;
        reasons.push_back("second_router_prefers_rag");
    }

    if (reference_like_question) {
        reasons.push_back("reference_grounding_needed");
        breakdown.evidence_quality = 0;
        action = "reroute_to_rag";
    } else if (unsafe_override) {
        reasons.push_back("unsafe_override_detected");
        breakdown.safety = 0;
        breakdown.evidence_quality = 0;
        action = "block";
    } else if (json_bool(server_llm_result, "needs_human_review", false) || risky_content) {
        reasons.push_back("human_review_required");
        breakdown.safety = 0;
        action = "human_review";
    }

    if (!answer.empty()) {
        breakdown.answer_quality = answer.size() >= 20 ? 18 : 10;
        breakdown.format_quality = 10;
    } else {
        reasons.push_back("empty_answer");
    }

    if (action == "retry_generation" || action == "release") {
        if (breakdown.total() >= 70) {
            action = "release";
            final_answer = answer;
        } else {
            action = "retry_generation";
        }
    }

    return build_score_decision("server_llm", action, reasons, breakdown, final_answer);
}

json final_score_snapshot(const json& score_result) {
    const auto display = ensure_object(score_result.at("display"));
    const auto decision = ensure_object(score_result.at("decision"));
    return json{
        {"final_score", display.at("final_score")},
        {"action", display.at("action")},
        {"brief", display.at("brief")},
        {"reasons", display.at("reasons")},
        {"final_answer", decision.value("final_answer", json(nullptr))},
    };
}

}  // namespace

nlohmann::json PipelineService::route(const nlohmann::json& request, bool debug) const {
    const auto normalized = normalize_router_input(request);
    json trace = json::array();
    trace.push_back(trace_entry(
        "normalize",
        "passed",
        "Input was normalized and server-side routing signals were extracted.",
        normalized.detected_signals.to_json()
    ));

    RouterDecision decision;
    std::string decision_source = "fallback";
    const bool upstream_rag = upstream_prefers_rag(normalized.metadata);

    if (config_.router_model_enabled) {
        try {
            const std::string user_prompt = build_router_user_prompt_payload(normalized).dump(2, ' ', false, json::error_handler_t::replace);
            const std::string raw_response = chat_completion(
                config_.router_model_endpoint,
                config_.router_model_name,
                config_.router_system_prompt,
                user_prompt,
                config_.router_temperature,
                config_.router_max_tokens,
                config_.router_reasoning_mode,
                config_.router_reasoning_budget,
                config_.request_timeout
            );
            const json parsed = parse_json_body(extract_json_text(raw_response));
            decision = decision_from_model_output(normalized, parsed);
            decision_source = "model";
            trace.push_back(trace_entry(
                "model",
                "generated",
                "Model produced a server routing decision.",
                json{{"route", decision.route}, {"confidence", decision.confidence}}
            ));
        } catch (const std::exception& exc) {
            trace.push_back(trace_entry(
                "model",
                "failed",
                "Model output was invalid and the server router fell back to deterministic routing.",
                json{{"error", exc.what()}}
            ));
            decision = fallback_decision(normalized);
            trace.push_back(trace_entry(
                "fallback",
                "applied",
                "Fallback applied a deterministic RAG-vs-LLM route.",
                json{{"route", decision.route}}
            ));
        }
    } else {
        decision = fallback_decision(normalized);
        trace.push_back(trace_entry(
            "fallback",
            "applied",
            "Fallback applied a deterministic RAG-vs-LLM route.",
            json{{"route", decision.route}}
        ));
    }

    if (upstream_rag && decision.route == "server_llm") {
        std::vector<std::string> reasons = decision.reason_codes;
        reasons.push_back("upstream_first_router_rag");
        decision = RouterDecision{
            "server_rag",
            true,
            decision.confidence == "low" ? "medium" : decision.confidence,
            reasons,
            decision.summary_for_handoff.empty() ? normalized.user_message : decision.summary_for_handoff,
            decision.retrieval_query.empty()
                ? truncate_normalized(
                    decision.summary_for_handoff.empty() ? normalized.user_message : decision.summary_for_handoff
                )
                : decision.retrieval_query,
        };
        trace.push_back(trace_entry(
            "post_policy",
            "overridden",
            "Upstream first-router RAG handoff kept the second router on the RAG path.",
            json{{"route", decision.route}}
        ));
    }

    const json handoff = build_router_handoff(normalized, decision);
    trace.push_back(trace_entry(
        "handoff",
        "generated",
        "Generated downstream handoff for the selected server route.",
        json{{"target_system", handoff.at("target_system")}, {"task_type", handoff.at("task_type")}}
    ));

    const json result = {
        {"display", build_router_display(decision)},
        {"decision_source", decision_source},
        {"decision", decision.to_json()},
        {"handoff", handoff},
        {"normalized_input", normalized.to_json()},
        {"trace", trace},
    };

    if (debug) {
        return result;
    }
    return json{
        {"display", result.at("display")},
        {"handoff", result.at("handoff")},
    };
}

nlohmann::json PipelineService::route_from_first_router(const nlohmann::json& request, bool debug) const {
    return route(adapt_first_router_input(request), debug);
}

nlohmann::json PipelineService::score(const nlohmann::json& request, bool debug) const {
    const auto metadata = ensure_object(request.value("metadata", json::object()));
    std::string request_id = truncate_normalized(json_string(request, "request_id"));
    if (request_id.empty()) {
        request_id = truncate_normalized(json_string(metadata, "request_id"));
    }
    if (request_id.empty()) {
        request_id = make_request_id();
    }

    const std::string original_question = truncate_normalized(json_string(request, "original_question"));
    if (original_question.empty()) {
        throw std::runtime_error("original_question must not be blank");
    }

    const std::string route_used = json_string(request, "route_used");
    if (route_used != "server_rag" && route_used != "server_llm") {
        throw std::runtime_error("route_used must be server_rag or server_llm");
    }

    json trace = json::array();
    trace.push_back(trace_entry(
        "normalize",
        "passed",
        "Input was normalized for deterministic final scoring.",
        json{{"request_id", request_id}, {"route_used", route_used}}
    ));

    const json normalized_input = {
        {"request_id", request_id},
        {"original_question", original_question},
        {"route_used", route_used},
        {"metadata", metadata},
        {"second_router", request.value("second_router", json(nullptr))},
        {"rag_result", request.value("rag_result", json(nullptr))},
        {"server_llm_result", request.value("server_llm_result", json(nullptr))},
    };

    const json decision = route_used == "server_rag" ? score_rag_path(normalized_input) : score_server_llm_path(normalized_input);
    trace.push_back(trace_entry(
        "evaluate",
        "applied",
        "Applied deterministic final-score policy.",
        json{{"action", decision.at("action")}, {"final_score", decision.at("final_score")}}
    ));
    trace.push_back(trace_entry(
        "decision",
        "applied",
        "Built the final score gate result.",
        json{{"reasons", decision.at("reasons")}}
    ));

    const json result = {
        {"display", build_score_display(decision)},
        {"decision", decision},
        {"normalized_input", normalized_input},
        {"trace", trace},
    };

    if (debug) {
        return result;
    }
    return json{
        {"display", result.at("display")},
        {"decision", result.at("decision")},
    };
}

nlohmann::json PipelineService::process_from_first_router(const nlohmann::json& request, bool debug) const {
    const json routing = route_from_first_router(request, true);
    const std::string original_question = routing.at("normalized_input").at("user_message").get<std::string>();
    const std::string route_used = routing.at("decision").at("route").get<std::string>();

    json execution;
    json score_payload = {
        {"original_question", original_question},
        {"route_used", route_used},
        {"second_router", routing.at("display")},
    };

    try {
        if (route_used == "server_rag") {
            const json rag_result = rag_ask_internal(json{
                {"request_id", routing.at("normalized_input").at("request_id")},
                {"question", original_question},
            });
            const json structured = rag_result.at("structured");
            const std::string answer_text = truncate_normalized(json_string(structured, "answer"));

            score_payload["rag_result"] = {
                {"answerable", structured.value("answerable", false)},
                {"answer", answer_text},
                {"used_chunk_ids", structured.value("used_chunk_ids", json::array())},
                {"needs_human_review", structured.value("needs_human_review", false)},
                {"warning", structured.value("warning", json(nullptr))},
                {"retrieved_scores", structured.value("retrieved_scores", json::array())},
            };

            execution = {
                {"target_system", "native_rag_answerer"},
                {"status", "completed"},
                {"answer", answer_text},
                {"details", {
                    {"response", rag_result.at("response")},
                    {"structured", structured},
                    {"retrieval", rag_result.at("retrieval")},
                }},
            };
        } else {
            const std::string answer = truncate_normalized(chat_completion(
                config_.answer_model_endpoint,
                config_.answer_model_name,
                config_.answer_system_prompt,
                original_question,
                config_.answer_temperature,
                config_.answer_max_tokens,
                "off",
                0,
                config_.request_timeout
            ));

            score_payload["server_llm_result"] = {
                {"answer", answer},
                {"needs_human_review", contains_any_lowered(to_lower_ascii(answer), kHumanReviewMarkers)},
                {"mentioned_references", contains_any_lowered(to_lower_ascii(answer), kReferenceMarkers)},
            };

            execution = {
                {"target_system", "server_large_llm"},
                {"status", "completed"},
                {"answer", answer},
                {"details", {
                    {"answer_model_endpoint", config_.answer_model_endpoint},
                    {"answer_model_name", config_.answer_model_name},
                }},
            };
        }
    } catch (const std::exception& exc) {
        execution = {
            {"target_system", route_used == "server_rag" ? "native_rag_answerer" : "server_large_llm"},
            {"status", "failed"},
            {"answer", nullptr},
            {"details", {
                {"error", exc.what()},
                {"endpoint", route_used == "server_rag" ? "/ask" : config_.answer_model_endpoint},
            }},
        };
    }

    json score_result;
    try {
        score_result = score(score_payload, true);
    } catch (const std::exception& exc) {
        score_result = {
            {"display", {
                {"final_score", 0},
                {"action", "retry_generation"},
                {"brief", "final-score 서비스 호출 실패"},
                {"reasons", json::array({"final_score_unavailable", exc.what()})},
            }},
            {"decision", {
                {"route_used", route_used},
                {"final_score", 0},
                {"action", "retry_generation"},
                {"reasons", json::array({"final_score_unavailable", exc.what()})},
                {"breakdown", {
                    {"routing_confidence", 0},
                    {"evidence_quality", 0},
                    {"safety", 0},
                    {"answer_quality", 0},
                    {"format_quality", 0},
                }},
                {"final_answer", nullptr},
            }},
        };
    }

    const json final_score = final_score_snapshot(score_result);
    const json result = {
        {"request_id", routing.at("normalized_input").at("request_id")},
        {"original_question", original_question},
        {"routing", routing},
        {"execution", execution},
        {"final_score", final_score},
        {"score_payload", score_payload},
        {"final_answer", final_score.value("final_answer", json(nullptr))},
    };

    if (debug) {
        return result;
    }

    return json{
        {"request_id", result.at("request_id")},
        {"original_question", result.at("original_question")},
        {"second_route", routing.at("display")},
        {"execution", execution},
        {"final_score", final_score},
        {"final_answer", result.at("final_answer")},
    };
}

nlohmann::json PipelineService::process_from_user(const nlohmann::json& request, bool debug) const {
    const json first_result = first_handle_internal(request);
    const json routed = first_result.at("routed");
    const std::string request_id = json_string(routed.at("normalized_input"), "request_id");
    const std::string original_question = json_string(routed.at("normalized_input"), "user_message");
    const std::string route = json_string(first_result.at("display"), "route");

    json server_pipeline = nullptr;
    json final_answer = nullptr;

    if (route == "server_rag" || route == "server_llm") {
        const json server_request = {
            {"request_id", request_id},
            {"original_question", original_question},
            {"metadata", routed.at("normalized_input").value("metadata", json::object())},
            {"first_router", {
                {"display", first_result.at("display")},
                {"handoff", first_result.at("handoff")},
            }},
        };
        server_pipeline = process_from_first_router(server_request, true);
        final_answer = server_pipeline.value("final_answer", json(nullptr));
    } else if (!first_result.value("execution", json(nullptr)).is_null()) {
        final_answer = first_result.at("execution").value("answer", json(nullptr));
    }

    const json result = {
        {"request_id", request_id},
        {"original_question", original_question},
        {"first_router", first_result},
        {"server_pipeline", server_pipeline},
        {"final_answer", final_answer},
    };

    if (debug) {
        return result;
    }

    return json{
        {"request_id", request_id},
        {"original_question", original_question},
        {"first_route", first_result.at("display")},
        {"first_handoff", first_result.at("handoff")},
        {"local_execution", first_result.value("execution", json(nullptr))},
        {"server_pipeline", server_pipeline.is_null() ? json(nullptr) : json{
            {"second_route", server_pipeline.at("routing").at("display")},
            {"execution", server_pipeline.at("execution")},
            {"final_score", server_pipeline.at("final_score")},
            {"final_answer", server_pipeline.value("final_answer", json(nullptr))},
        }},
        {"final_answer", final_answer},
    };
}

nlohmann::json PipelineService::health_snapshot() const {
    const bool rag_ready = !rag_corpus_chunks_.empty();
    const bool dense_ready = !rag_dense_embeddings_.empty() && rag_embedding_dim_ > 0;
    return json{
        {"status", rag_ready ? "ok" : "degraded"},
        {"engines", {
            {"first_router", "native"},
            {"transfer_robot_llm", "native"},
            {"rag_answerer", "native"},
            {"second_router", "native"},
            {"final_score", "native"},
        }},
        {"dependencies", {
            {"first_router_model_endpoint", config_.first_router_model_endpoint},
            {"transfer_robot_model_endpoint", config_.transfer_robot_model_endpoint},
            {"rag_model_endpoint", config_.rag_model_endpoint},
            {"rag_corpus_dir", config_.rag_corpus_dir},
            {"rag_index_dir", config_.rag_index_dir},
            {"rag_corpus_chunks", rag_corpus_chunks_.size()},
            {"rag_dense_vectors", dense_ready ? rag_corpus_chunks_.size() : 0},
            {"rag_embedding_dim", rag_embedding_dim_},
            {"rag_embedding_endpoint", config_.rag_embedding_endpoint},
            {"router_model_endpoint", config_.router_model_endpoint},
            {"answer_model_endpoint", config_.answer_model_endpoint},
            {"checks", {
                {"first_router_model", "not_checked"},
                {"transfer_robot_model", "not_checked"},
                {"rag_corpus_loaded", rag_ready ? "ok" : "missing"},
                {"rag_dense_index_loaded", dense_ready ? "ok" : "missing"},
                {"rag_embedding_helper", dense_ready ? "not_checked" : "not_configured"},
                {"rag_model", "not_checked"},
                {"router_model", "not_checked"},
                {"answer_model", "not_checked"},
            }},
        }},
    };
}
