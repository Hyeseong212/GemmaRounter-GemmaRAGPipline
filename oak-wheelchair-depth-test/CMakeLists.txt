cmake_minimum_required(VERSION 3.20)
project(oak_wheelchair_depth_test CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT DEFINED OpenCV_DIR AND EXISTS "/home/rbiotech-server/miniforge/lib/cmake/opencv4/OpenCVConfig.cmake")
    set(OpenCV_DIR "/home/rbiotech-server/miniforge/lib/cmake/opencv4" CACHE PATH "OpenCV config directory")
endif()

if(NOT DEFINED CMAKE_PREFIX_PATH AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/.deps/depthai-install/lib/cmake/depthai/depthaiConfig.cmake")
    set(CMAKE_PREFIX_PATH "${CMAKE_CURRENT_SOURCE_DIR}/.deps/depthai-install" CACHE STRING "Prefix path for local dependencies")
endif()

find_package(OpenCV REQUIRED)
find_package(depthai CONFIG QUIET)

if(NOT depthai_FOUND)
    message(FATAL_ERROR
        "depthai C++ SDK not found.\n"
        "Run oak-wheelchair-depth-test/scripts/bootstrap_depthai.sh first,\n"
        "then configure with:\n"
        "  cmake -S . -B build -DCMAKE_PREFIX_PATH=/absolute/path/to/depthai-install\n")
endif()

add_executable(oak_wheelchair_depth_test
    src/main.cpp
)

target_include_directories(oak_wheelchair_depth_test PRIVATE
    ${OpenCV_INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}/../llama-rest-core/external
)

target_link_libraries(oak_wheelchair_depth_test PRIVATE
    depthai::opencv
    ${OpenCV_LIBS}
)

target_compile_options(oak_wheelchair_depth_test PRIVATE
    -Wall
    -Wextra
    -Wpedantic
)
