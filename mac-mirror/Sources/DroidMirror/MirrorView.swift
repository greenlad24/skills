import AppKit
import AVFoundation
import CoreMedia

/// Renders the decoded phone screen and forwards mouse/keyboard input as Android touch/key events.
final class MirrorView: NSView {
    let displayLayer = AVSampleBufferDisplayLayer()
    private let assembler = H264Assembler()
    private var needsKeyframe = true

    /// Set when the stream starts; updated if the SPS reports a different size.
    var videoSize: CGSize = .zero {
        didSet {
            if videoSize != oldValue { onVideoSizeChanged?(videoSize) }
        }
    }
    var onVideoSizeChanged: ((CGSize) -> Void)?

    var controller: DeviceController?
    private var dragging = false

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer = CALayer()
        layer?.backgroundColor = NSColor.black.cgColor
        displayLayer.videoGravity = .resizeAspect
        displayLayer.backgroundColor = NSColor.black.cgColor
        layer?.addSublayer(displayLayer)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }

    override var acceptsFirstResponder: Bool { true }
    override var isFlipped: Bool { true }

    override func layout() {
        super.layout()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        displayLayer.frame = bounds
        CATransaction.commit()
    }

    // MARK: - Video

    func resetStream() {
        needsKeyframe = true
        displayLayer.flushAndRemoveImage()
    }

    func handleConfig(_ data: Data) {
        do {
            if try assembler.handleConfig(data) {
                displayLayer.flush()
                needsKeyframe = true
                updateSizeFromFormat()
            }
        } catch {
            NSLog("H264 config error: \(error)")
        }
    }

    func handleFrame(_ data: Data, keyframe: Bool) {
        if displayLayer.status == .failed {
            NSLog("Display layer failed: \(displayLayer.error?.localizedDescription ?? "?") — flushing")
            displayLayer.flush()
            needsKeyframe = true
        }
        if needsKeyframe && !keyframe { return }
        needsKeyframe = false
        do {
            var formatChanged = false
            guard let sample = try assembler.makeSampleBuffer(frame: data, formatChanged: &formatChanged) else { return }
            if formatChanged {
                displayLayer.flush()
                updateSizeFromFormat()
            }
            if displayLayer.isReadyForMoreMediaData {
                displayLayer.enqueue(sample)
            }
        } catch {
            NSLog("H264 frame error: \(error)")
            needsKeyframe = true
        }
    }

    private func updateSizeFromFormat() {
        guard let dims = assembler.dimensions else { return }
        let size = CGSize(width: CGFloat(dims.width), height: CGFloat(dims.height))
        DispatchQueue.main.async {
            self.videoSize = size
            self.controller?.screenSize = (UInt16(dims.width), UInt16(dims.height))
        }
    }

    // MARK: - Coordinate mapping

    /// The rectangle (in view coordinates) the video actually occupies with aspect-fit scaling.
    private var videoRect: CGRect {
        guard videoSize.width > 0, videoSize.height > 0, bounds.width > 0, bounds.height > 0 else { return bounds }
        let scale = min(bounds.width / videoSize.width, bounds.height / videoSize.height)
        let w = videoSize.width * scale
        let h = videoSize.height * scale
        return CGRect(x: (bounds.width - w) / 2, y: (bounds.height - h) / 2, width: w, height: h)
    }

    /// Convert a mouse event location to video pixel coordinates (clamped to the frame).
    private func devicePoint(for event: NSEvent) -> (x: Int32, y: Int32)? {
        guard videoSize.width > 0 else { return nil }
        let p = convert(event.locationInWindow, from: nil)
        let rect = videoRect
        let x = (p.x - rect.minX) / rect.width * videoSize.width
        let y = (p.y - rect.minY) / rect.height * videoSize.height
        let cx = min(max(x, 0), videoSize.width - 1)
        let cy = min(max(y, 0), videoSize.height - 1)
        return (x: Int32(cx), y: Int32(cy))
    }

    // MARK: - Mouse -> touch

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        guard let c = controller, let pt = devicePoint(for: event) else { return }
        dragging = true
        c.touch(.down, x: pt.x, y: pt.y)
    }

    override func mouseDragged(with event: NSEvent) {
        guard dragging, let c = controller, let pt = devicePoint(for: event) else { return }
        c.touch(.move, x: pt.x, y: pt.y)
    }

    override func mouseUp(with event: NSEvent) {
        guard dragging, let c = controller, let pt = devicePoint(for: event) else { return }
        dragging = false
        c.touch(.up, x: pt.x, y: pt.y)
    }

    /// Right click = Android Back (or wake the screen), like scrcpy.
    override func rightMouseDown(with event: NSEvent) {
        controller?.backOrScreenOn()
    }

    /// Middle click = Home.
    override func otherMouseDown(with event: NSEvent) {
        controller?.press(.home)
    }

    override func scrollWheel(with event: NSEvent) {
        guard let c = controller, let pt = devicePoint(for: event) else { return }
        var h = Float(event.scrollingDeltaX)
        var v = Float(event.scrollingDeltaY)
        if event.hasPreciseScrollingDeltas {
            h /= 40
            v /= 40
        }
        if h == 0 && v == 0 { return }
        c.scroll(x: pt.x, y: pt.y, horizontal: h, vertical: v)
    }

    // MARK: - Keyboard

    override func keyDown(with event: NSEvent) {
        guard let c = controller else { return }
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if flags.contains(.command) {
            // Command shortcuts belong to the menu bar.
            super.keyDown(with: event)
            return
        }
        if let key = KeyMap.androidKey(forMacKeyCode: event.keyCode) {
            c.key(key.rawValue, down: true, repeatCount: event.isARepeat ? 1 : 0)
            return
        }
        if let text = event.characters, !text.isEmpty,
           text.unicodeScalars.allSatisfy({ !CharacterSet.controlCharacters.contains($0) }) {
            c.injectText(text)
        }
    }

    override func keyUp(with event: NSEvent) {
        guard let c = controller else { return }
        if let key = KeyMap.androidKey(forMacKeyCode: event.keyCode) {
            c.key(key.rawValue, down: false)
        }
    }
}
