#include <depthai/depthai.hpp>
#include <opencv2/opencv.hpp>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "httplib.h"
#include "nlohmann/json.hpp"

namespace fs = std::filesystem;
using json = nlohmann::json;

namespace {

constexpr char kRgbWindowName[] = "oak-rgb";
constexpr char kDepthWindowName[] = "oak-depth";
constexpr char kDefaultPrompt[] = "이 이미지에서 휠체어가 어딨는지 중심을 좌표로 나타내봐";

struct AppConfig {
    std::string server_url = "http://127.0.0.1:18088/infer";
    std::string prompt = kDefaultPrompt;
    fs::path output_dir = "/tmp/oak-wheelchair-depth-test";
    int roi_size = 21;
    int rgb_width = 1280;
    int rgb_height = 720;
};

struct ParsedUrl {
    std::string scheme;
    std::string host;
    int port = 80;
    std::string path;
};

struct InferenceResult {
    cv::Point bottom_left;
    cv::Point top_left;
    std::optional<int> depth_mm;
    std::string depth_status;
    std::string capture_path;
    std::string raw_response;
};

std::string timestamp_string() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t tt = std::chrono::system_clock::to_time_t(now);
    std::tm tm{};
    localtime_r(&tt, &tm);

    std::ostringstream oss;
    oss << std::put_time(&tm, "%Y%m%d-%H%M%S");
    return oss.str();
}

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error(message);
}

ParsedUrl parse_http_url(const std::string& url) {
    static const std::regex pattern(R"(^(http)://([^/:]+)(?::([0-9]+))?(\/.*)$)");
    std::smatch match;
    if (!std::regex_match(url, match, pattern)) {
        fail("Unsupported server URL: " + url);
    }

    ParsedUrl parsed;
    parsed.scheme = match[1].str();
    parsed.host = match[2].str();
    parsed.port = match[3].matched ? std::stoi(match[3].str()) : 80;
    parsed.path = match[4].str();
    return parsed;
}

cv::Mat colorize_depth(const cv::Mat& depth_mm) {
    if (depth_mm.empty()) {
        return {};
    }

    cv::Mat mask = depth_mm > 0;
    if (cv::countNonZero(mask) == 0) {
        return cv::Mat(depth_mm.rows, depth_mm.cols, CV_8UC3, cv::Scalar(0, 0, 0)).clone();
    }

    double min_val = 0.0;
    double max_val = 0.0;
    cv::minMaxIdx(depth_mm, &min_val, &max_val, nullptr, nullptr, mask);
    if (max_val <= min_val) {
        max_val = min_val + 1.0;
    }

    cv::Mat normalized;
    depth_mm.convertTo(normalized, CV_8U, 255.0 / (max_val - min_val), -min_val * 255.0 / (max_val - min_val));
    normalized.setTo(0, ~mask);

    cv::Mat colored;
    cv::applyColorMap(normalized, colored, cv::COLORMAP_TURBO);
    colored.setTo(cv::Scalar(0, 0, 0), ~mask);
    return colored;
}

std::optional<cv::Point> extract_first_coordinate(const std::string& text) {
    static const std::regex pattern(R"(\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\])");
    std::smatch match;
    if (!std::regex_search(text, match, pattern)) {
        return std::nullopt;
    }
    return cv::Point(std::stoi(match[1].str()), std::stoi(match[2].str()));
}

cv::Point clamp_point(const cv::Point& point, const cv::Size& size) {
    return {
        std::clamp(point.x, 0, std::max(0, size.width - 1)),
        std::clamp(point.y, 0, std::max(0, size.height - 1)),
    };
}

cv::Point bottom_left_to_top_left(const cv::Point& bottom_left, int image_height) {
    return {bottom_left.x, image_height - bottom_left.y};
}

