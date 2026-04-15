#ifndef LLMMANAGER_H
#define LLMMANAGER_H

#include <vector>
#include <string>
#include <functional>
#include <iostream>

#include "llama.h"
#include "clip.h"

struct InferenceSlot {
    int id;
    bool is_active;
    std::string generated_text;
    std::vector<llama_token> pending_input_tokens;
    int n_pos;                  
    struct llama_sampler* sampler = nullptr;
    std::function<void(std::string)> callback;
};

class LLMManager {
public:
    LLMManager(const std::string& modelPath, const std::string& mmprojPath, int n_parallel);
    ~LLMManager();

    bool isValid() const;
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
    
    // ★ [수정] 배치를 용도별로 분리하여 충돌 방지
    struct llama_batch batch_text;  // 텍스트용 (임베딩 X)
    struct llama_batch batch_image; // 이미지용 (임베딩 O)
    
    int n_parallel;         
    int batch_capacity;     
};

#endif