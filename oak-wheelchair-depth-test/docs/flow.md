# OAK 휠체어-Depth 플로우

## 목적

라이브 카메라 프레임에서 휠체어 위치를 기존 `18088 /infer` 서버로 추론하고, 같은 프레임의 RGB 정렬 depth에서 depth 값을 읽는다.

## 프레임 플로우

1. OAK RGB 프레임 수신
2. OAK depth 프레임 수신
3. depth를 RGB 기준으로 정렬
4. 사용자가 `c` 입력
5. 현재 RGB 프레임을 PNG로 저장
6. 저장 경로를 `18088 /infer`에 `image_path`로 전달
7. 응답에서 첫 번째 좌표쌍 `[x, y]` 추출
8. 응답 좌표는 `좌하단 원점`으로 가정
9. RGB/depth 조회용 `top-left` 좌표로 변환
10. ROI depth median 계산
11. 화면/콘솔에 결과 출력

## 좌표계 규칙

서버 응답:
- `bottom-left origin`
- `x`: 왼쪽 -> 오른쪽 증가
- `y`: 아래 -> 위 증가

depth 조회용 내부 좌표:
- `top-left origin`
- `x`: 왼쪽 -> 오른쪽 증가
- `y`: 위 -> 아래 증가

변환식:

```text
x_img = x_bottom_left
y_img = image_height - y_bottom_left
```

최종 픽셀 인덱스는 depth/RGB 프레임 범위로 clamp 한다.

## Depth 계산 규칙

v1 기본값:
- ROI 크기: `21x21`
- 유효 depth 값만 사용
- `0` 또는 비정상 depth는 무시
- 유효 depth가 1개 이상이면 `median`
- 유효 depth가 없으면 `depth_unavailable`

ROI median을 기본으로 둔 이유:
- 단일 픽셀은 hole/noise 영향을 많이 받음
- 휠체어 중심 좌표가 1~2픽셀 흔들려도 depth 안정성이 더 높음

## 출력

필수 출력:
- `wheelchair_coord_bottom_left`
- `wheelchair_coord_top_left`
- `depth_mm`
- `depth_status`
- `capture_path`

## 범위 밖

- 3D XYZ 계산
- 자동 재시도
- 영상 기록/DB 적재
- 로봇 제어
- detector 교체
