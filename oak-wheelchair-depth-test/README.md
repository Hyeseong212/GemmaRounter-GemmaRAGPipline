# OAK Wheelchair Depth Test

OAK 카메라에서 `RGB + depth`를 받아 현재 `18088 /infer` 서버로 휠체어 중심 좌표를 추론하고, 해당 위치의 depth를 계산하는 C++ 테스트 하네스입니다.

기본 동작:
- 라이브 프리뷰 실행
- `c` 입력 시 현재 RGB 프레임을 캡처
- `http://127.0.0.1:18088/infer` 로 이미지 전송
- 서버 응답 좌표를 `좌하단 원점 [x, y]`로 해석
- `top-left` 좌표로 변환 후 depth ROI median 계산
- 콘솔과 화면에 좌표/depth 출력

## 요구 사항

- OAK / DepthAI 계열 카메라 연결
- OpenCV 4
- DepthAI C++ SDK
- 서버 `http://127.0.0.1:18088/infer` 실행 중

현재 이 서버 기준으로 OpenCV는 `miniforge` 경로를 기본 탐색합니다.

- `/home/rbiotech-server/miniforge/lib/cmake/opencv4/OpenCVConfig.cmake`

현재 시스템 확인 예:

```bash
lsusb | grep -i movidius
curl http://127.0.0.1:18088/healthz
pkg-config --modversion opencv4
```

## DepthAI SDK 설치

로컬 prefix에 설치:

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test
./scripts/bootstrap_depthai.sh
```

기본 설치 위치:

```bash
./.deps/depthai-install
```

현재 부트스트랩 스크립트는 테스트 하네스에 필요 없는 `CURL/OpenSSL`을 끄고 설치합니다. 기본 빌드보다 설치 시간이 짧습니다.

## udev / 권한

실행 시 아래처럼 나오면 코드 문제가 아니라 USB 권한 문제입니다.

```text
No accessible OAK/DepthAI device found.
Connected USB devices exist but this account cannot open them.
```

또는 로그에 다음이 보일 수 있습니다.

```text
Insufficient permissions to communicate with X_LINK_UNBOOTED device
```

이 경우 `udev` 규칙을 넣어야 합니다. 이 테스트 하네스 기준으로는 Movidius USB vendor id `03e7`에 대한 규칙 하나면 충분합니다.

예시 절차:

```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | \
  sudo tee /etc/udev/rules.d/80-movidius.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

적용 후 카메라를 다시 꽂고 재실행합니다.

## 빌드

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test
cmake -S . -B build -DCMAKE_PREFIX_PATH="$PWD/.deps/depthai-install"
cmake --build build -j"$(nproc)"
```

## 실행

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test
./build/oak_wheelchair_depth_test --server http://127.0.0.1:18088/infer
```

기본 옵션:
- `--server http://127.0.0.1:18088/infer`
- `--output-dir /tmp/oak-wheelchair-depth-test`
- `--roi-size 21`
- `--width 1280`
- `--height 720`

## 키 입력

- `c`: 현재 RGB 프레임 캡처 후 추론 실행
- `q`: 종료

## 콘솔 출력 예시

```text
wheelchair_coord_bottom_left=[946,592]
wheelchair_coord_top_left=[946,128]
depth_mm=1842
depth_status=ok
capture_path=/tmp/oak-wheelchair-depth-test/capture-20260416-112233.png
```

depth를 찾지 못한 경우:

```text
wheelchair_coord_bottom_left=[946,592]
wheelchair_coord_top_left=[946,128]
depth_mm=unavailable
depth_status=depth_unavailable
```

## 동작 메모

- 서버 응답 좌표는 `좌하단 원점` 기준으로 가정합니다.
- depth 조회는 RGB에 정렬된 depth 프레임에서 수행합니다.
- depth는 중심 좌표 주변 ROI의 `median`을 사용합니다.
- v1은 `XYZ`나 로봇 제어를 하지 않습니다.

추가 설계 메모는 [docs/flow.md](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/docs/flow.md) 에 정리돼 있습니다.
