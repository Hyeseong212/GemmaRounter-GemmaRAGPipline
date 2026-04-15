#include "PipelineService.h"

#include <algorithm>
#include <map>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "PipelineInternal.h"

using pipeline_internal::chat_completion;
using pipeline_internal::contains_any_lowered;
using pipeline_internal::ensure_object;
using pipeline_internal::extract_json_text;
using pipeline_internal::json;
using pipeline_internal::json_bool;
using pipeline_internal::json_string;
using pipeline_internal::json_string_array;
using pipeline_internal::make_request_id;
using pipeline_internal::normalize_whitespace;
using pipeline_internal::parse_json_body;
using pipeline_internal::trace_entry;
using pipeline_internal::to_lower_ascii;
using pipeline_internal::truncate_normalized;

namespace {

const std::regex kErrorCodePattern(R"(\b[Ee]\d{2,4}\b)");

const std::vector<std::string> kFirstPatientKeywords = {
    "patient", "환자", "맥박", "pulse", "혈압", "pressure", "spo2", "산소", "symptom", "증상",
};
const std::vector<std::string> kFirstMedicationKeywords = {
    "medication", "medicine", "drug", "dose", "dosage", "약", "약물", "복약", "투약", "처방",
};
const std::vector<std::string> kFirstTreatmentKeywords = {
    "treatment", "therapy", "diagnosis", "diagnostic", "치료", "진단", "처치", "중단", "계속 써도", "계속 사용",
};
const std::vector<std::string> kFirstOverrideKeywords = {
    "override", "ignore", "bypass", "force", "무시", "우회", "강제로",
};
const std::vector<std::string> kFirstStatusKeywords = {
    "battery", "status", "serial", "version", "wifi", "network", "temperature",
    "배터리", "상태", "잔량", "전원", "시리얼", "버전", "네트워크", "온도",
};
const std::vector<std::string> kFirstVisualKeywords = {
    "photo", "image", "picture", "screenshot", "screen shot", "사진", "이미지", "스크린샷", "캡처", "캡쳐", "첨부",
};
const std::vector<std::string> kFirstManualKeywords = {
    "manual", "procedure", "sop", "reference", "document", "guide", "meaning", "what does", "how should",
    "매뉴얼", "절차", "문서", "레퍼런스", "참고자료", "설명서", "사용설명서", "의미", "조치",
};
const std::vector<std::string> kFirstDeviceKeywords = {
    "device", "equipment", "instrument", "robot",
    "장비", "기기", "기계", "기구", "분석기", "측정기", "검사지", "로봇",
};
const std::vector<std::string> kFirstOperationalReferenceKeywords = {
    "charge", "charging", "measure", "measurement", "clean", "cleaning", "disinfect", "storage",
    "replace", "insert", "remove", "reuse", "expiration", "expiry", "strip",
    "충전", "측정", "세척", "소독", "보관", "교체", "삽입", "제거", "재사용", "유효기간", "검사지",
    "주의사항", "확인사항", "사용방법", "사용법", "사용 중", "사용후",
};
const std::vector<std::string> kFirstPermissionKeywords = {
    "can i", "can we", "is it ok", "allowed", "should i", "should we", "safe to",
    "해도", "써도", "되나", "되나요", "가능", "괜찮", "금지", "주의", "확인해야",
};
const std::vector<std::string> kFirstProcedureCueKeywords = {
    "how to", "step", "steps", "sequence", "before use", "during use", "after use",
    "어떻게", "순서", "단계", "전에는", "사용전", "사용중", "사용후", "먼저", "다음",
};
const std::vector<std::string> kFirstShortReplyKeywords = {
    "간단히", "짧게", "짧은", "한줄", "한 줄", "한문장", "한 문장", "한마디", "20글자", "20자",
    "멘트", "안내멘트", "안내 멘트", "음성안내", "tts", "답만",
};
const std::vector<std::string> kFirstShortReplySuffixes = {
    "돼?", "되나?", "되나요?", "가능해?", "가능해요?", "괜찮아?", "괜찮나요?", "맞아?", "맞나요?",
};
const std::vector<std::string> kFirstComplexReasoningKeywords = {
    "compare", "comparison", "why", "analyze", "analysis", "tradeoff", "pros and cons", "summarize",
    "explain in detail", "difference", "비교", "왜", "분석", "장단점", "정리", "자세히", "상세히", "차이", "원리",
};

json first_make_decision(
    const std::string& intent,
    const std::string& risk_level,
    const std::string& route,
    bool needs_human_review,
    bool patient_related,
    const std::string& priority,
    const std::vector<std::string>& required_tools,
    const std::vector<std::string>& reason_codes,
    const std::string& summary_for_server,
    const std::string& local_action
) {
    return json{
        {"intent", intent},
        {"risk_level", risk_level},
        {"route", route},
        {"needs_human_review", needs_human_review},
        {"patient_related", patient_related},
        {"priority", priority},
        {"required_tools", required_tools},
        {"reason_codes", reason_codes},
        {"summary_for_server", truncate_normalized(summary_for_server)},
        {"local_action", local_action},
    };
}

std::string first_summary(const json& normalized_request, const std::string& summary_for_server) {
    if (!truncate_normalized(summary_for_server).empty()) {
        return truncate_normalized(summary_for_server);
    }
    return truncate_normalized(json_string(normalized_request, "user_message"));
}

json first_request_metadata(const json& normalized_request) {
    const std::string request_id = json_string(normalized_request, "request_id");
    const std::string question = json_string(normalized_request, "user_message");
    return json{
        {"request_id", request_id},
        {"question", question},
        {"original_question", question},
    };
}

std::string first_local_rule_brief(const std::string& local_action) {
    if (local_action == "respond_with_device_api") {
        return "로컬 장비 API로 바로 처리";
    }
    if (local_action == "show_cached_error_help") {
        return "오프라인 캐시 안내로 처리";
    }
    if (local_action == "show_limited_mode_notice") {
        return "제한 모드 안내로 처리";
    }
    if (local_action == "handoff_to_operator") {
        return "사람 검토로 넘김";
    }
    if (local_action == "block_and_warn") {
        return "정책 경고 후 차단";
    }
    return "로컬 규칙으로 처리";
}

json first_build_display(const std::string& decision_source, const json& decision, const json& handoff) {
    static const std::map<std::string, std::string> brief_map = {
        {"local_llm", "20자 이내 로컬 답변으로 처리"},
        {"server_rag", "문서 근거가 필요해 RAG로 전달"},
        {"server_llm", "설명형 일반 질문이라 서버 LLM으로 전달"},
        {"human_review", "자동 처리 대신 사람 검토가 필요함"},
        {"block", "안전 정책상 요청을 차단함"},
    };
    const std::string route = json_string(decision, "route");
    std::string brief = first_local_rule_brief(json_string(decision, "local_action"));
    auto iter = brief_map.find(route);
    if (iter != brief_map.end()) {
        brief = iter->second;
    }
    return json{
        {"route", route},
        {"decision_source", decision_source},
        {"brief", brief},
        {"target_system", json_string(handoff, "target_system")},
        {"reason_codes", decision.value("reason_codes", json::array())},
    };
}

json first_compact_handoff(const json& handoff) {
    return json{
        {"route", handoff.at("route")},
        {"target_system", handoff.at("target_system")},
        {"task_type", handoff.at("task_type")},
        {"summary", handoff.at("summary")},
        {"required_inputs", handoff.at("required_inputs")},
        {"metadata", handoff.at("metadata")},
    };
}

json first_build_handoff(const json& normalized_request, const json& decision) {
    const std::string route = json_string(decision, "route");
    const std::string summary = first_summary(normalized_request, json_string(decision, "summary_for_server"));

    if (route == "local_llm") {
        return json{
            {"route", "local_llm"},
            {"target_system", "local_gemma_answerer"},
            {"task_type", "short_general_answer"},
            {"summary", summary},
            {"instructions", json::array({
                "Answer with the local on-device model only.",
                "Keep the final Korean answer within 20 characters.",
                "If the answer will exceed 20 characters, reroute to server_llm.",
            })},
            {"required_inputs", json::array({"user_message"})},
            {"must_extract", json::array({"short_answer", "answer_char_count"})},
            {"must_not_do", json::array({
                "Do not invent manual or SOP facts.",
                "Do not provide diagnosis, treatment, or medication advice.",
            })},
            {"escalation_triggers", json::array({
                "Answer exceeds 20 Korean characters",
                "Question actually needs grounded reference lookup",
            })},
            {"metadata", json{
                {"request_id", json_string(normalized_request, "request_id")},
                {"question", json_string(normalized_request, "user_message")},
                {"original_question", json_string(normalized_request, "user_message")},
                {"max_answer_chars", 20},
                {"overflow_route", "server_llm"},
            }},
        };
    }

    if (route == "server_rag") {
        std::string retrieval_query = summary;
        for (const auto& code : json_string_array(normalized_request.at("detected_signals").value("error_codes", json::array()))) {
            if (retrieval_query.empty()) {
                retrieval_query = code;
            } else {
                retrieval_query = code + " " + retrieval_query;
            }
        }

        return json{
            {"route", "server_rag"},
            {"target_system", "rag_reference_api"},
            {"task_type", "grounded_reference_lookup"},
            {"summary", summary},
            {"instructions", json::array({
                "Retrieve reference context before answering.",
                "Answer only from grounded retrieved material.",
            })},
            {"required_inputs", json::array({"user_message", "retrieved_context"})},
            {"must_extract", json::array({"grounded_answer", "source_file_names", "source_page_labels"})},
            {"must_not_do", json::array({
                "Do not answer from memory alone.",
                "Do not provide diagnosis, treatment, or medication advice.",
            })},
            {"escalation_triggers", json::array({
                "No supporting reference found",
                "Question becomes patient-specific",
            })},
            {"metadata", json{
                {"request_id", json_string(normalized_request, "request_id")},
                {"question", json_string(normalized_request, "user_message")},
                {"original_question", json_string(normalized_request, "user_message")},
                {"retrieval_query", truncate_normalized(retrieval_query)},
                {"api_contract", json{
                    {"endpoint", "/ask"},
                    {"request_json", json{{"question", json_string(normalized_request, "user_message")}}},
                    {"response_key", "answer"},
                }},
            }},
        };
    }

    if (route == "server_llm") {
        return json{
            {"route", "server_llm"},
            {"target_system", "server_large_llm"},
            {"task_type", "general_answer_generation"},
            {"summary", summary},
            {"instructions", json::array({
                "Answer the general question with the server-scale model.",
                "Keep the answer concise unless the user explicitly asks for detail.",
            })},
            {"required_inputs", json::array({"user_message"})},
            {"must_extract", json::array({"final_answer"})},
            {"must_not_do", json::array({
                "Do not pretend the answer is retrieval-grounded when it is not.",
                "Do not provide diagnosis, treatment, or medication advice.",
            })},
            {"escalation_triggers", json::array({
                "Question turns out to need reference grounding",
                "Question turns out to need human review",
            })},
            {"metadata", first_request_metadata(normalized_request)},
        };
    }

    if (route == "human_review") {
        return json{
            {"route", "human_review"},
            {"target_system", "operator_review_queue"},
            {"task_type", "operator_escalation"},
            {"summary", summary},
            {"instructions", json::array({
                "Show the original request, route, and reason codes to the operator.",
                "Require operator confirmation before answering.",
            })},
            {"required_inputs", json::array({"user_message", "decision", "reason_codes"})},
            {"must_extract", json::array({"review_reason", "recommended_next_step"})},
            {"must_not_do", json::array({"Do not auto-answer without operator review."})},
            {"escalation_triggers", json::array({"Any patient-specific or visually ambiguous outcome"})},
            {"metadata", json{
                {"request_id", json_string(normalized_request, "request_id")},
                {"question", json_string(normalized_request, "user_message")},
                {"original_question", json_string(normalized_request, "user_message")},
                {"priority", json_string(decision, "priority")},
                {"has_image", json_bool(normalized_request, "has_image", false)},
            }},
        };
    }

    if (route == "block") {
        return json{
            {"route", "block"},
            {"target_system", "policy_blocker"},
            {"task_type", "unsafe_request_refusal"},
            {"summary", summary},
            {"instructions", json::array({
                "Refuse the request with the approved warning copy.",
                "Log the unsafe request without continuing downstream.",
            })},
            {"required_inputs", json::array({"decision", "reason_codes"})},
            {"must_extract", json::array({"warning_copy_variant"})},
            {"must_not_do", json::array({"Do not call any downstream answer pipeline."})},
            {"escalation_triggers", json::array({"Repeated override attempts"})},
            {"metadata", json{
                {"request_id", json_string(normalized_request, "request_id")},
                {"question", json_string(normalized_request, "user_message")},
                {"original_question", json_string(normalized_request, "user_message")},
                {"priority", json_string(decision, "priority")},
            }},
        };
    }

    std::string task_type = "local_fallback";
    const std::string local_action = json_string(decision, "local_action");
    if (local_action == "respond_with_device_api") {
        task_type = "local_device_status";
    } else if (local_action == "show_cached_error_help") {
        task_type = "cached_error_help";
    } else if (local_action == "show_limited_mode_notice") {
        task_type = "limited_mode_notice";
    }

    return json{
        {"route", route},
        {"target_system", "local_device_stack"},
        {"task_type", task_type},
        {"summary", summary},
        {"instructions", json::array({"Resolve the request using deterministic local logic only."})},
        {"required_inputs", decision.value("required_tools", json::array())},
        {"must_extract", json::array({"local_execution_result"})},
        {"must_not_do", json::array({"Do not call remote reasoning services from this path."})},
        {"escalation_triggers", json::array({"Required local tool unavailable"})},
        {"metadata", json{
            {"request_id", json_string(normalized_request, "request_id")},
            {"question", json_string(normalized_request, "user_message")},
            {"original_question", json_string(normalized_request, "user_message")},
            {"local_action", local_action},
        }},
    };
}

json first_extract_signals(const json& request) {
    const std::string message = json_string(request, "user_message");
    const std::string lowered = to_lower_ascii(message);
    std::vector<std::string> error_codes;
    for (std::sregex_iterator iter(message.begin(), message.end(), kErrorCodePattern), end; iter != end; ++iter) {
        std::string code = iter->str();
        std::transform(code.begin(), code.end(), code.begin(), [](unsigned char ch) {
            return static_cast<char>(std::toupper(ch));
        });
        if (std::find(error_codes.begin(), error_codes.end(), code) == error_codes.end()) {
            error_codes.push_back(code);
        }
    }

    const bool has_image = json_bool(request, "has_image", false);
    const bool patient_related = contains_any_lowered(lowered, kFirstPatientKeywords);
    const bool medication_related = contains_any_lowered(lowered, kFirstMedicationKeywords);
    const bool treatment_related = contains_any_lowered(lowered, kFirstTreatmentKeywords);
    const bool override_related = contains_any_lowered(lowered, kFirstOverrideKeywords);
    const bool visual_related = has_image || contains_any_lowered(lowered, kFirstVisualKeywords);
    const bool status_related = error_codes.empty() && contains_any_lowered(lowered, kFirstStatusKeywords);
    const bool device_related =
        contains_any_lowered(lowered, kFirstDeviceKeywords) ||
        contains_any_lowered(lowered, kFirstOperationalReferenceKeywords);
    const bool permission_or_safety_question = contains_any_lowered(lowered, kFirstPermissionKeywords);
    const bool procedural_operation_question = contains_any_lowered(lowered, kFirstProcedureCueKeywords);
    const bool operational_reference_question =
        device_related &&
        (permission_or_safety_question || procedural_operation_question);
    const bool reference_grounding_required =
        !error_codes.empty() ||
        contains_any_lowered(lowered, kFirstManualKeywords) ||
        operational_reference_question;
    bool short_answer_expected = contains_any_lowered(lowered, kFirstShortReplyKeywords);
    for (const auto& suffix : kFirstShortReplySuffixes) {
        if (lowered.size() >= suffix.size() && lowered.rfind(to_lower_ascii(suffix)) == lowered.size() - suffix.size()) {
            short_answer_expected = true;
            break;
        }
    }
    const bool complex_reasoning_requested =
        contains_any_lowered(lowered, kFirstComplexReasoningKeywords) || message.size() >= 120;
    const bool general_question_candidate =
        !patient_related &&
        !medication_related &&
        !treatment_related &&
        !override_related &&
        !visual_related &&
        !status_related &&
        !reference_grounding_required;

    return json{
        {"error_codes", error_codes},
        {"patient_related", patient_related},
        {"medication_related", medication_related},
        {"treatment_related", treatment_related},
        {"override_related", override_related},
        {"visual_related", visual_related},
        {"status_related", status_related},
        {"device_related", device_related},
        {"permission_or_safety_question", permission_or_safety_question},
        {"procedural_operation_question", procedural_operation_question},
        {"operational_reference_question", operational_reference_question},
        {"general_question_candidate", general_question_candidate},
        {"complex_reasoning_requested", complex_reasoning_requested},
        {"short_answer_expected", short_answer_expected},
        {"reference_grounding_required", reference_grounding_required},
        {"network_limited", json_string(request, "network_status", "online") != "online"},
    };
}

json normalize_first_router_input(const json& request) {
    const auto metadata = ensure_object(request.value("metadata", json::object()));
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

    json local_tools = request.value("local_tools_available", json::array({"device_status_api", "cached_error_help"}));
    if (!local_tools.is_array()) {
        local_tools = json::array({"device_status_api", "cached_error_help"});
    }

    return json{
        {"request_id", request_id},
        {"user_message", user_message},
        {"has_image", json_bool(request, "has_image", false)},
        {"network_status", json_string(request, "network_status", "online")},
        {"local_tools_available", json_string_array(local_tools)},
        {"metadata", metadata},
        {"detected_signals", first_extract_signals(json{
            {"user_message", user_message},
            {"has_image", json_bool(request, "has_image", false)},
            {"network_status", json_string(request, "network_status", "online")},
        })},
    };
}

json first_build_router_user_prompt_payload(const json& request) {
    return json{
        {"request_id", request.at("request_id")},
        {"user_message", request.at("user_message")},
        {"network_status", request.at("network_status")},
        {"detected_signals", {
            {"error_codes", request.at("detected_signals").at("error_codes")},
            {"reference_grounding_required", request.at("detected_signals").at("reference_grounding_required")},
            {"short_answer_expected", request.at("detected_signals").at("short_answer_expected")},
            {"complex_reasoning_requested", request.at("detected_signals").at("complex_reasoning_requested")},
            {"general_question_candidate", request.at("detected_signals").at("general_question_candidate")},
        }},
        {"route_rules", {
            {"local_llm", "Use only when the final Korean answer is likely to stay within 20 characters."},
            {"server_rag", "Use when manuals, SOPs, reference documents, or error-code grounding are needed."},
            {"server_llm", "Use for general answers likely to exceed 20 characters or requiring explanation."},
            {"human_review", "Use when the request is unsafe, ambiguous, image-based, or should not be auto-routed."},
            {"block", "Use only for unsafe override or bypass intent."},
        }},
        {"task", "Return the smallest valid routing JSON for this unresolved request."},
    };
}

json first_build_local_answer_prompt_payload(const json& request, int max_answer_chars) {
    return json{
        {"request_id", request.at("request_id")},
        {"user_message", request.at("user_message")},
        {"answer_rules", {
            {"language", "ko-KR"},
            {"max_answer_chars", max_answer_chars},
            {"style", "short robot guidance or acknowledgement"},
            {"output", "Return only the final Korean answer text."},
        }},
    };
}

json first_hard_rule_match(const json& normalized_request) {
    const auto signals = normalized_request.at("detected_signals");
    const bool patient_related = json_bool(signals, "patient_related", false);
    const bool medication_related = json_bool(signals, "medication_related", false);
    const bool treatment_related = json_bool(signals, "treatment_related", false);
    const bool override_related = json_bool(signals, "override_related", false);
    const bool status_related = json_bool(signals, "status_related", false);
    const bool visual_related = json_bool(signals, "visual_related", false);
    const bool reference_grounding_required = json_bool(signals, "reference_grounding_required", false);
    const bool network_limited = json_bool(signals, "network_limited", false);
    const bool general_question_candidate = json_bool(signals, "general_question_candidate", false);
    const bool short_answer_expected = json_bool(signals, "short_answer_expected", false);
    const bool has_image = json_bool(normalized_request, "has_image", false);
    const auto local_tools = json_string_array(normalized_request.value("local_tools_available", json::array()));
    const auto error_codes = json_string_array(signals.value("error_codes", json::array()));

    auto has_tool = [&](const std::string& tool) {
        return std::find(local_tools.begin(), local_tools.end(), tool) != local_tools.end();
    };

    if (override_related && (medication_related || treatment_related)) {
        return json{
            {"applied", true},
            {"rule_name", "block_contraindication_override"},
            {"detail", "Unsafe override wording was blocked before model execution."},
            {"decision", first_make_decision(
                "contraindication_override_request",
                "forbidden",
                "block",
                true,
                patient_related,
                "critical",
                {},
                {"contraindication_override", "unsafe_override_request"},
                json_string(normalized_request, "user_message"),
                "block_and_warn"
            )},
        };
    }

    if (medication_related) {
        return json{
            {"applied", true},
            {"rule_name", "escalate_medication_question"},
            {"detail", "Medication-related request was escalated before model execution."},
            {"decision", first_make_decision(
                "medication_advice_request",
                "high",
                "human_review",
                true,
                true,
                "critical",
                {},
                {"medication_or_treatment_change", "requires_operator_confirmation"},
                json_string(normalized_request, "user_message"),
                "handoff_to_operator"
            )},
        };
    }

    if (treatment_related || patient_related) {
        return json{
            {"applied", true},
            {"rule_name", "escalate_clinical_risk"},
            {"detail", "Patient-specific or treatment-related request was escalated before model execution."},
            {"decision", first_make_decision(
                "clinical_risk_question",
                "high",
                "human_review",
                true,
                true,
                "critical",
                {},
                {"patient_specific_clinical_judgment", "requires_operator_confirmation"},
                json_string(normalized_request, "user_message"),
                "handoff_to_operator"
            )},
        };
    }

    if (status_related) {
        if (has_tool("device_status_api")) {
            return json{
                {"applied", true},
                {"rule_name", "use_local_device_status"},
                {"detail", "Deterministic status question was routed to the local device API."},
                {"decision", first_make_decision(
                    "device_status_question",
                    "low",
                    "local_rule_only",
                    false,
                    false,
                    "normal",
                    {"device_status_api"},
                    {"local_status_available"},
                    "",
                    "respond_with_device_api"
                )},
            };
        }

        return json{
            {"applied", true},
            {"rule_name", "escalate_missing_status_tool"},
            {"detail", "Realtime status question cannot be answered without the local device API."},
            {"decision", first_make_decision(
                "device_status_question",
                "medium",
                "human_review",
                true,
                false,
                "high",
                {},
                {"requires_operator_confirmation"},
                json_string(normalized_request, "user_message"),
                "handoff_to_operator"
            )},
        };
    }

    if (has_image || visual_related) {
        return json{
            {"applied", true},
            {"rule_name", "escalate_visual_request"},
            {"detail", "Image or screen-reading requests were kept out of the small local router harness."},
            {"decision", first_make_decision(
                "unknown",
                "medium",
                "human_review",
                true,
                false,
                "high",
                {},
                {"requires_operator_confirmation"},
                json_string(normalized_request, "user_message"),
                "handoff_to_operator"
            )},
        };
    }

    if (reference_grounding_required) {
        if (network_limited) {
            if (!error_codes.empty() && has_tool("cached_error_help")) {
                return json{
                    {"applied", true},
                    {"rule_name", "offline_cached_error_help"},
                    {"detail", "Offline reference question with an error code was downgraded to cached local guidance."},
                    {"decision", first_make_decision(
                        "device_error_question",
                        "medium",
                        "local_rule_only",
                        false,
                        false,
                        "high",
                        {"cached_error_help"},
                        {"needs_reference_grounding", "network_limited_mode"},
                        "",
                        "show_cached_error_help"
                    )},
                };
            }

            return json{
                {"applied", true},
                {"rule_name", "offline_reference_limited_mode"},
                {"detail", "Offline reference question stayed on device in limited mode."},
                {"decision", first_make_decision(
                    "manual_procedure_question",
                    "medium",
                    "local_rule_only",
                    false,
                    false,
                    "high",
                    {},
                    {"needs_reference_grounding", "network_limited_mode"},
                    "",
                    "show_limited_mode_notice"
                )},
            };
        }

        return json{
            {"applied", true},
            {"rule_name", "route_reference_question_to_rag"},
            {"detail", "Reference-grounded request was routed directly to RAG before model execution."},
            {"decision", first_make_decision(
                error_codes.empty() ? "manual_procedure_question" : "device_error_question",
                "medium",
                "server_rag",
                false,
                false,
                "high",
                {"manual_retrieval"},
                {"needs_reference_grounding"},
                json_string(normalized_request, "user_message"),
                "none"
            )},
        };
    }

    if (general_question_candidate && short_answer_expected) {
        return json{
            {"applied", true},
            {"rule_name", "use_local_llm_for_short_general_question"},
            {"detail", "Short general question was routed directly to the local LLM path."},
            {"decision", first_make_decision(
                "general_question",
                "low",
                "local_llm",
                false,
                false,
                "normal",
                {},
                {"local_general_answer_ok"},
                "",
                "answer_with_local_llm"
            )},
        };
    }

    if (network_limited) {
        return json{
            {"applied", true},
            {"rule_name", "offline_limited_mode_notice"},
            {"detail", "Offline non-short request stayed on device in limited mode."},
            {"decision", first_make_decision(
                "unknown",
                "medium",
                "local_rule_only",
                false,
                false,
                "high",
                {},
                {"network_limited_mode"},
                "",
                "show_limited_mode_notice"
            )},
        };
    }

    return json{{"applied", false}};
}

json first_fallback_decision(const json& normalized_request) {
    const auto signals = normalized_request.at("detected_signals");
    const bool reference_grounding_required = json_bool(signals, "reference_grounding_required", false);
    const bool network_limited = json_bool(signals, "network_limited", false);
    const bool short_answer_expected = json_bool(signals, "short_answer_expected", false);
    const auto error_codes = json_string_array(signals.value("error_codes", json::array()));
    const auto local_tools = json_string_array(normalized_request.value("local_tools_available", json::array()));

    auto has_tool = [&](const std::string& tool) {
        return std::find(local_tools.begin(), local_tools.end(), tool) != local_tools.end();
    };

    if (reference_grounding_required) {
        if (network_limited) {
            if (!error_codes.empty() && has_tool("cached_error_help")) {
                return first_make_decision(
                    "device_error_question",
                    "medium",
                    "local_rule_only",
                    false,
                    false,
                    "high",
                    {"cached_error_help"},
                    {"needs_reference_grounding", "network_limited_mode"},
                    "",
                    "show_cached_error_help"
                );
            }
            return first_make_decision(
                "manual_procedure_question",
                "medium",
                "local_rule_only",
                false,
                false,
                "high",
                {},
                {"needs_reference_grounding", "network_limited_mode"},
                "",
                "show_limited_mode_notice"
            );
        }
        return first_make_decision(
            "manual_procedure_question",
            "medium",
            "server_rag",
            false,
            false,
            "high",
            {"manual_retrieval"},
            {"needs_reference_grounding"},
            json_string(normalized_request, "user_message"),
            "none"
        );
    }

    if (json_bool(signals, "general_question_candidate", false) && short_answer_expected) {
        return first_make_decision(
            "general_question",
            "low",
            "local_llm",
            false,
            false,
            "normal",
            {},
            {"local_general_answer_ok"},
            "",
            "answer_with_local_llm"
        );
    }

    if (json_string(normalized_request, "network_status", "online") == "online") {
        return first_make_decision(
            "general_question",
            "low",
            "server_llm",
            false,
            false,
            "normal",
            {"server_large_llm"},
            {"needs_large_model_reasoning"},
            json_string(normalized_request, "user_message"),
            "none"
        );
    }

    return first_make_decision(
        "unknown",
        "medium",
        "local_rule_only",
        false,
        false,
        "high",
        {},
        {"network_limited_mode", "unknown_request_type"},
        "",
        "show_limited_mode_notice"
    );
}

json first_decision_from_model_output(const json& normalized_request, const json& parsed) {
    const auto signals = normalized_request.at("detected_signals");
    const std::string route = json_string(parsed, "route");
    const std::string summary = first_summary(normalized_request, json_string(parsed, "summary_for_server"));
    const bool patient_related = json_bool(signals, "patient_related", false);
    const auto error_codes = json_string_array(signals.value("error_codes", json::array()));

    if (route == "local_llm") {
        return first_make_decision("general_question", "low", "local_llm", false, false, "normal", {}, {"local_general_answer_ok"}, "", "answer_with_local_llm");
    }
    if (route == "server_rag") {
        return first_make_decision(error_codes.empty() ? "manual_procedure_question" : "device_error_question", "medium", "server_rag", false, false, "high", {"manual_retrieval"}, {"needs_reference_grounding"}, summary, "none");
    }
    if (route == "server_llm") {
        return first_make_decision("general_question", "low", "server_llm", false, false, "normal", {"server_large_llm"}, {"needs_large_model_reasoning"}, summary, "none");
    }
    if (route == "block") {
        return first_make_decision("contraindication_override_request", "forbidden", "block", true, patient_related, "critical", {}, {"contraindication_override", "unsafe_override_request"}, summary, "block_and_warn");
    }
    return first_make_decision(patient_related ? "clinical_risk_question" : "unknown", patient_related ? "high" : "medium", "human_review", true, patient_related, patient_related ? "critical" : "high", {}, {"requires_operator_confirmation"}, summary, "handoff_to_operator");
}

json first_stabilize_decision(const json& normalized_request, const json& decision) {
    json current = decision;
    current["summary_for_server"] = first_summary(normalized_request, json_string(decision, "summary_for_server"));
    std::vector<std::string> required_tools = json_string_array(decision.value("required_tools", json::array()));
    if (json_string(decision, "route") == "server_rag" && required_tools.empty()) {
        required_tools.push_back("manual_retrieval");
    } else if (json_string(decision, "route") == "server_llm" && required_tools.empty()) {
        required_tools.push_back("server_large_llm");
    }
    current["required_tools"] = required_tools;
    return current;
}

json first_apply_post_policies(const json& normalized_request, const json& original_decision, json& traces) {
    json current = first_stabilize_decision(normalized_request, original_decision);
    if (current != original_decision) {
        traces.push_back(trace_entry("post_policy", "overridden", "Filled minimal downstream fields from the chosen route."));
    }

    const auto signals = normalized_request.at("detected_signals");
    const bool patient_related = json_bool(signals, "patient_related", false);
    const bool medication_related = json_bool(signals, "medication_related", false);
    const bool treatment_related = json_bool(signals, "treatment_related", false);
    const bool override_related = json_bool(signals, "override_related", false);
    const bool visual_related = json_bool(signals, "visual_related", false);
    const bool network_limited = json_bool(signals, "network_limited", false);
    const bool short_answer_expected = json_bool(signals, "short_answer_expected", false);
    const bool has_image = json_bool(normalized_request, "has_image", false);

    if (override_related && (medication_related || treatment_related) && json_string(current, "route") != "block") {
        current = first_make_decision("contraindication_override_request", "forbidden", "block", true, patient_related, "critical", {}, {"contraindication_override", "unsafe_override_request"}, json_string(normalized_request, "user_message"), "block_and_warn");
        traces.push_back(trace_entry("post_policy", "overridden", "Unsafe override language forced the request to block."));
    }

    if ((patient_related || medication_related || treatment_related) && json_string(current, "route") != "human_review" && json_string(current, "route") != "block") {
        std::vector<std::string> reason_codes = json_string_array(current.value("reason_codes", json::array()));
        reason_codes.push_back("patient_specific_clinical_judgment");
        reason_codes.push_back("requires_operator_confirmation");
        current = first_make_decision(medication_related ? "medication_advice_request" : "clinical_risk_question", "high", "human_review", true, true, "critical", {}, reason_codes, first_summary(normalized_request, json_string(current, "summary_for_server")), "handoff_to_operator");
        traces.push_back(trace_entry("post_policy", "overridden", "Patient-specific content was escalated to human review."));
    }

    if ((has_image || visual_related) && json_string(current, "route") != "human_review" && json_string(current, "route") != "block") {
        std::vector<std::string> reason_codes = json_string_array(current.value("reason_codes", json::array()));
        reason_codes.push_back("requires_operator_confirmation");
        current = first_make_decision("unknown", "medium", "human_review", true, false, "high", {}, reason_codes, first_summary(normalized_request, json_string(current, "summary_for_server")), "handoff_to_operator");
        traces.push_back(trace_entry("post_policy", "overridden", "Visual requests were kept out of the simplified E2B routing path."));
    }

    if (json_string(current, "route") == "server_rag" && network_limited) {
        const auto error_codes = json_string_array(signals.value("error_codes", json::array()));
        const auto local_tools = json_string_array(normalized_request.value("local_tools_available", json::array()));
        const bool has_cached_error_help = std::find(local_tools.begin(), local_tools.end(), "cached_error_help") != local_tools.end();
        if (!error_codes.empty() && has_cached_error_help) {
            current = first_make_decision("device_error_question", "medium", "local_rule_only", false, false, "high", {"cached_error_help"}, {"needs_reference_grounding", "network_limited_mode"}, "", "show_cached_error_help");
            traces.push_back(trace_entry("post_policy", "overridden", "Offline RAG request was downgraded to cached local help."));
        } else {
            current = first_make_decision("manual_procedure_question", "medium", "local_rule_only", false, false, "high", {}, {"needs_reference_grounding", "network_limited_mode"}, "", "show_limited_mode_notice");
            traces.push_back(trace_entry("post_policy", "overridden", "Offline RAG request was replaced with a limited-mode notice."));
        }
    }

    if (json_string(current, "route") == "server_llm" && network_limited) {
        if (short_answer_expected) {
            current = first_make_decision("general_question", "low", "local_llm", false, false, "normal", {}, {"local_general_answer_ok", "network_limited_mode"}, "", "answer_with_local_llm");
            traces.push_back(trace_entry("post_policy", "overridden", "Offline short general question was downgraded from server LLM to local LLM."));
        } else {
            std::vector<std::string> reason_codes = json_string_array(current.value("reason_codes", json::array()));
            reason_codes.push_back("network_limited_mode");
            current = first_make_decision("unknown", "medium", "local_rule_only", false, false, "high", {}, reason_codes, "", "show_limited_mode_notice");
            traces.push_back(trace_entry("post_policy", "overridden", "Offline long general request was replaced with a limited-mode notice."));
        }
    }

    if (json_string(current, "route") == "local_llm" && !short_answer_expected) {
        if (json_string(normalized_request, "network_status", "online") == "online") {
            current = first_make_decision("general_question", "low", "server_llm", false, false, "normal", {"server_large_llm"}, {"needs_large_model_reasoning"}, first_summary(normalized_request, json_string(current, "summary_for_server")), "none");
            traces.push_back(trace_entry("post_policy", "overridden", "Local LLM was upgraded to server LLM because the 20-character budget is unlikely."));
        } else {
            current = first_make_decision("unknown", "medium", "local_rule_only", false, false, "high", {}, {"needs_large_model_reasoning", "network_limited_mode"}, "", "show_limited_mode_notice");
            traces.push_back(trace_entry("post_policy", "overridden", "Offline local LLM overflow was replaced with a limited-mode notice."));
        }
    }

    if (json_string(current, "route") == "local_rule_only") {
        const auto local_tools = json_string_array(normalized_request.value("local_tools_available", json::array()));
        std::vector<std::string> missing_tools;
        for (const auto& tool : json_string_array(current.value("required_tools", json::array()))) {
            if (std::find(local_tools.begin(), local_tools.end(), tool) == local_tools.end()) {
                missing_tools.push_back(tool);
            }
        }
        if (!missing_tools.empty()) {
            const bool online = json_string(normalized_request, "network_status", "online") == "online";
            current = first_make_decision(
                "unknown",
                "medium",
                online ? "human_review" : "local_rule_only",
                online,
                false,
                "high",
                {},
                online ? std::vector<std::string>{"requires_operator_confirmation"} : std::vector<std::string>{"network_limited_mode"},
                online ? first_summary(normalized_request, json_string(current, "summary_for_server")) : "",
                online ? "handoff_to_operator" : "show_limited_mode_notice"
            );
            traces.push_back(trace_entry("post_policy", "overridden", "Missing local tool caused rerouting away from local-only execution.", json{{"missing_tools", missing_tools}}));
        }
    }

    return current;
}

std::string first_extract_short_answer_from_json(const std::string& raw_text) {
    try {
        const json parsed = parse_json_body(extract_json_text(raw_text));
        for (const auto& key : {"short_answer", "answer", "reply", "reply_for_tts"}) {
            if (parsed.contains(key) && parsed.at(key).is_string()) {
                const std::string cleaned = truncate_normalized(parsed.at(key).get<std::string>());
                if (!cleaned.empty()) {
                    return cleaned;
                }
            }
        }
    } catch (...) {
    }
    return "";
}

std::string first_strip_answer_prefix(const std::string& text) {
    return std::regex_replace(text, std::regex(R"(^(short_answer|answer|답변)\s*:\s*)", std::regex_constants::icase), "");
}

std::string first_sanitize_local_answer(const std::string& raw_text) {
    std::string stripped = normalize_whitespace(raw_text);
    if (stripped.empty()) {
        return "";
    }
    const std::string parsed_answer = first_extract_short_answer_from_json(stripped);
    if (!parsed_answer.empty()) {
        return parsed_answer;
    }
    std::stringstream stream(stripped);
    std::string line;
    while (std::getline(stream, line)) {
        const std::string cleaned = truncate_normalized(first_strip_answer_prefix(line));
        if (!cleaned.empty()) {
            return cleaned;
        }
    }
    return "";
}

json first_build_local_execution_reroute_decision(const json& normalized_request, const std::string& reason) {
    const bool online = json_string(normalized_request, "network_status", "online") == "online";
    if (online) {
        std::vector<std::string> reason_codes = {"needs_large_model_reasoning"};
        if (reason == "local_answer_overflow") {
            reason_codes = {"local_answer_overflow", "needs_large_model_reasoning"};
        } else if (reason == "local_generation_failed") {
            reason_codes = {"local_generation_failed", "needs_large_model_reasoning"};
        }
        return first_make_decision("general_question", "low", "server_llm", false, false, "normal", {"server_large_llm"}, reason_codes, json_string(normalized_request, "user_message"), "none");
    }

    std::vector<std::string> reason_codes = {"network_limited_mode"};
    if (reason == "local_answer_overflow") {
        reason_codes = {"local_answer_overflow", "network_limited_mode"};
    } else if (reason == "local_generation_failed") {
        reason_codes = {"local_generation_failed", "network_limited_mode"};
    }
    return first_make_decision("unknown", "medium", "local_rule_only", false, false, "high", {}, reason_codes, "", "show_limited_mode_notice");
}

json first_build_local_execution_display(const json& decision, const json& handoff, const std::string& reason) {
    std::string brief = "로컬 답변이 어려워 제한 모드 안내로 처리";
    if (json_string(decision, "route") == "server_llm") {
        brief = reason == "local_answer_overflow"
            ? "로컬 답변이 20자를 넘어 서버 LLM으로 전달"
            : "로컬 답변 생성 실패로 서버 LLM으로 전달";
    }
    return json{
        {"route", json_string(decision, "route")},
        {"decision_source", "local_execution"},
        {"brief", brief},
        {"target_system", json_string(handoff, "target_system")},
        {"reason_codes", decision.value("reason_codes", json::array())},
    };
}

}  // namespace

