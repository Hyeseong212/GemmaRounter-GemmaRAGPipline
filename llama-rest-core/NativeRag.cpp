#include "PipelineService.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "PipelineInternal.h"

using pipeline_internal::chat_completion;
using pipeline_internal::contains_any_lowered;
using pipeline_internal::ensure_array;
using pipeline_internal::ensure_object;
using pipeline_internal::extract_json_text;
using pipeline_internal::extract_warning;
using pipeline_internal::json;
using pipeline_internal::json_string;
using pipeline_internal::json_string_array;
using pipeline_internal::load_text_file;
using pipeline_internal::make_request_id;
using pipeline_internal::normalize_whitespace;
using pipeline_internal::parse_json_body;
using pipeline_internal::post_json;
using pipeline_internal::to_lower_ascii;
using pipeline_internal::trace_entry;
using pipeline_internal::truncate_normalized;

namespace {

const std::regex kErrorCodePattern(R"(\b[Ee]\d{2,4}\b)");

const std::vector<std::string> kHumanReviewMarkers = {
    "사람 검토", "의사와 상의", "전문가와 상의", "담당자에게 문의", "추가 확인 필요", "환자별 판단",
};
const std::vector<std::string> kPermissionQuestionMarkers = {
    "되나", "되나요", "가능", "괜찮", "해도", "써도", "사용해도",
};
const std::vector<std::string> kRagQueryStopwords = {
    "무슨", "뜻", "뜻이", "뜻이고", "다음", "뭘", "무엇", "어떻게", "가장", "먼저",
    "사용", "사용할", "사용자가", "확인", "해야", "해야해", "해야하나", "해도",
    "되나", "되나요", "인가", "있는", "중", "중에는", "때", "항목", "가", "이",
};

bool is_query_stopword(const std::string& token) {
    return std::find(kRagQueryStopwords.begin(), kRagQueryStopwords.end(), token) != kRagQueryStopwords.end();
}

struct RagQueryProfile {
    std::string request_id;
    std::string question;
    std::string lowered_question;
    std::vector<std::string> tokens;
    std::vector<std::string> error_codes;
    int top_k = 3;
    double min_score = 0.18;
    json metadata = json::object();
};

struct RagCandidate {
    const json* chunk = nullptr;
    double score = 0.0;
    double token_ratio = 0.0;
    double code_ratio = 0.0;
    int matched_tokens = 0;
    int matched_codes = 0;
};

std::vector<std::string> extract_error_codes(const std::string& input) {
    std::vector<std::string> result;
    for (std::sregex_iterator iter(input.begin(), input.end(), kErrorCodePattern), end; iter != end; ++iter) {
        std::string code = iter->str();
        std::transform(code.begin(), code.end(), code.begin(), [](unsigned char ch) {
            return static_cast<char>(std::toupper(ch));
        });
        if (std::find(result.begin(), result.end(), code) == result.end()) {
            result.push_back(code);
        }
    }
    return result;
}

std::vector<std::string> tokenize_text(const std::string& input) {
    std::vector<std::string> tokens;
    std::string current;

    auto flush = [&]() {
        const std::string normalized = truncate_normalized(current, 64);
        current.clear();
        if (normalized.empty()) {
            return;
        }
        if (std::find(tokens.begin(), tokens.end(), normalized) == tokens.end()) {
            tokens.push_back(normalized);
        }
    };

    for (unsigned char ch : input) {
        if (ch < 128) {
            if (std::isalnum(ch) != 0) {
                current.push_back(static_cast<char>(std::tolower(ch)));
            } else {
                flush();
            }
        } else {
            current.push_back(static_cast<char>(ch));
        }
    }
    flush();

    std::vector<std::string> filtered;
    for (const auto& token : tokens) {
        if (token.size() >= 2 && !is_query_stopword(token)) {
            filtered.push_back(token);
        }
    }
    return filtered;
}

std::string sanitize_utf8_lossy(const std::string& input) {
    std::string output;
    output.reserve(input.size());

    auto is_continuation = [](unsigned char ch) {
        return (ch & 0xC0) == 0x80;
    };

    for (std::size_t index = 0; index < input.size();) {
        const unsigned char ch = static_cast<unsigned char>(input[index]);
        if (ch < 0x80) {
            if (ch == '\n' || ch == '\r' || ch == '\t' || ch >= 0x20) {
                output.push_back(static_cast<char>(ch));
            } else {
                output.push_back(' ');
            }
            ++index;
            continue;
        }

        if ((ch & 0xE0) == 0xC0 && index + 1 < input.size() && is_continuation(static_cast<unsigned char>(input[index + 1]))) {
            output.append(input, index, 2);
            index += 2;
            continue;
        }
        if ((ch & 0xF0) == 0xE0 && index + 2 < input.size() &&
            is_continuation(static_cast<unsigned char>(input[index + 1])) &&
            is_continuation(static_cast<unsigned char>(input[index + 2]))) {
            output.append(input, index, 3);
            index += 3;
            continue;
        }
        if ((ch & 0xF8) == 0xF0 && index + 3 < input.size() &&
            is_continuation(static_cast<unsigned char>(input[index + 1])) &&
            is_continuation(static_cast<unsigned char>(input[index + 2])) &&
            is_continuation(static_cast<unsigned char>(input[index + 3]))) {
            output.append(input, index, 4);
            index += 4;
            continue;
        }

        output.push_back(' ');
        ++index;
    }

    return output;
}

std::vector<std::string> split_pages(const std::string& raw_text) {
    std::vector<std::string> pages;
    std::string current;
    for (char ch : raw_text) {
        if (ch == '\f') {
            pages.push_back(current);
            current.clear();
        } else {
            current.push_back(ch);
        }
    }
    pages.push_back(current);

    std::vector<std::string> normalized_pages;
    for (const auto& page : pages) {
        if (!normalize_whitespace(page).empty()) {
            normalized_pages.push_back(page);
        }
    }
    if (normalized_pages.empty() && !normalize_whitespace(raw_text).empty()) {
        normalized_pages.push_back(raw_text);
    }
    return normalized_pages;
}

std::vector<std::string> split_paragraphs(const std::string& page_text) {
    std::vector<std::string> paragraphs;
    std::stringstream stream(page_text);
    std::string line;
    std::string current;

    auto flush = [&]() {
        const std::string normalized = normalize_whitespace(current);
        current.clear();
        if (!normalized.empty()) {
            paragraphs.push_back(normalized);
        }
    };

    while (std::getline(stream, line)) {
        const std::string normalized_line = normalize_whitespace(line);
        if (normalized_line.empty()) {
            flush();
            continue;
        }
        if (!current.empty()) {
            current += ' ';
        }
        current += normalized_line;
    }
    flush();

    if (paragraphs.empty()) {
        const std::string normalized = normalize_whitespace(page_text);
        if (!normalized.empty()) {
            paragraphs.push_back(normalized);
        }
    }
    return paragraphs;
}

std::string excerpt_text(const std::string& input, std::size_t max_len = 220) {
    const std::string normalized = normalize_whitespace(input);
    if (normalized.size() <= max_len) {
        return normalized;
    }

    std::size_t best = normalized.find(". ", 40);
    if (best == std::string::npos || best > max_len) {
        best = normalized.find("다. ", 40);
    }
    if (best != std::string::npos && best <= max_len) {
        return normalized.substr(0, best + 1);
    }
    return truncate_normalized(normalized, max_len);
}

std::vector<float> parse_npy_float32_matrix(
    const std::filesystem::path& path,
    std::size_t& rows,
    std::size_t& cols
) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream.is_open()) {
        throw std::runtime_error("Failed to open embeddings file: " + path.string());
    }

    char magic[6];
    stream.read(magic, 6);
    if (stream.gcount() != 6 || std::string(magic, 6) != "\x93NUMPY") {
        throw std::runtime_error("Unsupported NPY header");
    }

    unsigned char version[2];
    stream.read(reinterpret_cast<char*>(version), 2);

    std::uint32_t header_len = 0;
    if (version[0] == 1) {
        std::uint16_t len16 = 0;
        stream.read(reinterpret_cast<char*>(&len16), 2);
        header_len = len16;
    } else {
        stream.read(reinterpret_cast<char*>(&header_len), 4);
    }

    std::string header(header_len, '\0');
    stream.read(header.data(), static_cast<std::streamsize>(header.size()));
    std::smatch shape_match;
    if (!std::regex_search(header, shape_match, std::regex(R"(\'shape\':\s*\((\d+),\s*(\d+)\))"))) {
        if (!std::regex_search(header, shape_match, std::regex(R"(\((\d+),\s*(\d+)\))"))) {
            throw std::runtime_error("Failed to parse NPY shape");
        }
    }

    rows = static_cast<std::size_t>(std::stoull(shape_match[1].str()));
    cols = static_cast<std::size_t>(std::stoull(shape_match[2].str()));
    std::vector<float> values(rows * cols);
    stream.read(reinterpret_cast<char*>(values.data()), static_cast<std::streamsize>(values.size() * sizeof(float)));
    if (stream.gcount() != static_cast<std::streamsize>(values.size() * sizeof(float))) {
        throw std::runtime_error("NPY data payload was truncated");
    }
    return values;
}

