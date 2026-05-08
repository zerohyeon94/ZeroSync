import SwiftUI

struct StarfieldView: View {
    private let stars: [StarData] = StarData.generate(count: 220, seed: 7391)

    var body: some View {
        TimelineView(.animation) { timeline in
            Canvas { ctx, size in
                let t = timeline.date.timeIntervalSinceReferenceDate
                for star in stars {
                    let alpha = (sin(t * star.twinkleSpeed + star.phase) * 0.5 + 0.5)
                                * star.maxAlpha
                    let px = star.nx * size.width
                    let py = star.ny * size.height
                    let r  = star.size / 2

                    ctx.fill(
                        Path(ellipseIn: CGRect(x: px - r, y: py - r,
                                               width: star.size, height: star.size)),
                        with: .color(star.color.opacity(alpha))
                    )

                    // 밝은 별에 십자 글로우 추가
                    if star.size > 2.0 {
                        let gl = star.size * 3
                        let glowGrad = Gradient(stops: [
                            .init(color: star.color.opacity(alpha * 0.4), location: 0),
                            .init(color: .clear, location: 1)
                        ])
                        ctx.fill(
                            Path(ellipseIn: CGRect(x: px - gl, y: py - gl,
                                                   width: gl * 2, height: gl * 2)),
                            with: .radialGradient(glowGrad,
                                                  center: CGPoint(x: px, y: py),
                                                  startRadius: 0, endRadius: gl)
                        )
                    }
                }
            }
        }
        .ignoresSafeArea()
    }
}

// MARK: - Data

private struct StarData {
    let nx, ny, size, twinkleSpeed, phase, maxAlpha: Double
    let color: Color

    static func generate(count: Int, seed: UInt64) -> [StarData] {
        var s = seed
        func rand() -> Double {
            s = s &* 6364136223846793005 &+ 1442695040888963407
            return Double(s >> 33) / Double(UInt32.max)
        }

        return (0..<count).map { _ in
            let tier = rand()
            let size: Double
            let maxAlpha: Double

            if tier < 0.06 {         // 밝은 별 (6%)
                size = rand() * 1.5 + 2.0
                maxAlpha = 0.9 + rand() * 0.1
            } else if tier < 0.25 {  // 중간 별 (19%)
                size = rand() * 0.8 + 1.2
                maxAlpha = 0.5 + rand() * 0.35
            } else {                  // 희미한 별 (75%)
                size = rand() * 0.6 + 0.3
                maxAlpha = 0.15 + rand() * 0.3
            }

            // 색조: 흰색~파란색~약간 따뜻한 별
            let colorRoll = rand()
            let color: Color
            if colorRoll < 0.5 {
                color = Color(red: 0.85 + rand()*0.15, green: 0.88 + rand()*0.12, blue: 1.0)
            } else if colorRoll < 0.8 {
                color = Color(red: 1.0, green: 0.95 + rand()*0.05, blue: 0.85 + rand()*0.15)
            } else {
                color = Color(red: 1.0, green: 1.0, blue: 1.0)
            }

            return StarData(
                nx: rand(), ny: rand(),
                size: size,
                twinkleSpeed: rand() * 1.2 + 0.15,
                phase: rand() * .pi * 2,
                maxAlpha: maxAlpha,
                color: color
            )
        }
    }
}
