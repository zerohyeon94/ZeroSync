import SwiftUI

/// 화면을 돌아다니는 캐릭터 한 마리의 그림.
/// 에셋 없이 SwiftUI 도형으로 그린다. 기본 방향은 오른쪽.
struct PetView: View {
    let persona: Persona
    let visual: PetVisualState
    let onTap: () -> Void
    let onDragChanged: (CGSize) -> Void
    let onDragEnded: () -> Void

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 24.0)) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            let phase = visual.isWalking ? t * 9 : 0
            let bob = visual.isWalking ? sin(phase * 2) * 1.5 : 0
            let blinking = t.truncatingRemainder(dividingBy: 3.8) < 0.13

            ZStack(alignment: .bottom) {
                // 발밑 그림자
                Ellipse()
                    .fill(.black.opacity(visual.isAirborne ? 0.06 : 0.14))
                    .frame(width: 56, height: 10)
                    .offset(y: -2)

                character(phase: phase, blinking: blinking)
                    .offset(y: CGFloat(-8 + bob))
            }
        }
        .frame(width: 90, height: 84)
        .scaleEffect(x: visual.facing < 0 ? -1 : 1, y: 1)
        .contentShape(Rectangle())
        .onTapGesture { onTap() }
        .gesture(
            DragGesture(minimumDistance: 4, coordinateSpace: .global)
                .onChanged { onDragChanged($0.translation) }
                .onEnded { _ in onDragEnded() }
        )
    }

    // MARK: - 색상

    private var bodyColor: Color {
        switch persona {
        case .alpha: return Color(red: 0.294, green: 0.561, blue: 0.831)   // 늑대 파랑
        case .beta:  return Color(red: 0.97, green: 0.95, blue: 0.96)      // 북극곰 흰색
        }
    }

    private var darkColor: Color {
        switch persona {
        case .alpha: return Color(red: 0.20, green: 0.40, blue: 0.62)
        case .beta:  return Color(red: 0.86, green: 0.80, blue: 0.84)
        }
    }

    private var accentColor: Color {
        switch persona {
        case .alpha: return Color(red: 0.75, green: 0.87, blue: 0.98)      // 밝은 하늘색 배
        case .beta:  return Color(red: 0.910, green: 0.482, blue: 0.639)   // 핑크 포인트
        }
    }

    // MARK: - 캐릭터 (옆모습, 오른쪽 보기)

    private func character(phase: Double, blinking: Bool) -> some View {
        ZStack {
            tail(phase: phase)
            legs(phase: phase)
            bodyShape
            head(blinking: blinking)
        }
        .frame(width: 90, height: 76, alignment: .bottom)
    }

    private var bodyShape: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 17, style: .continuous)
                .fill(bodyColor)
                .frame(width: 54, height: 34)
            // 배
            Ellipse()
                .fill(persona == .alpha ? accentColor : .white)
                .frame(width: 36, height: 16)
                .offset(y: 9)
        }
        .offset(x: -4, y: 10)
    }

    private func legs(phase: Double) -> some View {
        HStack(spacing: 9) {
            ForEach(0..<4, id: \.self) { index in
                Capsule()
                    .fill(darkColor)
                    .frame(width: 7, height: 15)
                    .rotationEffect(
                        .degrees(sin(phase + Double(index) * .pi) * 16),
                        anchor: .top
                    )
            }
        }
        .offset(x: -4, y: 26)
    }

    @ViewBuilder
    private func tail(phase: Double) -> some View {
        switch persona {
        case .alpha:
            // 늑대 꼬리
            Capsule()
                .fill(darkColor)
                .frame(width: 26, height: 10)
                .rotationEffect(.degrees(-28 + sin(phase) * 6), anchor: .trailing)
                .offset(x: -38, y: 2)
        case .beta:
            // 곰 꼬리
            Circle()
                .fill(darkColor)
                .frame(width: 10, height: 10)
                .offset(x: -30, y: 8)
        }
    }

    private func head(blinking: Bool) -> some View {
        ZStack {
            ears

            Circle()
                .fill(bodyColor)
                .frame(width: 34, height: 34)

            // 주둥이
            Ellipse()
                .fill(persona == .alpha ? accentColor : .white)
                .frame(width: 16, height: 12)
                .offset(x: 9, y: 5)
            Circle()
                .fill(.black.opacity(0.8))
                .frame(width: 4.5, height: 4.5)
                .offset(x: 13, y: 3)

            // 눈
            Capsule()
                .fill(.black.opacity(0.85))
                .frame(width: 4.5, height: blinking ? 1.5 : 5.5)
                .offset(x: 3, y: -3)

            // 베타 볼터치
            if persona == .beta {
                Circle()
                    .fill(accentColor.opacity(0.55))
                    .frame(width: 7, height: 7)
                    .offset(x: 6, y: 4)
            }
        }
        .offset(x: 18, y: -14)
    }

    @ViewBuilder
    private var ears: some View {
        switch persona {
        case .alpha:
            // 뾰족 귀 두 개
            ForEach([-10, 2], id: \.self) { x in
                Triangle()
                    .fill(darkColor)
                    .frame(width: 13, height: 14)
                    .offset(x: CGFloat(x), y: -19)
            }
        case .beta:
            // 둥근 귀 두 개
            ForEach([-11, 3], id: \.self) { x in
                ZStack {
                    Circle().fill(bodyColor)
                    Circle().fill(accentColor.opacity(0.5)).scaleEffect(0.55)
                }
                .frame(width: 13, height: 13)
                .offset(x: CGFloat(x), y: -15)
            }
        }
    }
}

/// 위가 뾰족한 삼각형
struct Triangle: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}