bool load_dense_index(
    const std::filesystem::path& index_dir,
    json& chunks_out,
    std::vector<float>& embeddings_out,
    std::size_t& embedding_dim_out,
    std::size_t& document_count_out,
    std::size_t& page_count_out
) {
    const auto manifest_path = index_dir / "manifest.json";
    const auto chunks_path = index_dir / "chunks.jsonl";
    const auto embeddings_path = index_dir / "embeddings.npy";
    if (!std::filesystem::exists(manifest_path) || !std::filesystem::exists(chunks_path) || !std::filesystem::exists(embeddings_path)) {
        return false;
    }

    const json manifest = parse_json_body(load_text_file(manifest_path));
    chunks_out = json::array();
    embeddings_out.clear();
    embedding_dim_out = 0;

    std::ifstream chunks_stream(chunks_path);
    if (!chunks_stream.is_open()) {
        throw std::runtime_error("Failed to open dense index chunks: " + chunks_path.string());
    }

    std::vector<std::string> unique_pages;
    std::string line;
    while (std::getline(chunks_stream, line)) {
        const std::string normalized_line = normalize_whitespace(line);
        if (normalized_line.empty()) {
            continue;
        }
        json row = parse_json_body(line);
        const std::string text = sanitize_utf8_lossy(json_string(row, "text"));
        const std::string source_file = json_string(row, "source_file", json_string(row, "source", "unknown"));
        std::string page_label = json_string(row, "page_label");
        if (page_label.empty() && row.contains("start_page")) {
            page_label = std::to_string(row.at("start_page").get<int>());
        }
        if (page_label.empty()) {
            page_label = "1";
        }
        const std::string page_key = source_file + "#" + page_label;
        if (std::find(unique_pages.begin(), unique_pages.end(), page_key) == unique_pages.end()) {
            unique_pages.push_back(page_key);
        }

        chunks_out.push_back({
            {"chunk_id", json_string(row, "chunk_id")},
            {"source_file", source_file},
            {"page_label", page_label},
            {"text", normalize_whitespace(text)},
            {"search_text", to_lower_ascii(text)},
        });
    }

    std::size_t rows = 0;
    std::size_t cols = 0;
    embeddings_out = parse_npy_float32_matrix(embeddings_path, rows, cols);
    if (rows != chunks_out.size()) {
        throw std::runtime_error("Dense index row count does not match chunks.jsonl");
    }

    embedding_dim_out = cols;
    document_count_out = manifest.value("document_count", static_cast<int>(chunks_out.size()));
    page_count_out = unique_pages.size();
    return true;
}

