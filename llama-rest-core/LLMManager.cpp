#include "LLMManager.h"
#include "mtmd-image.h"
#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"
#include <cstring>
#include <iostream>
#include <thread>
#include <algorithm>
#include <cmath>
#include <cstdlib>

namespace {

void finish_slot_with_error(InferenceSlot& slot, const std::string& message) {
    if (slot.callback) {
        slot.callback("[ERROR] " + message);
    }
    slot.is_active = false;
}

int getenv_int_or(const char * key, int default_value) {
    const char * value = std::getenv(key);
    if (!value || !*value) {
        return default_value;
    }
    try {
        return std::stoi(value);
    } catch (...) {
        return default_value;
    }
}

}

// --------------------------------------------------------------------------
// [헬퍼] 텍스트 토큰 배치 추가
// --------------------------------------------------------------------------
static void my_batch_add(struct llama_batch & batch, llama_token id, llama_pos pos, const std::vector<llama_seq_id> & seq_ids, bool logits) {
    batch.token   [batch.n_tokens] = id;
    batch.pos     [batch.n_tokens] = pos;
    batch.n_seq_id[batch.n_tokens] = seq_ids.size();
    for (size_t i = 0; i < seq_ids.size(); ++i) {
        batch.seq_id[batch.n_tokens][i] = seq_ids[i];
    }
    batch.logits  [batch.n_tokens] = logits ? 1 : 0;
    batch.n_tokens++;
}

// --------------------------------------------------------------------------
// [헬퍼] 이미지 임베딩 배치 추가
// --------------------------------------------------------------------------
// [LLMManager.cpp] 상단 my_batch_add_embd 함수 교체

static void my_batch_add_embd(struct llama_batch & batch, float * embd_data, int clip_n_embd, int model_n_embd, llama_pos pos, const std::vector<llama_seq_id> & seq_ids) {
    // [수정] token 배열이 존재할 때만 값을 씀 (임베딩 전용 배치에서는 token이 NULL임)
    if (batch.token) {
        batch.token[batch.n_tokens] = -1; 
    }
    
    if (batch.embd) {
        // 정확한 오프셋 계산 (모델 임베딩 차원 기준)
        memcpy(batch.embd + (batch.n_tokens * model_n_embd), embd_data, clip_n_embd * sizeof(float));
    }

    batch.pos[batch.n_tokens] = pos;
    batch.n_seq_id[batch.n_tokens] = seq_ids.size();
    for (size_t i = 0; i < seq_ids.size(); ++i) {
        batch.seq_id[batch.n_tokens][i] = seq_ids[i];
    }
    batch.logits[batch.n_tokens] = 0; 
    batch.n_tokens++;
}
// --------------------------------------------------------------------------
// 생성자: 모델 로드 및 초기화
// --------------------------------------------------------------------------
LLMManager::LLMManager(const std::string& modelPath, const std::string& mmprojPath, int n_parallel)
    : n_parallel(n_parallel), batch_capacity(6144) //batch_capacity(8192) gemma
    { 
    
    std::cout << "\n========================================\n";
    std::cout << "[LLMManager] Initializing...\n";
    std::cout << "========================================\n";

    // 1. LLM 모델 로드
    llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = 99; 
    static float tensor_split[2] = {0.4f, 0.6f}; 
     model_params.tensor_split = tensor_split;
    model = llama_model_load_from_file(modelPath.c_str(), model_params);
    if (!model) { std::cerr << "❌ [Error] Failed to load LLM from: " << modelPath << "\n"; return; }
    else { std::cout << "✅ [LLM] Model Loaded Successfully.\n"; }

    // 2. Vision (CLIP) 로드 확인
    if (!mmprojPath.empty()) {
        std::cout << "\n[Vision Check] Trying to load CLIP...\n";
        std::cout << "   👉 Path: [" << mmprojPath << "]\n";

        // (1) 파일 존재 여부 물리적 확인
        FILE* f = fopen(mmprojPath.c_str(), "rb");
        if (!f) {
            std::cerr << "   ❌ [CRITICAL] File NOT FOUND at this path! (Check typos)\n";
            ctx_clip = nullptr;
        } else {
            // 파일 크기 체크
            fseek(f, 0, SEEK_END);
            long fsize = ftell(f);
            fclose(f);
            
            std::cout << "   ✅ File exists. Size: " << fsize << " bytes.\n";

            if (fsize < 1000) {
                 std::cerr << "   ❌ [CRITICAL] File is too small! (Download failed?)\n";
                 ctx_clip = nullptr;
            } else {
                // (2) 실제 로딩 시도
                struct clip_context_params params = {};
                params.use_gpu = true;
                params.image_min_tokens = getenv_int_or("LLAMA_REST_IMAGE_MIN_TOKENS", -1);
                params.image_max_tokens = getenv_int_or("LLAMA_REST_IMAGE_MAX_TOKENS", -1);
                std::cout << "   👉 image_min_tokens: " << params.image_min_tokens << "\n";
                std::cout << "   👉 image_max_tokens: " << params.image_max_tokens << "\n";
                
                std::cout << "   🔄 Calling clip_init()...\n";
                struct clip_init_result res = clip_init(mmprojPath.c_str(), params);
                ctx_clip = res.ctx_v;
                
                if (ctx_clip) {
                    std::cout << "   ✅ [Vision] CLIP Model Loaded Successfully!\n";
                } else {
                    std::cerr << "   ❌ [Vision] clip_init() failed! (Model format mismatch?)\n";
                }
            }
        }
    } else {
        std::cout << "ℹ️ [Vision] No mmproj path provided. Vision disabled.\n";
    }
    std::cout << "========================================\n\n";

    // 3. 컨텍스트 및 슬롯 초기화
    vocab = llama_model_get_vocab(model);
    llama_context_params ctx_params = llama_context_default_params();
    //ctx_params.n_ctx = 8192; gemma
    ctx_params.n_ctx = 8192; // internv3l  
    ctx_params.n_batch = 6144; 
    ctx_params.n_ubatch = 512;
    struct llama_context* ctx = llama_init_from_model(model, ctx_params);
    contexts.push_back(ctx);

    slots.resize(n_parallel);
    for (int i = 0; i < n_parallel; ++i) {
        slots[i].id = i;
        slots[i].is_active = false;
        slots[i].sampler = llama_sampler_chain_init(llama_sampler_chain_default_params());
        llama_sampler_chain_add(slots[i].sampler, llama_sampler_init_temp(0.15f));
        llama_sampler_chain_add(slots[i].sampler, llama_sampler_init_top_k(40));
        llama_sampler_chain_add(slots[i].sampler, llama_sampler_init_top_p(0.95f, 1));
        llama_sampler_chain_add(slots[i].sampler, llama_sampler_init_dist(LLAMA_DEFAULT_SEED));
    }

    int n_embd = llama_model_n_embd(model); 
    batch_text = llama_batch_init(batch_capacity, 0, 1);
    batch_image = llama_batch_init(batch_capacity, n_embd, 1);
}

