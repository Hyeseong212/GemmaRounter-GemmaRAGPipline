cmake_minimum_required(VERSION 3.20)
project(llama_Rest CXX)
set(CMAKE_CXX_STANDARD 17)

# 1. PIC 설정
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# 2. 경로 설정
set(LLAMA_SRC_DIR_DEFAULT "/home/rbiotech-server/llama_gemma4_latest")
if(DEFINED ENV{LLAMA_SRC_DIR} AND NOT "$ENV{LLAMA_SRC_DIR}" STREQUAL "")
    set(LLAMA_SRC_DIR "$ENV{LLAMA_SRC_DIR}")
else()
    set(LLAMA_SRC_DIR "${LLAMA_SRC_DIR_DEFAULT}")
endif()

set(BUILD_ROOT_DEFAULT "${LLAMA_SRC_DIR}/build")
if(DEFINED ENV{LLAMA_BUILD_ROOT} AND NOT "$ENV{LLAMA_BUILD_ROOT}" STREQUAL "")
    set(BUILD_ROOT "$ENV{LLAMA_BUILD_ROOT}")
else()
    set(BUILD_ROOT "${BUILD_ROOT_DEFAULT}")
endif()

# CUDA 경로
link_directories(/usr/local/cuda-13.0/lib64)
link_directories(/usr/local/cuda-13.0/targets/x86_64-linux/lib)

# ★ [수정] 중복 소스 제거! (clip.cpp 등은 libmtmd.a에 있으니 뺍니다)
add_executable(llama_Rest 
    rest.cpp          
    LLMManager.cpp
    PipelineGateway.cpp
    PipelineInternal.cpp
    PipelineService.cpp
    FirstRouterNative.cpp
    TransferRobotNative.cpp
    NativeRag.cpp
    ServerPipelineNative.cpp
    LLMManager.h
    PipelineGateway.h
    PipelineInternal.h
    PipelineService.h
)

# 4. 인클루드 경로
target_include_directories(llama_Rest PRIVATE
  ${LLAMA_SRC_DIR}/include
  ${LLAMA_SRC_DIR}/src
  ${LLAMA_SRC_DIR}/common
  ${LLAMA_SRC_DIR}/ggml/include
  ${LLAMA_SRC_DIR}/ggml/src
  ${LLAMA_SRC_DIR}/ggml/src/ggml-cuda 
  ${LLAMA_SRC_DIR}/tools/mtmd
  ${LLAMA_SRC_DIR}/tools/mtmd/models
  /usr/local/cuda-13.0/include
)

find_package(Threads REQUIRED)
find_package(OpenMP REQUIRED)

# 5. 라이브러리 경로 (HS님이 확인해주신 경로)
set(LIB_LLAMA      "${BUILD_ROOT}/src/libllama.a")
set(LIB_COMMON     "${BUILD_ROOT}/common/libcommon.a")
set(LIB_MTMD       "${BUILD_ROOT}/tools/mtmd/libmtmd.a")
set(LIB_GGML       "${BUILD_ROOT}/ggml/src/libggml.a")
set(LIB_GGML_CUDA  "${BUILD_ROOT}/ggml/src/ggml-cuda/libggml-cuda.a")
set(LIB_GGML_BASE  "${BUILD_ROOT}/ggml/src/libggml-base.a")
set(LIB_GGML_CPU   "${BUILD_ROOT}/ggml/src/libggml-cpu.a")

# 6. 파일 존재 확인
foreach(LIB_PATH ${LIB_LLAMA} ${LIB_COMMON} ${LIB_MTMD} ${LIB_GGML} ${LIB_GGML_CUDA} ${LIB_GGML_BASE} ${LIB_GGML_CPU})
    if(NOT EXISTS "${LIB_PATH}")
        message(FATAL_ERROR "❌ 라이브러리 파일 누락: ${LIB_PATH}")
    endif()
endforeach()

# 7. 링킹
target_link_options(llama_Rest PRIVATE "-no-pie")

target_link_libraries(llama_Rest PRIVATE
    "-Wl,--start-group"
    ${LIB_LLAMA}
    ${LIB_COMMON}
    ${LIB_MTMD}      # 여기에 clip, qwen, siglip 기능이 다 들어있음
    ${LIB_GGML}
    ${LIB_GGML_CUDA}
    ${LIB_GGML_BASE}
    ${LIB_GGML_CPU}
    "-Wl,--end-group"
    
    OpenMP::OpenMP_CXX
    Threads::Threads
    dl
    rt
    cuda
    cudart
    cublas
    cublasLt
    nccl
)

target_compile_definitions(llama_Rest PRIVATE GGML_USE_CUDA)