std::vector<float> request_query_embedding(const std::string& endpoint, const std::string& text, double timeout_seconds) {
    const json body = parse_json_body(post_json(endpoint, json{{"text", text}}, timeout_seconds));
    const auto embedding_json = body.contains("embedding") ? body.at("embedding") : json::array();
    if (!embedding_json.is_array() || embedding_json.empty()) {
        throw std::runtime_error("Embedding helper returned no embedding");
    }
    std::vector<float> values;
    values.reserve(embedding_json.size());
    for (const auto& item : embedding_json) {
        if (!item.is_number()) {
            throw std::runtime_error("Embedding helper returned a non-numeric element");
        }
        values.push_back(item.get<float>());
    }
    return values;
}

std::string short_token_prefix(const std::string& token) {
    if (token.size() <= 6) {
        return token;
    }
    return truncate_normalized(token, 6);
}

RagQueryProfile normalize_rag_request(const json& request, int default_top_k, double default_min_score) {
    const auto metadata = ensure_object(request.value("metadata", json::object()));
    std::string request_id = truncate_normalized(json_string(request, "request_id"));
    if (request_id.empty()) {
        request_id = truncate_normalized(json_string(metadata, "request_id"));
    }
    if (request_id.empty()) {
        request_id = make_request_id();
    }

    const std::string question = truncate_normalized(json_string(request, "question"));
    if (question.empty()) {
        throw std::runtime_error("question must not be blank");
    }

    int top_k = request.value("top_k", default_top_k);
    if (top_k <= 0) {
        top_k = default_top_k;
    }

    double min_score = request.value("min_score", default_min_score);
    if (min_score < 0.0) {
        min_score = default_min_score;
    }

    return RagQueryProfile{
        request_id,
        question,
        to_lower_ascii(question),
        tokenize_text(question),
        extract_error_codes(question),
        top_k,
        min_score,
        metadata,
    };
}