LLMManager::~LLMManager() {
    for (auto& s : slots) if (s.sampler) llama_sampler_free(s.sampler);
    
    // 두 배치 모두 해제
    llama_batch_free(batch_text);
    llama_batch_free(batch_image);
    
    for (auto* c : contexts) llama_free(c);
    if (ctx_clip) clip_free(ctx_clip);
    if (model) llama_model_free(model);
}

bool LLMManager::isValid() const { return model != nullptr; }
bool LLMManager::has_free_slot() { for (const auto& s : slots) if (!s.is_active) return true; return false; }
bool LLMManager::is_all_idle() { for (const auto& s : slots) if (s.is_active) return false; return true; }

// --------------------------------------------------------------------------
// [핵심] 요청 추가 (이미지 처리 및 추적 로그 포함)
// --------------------------------------------------------------------------
// [LLMManager.cpp] add_request 함수 전체

bool LLMManager::add_request(const std::string& prompt, const std::string& image_bytes, std::function<void(std::string)> on_complete) {
    // 1. 빈 슬롯 찾기
    int slot_idx = -1;
    for (int i = 0; i < n_parallel; ++i) { 
        if (!slots[i].is_active) { 
            slot_idx = i; 
            break; 
        } 
    }
    if (slot_idx == -1) return false;

    std::cout << "[Debug Manager] add_request called.\n";
    
    // 2. 슬롯 초기화
    InferenceSlot& slot = slots[slot_idx];
    slot.is_active = true;
    slot.callback = on_complete;
    slot.generated_text = "";
    slot.n_pos = 0;
    slot.pending_input_tokens.clear();

    struct llama_context* ctx = contexts[0];

    // 3. 이전 기억(KV Cache) 삭제
    llama_memory_t mem = llama_get_memory(ctx);
    llama_memory_seq_rm(mem, slot.id, -1, -1);

    // ▼▼▼ [핵심 수정 구간: 프롬프트 분리 및 순차적 KV 캐시 할당] ▼▼▼

    // 4. 프롬프트 파싱 (<image> 태그 기준 분리)
    std::string prefix = "";
    std::string suffix = prompt;
    size_t img_pos = prompt.find("<image>");
    
    if (img_pos != std::string::npos) {
        prefix = prompt.substr(0, img_pos);
        suffix = prompt.substr(img_pos + 7); // "<image>" 길이(7)만큼 건너뜀
    } else if (!image_bytes.empty()) {
    // [수정 1] InternVL 3.5 (Qwen 기반) 전용 프롬프트 템플릿 적용
        prefix = "<|im_start|>system\nYou are a helpful medical AI assistant.<|im_end|>\n<|im_start|>user\n";
        suffix = "\n" + prompt + "<|im_end|>\n<|im_start|>assistant\n";
    } else {
        // 이미지가 없는 경우
        prefix = "<|im_start|>system\n당신은 한국어로 소통하는 재활의학 전문 AI입니다. 사용자의 질문에 대해 제공된 문서를 바탕으로 친절한 한국어로 답변하십시오.<|im_end|>\n<|im_start|>user\n";
        suffix = prompt + "<|im_end|>\n<|im_start|>assistant\n";
    }

    // 5. Prefix 텍스트 처리 (이미지 앞부분 텍스트) -> 즉시 디코드
    if (!prefix.empty()) {
        std::vector<llama_token> prefix_tokens(prefix.size() + 32);
        // add_bos = true (대화의 시작이므로 BOS 추가)
        int n_tok = llama_tokenize(vocab, prefix.c_str(), prefix.size(), prefix_tokens.data(), prefix_tokens.size(), true, true);
        if (n_tok < 0) {
            prefix_tokens.resize(-n_tok);
            n_tok = llama_tokenize(vocab, prefix.c_str(), prefix.size(), prefix_tokens.data(), prefix_tokens.size(), true, true);
        }
        prefix_tokens.resize(n_tok);

        batch_text.n_tokens = 0;
        for (size_t i = 0; i < prefix_tokens.size(); i++) {
            my_batch_add(batch_text, prefix_tokens[i], slot.n_pos++, {slot.id}, false);
        }
        if (batch_text.n_tokens > 0) {
            if (llama_decode(ctx, batch_text) != 0) {
                finish_slot_with_error(slot, "Prefix decode failed");
                return false;
            }
            std::cout << "✅ [Trace] Prefix text decoded. Tokens: " << batch_text.n_tokens << "\n";
        }
    }

// 6. [이미지 처리 로직] -> 즉시 디코드 (Prefix 바로 뒤에 이어짐)
    if (!image_bytes.empty() && ctx_clip) {
        std::cout << "[Slot " << slot_idx << "] Processing Image...\n";
        int nx, ny, nc;
        unsigned char * data = stbi_load_from_memory((const stbi_uc*)image_bytes.data(), image_bytes.size(), &nx, &ny, &nc, 3);
        
        if (data) {
            struct clip_image_u8 * img = clip_image_u8_init();
            clip_build_img_from_pixels(data, nx, ny, img);
            stbi_image_free(data);

            struct clip_image_f32_batch * imgs = clip_image_f32_batch_init();
            mtmd_image_preprocessor_dyn_size image_preprocessor(ctx_clip);
            if (image_preprocessor.preprocess(*img, *imgs)) {
                
                // ▼▼▼ [수정 2] Opaque Pointer 에러 우회 (while 루프 적용) ▼▼▼
                int total_tokens = 0;
                int patch_count = 0;
                
                // imgs->size에 직접 접근하는 대신, nullptr이 반환될 때까지 안전하게 순회합니다.
                while (true) {
                    struct clip_image_f32 * res_img = clip_image_f32_get_img(imgs, patch_count);
                    if (!res_img) break; // 더 이상 조각(Patch)이 없으면 탈출
                    
                    total_tokens += clip_n_output_tokens(ctx_clip, res_img);
                    patch_count++;
                }
                
                int n_embd_clip = clip_n_mmproj_embd(ctx_clip);
                std::vector<float> image_embd(total_tokens * n_embd_clip);
                
                if (clip_image_batch_encode(ctx_clip, 4, imgs, image_embd.data())) {
                    int model_n_embd = llama_model_n_embd(model);       
                    batch_image.n_tokens = 0;
                    for (int i = 0; i < total_tokens; i++) {
                        my_batch_add_embd(batch_image, image_embd.data() + (i * n_embd_clip), n_embd_clip, model_n_embd, slot.n_pos++, {slot.id});
                    }
                    std::cout << "✅ [Trace] Image Batch filling done. Total tokens: " << batch_image.n_tokens << " (Patches: " << patch_count << ")\n";
                    int decode_res = llama_decode(ctx, batch_image);
                    if (decode_res != 0) {
                        std::cerr << "❌ [Error] Image decode failed: " << decode_res << "\n";
                        finish_slot_with_error(slot, "Image decode failed");
                        clip_image_f32_batch_free(imgs);
                        clip_image_u8_free(img);
                        return false;
                    }
                }
                // ▲▲▲ [수정 끝] ▲▲▲
            }
            clip_image_f32_batch_free(imgs);
            clip_image_u8_free(img);
        }
    }

    // 7. Suffix 텍스트 처리 (이미지 뒷부분 텍스트) -> step()에서 처리하도록 pending에 큐잉
    if (!suffix.empty()) {
        std::vector<llama_token> suffix_tokens(suffix.size() + 32);
        // [중요] add_bos = false로 설정하여 문장 중간에 시작 기호가 또 들어가는 것을 방지
        int n_tok = llama_tokenize(vocab, suffix.c_str(), suffix.size(), suffix_tokens.data(), suffix_tokens.size(), false, true);
        if (n_tok < 0) {
            suffix_tokens.resize(-n_tok);
            n_tok = llama_tokenize(vocab, suffix.c_str(), suffix.size(), suffix_tokens.data(), suffix_tokens.size(), false, true);
        }
        suffix_tokens.resize(n_tok);
        slot.pending_input_tokens = suffix_tokens;
        std::cout << "✅ [Trace] Suffix text queued. Tokens: " << suffix_tokens.size() << "\n";
    } else {
        slot.pending_input_tokens.clear();
    }

    return true;
}


