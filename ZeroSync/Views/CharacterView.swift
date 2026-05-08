import SwiftUI

// MARK: - Sprite Sheet Cropper
// 좌표는 전체 이미지 크기(2816×1536) 기준 0~1 정규화 값
// Xcode에서 실행 후 cropRect 값을 조정해 포즈를 맞추세요.

struct CharacterSpriteView: View {
    let cropRect: CGRect   // 정규화 좌표 (0~1)
    let size: CGSize

    var body: some View {
        let scaleX = size.width  / cropRect.width
        let scaleY = size.height / cropRect.height

        Image("CharacterSheet")
            .resizable()
            .frame(width: scaleX, height: scaleY)
            .offset(
                x: -cropRect.minX * scaleX,
                y: -cropRect.minY * scaleY
            )
            .frame(width: size.width, height: size.height)
            .clipped()
    }
}

// MARK: - Alpha Wolf Poses

enum AlphaWolfPose {
    case sitting        // 앉아있는 자세 (기본)
    case running        // 달리는 자세 (빠른 실행)
    case growling       // 으르렁 (경고/오류)
    case pawRaise       // 앞발 들기 (제안)
    case lying          // 누워있기 (대기)
    case earPerk        // 귀 쫑긋 (정보 감지)
    case howling        // 하울링 (중요 알림)

    var cropRect: CGRect {
        switch self {
        case .sitting:  return CGRect(x: 0.063, y: 0.465, width: 0.083, height: 0.230)
        case .running:  return CGRect(x: 0.158, y: 0.455, width: 0.095, height: 0.230)
        case .growling: return CGRect(x: 0.265, y: 0.455, width: 0.095, height: 0.230)
        case .pawRaise: return CGRect(x: 0.378, y: 0.455, width: 0.075, height: 0.225)
        case .lying:    return CGRect(x: 0.455, y: 0.505, width: 0.110, height: 0.175)
        case .earPerk:  return CGRect(x: 0.598, y: 0.455, width: 0.080, height: 0.225)
        case .howling:  return CGRect(x: 0.843, y: 0.445, width: 0.090, height: 0.250)
        }
    }
}

// MARK: - Beta Polar Bear Poses

enum BetaBearPose {
    case sitting        // 앉아있는 자세 (기본)
    case walking        // 느릿느릿 걷기 (안정적 진행)
    case defense        // 방어 자세 (경계)
    case lying          // 누워서 쉬기 (휴식 권유)
    case standing       // 일어서기 (알림)
    case playful        // 장난치는 모습 (긴장 해소)
    case comforting     // 포옹 자세 (위로/서포트)

    var cropRect: CGRect {
        switch self {
        case .sitting:    return CGRect(x: 0.470, y: 0.558, width: 0.090, height: 0.228)
        case .walking:    return CGRect(x: 0.572, y: 0.552, width: 0.095, height: 0.228)
        case .defense:    return CGRect(x: 0.680, y: 0.500, width: 0.075, height: 0.260)
        case .lying:      return CGRect(x: 0.752, y: 0.618, width: 0.100, height: 0.175)
        case .standing:   return CGRect(x: 0.855, y: 0.520, width: 0.068, height: 0.280)
        case .playful:    return CGRect(x: 0.930, y: 0.545, width: 0.070, height: 0.260)
        case .comforting: return CGRect(x: 0.855, y: 0.520, width: 0.068, height: 0.280)
        }
    }
}

// MARK: - Convenience Views

struct AlphaWolfView: View {
    var pose: AlphaWolfPose = .sitting
    var size: CGSize = CGSize(width: 100, height: 100)
    var glowing: Bool = false

    var body: some View {
        CharacterSpriteView(cropRect: pose.cropRect, size: size)
            .shadow(
                color: glowing ? Color(red: 0, green: 0.4, blue: 1).opacity(0.8) : .clear,
                radius: glowing ? 14 : 0
            )
            .animation(.easeInOut(duration: 0.4), value: glowing)
    }
}

struct BetaBearView: View {
    var pose: BetaBearPose = .sitting
    var size: CGSize = CGSize(width: 100, height: 100)
    var glowing: Bool = false

    var body: some View {
        CharacterSpriteView(cropRect: pose.cropRect, size: size)
            .shadow(
                color: glowing ? Color(red: 1.0, green: 0.65, blue: 0.2).opacity(0.8) : .clear,
                radius: glowing ? 14 : 0
            )
            .animation(.easeInOut(duration: 0.4), value: glowing)
    }
}
