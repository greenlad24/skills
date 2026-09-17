import Foundation

/// Android key codes we use.
enum AndroidKey: Int32 {
    case home = 3
    case back = 4
    case volumeUp = 24
    case volumeDown = 25
    case power = 26
    case tab = 61
    case space = 62
    case enter = 66
    case del = 67
    case dpadUp = 19
    case dpadDown = 20
    case dpadLeft = 21
    case dpadRight = 22
    case pageUp = 92
    case pageDown = 93
    case escape = 111
    case forwardDel = 112
    case moveHome = 122
    case moveEnd = 123
    case appSwitch = 187
}

/// Sends scrcpy 2.x control messages over the control socket.
final class DeviceController {
    enum TouchAction: UInt8 {
        case down = 0
        case up = 1
        case move = 2
        case cancel = 3
    }

    private enum MessageType: UInt8 {
        case injectKeycode = 0
        case injectText = 1
        case injectTouch = 2
        case injectScroll = 3
        case backOrScreenOn = 4
        case expandNotificationPanel = 5
        case expandSettingsPanel = 6
        case collapsePanels = 7
        case setScreenPowerMode = 10
        case rotateDevice = 11
    }

    /// scrcpy's POINTER_ID_GENERIC_FINGER: the server injects a touchscreen event rather than a mouse event.
    private static let fingerPointerID: UInt64 = 0xFFFF_FFFF_FFFF_FFFE

    private let socket: TCPSocket
    private let queue = DispatchQueue(label: "droidmirror.control")

    /// Size of the video frame; touch coordinates are expressed in this space.
    var screenSize: (width: UInt16, height: UInt16)

    var onError: ((Error) -> Void)?

    init(socket: TCPSocket, screenSize: (width: UInt16, height: UInt16)) {
        self.socket = socket
        self.screenSize = screenSize
    }

    private func send(_ data: Data) {
        queue.async {
            do { try self.socket.write(data) } catch { self.onError?(error) }
        }
    }

    // MARK: Touch

    func touch(_ action: TouchAction, x: Int32, y: Int32, pressure: Float = 1.0) {
        var msg = Data(capacity: 32)
        msg.append(MessageType.injectTouch.rawValue)
        msg.append(action.rawValue)
        msg.appendBE(DeviceController.fingerPointerID)
        msg.appendBE(UInt32(bitPattern: x))
        msg.appendBE(UInt32(bitPattern: y))
        msg.appendBE(screenSize.width)
        msg.appendBE(screenSize.height)
        let p = action == .up ? 0.0 : pressure
        msg.appendBE(UInt16(min(max(p, 0), 1) * 65535))
        msg.appendBE(UInt32(0)) // action button
        msg.appendBE(UInt32(0)) // buttons
        send(msg)
    }

    func scroll(x: Int32, y: Int32, horizontal: Float, vertical: Float) {
        var msg = Data(capacity: 21)
        msg.append(MessageType.injectScroll.rawValue)
        msg.appendBE(UInt32(bitPattern: x))
        msg.appendBE(UInt32(bitPattern: y))
        msg.appendBE(screenSize.width)
        msg.appendBE(screenSize.height)
        msg.appendBE(UInt16(bitPattern: DeviceController.fixedPoint16(horizontal)))
        msg.appendBE(UInt16(bitPattern: DeviceController.fixedPoint16(vertical)))
        msg.appendBE(UInt32(0)) // buttons
        send(msg)
    }

    /// scrcpy encodes [-1, 1] floats as signed 16-bit fixed point.
    private static func fixedPoint16(_ value: Float) -> Int16 {
        let clamped = min(max(value, -1), 1)
        let scaled = Int32(clamped * 32768)
        return Int16(min(max(scaled, -32768), 32767))
    }

    // MARK: Keys and text

    func key(_ keycode: Int32, down: Bool, metaState: UInt32 = 0, repeatCount: UInt32 = 0) {
        var msg = Data(capacity: 14)
        msg.append(MessageType.injectKeycode.rawValue)
        msg.append(down ? 0 : 1)
        msg.appendBE(UInt32(bitPattern: keycode))
        msg.appendBE(repeatCount)
        msg.appendBE(metaState)
        send(msg)
    }

    func press(_ key: AndroidKey, metaState: UInt32 = 0) {
        self.key(key.rawValue, down: true, metaState: metaState)
        self.key(key.rawValue, down: false, metaState: metaState)
    }

    func injectText(_ text: String) {
        guard let utf8 = text.data(using: .utf8), !utf8.isEmpty, utf8.count <= 300 else { return }
        var msg = Data(capacity: 5 + utf8.count)
        msg.append(MessageType.injectText.rawValue)
        msg.appendBE(UInt32(utf8.count))
        msg.append(utf8)
        send(msg)
    }

    // MARK: Device actions

    func backOrScreenOn() {
        // down + up
        send(Data([MessageType.backOrScreenOn.rawValue, 0]))
        send(Data([MessageType.backOrScreenOn.rawValue, 1]))
    }

    func expandNotificationPanel() { send(Data([MessageType.expandNotificationPanel.rawValue])) }
    func expandSettingsPanel() { send(Data([MessageType.expandSettingsPanel.rawValue])) }
    func collapsePanels() { send(Data([MessageType.collapsePanels.rawValue])) }
    func rotateDevice() { send(Data([MessageType.rotateDevice.rawValue])) }

    /// mode 0 = screen off (mirroring continues), 2 = normal.
    func setScreenPower(on: Bool) {
        send(Data([MessageType.setScreenPowerMode.rawValue, on ? 2 : 0]))
    }
}

extension Data {
    mutating func appendBE(_ value: UInt16) {
        var v = value.bigEndian
        append(Data(bytes: &v, count: 2))
    }
    mutating func appendBE(_ value: UInt32) {
        var v = value.bigEndian
        append(Data(bytes: &v, count: 4))
    }
    mutating func appendBE(_ value: UInt64) {
        var v = value.bigEndian
        append(Data(bytes: &v, count: 8))
    }
}
