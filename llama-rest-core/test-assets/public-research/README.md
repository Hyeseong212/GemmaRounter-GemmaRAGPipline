# Public Research Video Test Set

Reset on 2026-04-15. Previous multimodal test assets and result files in this folder were cleared and replaced with a new video-focused set for medical prompt testing.

Current set size: `10` MP4 assets

## Assets

- `brain_mri_post_glioblastoma_transverse.mp4`
- `brain_mri_glioblastoma_regrowth_transverse.mp4`
- `cervical_spine_mri_case0003.mp4`
- `lumbar_spine_mri_case01.mp4`
- `knee_mri_case0025.mp4`
- `brain_ct_normal_case2.mp4`
- `thorax_hrct_normal.mp4`
- `abdomen_pelvis_ct_normal_axial.mp4`
- `echocardiography_apical_two_chamber.mp4`
- `embryonic_ultrasound_8w3d.mp4`

## Source Notes

- The two glioblastoma MRI assets, the echocardiography asset, and the embryonic ultrasound asset were converted from publicly available Wikimedia Commons GIF files to MP4.
- The cervical spine MRI, lumbar spine MRI, knee MRI, brain CT, thorax CT, and abdomen/pelvis CT assets were created by sampling representative slices from scrollable Commons image stacks and encoding them as short MP4 clips for easier server-side testing.
- Source links and short descriptions are in `sources.tsv`.

## Usage

Example request:

```bash
curl http://127.0.0.1:18088/infer \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "연구용 테스트입니다. 이 영상의 전체 시퀀스를 기준으로 관찰 가능한 특징만 한국어로 3문장 이내로 설명하세요. 첫 프레임만 보지 말고, 확정 진단명을 말해주세요.",
    "video_path": "/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core/test-assets/public-research/brain_mri_post_glioblastoma_transverse.mp4"
  }'
```

## Important

- These are research/demo assets, not clinical workflow data.
- Several assets are reconstructed from image stacks or converted from GIF, so they are suitable for multimodal stress testing but not for medical validation.
- The `results/` folder is intentionally empty after the reset.
