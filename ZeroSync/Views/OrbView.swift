import SwiftUI

struct OrbView: View {
    enum OrbState { case idle, thinking }

    let state: OrbState
    let persona: Persona

    private var c: OrbColors {
        switch (state, persona) {
        case (.idle, .alpha):
            return OrbColors(
                core: Color(red: 0, green: 0.4, blue: 1),
                mid:  Color(red: 0, green: 0.267, blue: 0.8),
                outer: Color(red: 0, green: 0.1, blue: 0.4),
                glow: Color(red: 0, green: 0.4, blue: 1)
            )
        case (.thinking, .alpha):
            return OrbColors(
                core: Color(red: 0.659, green: 0.333, blue: 0.969),
                mid:  Color(red: 0.486, green: 0.231, blue: 0.929),
                outer: Color(red: 0.231, green: 0.027, blue: 0.392),
                glow: Color(red: 0.486, green: 0.231, blue: 0.929)
            )
        case (.idle, .beta):
            return OrbColors(
                core: Color(red: 1.0, green: 0.549, blue: 0.259),
                mid:  Color(red: 1.0, green: 0.42, blue: 0.208),
                outer: Color(red: 0.4, green: 0.133, blue: 0),
                glow: Color(red: 1.0, green: 0.42, blue: 0.208)
            )
        case (.thinking, .beta):
            return OrbColors(
                core: Color(red: 1.0, green: 0.761, blue: 0.031),
                mid:  Color(red: 0.898, green: 0.6, blue: 0.02),
                outer: Color(red: 0.4, green: 0.259, blue: 0),
                glow: Color(red: 1.0, green: 0.761, blue: 0.031)
            )
        }
    }

    var body: some View {
        TimelineView(.animation) { timeline in
            Canvas { ctx, size in
                let t = timeline.date.timeIntervalSinceReferenceDate
                draw(&ctx, size: size, time: t)
            }
        }
    }

