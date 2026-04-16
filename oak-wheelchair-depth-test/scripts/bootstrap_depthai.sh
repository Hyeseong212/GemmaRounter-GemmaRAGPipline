#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPS_DIR="${PROJECT_DIR}/.deps"
SRC_DIR="${DEPS_DIR}/depthai-core-src"
BUILD_DIR="${DEPS_DIR}/depthai-core-build"
INSTALL_DIR="${DEPS_DIR}/depthai-install"
BRANCH="${DEPTHAI_BRANCH:-v2_stable}"
CONDA_BASE="${CONDA_BASE:-/home/rbiotech-server/miniforge}"
OPENCV_DIR_DEFAULT="${CONDA_BASE}/lib/cmake/opencv4"
OPENCV_DIR="${OpenCV_DIR:-${OPENCV_DIR_DEFAULT}}"

mkdir -p "${DEPS_DIR}"

if [[ ! -f "${OPENCV_DIR}/OpenCVConfig.cmake" ]]; then
  echo "OpenCVConfig.cmake not found: ${OPENCV_DIR}/OpenCVConfig.cmake" >&2
  echo "Install OpenCV first or set OpenCV_DIR explicitly." >&2
  exit 1
fi

if [[ ! -d "${SRC_DIR}/.git" ]]; then
  git clone --branch "${BRANCH}" --depth 1 https://github.com/luxonis/depthai-core.git "${SRC_DIR}"
else
  git -C "${SRC_DIR}" fetch origin "${BRANCH}" --depth 1
  git -C "${SRC_DIR}" checkout "${BRANCH}"
  git -C "${SRC_DIR}" pull --ff-only origin "${BRANCH}"
fi

git -C "${SRC_DIR}" submodule update --init --recursive

cmake -S "${SRC_DIR}" -B "${BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DDEPTHAI_ENABLE_CURL=OFF \
  -DDEPTHAI_ENABLE_BACKWARD=OFF \
  -DDEPTHAI_BUILD_EXAMPLES=OFF \
  -DOpenCV_DIR="${OPENCV_DIR}" \
  -DCMAKE_INSTALL_PREFIX="${INSTALL_DIR}"

cmake --build "${BUILD_DIR}" -j"$(nproc)"
cmake --build "${BUILD_DIR}" --target install -j"$(nproc)"

echo
echo "DepthAI installed to: ${INSTALL_DIR}"
echo "Build this project with:"
echo "  cmake -S \"${PROJECT_DIR}\" -B \"${PROJECT_DIR}/build\" -DCMAKE_PREFIX_PATH=\"${INSTALL_DIR}\""
echo "  cmake --build \"${PROJECT_DIR}/build\" -j\$(nproc)"
