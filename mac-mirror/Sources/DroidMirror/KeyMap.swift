import AppKit

/// Maps macOS hardware key codes for non-printing keys to Android key codes.
enum KeyMap {
    static func androidKey(forMacKeyCode code: UInt16) -> AndroidKey? {
        switch code {
        case 36, 76: return .enter          // Return, keypad Enter
        case 51: return .del                // Delete (backspace)
        case 117: return .forwardDel        // Forward delete
        case 48: return .tab
        case 53: return .back               // Escape -> Android Back
        case 49: return .space
        case 123: return .dpadLeft
        case 124: return .dpadRight
        case 125: return .dpadDown
        case 126: return .dpadUp
        case 115: return .moveHome
        case 119: return .moveEnd
        case 116: return .pageUp
        case 121: return .pageDown
        default: return nil
        }
    }
}
