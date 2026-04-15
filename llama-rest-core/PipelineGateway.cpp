#include "PipelineGateway.h"

#include <cstdlib>
#include <string>

namespace {

bool getenv_or_default_bool(const char* key, bool default_value) {
    const char* value = std::getenv(key);
    if (!value || !*value) {
        return default_value;
    }

    const std::string normalized = value;
    return !(normalized == "0" || normalized == "false" || normalized == "FALSE");
}

}  // namespace

PipelineGateway::PipelineGateway() = default;

void PipelineGateway::register_routes(httplib::Server& server) const {
    const bool enable_dev_first_router = getenv_or_default_bool("LLAMA_REST_ENABLE_DEV_FIRST_ROUTER", false);
    const bool enable_dev_pipeline_from_user = getenv_or_default_bool("LLAMA_REST_ENABLE_DEV_PIPELINE_FROM_USER", false);

    if (enable_dev_first_router) {
        server.Post("/first-router/route", [this](const httplib::Request& req, httplib::Response& res) {
            try {
                res.set_content(service_.first_route(nlohmann::json::parse(req.body), false).dump(2), "application/json; charset=utf-8");
            } catch (const std::exception& exc) {
                handle_json_exception(res, exc);
            }
        });

        server.Post("/first-router/route/debug", [this](const httplib::Request& req, httplib::Response& res) {
            try {
                res.set_content(service_.first_route(nlohmann::json::parse(req.body), true).dump(2), "application/json; charset=utf-8");
            } catch (const std::exception& exc) {
                handle_json_exception(res, exc);
            }
        });

        server.Post("/first-router/handle", [this](const httplib::Request& req, httplib::Response& res) {
            try {
                res.set_content(service_.first_handle(nlohmann::json::parse(req.body), false).dump(2), "application/json; charset=utf-8");
            } catch (const std::exception& exc) {
                handle_json_exception(res, exc);
            }
        });
    }

    server.Post("/transfer-robot/stt", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.transfer_robot_stt(nlohmann::json::parse(req.body), false).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/transfer-robot/stt/debug", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.transfer_robot_stt(nlohmann::json::parse(req.body), true).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/ask", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.rag_ask(nlohmann::json::parse(req.body), false).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/ask/debug", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.rag_ask(nlohmann::json::parse(req.body), true).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/rag/ask", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.rag_ask(nlohmann::json::parse(req.body), false).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/rag/ask/debug", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.rag_ask(nlohmann::json::parse(req.body), true).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/route", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.route(nlohmann::json::parse(req.body), false).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/route/debug", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.route(nlohmann::json::parse(req.body), true).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/route/from-first-router/debug", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.route_from_first_router(nlohmann::json::parse(req.body), true).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/route/from-first-router", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.route_from_first_router(nlohmann::json::parse(req.body), false).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/score", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.score(nlohmann::json::parse(req.body), false).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/score/debug", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.score(nlohmann::json::parse(req.body), true).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/process/from-first-router/debug", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.process_from_first_router(nlohmann::json::parse(req.body), true).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    server.Post("/process/from-first-router", [this](const httplib::Request& req, httplib::Response& res) {
        try {
            res.set_content(service_.process_from_first_router(nlohmann::json::parse(req.body), false).dump(2), "application/json; charset=utf-8");
        } catch (const std::exception& exc) {
            handle_json_exception(res, exc);
        }
    });

    if (enable_dev_pipeline_from_user) {
        server.Post("/pipeline/from-user", [this](const httplib::Request& req, httplib::Response& res) {
            try {
                res.set_content(service_.process_from_user(nlohmann::json::parse(req.body), false).dump(2), "application/json; charset=utf-8");
            } catch (const std::exception& exc) {
                handle_json_exception(res, exc);
            }
        });

        server.Post("/pipeline/from-user/debug", [this](const httplib::Request& req, httplib::Response& res) {
            try {
                res.set_content(service_.process_from_user(nlohmann::json::parse(req.body), true).dump(2), "application/json; charset=utf-8");
            } catch (const std::exception& exc) {
                handle_json_exception(res, exc);
            }
        });
    }

    server.Get("/healthz", [](const httplib::Request&, httplib::Response& res) {
        res.set_content(
            "{\n"
            "  \"status\": \"ok\",\n"
            "  \"service\": \"llama-rest-core\"\n"
            "}\n",
            "application/json; charset=utf-8"
        );
    });

    server.Get("/healthz/pipeline", [this](const httplib::Request&, httplib::Response& res) {
        handle_pipeline_health(res);
    });
}

void PipelineGateway::handle_json_exception(httplib::Response& res, const std::exception& exc) const {
    res.status = 400;
    res.set_content(
        nlohmann::json{
            {"error", "bad_request"},
            {"detail", exc.what()},
        }.dump(2),
        "application/json; charset=utf-8"
    );
}

void PipelineGateway::handle_pipeline_health(httplib::Response& res) const {
    const auto snapshot = service_.health_snapshot();
    res.status = snapshot.value("status", "ok") == "ok" ? 200 : 503;
    res.set_content(snapshot.dump(2), "application/json; charset=utf-8");
}
