#include <iostream>
#include <thread>
#include <mutex>
#include <atomic>
#include <queue>
#include <future> 
#include <memory>
#include <vector>
#include <string>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <cstdio>
#include <sstream>
#include <algorithm>
#include <cmath>
#include <array>
#include <iomanip>
#include <regex>

#include "external/httplib.h"
#include "external/nlohmann/json.hpp"
#include "LLMManager.h" 
#include "PipelineGateway.h"
#include "stb_image.h"

// --------------------------------------------------------------------------
// 1. Base64 디코딩 헬퍼 함수 (이미지 처리에 필수)
// --------------------------------------------------------------------------
static const std::string base64_chars = 
             "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
             "abcdefghijklmnopqrstuvwxyz"
             "0123456789+/";

bool is_base64(unsigned char c) {
  return (isalnum(c) || (c == '+') || (c == '/'));
}

std::string base64_decode(const std::string& encoded_string) {
  if (encoded_string.empty()) return ""; // 빈 값 체크
  int in_len = encoded_string.size();
  int i = 0;
  int j = 0;
  int in_ = 0;
  unsigned char char_array_4[4], char_array_3[3];
  std::string ret;

  while (in_len-- && ( encoded_string[in_] != '=') && is_base64(encoded_string[in_])) {
    char_array_4[i++] = encoded_string[in_]; in_++;
    if (i ==4) {
      for (i = 0; i <4; i++)
        char_array_4[i] = base64_chars.find(char_array_4[i]);

      char_array_3[0] = (char_array_4[0] << 2) + ((char_array_4[1] & 0x30) >> 4);
      char_array_3[1] = ((char_array_4[1] & 0xf) << 4) + ((char_array_4[2] & 0x3c) >> 2);
      char_array_3[2] = ((char_array_4[2] & 0x3) << 6) + char_array_4[3];

      for (i = 0; (i < 3); i++)
        ret += char_array_3[i];
      i = 0;
    }
  }

  if (i) {
    for (j = i; j <4; j++)
      char_array_4[j] = 0;

    for (j = 0; j <4; j++)
      char_array_4[j] = base64_chars.find(char_array_4[j]);

    char_array_3[0] = (char_array_4[0] << 2) + ((char_array_4[1] & 0x30) >> 4);
    char_array_3[1] = ((char_array_4[1] & 0xf) << 4) + ((char_array_4[2] & 0x3c) >> 2);
    char_array_3[2] = ((char_array_4[2] & 0x3) << 6) + char_array_4[3];

    for (j = 0; (j < i - 1); j++) ret += char_array_3[j];
  }

  return ret;
}

// --------------------------------------------------------------------------
// 2. 작업 큐 구조체 (이미지 데이터 추가)
// --------------------------------------------------------------------------
struct Job {
    enum class Lane {
        Text,
        Multimodal,
    };

    std::string prompt;
    std::string image_bytes; // [추가] 디코딩된 이미지 바이너리
    Lane lane = Lane::Text;
    std::shared_ptr<std::promise<std::string>> prom; 
};

std::queue<Job> text_job_queue;
std::queue<Job> multimodal_job_queue;
std::mutex job_mutex;
std::atomic<bool> job_running{true};
std::atomic<bool> infer_worker_enabled{true};

namespace {

std::string getenv_or_default(const char* key, const std::string& default_value) {
    const char* value = std::getenv(key);
    if (!value || !*value) {
        return default_value;
    }
    return std::string(value);
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

bool getenv_or_default_bool(const char* key, bool default_value) {
    const char* value = std::getenv(key);
    if (!value || !*value) {
        return default_value;
    }

    const std::string normalized = value;
    return !(normalized == "0" || normalized == "false" || normalized == "FALSE");
}

std::size_t total_queue_size() {
    return text_job_queue.size() + multimodal_job_queue.size();
}

const char* lane_name(Job::Lane lane) {
    return lane == Job::Lane::Multimodal ? "multimodal" : "text";
}

void replace_all(std::string& text, const std::string& from, const std::string& to) {
    if (from.empty()) {
        return;
    }
    std::size_t start = 0;
    while ((start = text.find(from, start)) != std::string::npos) {
        text.replace(start, from.size(), to);
        start += to.size();
    }
}

std::string trim_ascii_whitespace(const std::string& input) {
    const auto begin = input.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) {
        return "";
    }
    const auto end = input.find_last_not_of(" \t\r\n");
    return input.substr(begin, end - begin + 1);
}

struct ImageDimensions {
    int width = 0;
    int height = 0;

