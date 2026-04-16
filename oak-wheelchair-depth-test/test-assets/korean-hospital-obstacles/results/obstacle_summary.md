# Korean Hospital Obstacle Metadata

- server: `http://127.0.0.1:18088/infer`
- prompt: `다음 이미지를 보고 환자이송 로봇 주행을 방해할 수 있는 병원 실내 장애물을 가능한 한 빠짐없이 분류해라. 최대 20개까지 허용하며, 중복 없이 실제 동선에 놓인 장애물만 골라라. 병실, 병동, 복도, 로비에서 실제 동선에 놓인 물체만 고르고 장식물이나 벽면 사진은 제외해라. 허용 클래스는 wheelchair, hospital_bed, bedside_table, chair, sofa, bench, medical_cart, iv_pole, monitor, sink, cabinet, person, stretcher, equipment, walker, reception_desk 이다. JSON만 출력해라. 형식은 {"obstacles":[{"class_name":"...","location_yx_1000":[0-1000,0-1000],"reason":"한 줄"}]} 이다. location_yx_1000는 이미지 내부 대략 위치를 [세로, 가로] 0~1000 정수로 적어라. 설명문, 코드펜스, 마크다운 없이 JSON만 출력해라.`

## transport_room_shared_01.jpg
- title: 소나무병원 다인 병실
- source_name: 소나무병원
- source_page: https://pine-hospital.com/hospitaltour
- image_size: 2500x1875
- person | yx_1000=[520, 480] | bottom_left=[1200, 900] | top_left=[1200, 975] | reason=복도 중앙에 보행자가 있어 로봇 주행 경로를 직접적으로 방해함
- medical_cart | yx_1000=[610, 320] | bottom_left=[800, 731] | top_left=[800, 1144] | reason=복도 측면에 배치된 의료 카트가 통행 가능 너비를 좁힘
- iv_pole | yx_1000=[580, 350] | bottom_left=[875, 787] | top_left=[875, 1088] | reason=의료 카트 옆에 세워진 수액 거치대가 돌출되어 충돌 위험이 있음
- wheelchair | yx_1000=[650, 610] | bottom_left=[1525, 656] | top_left=[1525, 1219] | reason=복도 벽면에 주차된 휠체어가 로봇의 회전 반경이나 주행 경로를 방해함
- person | yx_1000=[550, 650] | bottom_left=[1625, 844] | top_left=[1625, 1031] | reason=휠체어 근처에 서 있는 사람이 있어 동선에 장애가 됨
