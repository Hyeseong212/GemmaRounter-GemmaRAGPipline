# OAK Wheelchair Depth Test

OAK 카메라에서 `RGB + depth`를 받아 현재 `18088 /infer` 서버로 휠체어 중심 좌표를 추론하고, 해당 위치의 depth를 계산하는 C++ 테스트 하네스입니다.

기본 동작:
- 라이브 프리뷰 실행
- `c` 입력 시 현재 RGB 프레임을 캡처
- `http://127.0.0.1:18088/infer` 로 이미지 전송
- 서버 응답 좌표를 `좌하단 원점 [x, y]`로 해석
- `top-left` 좌표로 변환 후 depth ROI median 계산
- 콘솔과 화면에 좌표/depth 출력
- 각 캡처 결과를 `capture_log.csv`에 자동 기록
- 각 캡처 결과를 `capture_log.json`에도 자동 기록
- 실측 거리값을 채운 뒤 선형 보정 JSON을 만들면 다음 캡처부터 자동 보정 적용

기본 저장 위치는 이제 `/tmp`가 아니라 저장소 내부입니다.

```bash
/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/runtime-data
```

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
- `--output-dir /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/runtime-data`
- `--calibration-file .../oak-wheelchair-depth-test/runtime-data/depth_linear_calibration.json`
- `--log-file .../oak-wheelchair-depth-test/runtime-data/capture_log.csv`
- `--json-log-file .../oak-wheelchair-depth-test/runtime-data/capture_log.json`
- `--roi-size 21`
- `--width 1280`
- `--height 720`

## 키 입력

- `c`: 현재 RGB 프레임 캡처 후 추론 실행
- `q`: 종료

## 콘솔 출력 예시

```text
timestamp=20260420-153012
wheelchair_coord_bottom_left=[946,592]
wheelchair_coord_top_left=[946,128]
raw_depth_mm=1842
depth_mm=1842
depth_status=ok
capture_path=/tmp/oak-wheelchair-depth-test/capture-20260416-112233.png
capture_log_csv=/tmp/oak-wheelchair-depth-test/capture_log.csv
capture_log_json=/tmp/oak-wheelchair-depth-test/capture_log.json
calibration_file=/tmp/oak-wheelchair-depth-test/depth_linear_calibration.json
```

변경 후 기본 경로 예시:

```text
capture_log_csv=/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/runtime-data/capture_log.csv
capture_log_json=/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/runtime-data/capture_log.json
calibration_file=/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/runtime-data/depth_linear_calibration.json
```

depth를 찾지 못한 경우:

```text
timestamp=20260420-153045
wheelchair_coord_bottom_left=[946,592]
wheelchair_coord_top_left=[946,128]
raw_depth_mm=unavailable
depth_mm=unavailable
depth_status=depth_unavailable
```

선형 보정이 적용된 경우:

```text
timestamp=20260420-153102
wheelchair_coord_bottom_left=[946,592]
wheelchair_coord_top_left=[946,128]
raw_depth_mm=1842
corrected_depth_mm=1915
depth_mm=1915
depth_status=ok
```

## 캡처 로그

`c`를 누를 때마다 아래 파일이 자동으로 갱신됩니다.

```bash
/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/runtime-data/capture_log.csv
/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/runtime-data/capture_log.json
```

주요 컬럼:
- `timestamp`
- `capture_path`
- `image_width`, `image_height`
- `bottom_left_x`, `bottom_left_y`
- `top_left_x`, `top_left_y`
- `raw_depth_mm`
- `corrected_depth_mm`
- `depth_mm`
- `depth_status`
- `actual_distance_mm`
- `calibration_applied`
- `calibration_slope`, `calibration_intercept`
- `notes`

`actual_distance_mm`는 비워진 상태로 남습니다. 실측한 값을 나중에 직접 채우면 됩니다.

JSON 형식 예시:

```json
[
  {
    "timestamp": "20260420-153102",
    "capture_path": "/tmp/oak-wheelchair-depth-test/capture-20260420-153102.png",
    "image_width": 1280,
    "image_height": 720,
    "pixel_coord_bottom_left": [451, 199],
    "pixel_coord_top_left": [451, 521],
    "raw_depth_mm": 2827,
    "corrected_depth_mm": null,
    "depth_mm": 2827,
    "depth_status": "ok",
    "actual_distance_mm": null,
    "calibration_applied": false,
    "calibration_slope": null,
    "calibration_intercept": null,
    "notes": "",
    "prompt": "이 이미지에서 휠체어가 어딨는지 중심을 좌표로 나타내봐",
    "raw_response": "이 이미지에서 휠체어의 중심 좌표는 [451, 199]입니다."
  }
]
```

## 선형 보정 워크플로

1. 앱으로 여러 번 캡처합니다.
2. `capture_log.json`에서 `actual_distance_mm` 값에 실제 잰 거리(mm)를 채웁니다.
3. 아래 스크립트로 선형 보정식을 만듭니다.

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test
python scripts/fit_linear_depth_calibration.py \
  --log-file /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/runtime-data/capture_log.json \
  --output /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/runtime-data/depth_linear_calibration.json
```

4. 다음 캡처부터 앱이 `depth_linear_calibration.json`을 자동으로 읽어서 `corrected_depth_mm`를 같이 출력합니다.

예시 출력 JSON:

```json
{
  "model_type": "linear_depth_correction",
  "enabled": true,
  "slope": 1.0182,
  "intercept": -34.7,
  "sample_count": 8,
  "r_squared": 0.9921
}
```

## 동작 메모

- 서버 응답 좌표는 `좌하단 원점` 기준으로 가정합니다.
- depth 조회는 RGB에 정렬된 depth 프레임에서 수행합니다.
- depth는 중심 좌표 주변 ROI의 `median`을 사용합니다.
- 선형 보정 파일이 있으면 `raw_depth_mm`에 `y = slope * x + intercept`를 적용한 `corrected_depth_mm`를 함께 출력합니다.
- v1은 `XYZ`나 로봇 제어를 하지 않습니다.

추가 설계 메모는 [docs/flow.md](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/docs/flow.md) 에 정리돼 있습니다.