    private func draw(_ ctx: inout GraphicsContext, size: CGSize, time: Double) {
        let cx = size.width / 2
        let cy = size.height / 2
        let baseR = min(size.width, size.height) * 0.30
        let pulse  = 1.0 + sin(time * 2.5) * 0.04
        let orbR   = baseR * pulse
        let center = CGPoint(x: cx, y: cy)

        // ── 1. 원거리 글로우 ──
        let outerGlow = Gradient(stops: [
            .init(color: c.glow.opacity(0.12), location: 0),
            .init(color: c.glow.opacity(0.04), location: 0.5),
            .init(color: .clear, location: 1)
        ])
        ctx.fill(
            Path(ellipseIn: orbR.rect(center: center, scale: 1.8)),
            with: .radialGradient(outerGlow, center: center, startRadius: 0, endRadius: orbR * 1.8)
        )

        // ── 2. 회전 링 3개 ──
        for i in 0..<3 {
            let ringR  = baseR * (1.15 + Double(i) * 0.18)
            let speed  = (i % 2 == 0 ? 1.0 : -1.0) * (0.3 + Double(i) * 0.15)
            let alpha  = 0.35 - Double(i) * 0.08
            let dots   = 4 + i * 2

            ctx.drawLayer { rc in
                rc.translateBy(x: cx, y: cy)
                rc.rotate(by: Angle(radians: time * speed))

                rc.stroke(
                    Path(ellipseIn: ringR.rect(center: .zero)),
                    with: .color(c.core.opacity(alpha)),
                    style: StrokeStyle(lineWidth: 1.5 - Double(i) * 0.3,
                                      dash: [8 + Double(i) * 4, 12 + Double(i) * 6])
                )
                for j in 0..<dots {
                    let a  = Double(j) / Double(dots) * .pi * 2
                    let dr = 2.5 - Double(i) * 0.5
                    rc.fill(
                        Path(ellipseIn: dr.rect(center: CGPoint(x: cos(a) * ringR, y: sin(a) * ringR))),
                        with: .color(c.core)
                    )
                }
            }
        }

        // ── 3. HUD 눈금 링 ──
        ctx.drawLayer { hc in
            hc.translateBy(x: cx, y: cy)
            hc.rotate(by: Angle(radians: time * 0.2))

            for i in 0..<72 {
                let a      = Double(i) / 72.0 * .pi * 2
                let isLong = i % 6 == 0
                let isMed  = !isLong && i % 3 == 0
                let innerR = baseR * 1.05
                let outerR = innerR + (isLong ? 14 : isMed ? 9 : 5)
                let alpha  = isLong ? 0.9 : isMed ? 0.6 : 0.3

                var tick = Path()
                tick.move(to: CGPoint(x: cos(a) * innerR, y: sin(a) * innerR))
                tick.addLine(to: CGPoint(x: cos(a) * outerR, y: sin(a) * outerR))
                hc.stroke(tick, with: .color(c.core.opacity(alpha)), lineWidth: isLong ? 2 : 1)
            }
        }

        // ── 4. 근거리 글로우 오라 ──
        let aura = Gradient(stops: [
            .init(color: c.glow.opacity(0.45), location: 0),
            .init(color: c.glow.opacity(0.18), location: 0.45),
            .init(color: .clear, location: 1)
        ])
        ctx.fill(
            Path(ellipseIn: orbR.rect(center: center, scale: 1.3)),
            with: .radialGradient(aura, center: center, startRadius: orbR * 0.5, endRadius: orbR * 1.3)
        )

        // ── 5. 오브 본체 ──
        let orbPath = Path(ellipseIn: orbR.rect(center: center))
        let orbGrad = Gradient(stops: [
            .init(color: .white,   location: 0),
            .init(color: c.core,   location: 0.15),
            .init(color: c.mid,    location: 0.5),
            .init(color: c.outer,  location: 0.85),
            .init(color: Color(red: 0, green: 0.02, blue: 0.06), location: 1)
        ])
        let hlCenter = CGPoint(x: cx - orbR * 0.25, y: cy - orbR * 0.25)
        ctx.fill(orbPath, with: .radialGradient(orbGrad, center: hlCenter, startRadius: 0, endRadius: orbR))

        // ── 6. 테두리 글로우 ──
        ctx.stroke(orbPath, with: .color(c.core.opacity(0.7)), lineWidth: 2)

        // ── 7. 에너지 코어 ──
        let coreR   = orbR * 0.35
        let coreGrad = Gradient(stops: [
            .init(color: .white, location: 0),
            .init(color: c.core.opacity(0.9), location: 0.3),
            .init(color: .clear, location: 1)
        ])
        ctx.fill(
            Path(ellipseIn: coreR.rect(center: center)),
            with: .radialGradient(coreGrad, center: center, startRadius: 0, endRadius: coreR)
        )

        // ── 8. 하이라이트 반사 ──
        let specCenter = CGPoint(x: cx - orbR * 0.3, y: cy - orbR * 0.35)
        let specGrad = Gradient(stops: [
            .init(color: .white.opacity(0.5), location: 0),
            .init(color: .white.opacity(0.1), location: 0.5),
            .init(color: .clear, location: 1)
        ])
        ctx.fill(orbPath, with: .radialGradient(specGrad, center: specCenter, startRadius: 0, endRadius: orbR * 0.5))

        // ── 9. 사고 중 에너지 라인 ──
        if state == .thinking {
            ctx.drawLayer { ec in
                ec.translateBy(x: cx, y: cy)
                ec.rotate(by: Angle(radians: time * 1.5))

                ec.stroke(
                    Path(ellipseIn: (orbR * 0.6).rect(center: .zero)),
                    with: .color(c.core.opacity(0.25)), lineWidth: 1
                )
                for i in 0..<6 {
                    let a = Double(i) / 6.0 * .pi * 2
                    var line = Path()
                    line.move(to: .zero)
                    line.addLine(to: CGPoint(x: cos(a) * orbR * 0.55, y: sin(a) * orbR * 0.55))
                    ec.stroke(line, with: .color(c.core.opacity(0.25)), lineWidth: 1)
                }
            }
        }
    }
}

private struct OrbColors {
    let core, mid, outer, glow: Color
}

private extension CGFloat {
    func rect(center: CGPoint, scale: CGFloat = 1) -> CGRect {
        let r = self * scale
        return CGRect(x: center.x - r, y: center.y - r, width: r * 2, height: r * 2)
    }
}

private extension Double {
    func rect(center: CGPoint, scale: Double = 1) -> CGRect {
        CGFloat(self).rect(center: center, scale: CGFloat(scale))
    }
}
