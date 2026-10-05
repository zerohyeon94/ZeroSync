# Repository Guidelines

## Project Structure & Module Organization

ZeroSync is a macOS SwiftUI menu bar assistant app. Main application code lives in `ZeroSync/`:

- `ZeroSync/Views/` contains SwiftUI screens and reusable view components.
- `ZeroSync/Models/` contains app data types such as `Persona` and `Message`.
- `ZeroSync/Services/` contains integration code, including Claude API access.
- `ZeroSync/Assets.xcassets/` stores app icons, logo, background, and color assets.
- `ZeroSync/AppDelegate.swift` and `ZeroSync/ZeroSyncApp.swift` define app lifecycle behavior.

Tests are split into `ZeroSyncTests/` for Swift Testing unit tests and `ZeroSyncUITests/` for XCTest UI tests. Project documentation is under `docs/`, with ADRs in `docs/아키텍처 결정/`, feature notes in `docs/기능 개발/`, and daily logs in `docs/개발 일지/`. Treat `참고/` as reference material, not production source.

## Build, Test, and Development Commands

- `open ZeroSync.xcodeproj` opens the project in Xcode for local development.
- `xcodebuild -list -project ZeroSync.xcodeproj` lists available targets and schemes.
- `xcodebuild -scheme ZeroSync -project ZeroSync.xcodeproj build` builds the app.
- `xcodebuild -scheme ZeroSync -project ZeroSync.xcodeproj test` runs unit and UI tests configured for the scheme.
- `xcodebuild -scheme ZeroSync -project ZeroSync.xcodeproj -configuration Release archive` creates a release archive for distribution.

## Coding Style & Naming Conventions

Use Swift 5 and SwiftUI idioms. Follow existing two-level organization by feature type (`Views`, `Models`, `Services`). Use 4-space indentation, `UpperCamelCase` for types and files (`ChatView.swift`, `ClaudeService.swift`), and `lowerCamelCase` for functions, properties, and local variables. Keep SwiftUI views small enough to scan; extract reusable UI into separate `View` structs in `ZeroSync/Views/`.

## Testing Guidelines

Use Swift Testing (`import Testing`, `@Test`, `#expect`) for unit tests in `ZeroSyncTests/`. Use XCTest for UI and launch-performance coverage in `ZeroSyncUITests/`. Name tests after behavior, for example `@Test func sendsUserMessageToClaude()`. Run `xcodebuild -scheme ZeroSync -project ZeroSync.xcodeproj test` before opening a pull request.

## Commit & Pull Request Guidelines

History uses short Conventional Commit-style prefixes such as `feat:`, `chore:`, and `docs/feat:`. Keep commit subjects imperative and scoped to one change, for example `feat: add menu bar settings view`.

Pull requests should include a concise summary, test results, linked issue or doc entry when relevant, and screenshots or screen recordings for UI changes. For completed work, update `docs/개발 일지/YYYY-MM-DD.md` with what changed, blockers, and next steps.

## Security & Configuration Tips

Do not commit API keys, local credentials, derived data, or notarization secrets. Keep Claude API configuration local and review `ZeroSync/ZeroSync.entitlements` when changing app capabilities.
