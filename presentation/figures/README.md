# Figures

이 폴더는 발표용 다이어그램 원본을 보관한다.

현재 형식:

- `*.mmd`
  - Mermaid 원본

권장 렌더링:

```bash
npx -y @mermaid-js/mermaid-cli -i presentation/figures/01_system_pipeline.mmd -o presentation/figures/01_system_pipeline.png
npx -y @mermaid-js/mermaid-cli -i presentation/figures/02_coordinate_transform.mmd -o presentation/figures/02_coordinate_transform.png
npx -y @mermaid-js/mermaid-cli -i presentation/figures/03_oak_depth_flow.mmd -o presentation/figures/03_oak_depth_flow.png
```

Mermaid CLI가 없다면:

- VS Code Mermaid preview
- GitHub preview
- draw.io로 재도식화

중요:

- 발표용 최종본에는 PNG로 렌더링해 넣는 것이 안정적이다.
