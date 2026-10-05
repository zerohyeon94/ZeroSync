import AppKit
import SwiftUI

/// 캐릭터 뷰가 관찰하는 표시 상태
@MainActor
@Observable
final class PetVisualState {
    var facing: CGFloat = 1        // 1: 오른쪽, -1: 왼쪽
    var isWalking = false
    var isAirborne = false
}

/// 화면 위를 돌아다니는 알파·베타 데스크톱 캐릭터를 관리한다.
/// 캐릭터마다 투명 NSPanel 하나를 만들고, 30fps 틱으로 위치와 행동 상태를 갱신한다.
@MainActor
final class DesktopPetManager {
    static let shared = DesktopPetManager()
    static let enabledKey = "desktopPetsEnabled"

    /// 기본값 켜짐 (키가 없으면 true)
    static var isEnabled: Bool {
        UserDefaults.standard.object(forKey: enabledKey) == nil
            ? true
            : UserDefaults.standard.bool(forKey: enabledKey)
    }

    private var pets: [Pet] = []
    private var timer: Timer?
    private var lastTick = Date.now

    private init() {}

    func applyEnabledSetting() {
        if Self.isEnabled { start() } else { stop() }
    }

    func start() {
        guard pets.isEmpty, let screen = NSScreen.main else { return }
        let frame = screen.visibleFrame

        pets = Persona.allCases.enumerated().map { index, persona in
            let x = frame.midX - 120 + CGFloat(index) * 200
            return Pet(persona: persona, origin: CGPoint(x: x, y: frame.minY))
        }

        lastTick = .now
        let timer = Timer(timeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.tick() }
        }
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        for pet in pets { pet.panel.close() }
        pets.removeAll()
    }

    private func tick() {
        let now = Date.now
        let dt = min(now.timeIntervalSince(lastTick), 0.1)
        lastTick = now
        for pet in pets { pet.tick(dt: dt) }
    }
}

// MARK: - Pet

/// 캐릭터 한 마리의 행동 상태 머신 + 창
@MainActor
final class Pet {
    enum State {
        case idle(remaining: TimeInterval)
        case walking(remaining: TimeInterval)
        case airborne
        case dragging
    }

    let persona: Persona
    let panel: NSPanel
    let visual = PetVisualState()

    static let size = CGSize(width: 90, height: 84)

    private var state: State = .idle(remaining: 1.0)
    private var vx: CGFloat = 0
    private var vy: CGFloat = 0
    private var dragStartOrigin: CGPoint = .zero

    init(persona: Persona, origin: CGPoint) {
        self.persona = persona

        let panel = NSPanel(
            contentRect: NSRect(origin: origin, size: Self.size),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.isReleasedWhenClosed = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        self.panel = panel

        panel.contentView = NSHostingView(rootView: PetView(
            persona: persona,
            visual: visual,
            onTap: { [weak self] in self?.jump() },
            onDragChanged: { [weak self] translation in self?.dragChanged(translation) },
            onDragEnded: { [weak self] in self?.dragEnded() }
        ))
        panel.orderFrontRegardless()
    }

    // MARK: 행동

    func tick(dt: TimeInterval) {
        let bounds = (panel.screen ?? NSScreen.main)?.visibleFrame ?? .zero
        guard bounds.width > 0 else { return }
        var origin = panel.frame.origin

        switch state {
        case .dragging:
            return

        case .idle(let remaining):
            let left = remaining - dt
            if left <= 0 {
                startWalking()
            } else {
                state = .idle(remaining: left)
            }

        case .walking(let remaining):
            origin.x += vx * CGFloat(dt)
            if origin.x <= bounds.minX {
                origin.x = bounds.minX
                turnAround()
            } else if origin.x >= bounds.maxX - Pet.size.width {
                origin.x = bounds.maxX - Pet.size.width
                turnAround()
            }
            let left = remaining - dt
            if left <= 0 {
                startIdle()
            } else {
                state = .walking(remaining: left)
            }

        case .airborne:
            vy -= 1500 * CGFloat(dt)
            origin.y += vy * CGFloat(dt)
            origin.x += vx * CGFloat(dt)
            origin.x = min(max(origin.x, bounds.minX), bounds.maxX - Pet.size.width)
            if origin.y <= bounds.minY {
                origin.y = bounds.minY
                vy = 0
                visual.isAirborne = false
                startIdle(duration: .random(in: 0.4...1.2))
            }
        }

        panel.setFrameOrigin(origin)
    }

    private func startWalking() {
        let speed = CGFloat.random(in: 40...90)
        let direction: CGFloat = Bool.random() ? 1 : -1
        vx = speed * direction
        visual.facing = direction
        visual.isWalking = true
        state = .walking(remaining: .random(in: 3...8))
    }

    private func startIdle(duration: TimeInterval = .random(in: 1.5...4.5)) {
        vx = 0
        visual.isWalking = false
        state = .idle(remaining: duration)
    }

    private func turnAround() {
        vx = -vx
        visual.facing = vx >= 0 ? 1 : -1
    }

    /// 클릭 시 폴짝 뛰기
    private func jump() {
        if case .dragging = state { return }
        vy = 420
        visual.isAirborne = true
        visual.isWalking = false
        state = .airborne
    }

    // MARK: 드래그

    private func dragChanged(_ translation: CGSize) {
        if case .dragging = state {} else {
            state = .dragging
            visual.isWalking = false
            visual.isAirborne = true
            dragStartOrigin = panel.frame.origin
        }
        // SwiftUI는 y가 아래로 증가, 화면 좌표는 위로 증가
        panel.setFrameOrigin(CGPoint(
            x: dragStartOrigin.x + translation.width,
            y: dragStartOrigin.y - translation.height
        ))
    }

    private func dragEnded() {
        vx = 0
        vy = 0
        state = .airborne   // 공중에서 놓으면 낙하, 바닥이면 다음 틱에 착지 처리
    }
}
