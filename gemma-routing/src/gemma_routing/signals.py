from __future__ import annotations

import re
from uuid import uuid4

from .models import DetectedSignals, NormalizedRouterInput, RouterInput


ERROR_CODE_PATTERN = re.compile(r"\b[Ee]\d{2,4}\b")

PATIENT_KEYWORDS = {
    "patient",
    "환자",
    "맥박",
    "pulse",
    "혈압",
    "pressure",
    "spo2",
    "산소",
    "symptom",
    "증상",
}
MEDICATION_KEYWORDS = {
    "medication",
    "medicine",
    "drug",
    "dose",
    "dosage",
    "약",
    "약물",
    "복약",
    "투약",
    "처방",
}
TREATMENT_KEYWORDS = {
    "treatment",
    "therapy",
    "diagnosis",
    "diagnostic",
    "치료",
    "진단",
    "처치",
    "중단",
    "계속 써도",
    "계속 사용",
}
OVERRIDE_KEYWORDS = {
    "override",
    "ignore",
    "bypass",
    "force",
    "무시",
    "우회",
    "강제로",
}
STATUS_KEYWORDS = {
    "battery",
    "status",
    "serial",
    "version",
    "wifi",
    "network",
    "temperature",
    "배터리",
    "상태",
    "잔량",
    "전원",
    "시리얼",
    "버전",
    "네트워크",
    "온도",
}
VISUAL_KEYWORDS = {
    "photo",
    "image",
    "picture",
    "screenshot",
    "screen shot",
    "사진",
    "이미지",
    "스크린샷",
    "캡처",
    "캡쳐",
    "첨부",
}
MANUAL_KEYWORDS = {
    "manual",
    "procedure",
    "sop",
    "reference",
    "document",
    "guide",
    "meaning",
    "what does",
    "how should",
    "매뉴얼",
    "절차",
    "문서",
    "레퍼런스",
    "참고자료",
    "설명서",
    "사용설명서",
    "의미",
    "조치",
}
SHORT_REPLY_KEYWORDS = {
    "간단히",
    "짧게",
    "짧은",
    "한줄",
    "한 줄",
    "한문장",
    "한 문장",
    "한마디",
    "20글자",
    "20자",
    "멘트",
    "안내멘트",
    "안내 멘트",
    "음성안내",
    "tts",
    "답만",
}
SHORT_REPLY_SUFFIXES = (
    "돼?",
    "되나?",
    "되나요?",
    "가능해?",
    "가능해요?",
    "괜찮아?",
    "괜찮나요?",
    "맞아?",
    "맞나요?",
)
COMPLEX_REASONING_KEYWORDS = {
    "compare",
    "comparison",
    "why",
    "analyze",
    "analysis",
    "tradeoff",
    "pros and cons",
    "summarize",
    "explain in detail",
    "difference",
    "비교",
    "왜",
    "분석",
    "장단점",
    "정리",
    "자세히",
    "상세히",
    "차이",
    "원리",
}


def normalize_router_input(request: RouterInput) -> NormalizedRouterInput:
    resolved_request_id = (
        request.request_id
        or str(request.metadata.get("request_id", "")).strip()
        or uuid4().hex[:12]
    )
    signals = extract_signals(request)
    return NormalizedRouterInput(
        request_id=resolved_request_id,
        user_message=request.user_message,
        has_image=request.has_image,
        network_status=request.network_status,
        local_tools_available=request.local_tools_available,
        metadata=request.metadata,
        detected_signals=signals,
    )


def extract_signals(request: RouterInput) -> DetectedSignals:
    text = request.user_message.casefold()
    error_codes = [match.group(0).upper() for match in ERROR_CODE_PATTERN.finditer(request.user_message)]

    patient_related = _contains_any(text, PATIENT_KEYWORDS)
    medication_related = _contains_any(text, MEDICATION_KEYWORDS)
    treatment_related = _contains_any(text, TREATMENT_KEYWORDS)
    override_related = _contains_any(text, OVERRIDE_KEYWORDS)
    visual_related = request.has_image or _contains_any(text, VISUAL_KEYWORDS)
    status_related = not error_codes and _contains_any(text, STATUS_KEYWORDS)
    manual_grounding_required = bool(error_codes) or _contains_any(text, MANUAL_KEYWORDS)
    reference_grounding_required = manual_grounding_required
    complex_reasoning_requested = _contains_any(text, COMPLEX_REASONING_KEYWORDS) or len(request.user_message) >= 120
    short_answer_expected = _contains_any(text, SHORT_REPLY_KEYWORDS) or text.endswith(SHORT_REPLY_SUFFIXES)
    general_question_candidate = not any(
        [
            patient_related,
            medication_related,
            treatment_related,
            override_related,
            visual_related,
            status_related,
            reference_grounding_required,
        ]
    )

    return DetectedSignals(
        error_codes=error_codes,
        patient_related=patient_related,
        medication_related=medication_related,
        treatment_related=treatment_related,
        override_related=override_related,
        visual_related=visual_related,
        status_related=status_related,
        general_question_candidate=general_question_candidate,
        complex_reasoning_requested=complex_reasoning_requested,
        short_answer_expected=short_answer_expected,
        reference_grounding_required=reference_grounding_required,
        manual_grounding_required=manual_grounding_required,
        network_limited=request.network_status != "online",
    )


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)
