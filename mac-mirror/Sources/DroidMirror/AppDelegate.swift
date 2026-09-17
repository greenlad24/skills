import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, ScrcpySessionDelegate {
    private var window: NSWindow!
    private let mirrorView = MirrorView(frame: NSRect(x: 0, y: 0, width: 1200, height: 540))
    private let statusLabel = NSTextField(labelWithString: "")
    private let audioPlayer = AudioPlayer()

    private var session: ScrcpySession?
    private var controller: DeviceController?
    private var config = SessionConfig()
    private var userDisconnected = false
    private var reconnectTimer: Timer?
    private var deviceName = ""

    private var orientationItems: [NSMenuItem] = []
    private var audioItem: NSMenuItem!

    // MARK: - Launch

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        buildWindow()
        connect()
    }

    func applicationWillTerminate(_ notification: Notification) {
        session?.stop()
        audioPlayer.stop()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    private func buildWindow() {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 1200, height: 570))

        mirrorView.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(mirrorView)

        let bar = NSVisualEffectView()
        bar.material = .titlebar
        bar.blendingMode = .withinWindow
        bar.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(bar)

        statusLabel.font = NSFont.systemFont(ofSize: 11)
        statusLabel.textColor = .secondaryLabelColor
        statusLabel.lineBreakMode = .byTruncatingTail
        statusLabel.translatesAutoresizingMaskIntoConstraints = false

        let buttons = NSStackView(views: [
            makeButton("Back", #selector(pressBack)),
            makeButton("Home", #selector(pressHome)),
            makeButton("Recents", #selector(pressRecents)),
            makeButton("Power", #selector(pressPower)),
            makeButton("Vol −", #selector(volumeDown)),
            makeButton("Vol +", #selector(volumeUp)),
            makeButton("Notifications", #selector(expandNotifications)),
        ])
        buttons.orientation = .horizontal
        buttons.spacing = 6
        buttons.translatesAutoresizingMaskIntoConstraints = false

        bar.addSubview(statusLabel)
        bar.addSubview(buttons)

        NSLayoutConstraint.activate([
            mirrorView.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            mirrorView.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            mirrorView.topAnchor.constraint(equalTo: content.topAnchor),
            mirrorView.bottomAnchor.constraint(equalTo: bar.topAnchor),

            bar.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            bar.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            bar.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            bar.heightAnchor.constraint(equalToConstant: 30),

            statusLabel.leadingAnchor.constraint(equalTo: bar.leadingAnchor, constant: 10),
            statusLabel.centerYAnchor.constraint(equalTo: bar.centerYAnchor),
            statusLabel.trailingAnchor.constraint(lessThanOrEqualTo: buttons.leadingAnchor, constant: -10),

            buttons.trailingAnchor.constraint(equalTo: bar.trailingAnchor, constant: -8),
            buttons.centerYAnchor.constraint(equalTo: bar.centerYAnchor),
        ])

        window = NSWindow(contentRect: content.frame,
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "DroidMirror"
        window.contentView = content
        window.delegate = self
        window.minSize = NSSize(width: 480, height: 300)
        window.isReleasedWhenClosed = false
        window.center()
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(mirrorView)
        NSApp.activate(ignoringOtherApps: true)

        mirrorView.onVideoSizeChanged = { [weak self] size in self?.fitWindow(to: size) }
    }

    private func makeButton(_ title: String, _ action: Selector) -> NSButton {
        let b = NSButton(title: title, target: self, action: action)
        b.bezelStyle = .rounded
        b.controlSize = .small
        b.font = NSFont.systemFont(ofSize: 11)
        b.refusesFirstResponder = true
        return b
    }

    /// Resize the window so the video fills it without letterboxing, keeping it on screen.
    private func fitWindow(to size: CGSize) {
        guard size.width > 0, size.height > 0, let screen = window.screen ?? NSScreen.main else { return }
        let barHeight: CGFloat = 30
        let available = screen.visibleFrame
        var width = min(size.width, available.width * 0.9)
        var height = width * size.height / size.width
        let maxHeight = available.height * 0.9 - barHeight
        if height > maxHeight {
            height = maxHeight
            width = height * size.width / size.height
        }
        let contentSize = NSSize(width: round(width), height: round(height + barHeight))
        window.contentAspectRatio = .zero
        window.setContentSize(contentSize)
        window.contentResizeIncrements = NSSize(width: 1, height: 1)
        window.center()
    }

    // MARK: - Menu

    private func buildMenu() {
        let mainMenu = NSMenu()

        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About DroidMirror", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Hide DroidMirror", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit DroidMirror", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let appItem = NSMenuItem()
        appItem.submenu = appMenu
        mainMenu.addItem(appItem)

        let deviceMenu = NSMenu(title: "Device")
        deviceMenu.addItem(withTitle: "Connect", action: #selector(connectClicked), keyEquivalent: "r")
        deviceMenu.addItem(withTitle: "Disconnect", action: #selector(disconnectClicked), keyEquivalent: "d")
        deviceMenu.addItem(.separator())
        deviceMenu.addItem(withTitle: "Back", action: #selector(pressBack), keyEquivalent: "b")
        deviceMenu.addItem(withTitle: "Home", action: #selector(pressHome), keyEquivalent: "h").keyEquivalentModifierMask = [.command, .shift]
        deviceMenu.addItem(withTitle: "Recent Apps", action: #selector(pressRecents), keyEquivalent: "s")
        deviceMenu.addItem(withTitle: "Power", action: #selector(pressPower), keyEquivalent: "p")
        let upArrow = String(Character(UnicodeScalar(UInt16(NSUpArrowFunctionKey))!))
        let downArrow = String(Character(UnicodeScalar(UInt16(NSDownArrowFunctionKey))!))
        deviceMenu.addItem(withTitle: "Volume Up", action: #selector(volumeUp), keyEquivalent: upArrow)
        deviceMenu.addItem(withTitle: "Volume Down", action: #selector(volumeDown), keyEquivalent: downArrow)
        deviceMenu.addItem(.separator())
        deviceMenu.addItem(withTitle: "Expand Notifications", action: #selector(expandNotifications), keyEquivalent: "n")
        deviceMenu.addItem(withTitle: "Collapse Panels", action: #selector(collapsePanels), keyEquivalent: "")
        deviceMenu.addItem(withTitle: "Rotate Device", action: #selector(rotateDevice), keyEquivalent: "")
        deviceMenu.addItem(.separator())
        deviceMenu.addItem(withTitle: "Turn Phone Screen Off (keep mirroring)", action: #selector(screenOff), keyEquivalent: "o")
        deviceMenu.addItem(withTitle: "Turn Phone Screen On", action: #selector(screenOn), keyEquivalent: "O")
        let deviceItem = NSMenuItem()
        deviceItem.submenu = deviceMenu
        mainMenu.addItem(deviceItem)

        let viewMenu = NSMenu(title: "View")
        for orientation in [VideoOrientation.landscape, .landscapeReversed, .portrait, .followDevice] {
            let item = NSMenuItem(title: orientation.title, action: #selector(orientationSelected(_:)), keyEquivalent: "")
            item.tag = orientation.rawValue
            item.target = self
            viewMenu.addItem(item)
            orientationItems.append(item)
        }
        viewMenu.addItem(.separator())
        audioItem = NSMenuItem(title: "Audio", action: #selector(toggleAudio), keyEquivalent: "")
        viewMenu.addItem(audioItem)
        viewMenu.addItem(.separator())
        viewMenu.addItem(withTitle: "Fit Window to Video", action: #selector(fitWindowClicked), keyEquivalent: "0")
        viewMenu.addItem(withTitle: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f").keyEquivalentModifierMask = [.command, .control]
        let viewItem = NSMenuItem()
        viewItem.submenu = viewMenu
        mainMenu.addItem(viewItem)

        let windowMenu = NSMenu(title: "Window")
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        let windowItem = NSMenuItem()
        windowItem.submenu = windowMenu
        mainMenu.addItem(windowItem)
        NSApp.windowsMenu = windowMenu

        let helpMenu = NSMenu(title: "Help")
        helpMenu.addItem(withTitle: "Show Log in Finder", action: #selector(showLog), keyEquivalent: "l")
        helpMenu.addItem(withTitle: "Copy Log to Clipboard", action: #selector(copyLog), keyEquivalent: "L")
        let helpItem = NSMenuItem()
        helpItem.submenu = helpMenu
        mainMenu.addItem(helpItem)
        NSApp.helpMenu = helpMenu

        NSApp.mainMenu = mainMenu
        refreshMenuState()
    }

    private func refreshMenuState() {
        for item in orientationItems {
            item.state = item.tag == config.orientation.rawValue ? .on : .off
        }
        audioItem.state = config.audio ? .on : .off
    }

    // MARK: - Session lifecycle

    private func connect() {
        reconnectTimer?.invalidate()
        reconnectTimer = nil
        guard session == nil else { return }
        userDisconnected = false
        mirrorView.resetStream()
        do {
            let s = try ScrcpySession(config: config)
            s.delegate = self
            session = s
            s.start()
        } catch {
            setStatus("⚠︎ \(error.localizedDescription)")
            scheduleReconnect()
        }
    }

    private func disconnect() {
        reconnectTimer?.invalidate()
        reconnectTimer = nil
        session?.stop()
    }

    /// Restart the session (used when orientation / audio settings change).
    private func restart() {
        if session == nil {
            connect()
        } else {
            userDisconnected = false
            session?.stop()
            // The ended callback reconnects because userDisconnected is false.
        }
    }

    private func scheduleReconnect() {
        guard !userDisconnected, reconnectTimer == nil else { return }
        reconnectTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: false) { [weak self] _ in
            self?.reconnectTimer = nil
            self?.connect()
        }
    }

    private func setStatus(_ text: String) {
        statusLabel.stringValue = text
    }

    // MARK: - ScrcpySessionDelegate (called on background threads)

    func session(_ session: ScrcpySession, status: String) {
        DispatchQueue.main.async { self.setStatus(status) }
    }

    func session(_ session: ScrcpySession, connectedTo deviceName: String, controller: DeviceController) {
        DispatchQueue.main.async {
            self.deviceName = deviceName
            self.controller = controller
            self.mirrorView.controller = controller
            self.window.title = "DroidMirror — \(deviceName)"
            if self.config.audio { self.audioPlayer.start() }
        }
    }

    func session(_ session: ScrcpySession, videoStarted width: Int, height: Int) {
        DispatchQueue.main.async {
            self.mirrorView.videoSize = CGSize(width: width, height: height)
        }
    }

    func session(_ session: ScrcpySession, videoConfig data: Data) {
        mirrorView.handleConfig(data)
    }

    func session(_ session: ScrcpySession, videoFrame data: Data, keyframe: Bool) {
        mirrorView.handleFrame(data, keyframe: keyframe)
    }

    func session(_ session: ScrcpySession, audioPCM data: Data) {
        audioPlayer.enqueue(pcm: data)
    }

    func session(_ session: ScrcpySession, audioUnavailable reason: String) {
        DispatchQueue.main.async {
            self.audioPlayer.stop()
            self.setStatus("Mirroring \(self.deviceName) — no audio: \(reason)")
        }
    }

    func session(_ session: ScrcpySession, ended error: Error?) {
        DispatchQueue.main.async {
            guard session === self.session else { return }
            self.session = nil
            self.controller = nil
            self.mirrorView.controller = nil
            self.audioPlayer.stop()
            self.window.title = "DroidMirror"
            if let error = error {
                var text = "⚠︎ \(error.localizedDescription)"
                if let last = Log.lastServerLines(1).first { text += "  —  server: \(last)" }
                self.setStatus(text + "  (Help → Show Log)")
            } else {
                self.setStatus(self.userDisconnected ? "Disconnected" : "Device disconnected — waiting…")
            }
            self.scheduleReconnect()
        }
    }

    // MARK: - Actions

    @objc private func connectClicked() { connect() }

    @objc private func disconnectClicked() {
        userDisconnected = true
        disconnect()
    }

    @objc private func pressBack() { controller?.backOrScreenOn() }
    @objc private func pressHome() { controller?.press(.home) }
    @objc private func pressRecents() { controller?.press(.appSwitch) }
    @objc private func pressPower() { controller?.press(.power) }
    @objc private func volumeUp() { controller?.press(.volumeUp) }
    @objc private func volumeDown() { controller?.press(.volumeDown) }
    @objc private func expandNotifications() { controller?.expandNotificationPanel() }
    @objc private func collapsePanels() { controller?.collapsePanels() }
    @objc private func rotateDevice() { controller?.rotateDevice() }
    @objc private func screenOff() { controller?.setScreenPower(on: false) }
    @objc private func screenOn() { controller?.setScreenPower(on: true) }
    @objc private func fitWindowClicked() { fitWindow(to: mirrorView.videoSize) }

    @objc private func showLog() {
        NSWorkspace.shared.activateFileViewerSelecting([Log.fileURL])
    }

    @objc private func copyLog() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(Log.contents(), forType: .string)
        setStatus("Log copied to clipboard")
    }

    @objc private func orientationSelected(_ sender: NSMenuItem) {
        guard let orientation = VideoOrientation(rawValue: sender.tag), orientation != config.orientation else { return }
        config.orientation = orientation
        refreshMenuState()
        restart()
    }

    @objc private func toggleAudio() {
        config.audio.toggle()
        refreshMenuState()
        restart()
    }
}
