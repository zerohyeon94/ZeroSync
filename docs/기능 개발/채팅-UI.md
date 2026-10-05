# 기능: 채팅 UI (ChatWindow / MessageBubble)

> Phase 1 | 상태: 개발 중

---

## 목표

메뉴바 팝업 창 안에서 자연스러운 채팅 인터페이스를 제공한다.
Alpha는 냉색(딥 블루), Beta는 난색(웜 앰버)으로 시각적으로 구분된다.

## 관련 파일

| 파일 | 역할 |
|------|------|
| `ZeroSync/Views/ChatView.swift` | 전체 채팅 레이아웃, 메시지 목록, 입력창 |
| `ZeroSync/Views/MessageBubble.swift` | 단일 메시지 말풍선 (Alpha/Beta/User 구분) |
| `ZeroSync/Models/Message.swift` | SwiftData 메시지 모델 |

## 디자인 원칙

- **배경**: 다크 모드 우선 (`#0d0d0d` 계열)
- **Alpha 색상**: 딥 블루 / 아이스 화이트
- **Beta 색상**: 웜 앰버 / 소프트 크림
- **폰트**: Geist Mono (Alpha/코드) + Inter (Beta/대화)
- 이모지 사용 금지

## 구현 시 주의사항

- 메뉴바 팝업은 크기가 제한적 → ScrollView 처리 필수
- 스트리밍 응답: URLSession AsyncBytes 또는 완성 후 표시 결정 필요
- 코드 블록 렌더링: Alpha 응답에서 빈번 → AttributedString 또는 SwiftUI Text 포맷팅 고려

## 미결 사항

- [ ] 스트리밍 응답 지원 여부 (URLSession AsyncBytes)
- [ ] 마크다운 렌더링 (Alpha의 코드 블록 — AttributedString)
- [ ] 메시지 최대 표시 개수 (SwiftData fetch limit)
