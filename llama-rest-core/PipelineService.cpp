#include "PipelineService.h"

#include "PipelineInternal.h"

using pipeline_internal::getenv_or_default;
using pipeline_internal::getenv_or_default_bool;
using pipeline_internal::getenv_or_default_double;
using pipeline_internal::getenv_or_default_int;
using pipeline_internal::load_text_file;
using pipeline_internal::repo_root;

PipelineService::PipelineService() {
    const auto root = repo_root();
    config_.first_router_model_enabled = getenv_or_default_bool("FIRST_ROUTER_MODEL_ENABLED", true);
    config_.first_router_model_endpoint = getenv_or_default(
        "ROUTER_MODEL_ENDPOINT",
        "http://127.0.0.1:8080/v1/chat/completions"
    );
    config_.first_router_model_name = getenv_or_default("ROUTER_MODEL_NAME", "gemma-4-31b-it");
    config_.first_router_system_prompt = load_text_file(
        getenv_or_default(
            "ROUTER_PROMPT_PATH",
            (root / "first-router" / "prompts" / "medical_router_system_prompt.txt").string()
        )
    );
    config_.first_router_local_answer_prompt = load_text_file(
        getenv_or_default(
            "LOCAL_ANSWER_PROMPT_PATH",
            (root / "first-router" / "prompts" / "local_short_answer_system_prompt.txt").string()
        )
    );
    config_.first_router_request_timeout = getenv_or_default_double("ROUTER_REQUEST_TIMEOUT", 20.0);
    config_.first_router_temperature = getenv_or_default_double("ROUTER_TEMPERATURE", 0.2);
    config_.first_router_max_tokens = getenv_or_default_int("ROUTER_MAX_TOKENS", 96);
    config_.first_router_local_answer_temperature = getenv_or_default_double("LOCAL_ANSWER_TEMPERATURE", 0.2);
    config_.first_router_local_answer_max_tokens = getenv_or_default_int("LOCAL_ANSWER_MAX_TOKENS", 48);
    config_.first_router_reasoning_mode = getenv_or_default("ROUTER_REASONING_MODE", "off");
    config_.first_router_reasoning_budget = getenv_or_default_int("ROUTER_REASONING_BUDGET", 0);

    config_.transfer_robot_model_enabled = getenv_or_default_bool("TRANSFER_ROBOT_MODEL_ENABLED", true);
    config_.transfer_robot_model_endpoint = getenv_or_default(
        "TRANSFER_ROBOT_MODEL_ENDPOINT",
        config_.first_router_model_endpoint
    );
    config_.transfer_robot_model_name = getenv_or_default("TRANSFER_ROBOT_MODEL_NAME", "gemma-4-31b-it");
    config_.transfer_robot_system_prompt = load_text_file(
        getenv_or_default(
            "TRANSFER_ROBOT_PROMPT_PATH",
            (root / "transfer-robot-llm" / "prompts" / "transfer_robot_system_prompt.txt").string()
        )
    );
    config_.transfer_robot_request_timeout = getenv_or_default_double(
        "TRANSFER_ROBOT_REQUEST_TIMEOUT",
        config_.first_router_request_timeout
    );
    config_.transfer_robot_temperature = getenv_or_default_double("TRANSFER_ROBOT_TEMPERATURE", 0.2);
    config_.transfer_robot_max_tokens = getenv_or_default_int("TRANSFER_ROBOT_MAX_TOKENS", 160);
    config_.transfer_robot_reasoning_mode = getenv_or_default("TRANSFER_ROBOT_REASONING_MODE", "off");
    config_.transfer_robot_reasoning_budget = getenv_or_default_int("TRANSFER_ROBOT_REASONING_BUDGET", 0);

    config_.router_model_enabled = getenv_or_default_bool("SERVER_ROUTER_MODEL_ENABLED", true);
    config_.router_model_endpoint = getenv_or_default(
        "SERVER_ROUTER_MODEL_ENDPOINT",
        "http://127.0.0.1:8180/v1/chat/completions"
    );
    config_.router_model_name = getenv_or_default("SERVER_ROUTER_MODEL_NAME", "gemma-4-31b-it");
    config_.router_system_prompt = load_text_file(
        getenv_or_default(
            "SERVER_ROUTER_PROMPT_PATH",
            (root / "second-router" / "prompts" / "server_router_system_prompt.txt").string()
        )
    );
    config_.request_timeout = getenv_or_default_double("SERVER_ROUTER_REQUEST_TIMEOUT", 30.0);
    config_.router_temperature = getenv_or_default_double("SERVER_ROUTER_TEMPERATURE", 0.1);
    config_.router_max_tokens = getenv_or_default_int("SERVER_ROUTER_MAX_TOKENS", 160);
    config_.router_reasoning_mode = getenv_or_default("SERVER_ROUTER_REASONING_MODE", "off");
    config_.router_reasoning_budget = getenv_or_default_int("SERVER_ROUTER_REASONING_BUDGET", 0);

    config_.answer_model_endpoint = getenv_or_default(
        "SERVER_ANSWER_MODEL_ENDPOINT",
        config_.router_model_endpoint
    );
    config_.answer_model_name = getenv_or_default("SERVER_ANSWER_MODEL_NAME", "gemma-4-31b-it");
    config_.answer_system_prompt = load_text_file(
        getenv_or_default(
            "SERVER_ANSWER_PROMPT_PATH",
            (root / "second-router" / "prompts" / "server_answer_system_prompt.txt").string()
        )
    );
    config_.answer_temperature = getenv_or_default_double("SERVER_ANSWER_TEMPERATURE", 0.2);
    config_.answer_max_tokens = getenv_or_default_int("SERVER_ANSWER_MAX_TOKENS", 400);

    config_.rag_model_enabled = getenv_or_default_bool("RAG_MODEL_ENABLED", true);
    config_.rag_model_endpoint = getenv_or_default(
        "RAG_MODEL_ENDPOINT",
        config_.answer_model_endpoint
    );
    config_.rag_model_name = getenv_or_default("RAG_MODEL_NAME", "gemma-4-31b-it");
    config_.rag_system_prompt = load_text_file(
        getenv_or_default(
            "RAG_PROMPT_PATH",
            (root / "rag-answerer" / "prompts" / "rag_answer_system_prompt.txt").string()
        )
    );
    config_.rag_temperature = getenv_or_default_double("RAG_TEMPERATURE", 0.1);
    config_.rag_max_tokens = getenv_or_default_int("RAG_MAX_TOKENS", 400);
    config_.rag_reasoning_mode = getenv_or_default("RAG_REASONING_MODE", "off");
    config_.rag_reasoning_budget = getenv_or_default_int("RAG_REASONING_BUDGET", 0);
    config_.rag_request_timeout = getenv_or_default_double("RAG_REQUEST_TIMEOUT", config_.request_timeout);
    config_.rag_corpus_dir = getenv_or_default(
        "RAG_CORPUS_DIR",
        (root / "rag-answerer" / "test-corpus" / "mfds-korean-medical-device" / "text").string()
    );
    config_.rag_index_dir = getenv_or_default(
        "RAG_INDEX_DIR",
        (root / "rag-answerer" / "indexes" / "mfds-korean-medical-device-text-bge-m3").string()
    );
    config_.rag_embedding_endpoint = getenv_or_default(
        "RAG_EMBEDDING_ENDPOINT",
        "http://127.0.0.1:18089/embed"
    );
    config_.rag_embedding_timeout = getenv_or_default_double("RAG_EMBEDDING_TIMEOUT", 30.0);
    config_.rag_top_k = getenv_or_default_int("RAG_TOP_K", 6);
    config_.rag_min_score = getenv_or_default_double("RAG_MIN_SCORE", 0.18);

    initialize_rag_corpus();
}