std::optional<int> compute_depth_median_mm(const cv::Mat& depth_mm, const cv::Point& center, int roi_size) {
    if (depth_mm.empty() || depth_mm.type() != CV_16UC1) {
        return std::nullopt;
    }

    const int radius = std::max(1, roi_size) / 2;
    const int left = std::max(0, center.x - radius);
    const int top = std::max(0, center.y - radius);
    const int right = std::min(depth_mm.cols - 1, center.x + radius);
    const int bottom = std::min(depth_mm.rows - 1, center.y + radius);

    std::vector<int> values;
    values.reserve(static_cast<size_t>((right - left + 1) * (bottom - top + 1)));

    for (int y = top; y <= bottom; ++y) {
        for (int x = left; x <= right; ++x) {
            const uint16_t value = depth_mm.at<uint16_t>(y, x);
            if (value > 0) {
                values.push_back(static_cast<int>(value));
            }
        }
    }

    if (values.empty()) {
        return std::nullopt;
    }

    const size_t middle = values.size() / 2;
    std::nth_element(values.begin(), values.begin() + static_cast<long>(middle), values.end());
    return values[middle];
}

std::string make_capture_path(const fs::path& output_dir) {
    return (output_dir / ("capture-" + timestamp_string() + ".png")).string();
}

void draw_crosshair(cv::Mat& image, const cv::Point& point, const cv::Scalar& color) {
    cv::drawMarker(image, point, color, cv::MARKER_CROSS, 24, 2);
}

void draw_last_result(cv::Mat& rgb_frame, cv::Mat& depth_preview, const InferenceResult& result, int roi_size) {
    const int radius = std::max(1, roi_size) / 2;
    const cv::Rect roi(
        std::max(0, result.top_left.x - radius),
        std::max(0, result.top_left.y - radius),
        std::min(rgb_frame.cols - std::max(0, result.top_left.x - radius), roi_size),
        std::min(rgb_frame.rows - std::max(0, result.top_left.y - radius), roi_size));

    draw_crosshair(rgb_frame, result.top_left, cv::Scalar(0, 255, 0));
    cv::rectangle(rgb_frame, roi, cv::Scalar(0, 255, 0), 2);

    draw_crosshair(depth_preview, result.top_left, cv::Scalar(0, 255, 0));
    cv::rectangle(depth_preview, roi, cv::Scalar(0, 255, 0), 2);

    std::ostringstream line1;
    line1 << "BL [" << result.bottom_left.x << ", " << result.bottom_left.y << "] "
          << "TL [" << result.top_left.x << ", " << result.top_left.y << "]";

    std::ostringstream line2;
    line2 << "depth: ";
    if (result.depth_mm.has_value()) {
        line2 << *result.depth_mm << " mm";
    } else {
        line2 << "unavailable";
    }

    cv::putText(rgb_frame, line1.str(), {20, 36}, cv::FONT_HERSHEY_SIMPLEX, 0.8, cv::Scalar(0, 255, 0), 2);
    cv::putText(rgb_frame, line2.str(), {20, 72}, cv::FONT_HERSHEY_SIMPLEX, 0.8, cv::Scalar(0, 255, 0), 2);
}

AppConfig parse_args(int argc, char** argv) {
    AppConfig config;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--server" && i + 1 < argc) {
            config.server_url = argv[++i];
        } else if (arg == "--prompt" && i + 1 < argc) {
            config.prompt = argv[++i];
        } else if (arg == "--output-dir" && i + 1 < argc) {
            config.output_dir = argv[++i];
        } else if (arg == "--roi-size" && i + 1 < argc) {
            config.roi_size = std::stoi(argv[++i]);
        } else if (arg == "--width" && i + 1 < argc) {
            config.rgb_width = std::stoi(argv[++i]);
        } else if (arg == "--height" && i + 1 < argc) {
            config.rgb_height = std::stoi(argv[++i]);
        } else if (arg == "--help") {
            std::cout
                << "Usage: oak_wheelchair_depth_test [options]\n"
                << "  --server URL       default: http://127.0.0.1:18088/infer\n"
                << "  --prompt TEXT      default wheelchair coordinate prompt\n"
                << "  --output-dir PATH  default: /tmp/oak-wheelchair-depth-test\n"
                << "  --roi-size N       default: 21\n"
                << "  --width N          default: 1280\n"
                << "  --height N         default: 720\n";
            std::exit(0);
        } else {
            fail("Unknown argument: " + arg);
        }
    }

    if (config.roi_size < 3 || config.roi_size % 2 == 0) {
        fail("roi-size must be an odd integer >= 3");
    }

    return config;
}