RagCandidate score_chunk(const RagQueryProfile& query, const json& chunk) {
    const std::string search_text = json_string(chunk, "search_text");
    if (search_text.empty()) {
        return {};
    }

    int matched_tokens = 0;
    double matched_token_weight = 0.0;
    double total_token_weight = 0.0;
    for (const auto& token : query.tokens) {
        if (token.empty()) {
            continue;
        }
        const double token_weight = 1.0 + std::min(4.0, static_cast<double>(token.size()) / 6.0);
        total_token_weight += token_weight;
        bool matched = search_text.find(token) != std::string::npos;
        double applied_weight = token_weight;
        if (!matched) {
            const std::string prefix = short_token_prefix(token);
            if (!prefix.empty() && prefix != token && search_text.find(prefix) != std::string::npos) {
                matched = true;
                applied_weight = token_weight * 0.75;
            }
        }
        if (matched) {
            ++matched_tokens;
            matched_token_weight += applied_weight;
        }
    }

    int matched_codes = 0;
    for (const auto& code : query.error_codes) {
        const std::string lowered_code = to_lower_ascii(code);
        if (search_text.find(lowered_code) != std::string::npos) {
            ++matched_codes;
        }
    }

    const double token_ratio = total_token_weight <= 0.0
        ? 0.0
        : matched_token_weight / total_token_weight;
    const double code_ratio = query.error_codes.empty()
        ? 0.0
        : static_cast<double>(matched_codes) / static_cast<double>(query.error_codes.size());
    const double phrase_bonus =
        query.lowered_question.size() >= 8 && search_text.find(query.lowered_question) != std::string::npos
            ? 1.0
            : 0.0;

    double score = 0.0;
    if (!query.error_codes.empty()) {
        score = (0.45 * token_ratio) + (0.45 * code_ratio) + (0.10 * phrase_bonus);
    } else {
        score = (0.90 * token_ratio) + (0.10 * phrase_bonus);
    }

    if (matched_tokens == 0 && matched_codes == 0) {
        score = 0.0;
    }

    return RagCandidate{
        &chunk,
        score,
        token_ratio,
        code_ratio,
        matched_tokens,
        matched_codes,
    };
}

