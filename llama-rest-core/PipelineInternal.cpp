#include "PipelineInternal.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <random>
#include <regex>
#include <sstream>
#include <stdexcept>

#include "external/httplib.h"

namespace pipeline_internal {

namespace {

const std::regex kSourceLinePattern(R"(^출처:\s*(.+)$)");
const std::vector<std::string> kWarningMarkers = {
    "금지", "중지", "주의", "경고", "stop", "warning",
};

std::size_t utf8_safe_prefix_length(const std::string& input, std::size_t limit) {
    if (input.size() <= limit) {
        return input.size();
    }
    std::size_t end = limit;
    while (end > 0 && (static_cast<unsigned char>(input[end]) & 0xC0) == 0x80) {
        --end;
    }
    if (end == 0) {
        return limit;
    }
    return end;
}

}  // namespace

std::string getenv_or_default(const char* key, const std::string& default_value) {
    const char* value = std::getenv(key);
    if (!value || !*value) {
        return default_value;
    }
    return std::string(value);
}

bool getenv_or_default_bool(const char* key, bool default_value) {
    const char* value = std::getenv(key);
    if (!value || !*value) {
        return default_value;
    }
    const std::string normalized = value;
    return !(normalized == "0" || normalized == "false" || normalized == "FALSE");
}

double getenv_or_default_double(const char* key, double default_value) {
    const char* value = std::getenv(key);
    if (!value || !*value) {
        return default_value;
    }
    try {
        return std::stod(value);
    } catch (...) {
        return default_value;
    }
}

int getenv_or_default_int(const char* key, int default_value) {
    const char* value = std::getenv(key);
    if (!value || !*value) {
        return default_value;
    }
    try {
        return std::stoi(value);
    } catch (...) {
        return default_value;
    }
}

std::filesystem::path repo_root() {
    return std::filesystem::path(__FILE__).parent_path().parent_path();
}

std::string load_text_file(const std::filesystem::path& path) {
    std::ifstream stream(path);
    if (!stream.is_open()) {
        throw std::runtime_error("Failed to open file: " + path.string());
    }
    std::stringstream buffer;
    buffer << stream.rdbuf();
    return buffer.str();
}

std::string normalize_whitespace(const std::string& input) {
    std::string output;
    output.reserve(input.size());
    bool in_whitespace = false;
    for (unsigned char ch : input) {
        if (std::isspace(ch) != 0) {
            if (!output.empty() && !in_whitespace) {
                output.push_back(' ');
            }
            in_whitespace = true;
        } else {
            output.push_back(static_cast<char>(ch));
            in_whitespace = false;
        }
    }
    if (!output.empty() && output.back() == ' ') {
        output.pop_back();
    }
    return output;
}

std::string to_lower_ascii(const std::string& input) {
    std::string output = input;
    std::transform(output.begin(), output.end(), output.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return output;
}

std::string truncate_normalized(const std::string& input, std::size_t limit) {
    const std::string normalized = normalize_whitespace(input);
    if (normalized.size() <= limit) {
        return normalized;
    }
    return normalized.substr(0, utf8_safe_prefix_length(normalized, limit));
}

bool contains_any_lowered(const std::string& lowered, const std::vector<std::string>& keywords) {
    for (const auto& keyword : keywords) {
        if (lowered.find(to_lower_ascii(keyword)) != std::string::npos) {
            return true;
        }
    }
    return false;
}

json ensure_object(const json& value) {
    return value.is_object() ? value : json::object();
}

json ensure_array(const json& value) {
    return value.is_array() ? value : json::array();
}

std::vector<std::string> json_string_array(const json& value) {
    std::vector<std::string> result;
    if (!value.is_array()) {
        return result;
    }
    for (const auto& item : value) {
        if (!item.is_string()) {
            continue;
        }
        const std::string normalized = truncate_normalized(item.get<std::string>());
        if (!normalized.empty() && std::find(result.begin(), result.end(), normalized) == result.end()) {
            result.push_back(normalized);
        }
    }
    return result;
}

json json_array_from_strings(const std::vector<std::string>& values) {
    json result = json::array();
    for (const auto& value : values) {
        result.push_back(value);
    }
    return result;
}

std::string json_string(const json& obj, const std::string& key, const std::string& default_value) {
    if (!obj.is_object() || !obj.contains(key) || !obj.at(key).is_string()) {
        return default_value;
    }
    return obj.at(key).get<std::string>();
}

bool json_bool(const json& obj, const std::string& key, bool default_value) {
    if (!obj.is_object() || !obj.contains(key) || !obj.at(key).is_boolean()) {
        return default_value;
    }
    return obj.at(key).get<bool>();
}

std::string make_request_id() {
    static std::mt19937_64 engine{std::random_device{}()};
    std::uniform_int_distribution<unsigned long long> distribution;
    const auto value = distribution(engine) & 0xFFFFFFFFFFFFULL;
    std::ostringstream stream;
    stream << std::hex << std::setw(12) << std::setfill('0') << value;
    return stream.str();
}

json trace_entry(const std::string& stage, const std::string& status, const std::string& detail, const json& data) {
    return json{
        {"stage", stage},
        {"status", status},
        {"detail", detail},
        {"data", data},
    };
}

ParsedUrl parse_url(const std::string& url) {
    static const std::regex pattern(R"(^(https?://[^/]+)(/.*)?$)");
    std::smatch match;
    if (!std::regex_match(url, match, pattern)) {
        throw std::runtime_error("Unsupported URL: " + url);
    }
    return ParsedUrl{match[1].str(), match[2].matched ? match[2].str() : "/"};
}

bool is_infer_endpoint(const std::string& url) {
    const auto parsed = parse_url(url);
    return parsed.path == "/infer";
}

json parse_json_body(const std::string& body) {
    try {
        return json::parse(body);
    } catch (const std::exception& exc) {
        throw std::runtime_error(std::string("Invalid JSON body: ") + exc.what());
    }
}

std::string extract_json_text(const std::string& raw_text) {
    std::string stripped = normalize_whitespace(raw_text);
    const auto start = stripped.find('{');
    const auto end = stripped.rfind('}');
    if (start == std::string::npos || end == std::string::npos || end <= start) {
        throw std::runtime_error("No JSON object found in model output");
    }
    return stripped.substr(start, end - start + 1);
}

std::string post_json(const std::string& url, const json& payload, double timeout_seconds) {
    const auto parsed = parse_url(url);
    httplib::Client client(parsed.base);
    const auto timeout_whole = static_cast<time_t>(timeout_seconds);
    const auto timeout_fractional = static_cast<time_t>((timeout_seconds - timeout_whole) * 1000000);
    client.set_connection_timeout(timeout_whole, timeout_fractional);
    client.set_read_timeout(timeout_whole, timeout_fractional);
    client.set_write_timeout(timeout_whole, timeout_fractional);

    httplib::Headers headers = {
        {"Content-Type", "application/json"},
        {"Accept", "application/json"},
    };

    auto result = client.Post(parsed.path, headers, payload.dump(), "application/json");
    if (!result) {
        throw std::runtime_error("HTTP request failed: " + httplib::to_string(result.error()));
    }
    if (result->status < 200 || result->status >= 300) {
        throw std::runtime_error("HTTP status " + std::to_string(result->status));
    }
    return result->body;
}

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
) {
    if (is_infer_endpoint(endpoint)) {
        std::string prompt;
        if (!system_prompt.empty()) {
            prompt += system_prompt;
            if (!user_prompt.empty()) {
                prompt += "\n\n";
            }
        }
        prompt += user_prompt;

        const json infer_payload = {
            {"prompt", prompt},
            {"lane", "text"},
        };
        return post_json(endpoint, infer_payload, timeout_seconds);
    }

    const json payload = {
        {"model", model_name},
        {"temperature", temperature},
        {"max_tokens", max_tokens},
        {"reasoning", reasoning_mode},
        {"reasoning_budget", reasoning_budget},
        {"messages", json::array({
            json{{"role", "system"}, {"content", system_prompt}},
            json{{"role", "user"}, {"content", user_prompt}},
        })},
    };

    const json body = parse_json_body(post_json(endpoint, payload, timeout_seconds));
    return body.at("choices").at(0).at("message").at("content").get<std::string>();
}

std::pair<std::string, std::vector<std::string>> split_legacy_rag_answer(const std::string& raw_answer) {
    if (raw_answer.empty()) {
        return {"", {}};
    }

    const std::string separator = "\n\n---\n";
    const auto separator_position = raw_answer.find(separator);
    std::string body = raw_answer;
    std::string tail;
    if (separator_position != std::string::npos) {
        body = raw_answer.substr(0, separator_position);
        tail = raw_answer.substr(separator_position + separator.size());
    }

    std::vector<std::string> source_ids;
    std::stringstream stream(tail);
    std::string line;
    while (std::getline(stream, line)) {
        std::smatch match;
        if (std::regex_match(line, match, kSourceLinePattern)) {
            const std::string source = truncate_normalized(match[1].str());
            if (!source.empty() && std::find(source_ids.begin(), source_ids.end(), source) == source_ids.end()) {
                source_ids.push_back(source);
            }
        }
    }

    return {truncate_normalized(body), source_ids};
}

std::string extract_warning(const std::string& answer_text) {
    std::stringstream stream(answer_text);
    std::string line;
    while (std::getline(stream, line, '\n')) {
        const std::string normalized = truncate_normalized(line);
        if (!normalized.empty() && contains_any_lowered(to_lower_ascii(normalized), kWarningMarkers)) {
            return normalized;
        }
    }
    return "";
}

}  // namespace pipeline_internal
