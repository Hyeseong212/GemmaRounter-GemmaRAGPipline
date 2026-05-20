#ifndef LLMMANAGER_H
#define LLMMANAGER_H

#include <vector>
#include <string>
#include <functional>
#include <iostream>
#include <mutex>

#include "llama.h"
#include "clip.h"

struct InferenceSlot {
    int id;
    int context_index = -1;
    bool is_active;
    std::string generated_text;
    std::vector<llama_token> pending_input_tokens;
    int n_pos = 0;
    struct llama_sampler* sampler = nullptr;
    struct llama_batch batch_text = {};
    struct llama_batch batch_image = {};
    std::function<void(std::string)> callback;
};

class LLMManager {
public:
    LLMManager(const std::string& modelPath, const std::string& mmprojPath, int n_parallel);
    ~LLMManager();

    bool isValid() const;
    std::string infer_on_slot(int slot_idx, const std::string& prompt, const std::string& image_bytes);
    bool add_request(const std::string& prompt, const std::string& image_bytes, std::function<void(std::string)> on_complete);
    
    bool has_free_slot();
    void step();        
    bool is_all_idle();

private:
    struct llama_model* model = nullptr;       
    struct clip_ctx* ctx_clip = nullptr; 
    const struct llama_vocab* vocab = nullptr;
    
    std::vector<struct llama_context*> contexts; 
    std::vector<InferenceSlot> slots;
    std::mutex vision_mutex;

    int n_parallel;         
    int batch_capacity;
    int n_ctx;
};

#endif