    bool valid() const {
        return width > 0 && height > 0;
    }
};

ImageDimensions probe_image_dimensions_from_bytes(const std::string& image_bytes) {
    if (image_bytes.empty()) {
        return {};
    }

    int width = 0;
    int height = 0;
    int channels = 0;
    if (!stbi_info_from_memory(
            reinterpret_cast<const stbi_uc*>(image_bytes.data()),
            static_cast<int>(image_bytes.size()),
            &width,
            &height,
            &channels)) {
        return {};
    }

    return {width, height};
}

bool is_coordinate_prompt(const std::string& prompt) {
    return prompt.find("좌표") != std::string::npos ||
           prompt.find("중심") != std::string::npos ||
           prompt.find("bounding box") != std::string::npos ||
           prompt.find("bbox") != std::string::npos;
}

std::string postprocess_coordinate_output(
        const std::string& text,
        const std::string& prompt,
        const ImageDimensions& dims) {
    if (!dims.valid() || !is_coordinate_prompt(prompt)) {
        return text;
    }

    // Heuristic:
    // Gemma4 GGUF often emits normalized [y, x] coordinates in roughly 0..1000 space
    // instead of raw pixel [x, y]. When that pattern is seen, remap to pixel coordinates.
    const std::regex bracket_pair(R"(\[\s*(\d{1,5})\s*,\s*(\d{1,5})\s*\])");
    std::smatch match;
    if (!std::regex_search(text, match, bracket_pair) || match.size() < 3) {
        return text;
    }

    const int raw_first = std::stoi(match[1].str());
    const int raw_second = std::stoi(match[2].str());
    if (raw_first < 0 || raw_second < 0) {
        return text;
    }

    // Only apply the remap when the output looks like normalized coordinates.
    if (std::max(raw_first, raw_second) > 1000 || dims.width <= 1000 || dims.height <= 500) {
        return text;
    }

    const int pixel_x = static_cast<int>(std::lround((static_cast<double>(raw_second) / 1000.0) * dims.width));
    const int pixel_y_image = static_cast<int>(std::lround((static_cast<double>(raw_first) / 1000.0) * dims.height));

    // Return Cartesian-style coordinates for the user:
    // origin at bottom-left, x grows to the right, y grows upward.
    const int clamped_x = std::clamp(pixel_x, 0, dims.width);
    const int clamped_y_image = std::clamp(pixel_y_image, 0, dims.height);
    const int pixel_y = dims.height - clamped_y_image;

    std::string corrected = text;
    corrected.replace(
        static_cast<size_t>(match.position(0)),
        static_cast<size_t>(match.length(0)),
        "[" + std::to_string(clamped_x) + ", " + std::to_string(pixel_y) + "]");
    return corrected;
}

std::string sanitize_infer_output(std::string text) {
    replace_all(text, "<|channel>thought", "");
    replace_all(text, "<|channel>answer", "");
    replace_all(text, "<channel|>", "");
    replace_all(text, "<start_of_turn>model", "");
    replace_all(text, "<end_of_turn>", "");
    replace_all(text, "<eos>", "");
    text = trim_ascii_whitespace(text);
    if (!text.empty() && text.back() != '\n') {
        text.push_back('\n');
    }
    return text;
}

std::string load_binary_file(const std::string& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream.is_open()) {
        return "";
    }
    return std::string((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
}

std::string shell_quote_single(const std::string& value) {
    std::string quoted = "'";
    for (char ch : value) {
        if (ch == '\'') {
            quoted += "'\\''";
        } else {
            quoted.push_back(ch);
        }
    }
    quoted.push_back('\'');
    return quoted;
}

std::string run_command_capture(const std::string& command) {
    std::string output;
    FILE* pipe = popen(command.c_str(), "r");
    if (!pipe) {
        return output;
    }

    char buffer[256];
    while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
        output += buffer;
    }
    pclose(pipe);
    return output;
}

double parse_double_or_negative(const std::string& value) {
    try {
        size_t parsed = 0;
        const double result = std::stod(value, &parsed);
        if (parsed == 0) {
            return -1.0;
        }
        return result;
    } catch (...) {
        return -1.0;
    }
}

double probe_video_duration_seconds(const std::string& video_path) {
    const std::string command =
        "ffprobe -v error -select_streams v:0 -show_entries format=duration -of csv=p=0 " +
        shell_quote_single(video_path) + " 2>/dev/null";
    std::string output = run_command_capture(command);
    output.erase(std::remove(output.begin(), output.end(), '\n'), output.end());
    output.erase(std::remove(output.begin(), output.end(), '\r'), output.end());
    return parse_double_or_negative(output);
}

double estimate_image_mean_luminance(const std::string& image_bytes) {
    if (image_bytes.empty()) {
        return -1.0;
    }

    int width = 0;
    int height = 0;
    int channels = 0;
    unsigned char* data = stbi_load_from_memory(
        reinterpret_cast<const stbi_uc*>(image_bytes.data()),
        static_cast<int>(image_bytes.size()),
        &width,
        &height,
        &channels,
        3
    );
    if (!data || width <= 0 || height <= 0) {
        if (data) {
            stbi_image_free(data);
        }
        return -1.0;
    }

    const size_t pixel_count = static_cast<size_t>(width) * static_cast<size_t>(height);
    double sum = 0.0;
    for (size_t i = 0; i < pixel_count; ++i) {
        const unsigned char r = data[i * 3 + 0];
        const unsigned char g = data[i * 3 + 1];
        const unsigned char b = data[i * 3 + 2];
        sum += 0.2126 * static_cast<double>(r) +
               0.7152 * static_cast<double>(g) +
               0.0722 * static_cast<double>(b);
    }

    stbi_image_free(data);
    return sum / static_cast<double>(pixel_count);
}

std::string extract_video_frame_at_seconds_bytes(const std::string& video_path, double timestamp_seconds) {
    namespace fs = std::filesystem;
    const fs::path run_dir("/tmp/llama-rest-core");
    fs::create_directories(run_dir);
    const fs::path frame_path = run_dir / ("video-frame-" + std::to_string(std::rand()) + ".jpg");

    std::ostringstream timestamp_stream;
    timestamp_stream.setf(std::ios::fixed);
    timestamp_stream.precision(3);
    timestamp_stream << std::max(0.0, timestamp_seconds);

    const std::string command =
        "ffmpeg -y -ss " + timestamp_stream.str() + " -i " + shell_quote_single(video_path) +
        " -frames:v 1 -q:v 2 " + shell_quote_single(frame_path.string()) +
        " >/dev/null 2>&1";

    const int result = std::system(command.c_str());
    if (result != 0) {
        std::error_code ignore_ec;
        fs::remove(frame_path, ignore_ec);
        return "";
    }

    const std::string bytes = load_binary_file(frame_path.string());
    std::error_code ignore_ec;
    fs::remove(frame_path, ignore_ec);
    return bytes;
}

std::string build_contact_sheet_from_frames(const std::vector<std::string>& frame_bytes_list) {
    namespace fs = std::filesystem;
    if (frame_bytes_list.empty()) {
        return "";
    }

    const fs::path run_dir("/tmp/llama-rest-core");
    fs::create_directories(run_dir);
    const fs::path temp_dir = run_dir / ("video-summary-" + std::to_string(std::rand()));
    fs::create_directories(temp_dir);

    int frame_index = 1;
    for (const std::string& bytes : frame_bytes_list) {
        std::ostringstream name;
        name << "frame_" << std::setw(3) << std::setfill('0') << frame_index++ << ".jpg";
        std::ofstream out(temp_dir / name.str(), std::ios::binary);
        out.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    }

    const fs::path output_path = temp_dir / "summary.jpg";
    const std::string command =
        "ffmpeg -y -framerate 1 -i " + shell_quote_single((temp_dir / "frame_%03d.jpg").string()) +
        " -vf " + shell_quote_single("scale=320:-1:force_original_aspect_ratio=decrease,pad=320:320:(ow-iw)/2:(oh-ih)/2:white,tile=3x2:padding=6:margin=6:color=white") +
        " -frames:v 1 " + shell_quote_single(output_path.string()) +
        " >/dev/null 2>&1";

    const int result = std::system(command.c_str());
    std::string output_bytes;
    if (result == 0) {
        output_bytes = load_binary_file(output_path.string());
    }

    std::error_code ignore_ec;
    fs::remove_all(temp_dir, ignore_ec);
    return output_bytes;
}

std::string extract_video_frame_bytes(const std::string& video_path) {
    namespace fs = std::filesystem;
    if (video_path.empty() || !fs::exists(video_path)) {
        return "";
    }

    std::vector<double> timestamps = {0.0};
    const double duration_seconds = probe_video_duration_seconds(video_path);
    if (duration_seconds > 0.0) {
        timestamps.push_back(std::min(0.5, duration_seconds));
        timestamps.push_back(duration_seconds * 0.10);
        timestamps.push_back(duration_seconds * 0.20);
        timestamps.push_back(duration_seconds * 0.25);
        timestamps.push_back(duration_seconds * 0.35);
        timestamps.push_back(duration_seconds * 0.50);
        timestamps.push_back(duration_seconds * 0.65);
        timestamps.push_back(duration_seconds * 0.75);
        timestamps.push_back(duration_seconds * 0.90);
        timestamps.push_back(std::max(0.0, duration_seconds - 0.5));
    }

    std::vector<double> unique_timestamps;
    for (double ts : timestamps) {
        const double normalized = std::max(0.0, ts);
        bool duplicate = false;
        for (double existing : unique_timestamps) {
            if (std::fabs(existing - normalized) < 0.05) {
                duplicate = true;
                break;
            }
        }
        if (!duplicate) {
            unique_timestamps.push_back(normalized);
        }
    }

    struct VideoFrameCandidate {
        double timestamp_seconds;
        double luminance;
        std::string bytes;
    };

    std::vector<VideoFrameCandidate> candidates;
    std::string best_bytes;
    double best_luminance = -1.0;
    constexpr double kNonBlackFrameLuminance = 12.0;

    for (double ts : unique_timestamps) {
        const std::string bytes = extract_video_frame_at_seconds_bytes(video_path, ts);
        if (bytes.empty()) {
            continue;
        }

        const double luminance = estimate_image_mean_luminance(bytes);
        if (luminance > best_luminance) {
            best_luminance = luminance;
            best_bytes = bytes;
        }
        if (luminance >= kNonBlackFrameLuminance) {
            candidates.push_back({ts, luminance, bytes});
        }
    }

    if (!candidates.empty()) {
        if (candidates.size() == 1) {
            return candidates.front().bytes;
        }
        std::stable_sort(candidates.begin(), candidates.end(), [](const VideoFrameCandidate& lhs, const VideoFrameCandidate& rhs) {
            return lhs.luminance > rhs.luminance;
        });

        std::vector<VideoFrameCandidate> selected_candidates;
        const size_t frame_count = std::min<size_t>(6, candidates.size());
        for (size_t i = 0; i < frame_count; ++i) {
            selected_candidates.push_back(candidates[i]);
        }

        std::stable_sort(selected_candidates.begin(), selected_candidates.end(), [](const VideoFrameCandidate& lhs, const VideoFrameCandidate& rhs) {
            return lhs.timestamp_seconds < rhs.timestamp_seconds;
        });

        std::vector<std::string> selected_frames;
        for (const auto& candidate : selected_candidates) {
            selected_frames.push_back(candidate.bytes);
        }

        const std::string summary_bytes = build_contact_sheet_from_frames(selected_frames);
        if (!summary_bytes.empty()) {
            return summary_bytes;
        }
    }

    return best_bytes;
}

}  // namespace