// --------------------------------------------------------------------------
// 스텝 함수: 실제 추론 진행 및 터미널 출력
// --------------------------------------------------------------------------
void LLMManager::step() {
    struct llama_context* ctx = contexts[0];

    for (auto& slot : slots) {
        if (!slot.is_active) continue;

        // Prefill (입력 텍스트 처리)
        if (!slot.pending_input_tokens.empty()) {
            batch_text.n_tokens = 0; 
            int chunk = (std::min)((int)slot.pending_input_tokens.size(), batch_capacity);
            
            for (int i = 0; i < chunk; ++i) {
                my_batch_add(batch_text, slot.pending_input_tokens[i], slot.n_pos++, { slot.id }, false);
            }
            batch_text.logits[batch_text.n_tokens - 1] = true;
            
            slot.pending_input_tokens.erase(slot.pending_input_tokens.begin(), slot.pending_input_tokens.begin() + chunk);
            
            if (llama_decode(ctx, batch_text) != 0) {
                std::cerr << "[Error] Decode failed in step (prefill)\n";
                finish_slot_with_error(slot, "Prefill decode failed");
                continue;
            }
            if (!slot.pending_input_tokens.empty()) continue; 
        }

        // Generate (다음 단어 생성)
        llama_token new_token = llama_sampler_sample(slot.sampler, ctx, batch_text.n_tokens - 1);
        std::cout << "[Debug Token ID: " << new_token << "]" << std::endl;
        //if (llama_vocab_is_eog(vocab, new_token) || slot.n_pos >= 8192) { gemma
        if (llama_vocab_is_eog(vocab, new_token) || slot.n_pos >= 16384) {
            std::cout << "[Slot " << slot.id << "] Done.\n";
            if (slot.callback) slot.callback(slot.generated_text);
            slot.is_active = false;
            continue;
        }

        char buf[256];
        int n = llama_token_to_piece(vocab, new_token, buf, sizeof(buf), 0, true);
        if (n >= 0) {
            std::string piece = std::string(buf, n);
            slot.generated_text += piece;

            // 터미널 실시간 출력
            std::cout << piece << std::flush; 
        }

        batch_text.n_tokens = 0;
        my_batch_add(batch_text, new_token, slot.n_pos++, { slot.id }, true);
        
        if (llama_decode(ctx, batch_text) != 0) {
            std::cerr << "[Error] Decode failed in step (generate)\n";
            finish_slot_with_error(slot, "Generate decode failed");
        }
    }
}