std::string run_infer_request(const AppConfig& config, const std::string& image_path) {
    const ParsedUrl parsed = parse_http_url(config.server_url);

    httplib::Client client(parsed.host, parsed.port);
    client.set_connection_timeout(5, 0);
    client.set_read_timeout(300, 0);
    client.set_write_timeout(30, 0);

    json payload = {
        {"prompt", config.prompt},
        {"image_path", image_path},
    };

    auto response = client.Post(parsed.path.c_str(), payload.dump(), "application/json");
    if (!response) {
        fail("Failed to call infer server: " + config.server_url);
    }
    if (response->status < 200 || response->status >= 300) {
        fail("Infer server returned HTTP " + std::to_string(response->status) + ": " + response->body);
    }
    return response->body;
}

dai::Pipeline create_pipeline(int rgb_width, int rgb_height) {
    dai::Pipeline pipeline;

    auto cam_rgb = pipeline.create<dai::node::ColorCamera>();
    auto mono_left = pipeline.create<dai::node::MonoCamera>();
    auto mono_right = pipeline.create<dai::node::MonoCamera>();
    auto stereo = pipeline.create<dai::node::StereoDepth>();
    auto sync = pipeline.create<dai::node::Sync>();
    auto xout = pipeline.create<dai::node::XLinkOut>();

    xout->setStreamName("out");

    cam_rgb->setBoardSocket(dai::CameraBoardSocket::CAM_A);
    cam_rgb->setResolution(dai::ColorCameraProperties::SensorResolution::THE_1080_P);
    cam_rgb->setInterleaved(false);
    cam_rgb->setColorOrder(dai::ColorCameraProperties::ColorOrder::BGR);
    cam_rgb->setPreviewSize(rgb_width, rgb_height);

    mono_left->setCamera("left");
    mono_right->setCamera("right");
    mono_left->setResolution(dai::MonoCameraProperties::SensorResolution::THE_400_P);
    mono_right->setResolution(dai::MonoCameraProperties::SensorResolution::THE_400_P);

    stereo->setDefaultProfilePreset(dai::node::StereoDepth::PresetMode::DEFAULT);
    stereo->setLeftRightCheck(true);
    stereo->setSubpixel(true);
    stereo->setDepthAlign(dai::CameraBoardSocket::CAM_A);
    stereo->setOutputSize(rgb_width, rgb_height);

    sync->setSyncThreshold(std::chrono::milliseconds(20));

    mono_left->out.link(stereo->left);
    mono_right->out.link(stereo->right);
    cam_rgb->preview.link(sync->inputs["rgb"]);
    stereo->depth.link(sync->inputs["depth_aligned"]);
    sync->out.link(xout->input);

    return pipeline;
}

InferenceResult perform_capture_and_inference(const AppConfig& config, const cv::Mat& rgb_frame, const cv::Mat& depth_frame) {
    if (rgb_frame.empty() || depth_frame.empty()) {
        fail("RGB or depth frame is empty");
    }

    fs::create_directories(config.output_dir);
    const std::string capture_path = make_capture_path(config.output_dir);
    if (!cv::imwrite(capture_path, rgb_frame)) {
        fail("Failed to save capture frame: " + capture_path);
    }

    const std::string response_body = run_infer_request(config, capture_path);
    const auto coordinate = extract_first_coordinate(response_body);
    if (!coordinate.has_value()) {
        fail("No coordinate found in infer response: " + response_body);
    }

    InferenceResult result;
    result.bottom_left = clamp_point(*coordinate, rgb_frame.size());
    result.top_left = clamp_point(bottom_left_to_top_left(result.bottom_left, rgb_frame.rows), rgb_frame.size());
    result.depth_mm = compute_depth_median_mm(depth_frame, result.top_left, config.roi_size);
    result.depth_status = result.depth_mm.has_value() ? "ok" : "depth_unavailable";
    result.capture_path = capture_path;
    result.raw_response = response_body;
    return result;
}

