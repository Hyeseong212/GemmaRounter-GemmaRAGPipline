#ifndef PIPELINE_SERVICE_H
#define PIPELINE_SERVICE_H

#include <cstddef>
#include <string>
#include <vector>

#include "external/nlohmann/json.hpp"

class PipelineService {
public:
    PipelineService();

    nlohmann::json first_route(const nlohmann::json& request, bool debug) const;
    nlohmann::json first_handle(const nlohmann::json& request, bool debug) const;
    nlohmann::json transfer_robot_stt(const nlohmann::json& request, bool debug) const;
    nlohmann::json rag_ask(const nlohmann::json& request, bool debug) const;
    nlohmann::json route(const nlohmann::json& request, bool debug) const;
    nlohmann::json route_from_first_router(const nlohmann::json& request, bool debug) const;
    nlohmann::json score(const nlohmann::json& request, bool debug) const;
    nlohmann::json process_from_first_router(const nlohmann::json& request, bool debug) const;
    nlohmann::json process_from_user(const nlohmann::json& request, bool debug) const;
    nlohmann::json health_snapshot() const;

private:
    nlohmann::json first_route_internal(const nlohmann::json& request) const;
    nlohmann::json first_handle_internal(const nlohmann::json& request) const;
    nlohmann::json transfer_robot_stt_internal(const nlohmann::json& request) const;
    nlohmann::json rag_ask_internal(const nlohmann::json& request) const;
    void initialize_rag_corpus();

    struct Config {
        bool first_router_model_enabled = true;
        std::string first_router_model_endpoint;
        std::string first_router_model_name;
        std::string first_router_system_prompt;
        std::string first_router_local_answer_prompt;
        double first_router_request_timeout = 20.0;
        double first_router_temperature = 0.2;
        int first_router_max_tokens = 96;
        double first_router_local_answer_temperature = 0.2;
        int first_router_local_answer_max_tokens = 48;
        std::string first_router_reasoning_mode = "off";
        int first_router_reasoning_budget = 0;

        bool transfer_robot_model_enabled = true;
        std::string transfer_robot_model_endpoint;
        std::string transfer_robot_model_name;
        std::string transfer_robot_system_prompt;
        double transfer_robot_request_timeout = 20.0;
        double transfer_robot_temperature = 0.2;
        int transfer_robot_max_tokens = 160;
        std::string transfer_robot_reasoning_mode = "off";
        int transfer_robot_reasoning_budget = 0;

        bool router_model_enabled = true;
        std::string router_model_endpoint;
        std::string router_model_name;
        std::string router_system_prompt;
        double request_timeout = 30.0;
        double router_temperature = 0.1;
        int router_max_tokens = 160;
        std::string router_reasoning_mode = "off";
        int router_reasoning_budget = 0;

        std::string answer_model_endpoint;
        std::string answer_model_name;
        std::string answer_system_prompt;
        double answer_temperature = 0.2;
        int answer_max_tokens = 400;

        bool rag_model_enabled = true;
        std::string rag_model_endpoint;
        std::string rag_model_name;
        std::string rag_system_prompt;
        double rag_temperature = 0.1;
        int rag_max_tokens = 400;
        std::string rag_reasoning_mode = "off";
        int rag_reasoning_budget = 0;
        double rag_request_timeout = 30.0;
        std::string rag_corpus_dir;
        std::string rag_index_dir;
        std::string rag_embedding_endpoint;
        double rag_embedding_timeout = 30.0;
        int rag_top_k = 6;
        double rag_min_score = 0.18;
    };

    Config config_;
    nlohmann::json rag_corpus_chunks_ = nlohmann::json::array();
    std::vector<float> rag_dense_embeddings_;
    std::size_t rag_embedding_dim_ = 0;
    std::size_t rag_document_count_ = 0;
    std::size_t rag_page_count_ = 0;
};

#endif
