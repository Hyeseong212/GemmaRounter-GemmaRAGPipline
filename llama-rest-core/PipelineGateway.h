#ifndef PIPELINE_GATEWAY_H
#define PIPELINE_GATEWAY_H

#include "external/httplib.h"
#include "PipelineService.h"

class PipelineGateway {
public:
    PipelineGateway();

    void register_routes(httplib::Server& server) const;

private:
    PipelineService service_;

    void handle_json_exception(httplib::Response& res, const std::exception& exc) const;
    void handle_pipeline_health(httplib::Response& res) const;
};

#endif