std::vector<RagCandidate> dense_candidates_from_embeddings(
    const RagQueryProfile& query,
    const std::vector<float>& query_embedding,
    const json& chunks,
    const std::vector<float>& embeddings,
    std::size_t embedding_dim,
    int top_k
) {
    std::vector<RagCandidate> candidates;
    if (embedding_dim == 0 || query_embedding.size() != embedding_dim) {
        throw std::runtime_error("Dense embedding dimension mismatch");
    }
    if (chunks.size() * embedding_dim > embeddings.size()) {
        throw std::runtime_error("Dense embedding matrix is smaller than chunk metadata");
    }

    candidates.reserve(chunks.size());
    for (std::size_t row = 0; row < chunks.size(); ++row) {
        const float* base = embeddings.data() + (row * embedding_dim);
        double dense_score = 0.0;
        for (std::size_t col = 0; col < embedding_dim; ++col) {
            dense_score += static_cast<double>(base[col]) * static_cast<double>(query_embedding[col]);
        }
        const RagCandidate lexical = score_chunk(query, chunks.at(row));
        const double score = (dense_score * 0.75) + (lexical.score * 0.25);
        candidates.push_back(RagCandidate{
            &chunks.at(row),
            score,
            lexical.token_ratio,
            lexical.code_ratio,
            lexical.matched_tokens,
            lexical.matched_codes,
        });
    }

    std::sort(candidates.begin(), candidates.end(), [](const RagCandidate& left, const RagCandidate& right) {
        return left.score > right.score;
    });
    if (static_cast<int>(candidates.size()) > top_k) {
        candidates.resize(static_cast<std::size_t>(top_k));
    }
    return candidates;
}

json retrieval_snapshot(
    const RagQueryProfile& query,
    const std::vector<RagCandidate>& candidates,
    std::size_t document_count,
    std::size_t page_count,
    std::size_t chunk_count,
    const std::string& corpus_dir
) {
    json matched = json::array();
    for (const auto& candidate : candidates) {
        if (!candidate.chunk) {
            continue;
        }
        matched.push_back({
            {"chunk_id", candidate.chunk->at("chunk_id")},
            {"source_file", candidate.chunk->at("source_file")},
            {"page_label", candidate.chunk->at("page_label")},
            {"score", candidate.score},
            {"matched_tokens", candidate.matched_tokens},
            {"matched_codes", candidate.matched_codes},
            {"text_preview", excerpt_text(json_string(*candidate.chunk, "text"), 180)},
            {"text", candidate.chunk->at("text")},
        });
    }

    return json{
        {"request_id", query.request_id},
        {"question", query.question},
        {"top_k", query.top_k},
        {"min_score", query.min_score},
        {"matched_chunks", matched},
        {"corpus", {
            {"documents", document_count},
            {"pages", page_count},
            {"chunks", chunk_count},
            {"directory", corpus_dir},
        }},
    };
}

std::string build_context_prompt(const std::vector<RagCandidate>& candidates) {
    std::ostringstream stream;
    for (std::size_t index = 0; index < candidates.size(); ++index) {
        const auto& candidate = candidates[index];
        if (!candidate.chunk) {
            continue;
        }
        stream << "[chunk-" << std::setw(2) << std::setfill('0') << (index + 1) << "] "
               << "chunk_id=" << json_string(*candidate.chunk, "chunk_id")
               << " source=" << json_string(*candidate.chunk, "source_file")
               << " page=" << json_string(*candidate.chunk, "page_label")
               << " score=" << std::fixed << std::setprecision(2) << candidate.score
               << "\n"
               << json_string(*candidate.chunk, "text")
               << "\n\n";
    }
    return stream.str();
}

