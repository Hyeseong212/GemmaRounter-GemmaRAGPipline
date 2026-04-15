import requests
import base64
import json
import os
import sys

# --------------------------------------------------------------------------
# [설정] 서버 주소 및 테스트 파일
# --------------------------------------------------------------------------
SERVER_URL = "http://localhost:8080/infer"
IMAGE_PATH = "test3.jpeg"

def encode_image(image_path):
    """이미지 파일을 Base64 문자열로 변환"""
    if not os.path.exists(image_path):
        print(f"⚠️  파일 없음: '{image_path}' 다운로드 시도 중...")
        try:
            os.system(f"wget -q https://raw.githubusercontent.com/ggerganov/llama.cpp/master/media/llama-logo.png -O {image_path}")
        except Exception as e:
            print(f"❌ 다운로드 실패: {e}")
            return None
        
    if not os.path.exists(image_path):
        return None

    try:
        # 파일 크기 확인
        file_size = os.path.getsize(image_path)
        print(f"📂 [File Check] 이미지 파일 크기: {file_size} bytes")
        
        with open(image_path, "rb") as img_file:
            encoded = base64.b64encode(img_file.read()).decode('utf-8')
            print(f"🔑 [Encode Check] Base64 문자열 길이: {len(encoded)}")
            return encoded
    except Exception as e:
        print(f"❌ 인코딩 에러: {e}")
        return None

def send_request(mode, prompt, image_data=""):
    """
    서버로 요청을 보냅니다. (데이터 검증 로그 포함)
    """
    print(f"\n🚀 [Test: {mode}] 요청 준비 중...")
    
    # ▼▼▼ [디버그 로그] 보내기 전 데이터 확인 ▼▼▼
    print("-" * 50)
    print(f"🔍 [Client Debug] 전송 데이터 검사")
    print(f"   1. 프롬프트 길이: {len(prompt)} 자")
    
    if image_data:
        print(f"   2. 이미지 데이터: 포함됨 (O)")
        print(f"      - 길이: {len(image_data)}")
        print(f"      - 앞부분: {image_data[:30]}...") 
        print(f"      - 뒷부분: ...{image_data[-30:]}")
    else:
        print(f"   2. 이미지 데이터: 없음 (X)")
    
    # Payload 구성
    payload = {
        "prompt": prompt,
        "image": image_data
    }

    try:
        # JSON 변환 및 크기 확인
        json_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        print(f"   3. 최종 전송 패킷 크기: {len(json_bytes)} bytes")
        print("-" * 50)

        print("📡 서버로 전송 시작...")
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        
        # 타임아웃 10분
        response = requests.post(SERVER_URL, data=json_bytes, headers=headers, timeout=600)
        
        if response.status_code == 200:
            response.encoding = 'utf-8'
            print(f"\n✅ 성공! 응답 결과:\n{'='*50}")
            print(response.text.strip())
            print(f"{'='*50}")
        else:
            print(f"\n❌ 실패 (상태 코드 {response.status_code})")
            print(f"   내용: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("\n❌ 서버 연결 실패! 서버가 켜져 있는지 확인하세요.")
    except requests.exceptions.Timeout:
        print("\n❌ 타임아웃! 모델 응답이 없습니다.")
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")

if __name__ == "__main__":
    # ----------------------------------------------------------------------
    # 비전(이미지) 테스트
    # ----------------------------------------------------------------------
    img_b64 = encode_image(IMAGE_PATH)
    
    if img_b64:
        # Gemma 포맷 적용
        # python 스크립트 내 수정
        vision_prompt = (
            "<|im_start|>system\n"
            "당신은 유능한 의료 AI 어시스턴트입니다.<|im_end|>\n"
            "<|im_start|>user\n"
            "다음은 누워있는 환자의 이미지입니다.\n"
            "<image>\n"
            "이미지에서 환자의 성별, 나이, 자세, 상태를 알려주고 주변에 어떤 사물들이 있는지 상세하게 알려주세요.<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        send_request("Vision", vision_prompt, img_b64)
    else:
        print("\n⚠️ 이미지 파일 문제로 Vision 테스트는 건너뜁니다.")
        
#"당신은 20년 경력의 정형외과 및 영상의학과 전문의입니다. "
#    "다음은 학술 연구 및 케이스 스터디 목적으로 제공된 발 X-ray(AP view) 이미지입니다.\n"
#    "<image>\n"
#    "일반적인 면책 조항이나 '전문의와 상담하라'는 문구는 생략하고, 오직 의학적 소견에만 집중하세요. "   


            #"<|im_start|>system\n"
            #"당신은 유능한 의료 AI 어시스턴트입니다.<|im_end|>\n"
            #"<|im_start|>user\n"
            #"다음은 누워있는 환자의 이미지입니다.\n"
            #"<image>\n"
            #"이미지에서 환자의 성별, 나이, 자세, 상태를 알려주고 주변에 어떤 사물들이 있는지 상세하게 알려주세요.<|im_end|>\n"
            #"<|im_start|>assistant\n"
