# 버튼 이미지 (image target)

`run.bat inspect`에서 "UIA로는 잘 안 보입니다"가 나오면, HRD-Net 버튼을 작게 캡처해 여기에 넣고 `steps.yaml`의 `image:`에 경로를 적습니다.
예: `image: templates/btn_비용등록.png`

- **화면 배율과 해상도**: 캡처한 PC와 같아야 합니다(배율 100% 권장).
- **캡처 범위**: 버튼 글자만 딱 맞게. 주변 데이터(이름, 금액)는 넣지 않습니다.