json fallback_rag_response(const RagQueryProfile& query, const std::vector<RagCandidate>& candidates) {
    if (candidates.empty() || !candidates.front().chunk || candidates.front().score < query.min_score) {
        return json{
            {"answerable", false},
            {"answer", "문서 근거가 부족해 현재 답을 확정하기 어렵습니다."},
            {"used_chunk_ids", json::array()},
            {"needs_human_review", true},
            {"warning", nullptr},
        };
    }

    json used_chunk_ids = json::array();
    json retrieved_scores = json::array();
    std::vector<std::string> bullets;
    std::string warning;
    std::vector<const RagCandidate*> ordered_candidates;
    const std::string lowered_question = to_lower_ascii(query.question);
    const bool asks_permission = contains_any_lowered(lowered_question, kPermissionQuestionMarkers);

    if (asks_permission) {
        for (const auto& candidate : candidates) {
            if (!candidate.chunk) {
                continue;
            }
            const std::string candidate_warning = extract_warning(json_string(*candidate.chunk, "text"));
            if (!candidate_warning.empty()) {
                ordered_candidates.push_back(&candidate);
                break;
            }
        }
    }
    for (const auto& candidate : candidates) {
        if (!candidate.chunk) {
            continue;
        }
        bool already_added = false;
        for (const auto* existing : ordered_candidates) {
            if (existing->chunk == candidate.chunk) {
                already_added = true;
                break;
            }
        }
        if (!already_added) {
            ordered_candidates.push_back(&candidate);
        }
    }

    for (const auto* candidate_ptr : ordered_candidates) {
        const auto& candidate = *candidate_ptr;
        if (!candidate.chunk || candidate.score < query.min_score * 0.75) {
            continue;
        }
        used_chunk_ids.push_back(candidate.chunk->at("chunk_id"));
        retrieved_scores.push_back(candidate.score);
        bullets.push_back("- " + excerpt_text(json_string(*candidate.chunk, "text"), 180));
        if (warning.empty()) {
            warning = extract_warning(json_string(*candidate.chunk, "text"));
        }
        if (bullets.size() >= 2) {
            break;
        }
    }

    std::ostringstream answer;
    answer << "문서 기준으로 확인된 내용:\n";
    for (const auto& bullet : bullets) {
        answer << bullet << "\n";
    }

    return json{
        {"answerable", true},
        {"answer", truncate_normalized(answer.str(), 600)},
        {"used_chunk_ids", used_chunk_ids},
        {"needs_human_review", !warning.empty()},
        {"warning", warning.empty() ? json(nullptr) : json(warning)},
        {"retrieved_scores", retrieved_scores},
    };
}

json sanitize_model_rag_response(const json& parsed, const json& retrieval) {
    const auto matched_chunks = ensure_array(retrieval.value("matched_chunks", json::array()));
    const auto candidate_ids = json_string_array(parsed.value("used_chunk_ids", json::array()));
    json validated_ids = json::array();
    json retrieved_scores = json::array();

    for (const auto& candidate_id : candidate_ids) {
        for (const auto& matched : matched_chunks) {
            if (json_string(matched, "chunk_id") == candidate_id) {
                validated_ids.push_back(candidate_id);
                retrieved_scores.push_back(matched.value("score", 0.0));
                break;
            }
        }
    }

    if (validated_ids.empty() && !matched_chunks.empty()) {
        validated_ids.push_back(matched_chunks.at(0).at("chunk_id"));
        retrieved_scores.push_back(matched_chunks.at(0).value("score", 0.0));
    }

    const bool answerable = parsed.contains("answerable") && parsed.at("answerable").is_boolean()
        ? parsed.at("answerable").get<bool>()
        : false;

    std::string answer = truncate_normalized(json_string(parsed, "answer"), 600);
    if (!answerable && answer.empty()) {
        answer = "문서 근거가 부족해 현재 답을 확정하기 어렵습니다.";
    }

    std::string warning = json_string(parsed, "warning");
    if (warning.empty()) {
        warning = "";
    }

    return json{
        {"answerable", answerable},
        {"answer", answer},
        {"used_chunk_ids", validated_ids},
        {"needs_human_review", parsed.value("needs_human_review", false)},
        {"warning", warning.empty() ? json(nullptr) : json(warning)},
        {"retrieved_scores", retrieved_scores},
    };
}

std::string build_legacy_answer(const json& structured, const json& retrieval) {
    const std::string answer = truncate_normalized(json_string(structured, "answer"), 800);
    const auto used_chunk_ids = json_string_array(structured.value("used_chunk_ids", json::array()));
    const auto matched_chunks = ensure_array(retrieval.value("matched_chunks", json::array()));

    std::vector<std::string> source_lines;
    for (const auto& used_id : used_chunk_ids) {
        for (const auto& matched : matched_chunks) {
            if (json_string(matched, "chunk_id") != used_id) {
                continue;
            }
            const std::string file_name = json_string(matched, "source_file", "unknown");
            const std::string page_label = json_string(matched, "page_label", "N/A");
            const std::string source_line = "출처: " + file_name + " (p." + page_label + ")";
            if (std::find(source_lines.begin(), source_lines.end(), source_line) == source_lines.end()) {
                source_lines.push_back(source_line);
            }
            break;
        }
    }

    std::string combined = answer;
    if (!source_lines.empty()) {
        combined += "\n\n---\n";
        for (std::size_t index = 0; index < source_lines.size(); ++index) {
            combined += source_lines[index];
            if (index + 1 < source_lines.size()) {
                combined += "\n";
            }
        }
    }
    return combined;
}

}  // namespace