// --------------------------------------------------------------------------
// 3. 워커 스레드 (생성자 및 함수 호출 수정)
// --------------------------------------------------------------------------
void worker_thread_loop() {
// 1. 모델 경로 (Q5_K_M 버전이 메모리도 적게 먹고 빠릅니다. F16은 너무 클 수 있어요)
    // 메모리가 충분하다면 f16을 쓰셔도 되지만, 안전하게 Q5부터 추천드립니다.
    // (기존 f16 파일 쓰시려면 아래 주석 풀고 쓰세요)
    
    std::string model_path = getenv_or_default(
        "LLAMA_REST_MODEL_PATH",
        "/home/rbiotech-server/llama_Rest/models/gemma4-31b/gemma-4-31B-it-Q4_K_M.gguf"
    );
    std::string mmproj_path = getenv_or_default(
        "LLAMA_REST_MMPROJ_PATH",
        "/home/rbiotech-server/llama_Rest/models/gemma4-31b/mmproj-gemma-4-31B-it-Q8_0.gguf"
    );
    // [수정] 생성자 인자 3개 (모델경로, 비전경로, 병렬수)
    //LLMManager manager(model_path, mmproj_path, 4); gemma
    LLMManager manager(model_path, mmproj_path, getenv_or_default_int("LLAMA_REST_PARALLEL", 1));

    if (!manager.isValid()) {
        fprintf(stderr, "[Worker] Manager initialization failed. Exiting thread.\n");
        return;
    }

    printf("[Worker] System Ready. Waiting for requests...\n");

    int consecutive_text_jobs = 0;

    while (job_running) {
        bool busy = false;

        if (manager.has_free_slot()) {
            std::unique_lock<std::mutex> lock(job_mutex);
            if (!text_job_queue.empty() || !multimodal_job_queue.empty()) {
                const bool prefer_text = !text_job_queue.empty() &&
                    (multimodal_job_queue.empty() || consecutive_text_jobs < 3);

                Job job;
                if (prefer_text) {
                    job = text_job_queue.front();
                    text_job_queue.pop();
                    ++consecutive_text_jobs;
                } else {
                    job = multimodal_job_queue.front();
                    multimodal_job_queue.pop();
                    consecutive_text_jobs = 0;
                }
                lock.unlock();

                // [수정] add_request 인자 3개 (프롬프트, 이미지바이트, 콜백)
                if (!manager.add_request(job.prompt, job.image_bytes, [prom = job.prom](std::string result) {
                    try { prom->set_value(sanitize_infer_output(std::move(result))); } catch (...) {}
                })) {
                    try { job.prom->set_value("[ERROR] Failed to queue inference request"); } catch (...) {}
                }
                std::cout << "[Scheduler] dispatched lane=" << lane_name(job.lane)
                          << " text_q=" << text_job_queue.size()
                          << " mm_q=" << multimodal_job_queue.size() << "\n";
                busy = true;
            }
        }

        if (!manager.is_all_idle()) {
            manager.step();
            busy = true;
        }

        if (!busy) {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    }
}

// --------------------------------------------------------------------------
// 4. 메인 서버 (JSON 파싱 및 디코딩 추가)
// --------------------------------------------------------------------------
int main() {
    httplib::Server svr;
    std::unique_ptr<std::thread> worker;
    PipelineGateway gateway;
    gateway.register_routes(svr);

    infer_worker_enabled = getenv_or_default_bool("LLAMA_REST_ENABLE_INFER", true);
    if (infer_worker_enabled) {
        worker = std::make_unique<std::thread>(worker_thread_loop);
    } else {
        std::cout << "[LLama_REST] Infer worker disabled. Gateway-only mode enabled.\n";
    }

    svr.Post("/infer", [](const httplib::Request& req, httplib::Response& res) {
        if (!infer_worker_enabled) {
            res.status = 503;
            res.set_content("Infer worker disabled", "text/plain");
            return;
        }

        std::string body = req.body;
        
        // ▼▼▼ [디버그 1] 요청 도착 및 전체 크기 확인 ▼▼▼
        std::cout << "\n[Debug] HTTP Request Received. Body Size: " << body.size() << " bytes\n";

        std::string prompt;
        std::string image_b64;
        std::string image_path;
        std::string video_b64;
        std::string video_path;
        std::string requested_lane;

        try {
            const nlohmann::json payload = nlohmann::json::parse(body);
            if (payload.contains("prompt") && payload.at("prompt").is_string()) {
                prompt = payload.at("prompt").get<std::string>();
            }
            if (payload.contains("image") && payload.at("image").is_string()) {
                image_b64 = payload.at("image").get<std::string>();
            }
            if (payload.contains("image_path") && payload.at("image_path").is_string()) {
                image_path = payload.at("image_path").get<std::string>();
            }
            if (payload.contains("video") && payload.at("video").is_string()) {
                video_b64 = payload.at("video").get<std::string>();
            }
            if (payload.contains("video_path") && payload.at("video_path").is_string()) {
                video_path = payload.at("video_path").get<std::string>();
            }
            if (payload.contains("lane") && payload.at("lane").is_string()) {
                requested_lane = payload.at("lane").get<std::string>();
            }
        } catch (const nlohmann::json::parse_error& err) {
            res.status = 400;
            res.set_content(std::string("Invalid JSON: ") + err.what(), "text/plain");
            return;
        } catch (const nlohmann::json::exception& err) {
            res.status = 400;
            res.set_content(std::string("Invalid request payload: ") + err.what(), "text/plain");
            return;
        }

        // ▼▼▼ [디버그 2] 파싱 결과 확인 (여기서 0이면 파싱 실패) ▼▼▼
        std::cout << "[Debug] Parsed Prompt Length: " << prompt.length() << "\n";
        std::cout << "[Debug] Parsed Image Base64 Length: " << image_b64.length() << "\n";
        std::cout << "[Debug] Parsed Image Path: " << image_path << "\n";
        std::cout << "[Debug] Parsed Video Base64 Length: " << video_b64.length() << "\n";
        std::cout << "[Debug] Parsed Video Path: " << video_path << "\n";

        if (prompt.empty() && body.find("{") == std::string::npos) {
            prompt = body; 
        }

        if (prompt.empty() && image_b64.empty() && image_path.empty() && video_b64.empty() && video_path.empty()) {
            res.status = 400;
            res.set_content("Request must include at least one of: prompt, image, image_path, video, video_path", "text/plain");
            return;
        }

        std::string image_raw = "";
        bool derived_from_video = false;
        if (!image_b64.empty()) {
            image_raw = base64_decode(image_b64);
        } else if (!image_path.empty()) {
            image_raw = load_binary_file(image_path);
        } else if (!video_b64.empty()) {
            namespace fs = std::filesystem;
            const fs::path run_dir("/tmp/llama-rest-core");
            fs::create_directories(run_dir);
            const fs::path temp_video_path = run_dir / ("request-video-" + std::to_string(std::rand()) + ".mp4");
            std::ofstream out(temp_video_path, std::ios::binary);
            const std::string video_raw = base64_decode(video_b64);
            out.write(video_raw.data(), static_cast<std::streamsize>(video_raw.size()));
            out.close();
            image_raw = extract_video_frame_bytes(temp_video_path.string());
            derived_from_video = !image_raw.empty();
            std::error_code ignore_ec;
            fs::remove(temp_video_path, ignore_ec);
        } else if (!video_path.empty()) {
            image_raw = extract_video_frame_bytes(video_path);
            derived_from_video = !image_raw.empty();
        }

        if (derived_from_video && !prompt.empty()) {
            prompt =
                "참고: 입력 이미지는 비디오 전체에서 여러 시점을 시간 순서대로 모아 만든 프레임 요약 이미지입니다. "
                "한 장면만 보지 말고 프레임 간 차이와 반복되는 특징을 바탕으로 답하세요.\n\n" + prompt;
        }

        Job::Lane lane = Job::Lane::Text;
        if (!image_raw.empty() || !image_b64.empty() || !image_path.empty() || !video_b64.empty() || !video_path.empty()) {
            lane = Job::Lane::Multimodal;
        } else if (requested_lane == "multimodal") {
            lane = Job::Lane::Multimodal;
        }

        // ▼▼▼ [디버그 3] 디코딩 결과 확인 (이게 0이면 Base64 문제) ▼▼▼
        std::cout << "[Debug] Decoded Image Bytes: " << image_raw.size() << "\n";
        const ImageDimensions image_dims = probe_image_dimensions_from_bytes(image_raw);
        if (image_dims.valid()) {
            std::cout << "[Debug] Image Dimensions: " << image_dims.width << "x" << image_dims.height << "\n";
        }

        auto prom = std::make_shared<std::promise<std::string>>();
        auto fut = prom->get_future();

        {
            std::lock_guard<std::mutex> lock(job_mutex);
            if (total_queue_size() >= 128) {
                res.status = 429;
                res.set_content("Server busy", "text/plain");
                return;
            }
            
            std::cout << "[Debug] Pushing Job to Queue... lane=" << lane_name(lane) << "\n"; // 큐 진입 확인
            if (lane == Job::Lane::Multimodal) {
                multimodal_job_queue.push({prompt, image_raw, lane, prom});
            } else {
                text_job_queue.push({prompt, image_raw, lane, prom});
            }
        }

        if (fut.wait_for(std::chrono::seconds(300)) != std::future_status::ready) {
            res.status = 504;
            res.set_content("Timeout", "text/plain");
            return;
        }

        const std::string result = fut.get();
        const std::string adjusted_result = postprocess_coordinate_output(result, prompt, image_dims);
        if (adjusted_result.rfind("[ERROR]", 0) == 0) {
            res.status = 500;
        }
        res.set_content(adjusted_result, "text/plain");
    });

    const std::string host = getenv_or_default("LLAMA_REST_HOST", "0.0.0.0");
    const int port = getenv_or_default_int("LLAMA_REST_PORT", 18088);

    std::cout << "LLM Server running on " << host << ":" << port << "\n";
    svr.listen(host, port);

    job_running = false;
    if (worker && worker->joinable()) {
        worker->join();
    }

    return 0;
}