nlohmann::json PipelineService::first_route_internal(const nlohmann::json& request) const {
    const json normalized_request = normalize_first_router_input(request);
    json trace = json::array();
    trace.push_back(trace_entry(
        "normalize",
        "passed",
        "Input was normalized and routing signals were extracted.",
        normalized_request.at("detected_signals")
    ));

    const json hard_rule_match = first_hard_rule_match(normalized_request);
    if (json_bool(hard_rule_match, "applied", false)) {
        trace.push_back(trace_entry(
            "hard_rule",
            "applied",
            json_string(hard_rule_match, "detail"),
            json{{"rule_name", hard_rule_match.at("rule_name")}}
        ));

        json policy_traces = json::array();
        const json final_decision = first_apply_post_policies(normalized_request, hard_rule_match.at("decision"), policy_traces);
        for (const auto& entry : policy_traces) {
            trace.push_back(entry);
        }

        const json handoff = first_build_handoff(normalized_request, final_decision);
        trace.push_back(trace_entry(
            "handoff",
            "generated",
            "Generated downstream execution contract for the selected route.",
            json{{"target_system", handoff.at("target_system")}, {"task_type", handoff.at("task_type")}}
        ));

        return json{
            {"display", first_build_display("hard_rule", final_decision, handoff)},
            {"decision_source", "hard_rule"},
            {"decision", final_decision},
            {"handoff", handoff},
            {"normalized_input", normalized_request},
            {"trace", trace},
        };
    }

    json model_or_fallback_traces = json::array();
    json model_decision;
    std::string decision_source = "fallback";

    if (config_.first_router_model_enabled) {
        try {
            const std::string user_prompt = first_build_router_user_prompt_payload(normalized_request).dump(2, ' ', false, json::error_handler_t::replace);
            const std::string raw_response = chat_completion(
                config_.first_router_model_endpoint,
                config_.first_router_model_name,
                config_.first_router_system_prompt,
                user_prompt,
                config_.first_router_temperature,
                config_.first_router_max_tokens,
                config_.first_router_reasoning_mode,
                config_.first_router_reasoning_budget,
                config_.first_router_request_timeout
            );
            model_decision = first_decision_from_model_output(normalized_request, parse_json_body(extract_json_text(raw_response)));
            decision_source = "model";
            model_or_fallback_traces.push_back(trace_entry(
                "model",
                "generated",
                "Model produced a compact route choice.",
                json{{"route", model_decision.at("route")}}
            ));
        } catch (const std::exception& exc) {
            model_or_fallback_traces.push_back(trace_entry(
                "model",
                "failed",
                "Model output was invalid and the router fell back to deterministic routing.",
                json{{"error", exc.what()}}
            ));
            model_decision = first_fallback_decision(normalized_request);
            model_or_fallback_traces.push_back(trace_entry(
                "fallback",
                "applied",
                "Fallback applied a deterministic minimal route.",
                json{{"route", model_decision.at("route")}}
            ));
        }
    } else {
        model_decision = first_fallback_decision(normalized_request);
        model_or_fallback_traces.push_back(trace_entry(
            "fallback",
            "applied",
            "Fallback applied a deterministic minimal route.",
            json{{"route", model_decision.at("route")}}
        ));
    }

    for (const auto& entry : model_or_fallback_traces) {
        trace.push_back(entry);
    }

    json policy_traces = json::array();
    const json final_decision = first_apply_post_policies(normalized_request, model_decision, policy_traces);
    for (const auto& entry : policy_traces) {
        trace.push_back(entry);
    }

    const json handoff = first_build_handoff(normalized_request, final_decision);
    trace.push_back(trace_entry(
        "handoff",
        "generated",
        "Generated downstream execution contract for the selected route.",
        json{{"target_system", handoff.at("target_system")}, {"task_type", handoff.at("task_type")}}
    ));

    return json{
        {"display", first_build_display(decision_source, final_decision, handoff)},
        {"decision_source", decision_source},
        {"decision", final_decision},
        {"handoff", handoff},
        {"normalized_input", normalized_request},
        {"trace", trace},
    };
}