void PipelineService::initialize_rag_corpus() {
    rag_corpus_chunks_ = json::array();
    rag_dense_embeddings_.clear();
    rag_embedding_dim_ = 0;
    rag_document_count_ = 0;
    rag_page_count_ = 0;

    try {
        if (load_dense_index(
            std::filesystem::path(config_.rag_index_dir),
            rag_corpus_chunks_,
            rag_dense_embeddings_,
            rag_embedding_dim_,
            rag_document_count_,
            rag_page_count_
        )) {
            return;
        }
    } catch (...) {
        rag_corpus_chunks_ = json::array();
        rag_dense_embeddings_.clear();
        rag_embedding_dim_ = 0;
        rag_document_count_ = 0;
        rag_page_count_ = 0;
    }

    const std::filesystem::path corpus_dir(config_.rag_corpus_dir);
    if (!std::filesystem::exists(corpus_dir)) {
        return;
    }

    const std::size_t max_chunk_chars = 700;

    for (const auto& entry : std::filesystem::recursive_directory_iterator(corpus_dir)) {
        if (!entry.is_regular_file() || entry.path().extension() != ".txt") {
            continue;
        }

        ++rag_document_count_;
        const std::string raw_text = sanitize_utf8_lossy(load_text_file(entry.path()));
        const auto pages = split_pages(raw_text);
        std::size_t chunk_index = 0;

        for (std::size_t page_index = 0; page_index < pages.size(); ++page_index) {
            ++rag_page_count_;
            const auto paragraphs = split_paragraphs(pages[page_index]);
            std::string current_chunk;

            auto flush_chunk = [&]() {
                const std::string normalized = normalize_whitespace(sanitize_utf8_lossy(current_chunk));
                current_chunk.clear();
                if (normalized.empty()) {
                    return;
                }
                ++chunk_index;
                rag_corpus_chunks_.push_back({
                    {"chunk_id", entry.path().stem().string() + "-p" + std::to_string(page_index + 1) + "-c" + std::to_string(chunk_index)},
                    {"source_file", entry.path().filename().string()},
                    {"page_label", std::to_string(page_index + 1)},
                    {"text", normalized},
                    {"search_text", to_lower_ascii(normalized)},
                });
            };

            for (const auto& paragraph : paragraphs) {
                if (current_chunk.empty()) {
                    current_chunk = paragraph;
                    continue;
                }
                if (current_chunk.size() + paragraph.size() + 1 > max_chunk_chars) {
                    flush_chunk();
                    current_chunk = paragraph;
                } else {
                    current_chunk += "\n";
                    current_chunk += paragraph;
                }
            }
            flush_chunk();
        }
    }
}

