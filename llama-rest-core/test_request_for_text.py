import requests
import json

# --------------------------------------------------------------------------
# [설정] 서버 주소
# --------------------------------------------------------------------------
SERVER_URL = "http://localhost:8080/infer"

def test_request(prompt):
    """
    텍스트 전용 추론 요청을 보냅니다.
    """
    print(f"\n🚀 [Test: Text-Only] 요청 전송 중... (잠시만 기다려주세요)")
    
    # 이미지 데이터 없이 프롬프트만 구성
    payload = {
        "prompt": prompt
    }

    try:
        # 모델 로딩/추론 시간을 고려해 타임아웃 설정 (10분)
        response = requests.post(SERVER_URL, json=payload, timeout=600)
        
        if response.status_code == 200:
            # 성공 시 결과 출력
            print(f"✅ 성공! 응답 결과:\n{'-'*40}\n{response.text.strip()}\n{'-'*40}")
        else:
            # 실패 시 에러 코드 및 메시지 출력
            print(f"❌ 실패 (상태 코드 {response.status_code})")
            print(f"   내용: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ 서버 연결 실패! 서버(./llama_Rest)가 켜져 있는지 확인하세요.")
    except requests.exceptions.Timeout:
        print("❌ 타임아웃! 모델 응답이 지연되고 있습니다.")
    except Exception as e:
        print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    # ----------------------------------------------------------------------
    # [테스트] 원하는 질문을 입력하세요
    # ----------------------------------------------------------------------
    user_prompt = "Python 언어의 장점을 3가지로 요약해줘."
    
    test_request(user_prompt)