nlohmann::json PipelineService::first_route(const nlohmann::json& request, bool debug) const {
    const json result = first_route_internal(request);
    if (debug) {
        return result;
    }
    return json{
        {"display", result.at("display")},
        {"handoff", first_compact_handoff(result.at("handoff"))},
    };
}

nlohmann::json PipelineService::first_handle_internal(const nlohmann::json& request) const {
    const json routed = first_route_internal(request);
    if (json_string(routed.at("decision"), "route") != "local_llm") {
        return json{
            {"routed", routed},
            {"display", routed.at("display")},
            {"handoff", first_compact_handoff(routed.at("handoff"))},
            {"execution", nullptr},
        };
    }

    const json normalized_request = routed.at("normalized_input");
    const json handoff = routed.at("handoff");
    const int max_answer_chars = handoff.at("metadata").value("max_answer_chars", 20);

    try {
        const std::string raw_response = chat_completion(
            config_.first_router_model_endpoint,
            config_.first_router_model_name,
            config_.first_router_local_answer_prompt,
            first_build_local_answer_prompt_payload(normalized_request, max_answer_chars).dump(2, ' ', false, json::error_handler_t::replace),
            config_.first_router_local_answer_temperature,
            config_.first_router_local_answer_max_tokens,
            config_.first_router_reasoning_mode,
            config_.first_router_reasoning_budget,
            config_.first_router_request_timeout
        );
        const std::string answer = first_sanitize_local_answer(raw_response);
        if (answer.empty()) {
            throw std::runtime_error("local_generation_failed");
        }
        if (static_cast<int>(answer.size()) > max_answer_chars) {
            const json rerouted_decision = first_build_local_execution_reroute_decision(normalized_request, "local_answer_overflow");
            const json rerouted_handoff = first_build_handoff(normalized_request, rerouted_decision);
            return json{
                {"routed", routed},
                {"display", first_build_local_execution_display(rerouted_decision, rerouted_handoff, "local_answer_overflow")},
                {"handoff", first_compact_handoff(rerouted_handoff)},
                {"execution", json{
                    {"mode", "local_llm"},
                    {"status", "rerouted"},
                    {"answer", nullptr},
                    {"answer_char_count", static_cast<int>(answer.size())},
                    {"reason", "local_answer_overflow"},
                    {"rerouted_to", json_string(rerouted_decision, "route")},
                }},
            };
        }

        return json{
            {"routed", routed},
            {"display", routed.at("display")},
            {"handoff", first_compact_handoff(routed.at("handoff"))},
            {"execution", json{
                {"mode", "local_llm"},
                {"status", "completed"},
                {"answer", answer},
                {"answer_char_count", static_cast<int>(answer.size())},
                {"reason", "completed"},
                {"rerouted_to", nullptr},
            }},
        };
    } catch (const std::exception&) {
        const json rerouted_decision = first_build_local_execution_reroute_decision(normalized_request, "local_generation_failed");
        const json rerouted_handoff = first_build_handoff(normalized_request, rerouted_decision);
        return json{
            {"routed", routed},
            {"display", first_build_local_execution_display(rerouted_decision, rerouted_handoff, "local_generation_failed")},
            {"handoff", first_compact_handoff(rerouted_handoff)},
            {"execution", json{
                {"mode", "local_llm"},
                {"status", "rerouted"},
                {"answer", nullptr},
                {"answer_char_count", nullptr},
                {"reason", "local_generation_failed"},
                {"rerouted_to", json_string(rerouted_decision, "route")},
            }},
        };
    }
}

nlohmann::json PipelineService::first_handle(const nlohmann::json& request, bool debug) const {
    const json result = first_handle_internal(request);
    if (debug) {
        return result;
    }
    return json{
        {"display", result.at("display")},
        {"handoff", result.at("handoff")},
        {"execution", result.value("execution", json(nullptr))},
    };
}