nlohmann::json PipelineService::rag_ask_internal(const nlohmann::json& request) const {
    const RagQueryProfile normalized = normalize_rag_request(request, config_.rag_top_k, config_.rag_min_score);
    json trace = json::array();
    trace.push_back(trace_entry(
        "normalize",
        "passed",
        "RAG request was normalized.",
        json{{"request_id", normalized.request_id}, {"question", normalized.question}}
    ));

    std::vector<RagCandidate> candidates;
    bool used_dense_retrieval = false;
    if (!rag_dense_embeddings_.empty() && rag_embedding_dim_ > 0 && !config_.rag_embedding_endpoint.empty()) {
        try {
            const std::vector<float> query_embedding = request_query_embedding(
                config_.rag_embedding_endpoint,
                normalized.question,
                config_.rag_embedding_timeout
            );
            candidates = dense_candidates_from_embeddings(
                normalized,
                query_embedding,
                rag_corpus_chunks_,
                rag_dense_embeddings_,
                rag_embedding_dim_,
                normalized.top_k
            );
            used_dense_retrieval = true;
            trace.push_back(trace_entry(
                "embed",
                "completed",
                "Generated dense query embedding from the embedding helper.",
                json{{"embedding_dim", query_embedding.size()}, {"endpoint", config_.rag_embedding_endpoint}}
            ));
        } catch (const std::exception& exc) {
            trace.push_back(trace_entry(
                "embed",
                "failed",
                "Dense embedding generation failed and retrieval fell back to lexical scoring.",
                json{{"error", exc.what()}, {"endpoint", config_.rag_embedding_endpoint}}
            ));
        }
    }

    if (!used_dense_retrieval) {
        candidates.reserve(rag_corpus_chunks_.size());
        for (const auto& chunk : rag_corpus_chunks_) {
            RagCandidate candidate = score_chunk(normalized, chunk);
            if (candidate.chunk && candidate.score > 0.0) {
                candidates.push_back(candidate);
            }
        }

        std::sort(candidates.begin(), candidates.end(), [](const RagCandidate& left, const RagCandidate& right) {
            if (left.score == right.score) {
                return left.matched_tokens > right.matched_tokens;
            }
            return left.score > right.score;
        });

        if (static_cast<int>(candidates.size()) > normalized.top_k) {
            candidates.resize(static_cast<std::size_t>(normalized.top_k));
        }
    }

    const json retrieval = retrieval_snapshot(
        normalized,
        candidates,
        rag_document_count_,
        rag_page_count_,
        rag_corpus_chunks_.size(),
        config_.rag_corpus_dir
    );
    trace.push_back(trace_entry(
        "retrieve",
        "completed",
        used_dense_retrieval
            ? "Native dense vector retrieval selected top context chunks."
            : "Native lexical retrieval selected top context chunks.",
        json{
            {"matched_chunks", retrieval.at("matched_chunks").size()},
            {"corpus_chunks", rag_corpus_chunks_.size()},
            {"mode", used_dense_retrieval ? "dense" : "lexical"}
        }
    ));

    json structured;
    if (!candidates.empty() && candidates.front().score >= normalized.min_score && config_.rag_model_enabled) {
        try {
            const std::string user_prompt =
                "Question: " + normalized.question + "\n\nContext:\n" + build_context_prompt(candidates);
            const std::string raw_response = chat_completion(
                config_.rag_model_endpoint,
                config_.rag_model_name,
                config_.rag_system_prompt,
                user_prompt,
                config_.rag_temperature,
                config_.rag_max_tokens,
                config_.rag_reasoning_mode,
                config_.rag_reasoning_budget,
                config_.rag_request_timeout
            );
            structured = sanitize_model_rag_response(
                parse_json_body(extract_json_text(raw_response)),
                retrieval
            );
            trace.push_back(trace_entry(
                "generate",
                "completed",
                "Native RAG answer model produced structured output.",
                json{{"model_name", config_.rag_model_name}}
            ));
        } catch (const std::exception& exc) {
            structured = fallback_rag_response(normalized, candidates);
            trace.push_back(trace_entry(
                "generate",
                "fallback",
                "RAG model generation failed and the engine used extractive fallback.",
                json{{"error", exc.what()}}
            ));
        }
    } else {
        structured = fallback_rag_response(normalized, candidates);
        trace.push_back(trace_entry(
            "generate",
            "fallback",
            "The engine used extractive fallback because retrieval was weak or the RAG model was disabled.",
            json{{"rag_model_enabled", config_.rag_model_enabled}}
        ));
    }

    const std::string legacy_answer = build_legacy_answer(structured, retrieval);
    return json{
        {"response", json{{"answer", legacy_answer}}},
        {"structured", structured},
        {"retrieval", retrieval},
        {"trace", trace},
    };
}

nlohmann::json PipelineService::rag_ask(const nlohmann::json& request, bool debug) const {
    const json result = rag_ask_internal(request);
    if (debug) {
        return result;
    }
    return result.at("response");
}