void print_result(const InferenceResult& result) {
    std::cout << "wheelchair_coord_bottom_left=[" << result.bottom_left.x << "," << result.bottom_left.y << "]\n";
    std::cout << "wheelchair_coord_top_left=[" << result.top_left.x << "," << result.top_left.y << "]\n";
    if (result.depth_mm.has_value()) {
        std::cout << "depth_mm=" << *result.depth_mm << "\n";
    } else {
        std::cout << "depth_mm=unavailable\n";
    }
    std::cout << "depth_status=" << result.depth_status << "\n";
    std::cout << "capture_path=" << result.capture_path << "\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const AppConfig config = parse_args(argc, argv);
        fs::create_directories(config.output_dir);

        std::cout << "server_url=" << config.server_url << "\n";
        std::cout << "output_dir=" << config.output_dir << "\n";
        std::cout << "roi_size=" << config.roi_size << "\n";
        std::cout << "controls: c=capture, q=quit\n";

        const auto available_devices = dai::XLinkConnection::getAllConnectedDevices(X_LINK_ANY_STATE, true);
        if (available_devices.empty()) {
            const auto connected_devices = dai::XLinkConnection::getAllConnectedDevices(X_LINK_ANY_STATE, false);
            std::ostringstream oss;
            if (!connected_devices.empty()) {
                oss << "No accessible OAK/DepthAI device found. Connected USB devices exist but this account cannot open them.\n"
                    << "Install Luxonis/DepthAI udev rules or run with proper device permissions.\n"
                    << "Connected devices:";
                for (const auto& dev : connected_devices) {
                    oss << "\n  - " << dev.toString();
                }
            } else {
                oss << "No OAK/DepthAI device detected. Check USB connection and power.";
            }
            fail(oss.str());
        }

        std::cout << "selected_device=" << available_devices.front().toString() << "\n";

        dai::Pipeline pipeline = create_pipeline(config.rgb_width, config.rgb_height);
        dai::Device device(pipeline);

        auto output_queue = device.getOutputQueue("out", 4, false);

        cv::Mat latest_rgb;
        cv::Mat latest_depth;
        std::optional<InferenceResult> last_result;

        cv::namedWindow(kRgbWindowName, cv::WINDOW_NORMAL);
        cv::namedWindow(kDepthWindowName, cv::WINDOW_NORMAL);

        while (true) {
            if (auto message_group = output_queue->tryGet<dai::MessageGroup>()) {
                auto in_rgb = message_group->get<dai::ImgFrame>("rgb");
                auto in_depth = message_group->get<dai::ImgFrame>("depth_aligned");
                if (in_rgb) {
                    latest_rgb = in_rgb->getCvFrame().clone();
                }
                if (in_depth) {
                    latest_depth = in_depth->getFrame().clone();
                }
            }

            if (!latest_rgb.empty() && !latest_depth.empty()) {
                cv::Mat rgb_preview = latest_rgb.clone();
                cv::Mat depth_preview = colorize_depth(latest_depth);

                if (last_result.has_value() && !depth_preview.empty()) {
                    draw_last_result(rgb_preview, depth_preview, *last_result, config.roi_size);
                }

                cv::imshow(kRgbWindowName, rgb_preview);
                cv::imshow(kDepthWindowName, depth_preview);
            }

            const int key = cv::waitKey(1);
            if (key == 'q' || key == 'Q') {
                break;
            }
            if (key == 'c' || key == 'C') {
                if (latest_rgb.empty() || latest_depth.empty()) {
                    std::cerr << "capture skipped: RGB/depth frame not ready\n";
                    continue;
                }

                try {
                    last_result = perform_capture_and_inference(config, latest_rgb, latest_depth);
                    print_result(*last_result);
                } catch (const std::exception& exc) {
                    std::cerr << "capture failed: " << exc.what() << "\n";
                }
            }
        }

        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "fatal: " << exc.what() << "\n";
        return 1;
    }
}
