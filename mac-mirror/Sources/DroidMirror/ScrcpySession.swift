import Foundation

/// Which way the mirrored video is locked. Values match scrcpy 2.x `lock_video_orientation`.
enum VideoOrientation: Int {
    case followDevice = -1
    case portrait = 0
    case landscape = 1          // 90° counter-clockwise
    case portraitUpsideDown = 2
    case landscapeReversed = 3  // 90° clockwise

    var title: String {
        switch self {
        case .followDevice: return "Follow Device"
        case .portrait: return "Portrait"
        case .landscape: return "Landscape"
        case .portraitUpsideDown: return "Portrait (Upside Down)"
        case .landscapeReversed: return "Landscape (Reversed)"
        }
    }
}

/// How the phone captures audio. `output` (REMOTE_SUBMIX) works on most devices; `playback`
/// (AudioPlaybackCapture, Android 13+) takes a different code path that avoids native-level
/// workarounds some vendor firmwares crash on.
enum AudioSource: String {
    case output
    case playback
}

struct SessionConfig {
    /// 0 = native resolution.
    var maxSize: Int = 0
    var videoBitRate: Int = 20_000_000
    /// 0 = no limit (as fast as the display refreshes).
    var maxFps: Int = 0
    var orientation: VideoOrientation = .landscape
    var audio: Bool = true
    var audioSource: AudioSource = .output
    var stayAwake: Bool = true
    var localPort: UInt16 = 27183
}

protocol ScrcpySessionDelegate: AnyObject {
    func session(_ session: ScrcpySession, status: String)
    func session(_ session: ScrcpySession, connectedTo deviceName: String, controller: DeviceController)
    func session(_ session: ScrcpySession, videoStarted width: Int, height: Int)
    func session(_ session: ScrcpySession, videoConfig data: Data)
    func session(_ session: ScrcpySession, videoFrame data: Data, keyframe: Bool)
    func session(_ session: ScrcpySession, audioPCM data: Data)
    func session(_ session: ScrcpySession, audioUnavailable reason: String)
    func session(_ session: ScrcpySession, ended error: Error?)
}

enum SessionError: LocalizedError {
    case serverDidNotStart
    case unexpectedCodec(UInt32)
    case audioFailed

    var errorDescription: String? {
        switch self {
        case .serverDidNotStart: return "The scrcpy server did not start on the device."
        case .unexpectedCodec(let id): return String(format: "Unexpected video codec id 0x%08x", id)
        case .audioFailed: return "Audio capture failed on the device."
        }
    }
}

/// Drives one mirroring session: pushes the scrcpy server, starts it over adb, then
/// reads the video / audio streams and hands out a controller for input.
final class ScrcpySession {
    static let serverVersion = "2.7"
    private static let remoteServerPath = "/data/local/tmp/scrcpy-server.jar"

    // Codec ids as sent in the scrcpy codec meta header.
    private static let codecH264: UInt32 = 0x6832_3634  // "h264"
    private static let codecRaw: UInt32 = 0x0072_6177   // "\0raw"
    private static let audioDisabled: UInt32 = 0x0000_0000
    private static let audioError: UInt32 = 0x0000_0001

    private static let flagConfig: UInt64 = 1 << 63
    private static let flagKeyframe: UInt64 = 1 << 62

    weak var delegate: ScrcpySessionDelegate?

    let config: SessionConfig
    private let adb: ADB
    private let serverPath: String
    private let scid: UInt32

    private let workQueue = DispatchQueue(label: "droidmirror.session")
    private var serverProcess: Process?
    private var serial: String?
    private var videoSocket: TCPSocket?
    private var audioSocket: TCPSocket?
    private var controlSocket: TCPSocket?
    private var stopped = false
    private var endReported = false

    init(config: SessionConfig) throws {
        self.config = config
        adb = try ADB()
        guard let server = Tools.scrcpyServerPath() else { throw ADBError.serverNotFound }
        serverPath = server
        scid = UInt32.random(in: 1..<0x7FFF_FFFF)
    }

    private var socketName: String { String(format: "scrcpy_%08x", scid) }

    func start() {
        workQueue.async { self.run() }
    }

    /// Safe to call from any thread; the work queue is busy reading video, so do not queue on it.
    func stop() {
        teardown(error: nil)
    }

    // MARK: - Setup

    private func run() {
        do {
            report("Looking for device…")
            let device = try adb.firstDevice()
            serial = device.serial

            report("Pushing scrcpy server…")
            try adb.push(local: serverPath, remote: ScrcpySession.remoteServerPath, serial: device.serial)

            try adb.forward(localPort: config.localPort, abstractSocket: socketName, serial: device.serial)

            report("Starting server…")
            Log.clearServerLines()
            Log.write("Starting server: \(serverCommand())")
            let process = try adb.shell(serverCommand(), serial: device.serial) { line in
                Log.server(line)
            }
            serverProcess = process

            // Video socket is opened first; the server writes a dummy byte on it as soon as it is listening.
            let video = try connectWithRetry(process: process)
            videoSocket = video

            // The server accepts video, audio and control in that order and only then sends the
            // device name, so every socket must be connected before reading anything else.
            if config.audio {
                audioSocket = try TCPSocket(port: config.localPort)
            }
            let control = try TCPSocket(port: config.localPort)
            controlSocket = control

            let nameData = try video.readExactly(64)
            let deviceName = String(decoding: nameData.prefix { $0 != 0 }, as: UTF8.self)

            // Video codec meta: codec id, width, height.
            let codecID = try video.readUInt32BE()
            let width = try video.readUInt32BE()
            let height = try video.readUInt32BE()
            guard codecID == ScrcpySession.codecH264 else { throw SessionError.unexpectedCodec(codecID) }

            let controller = DeviceController(socket: control, screenSize: (UInt16(width), UInt16(height)))
            controller.onError = { [weak self] error in
                self?.teardown(error: error)
            }

            let displayName = deviceName.isEmpty ? (device.model.isEmpty ? device.serial : device.model) : deviceName
            delegate?.session(self, connectedTo: displayName, controller: controller)
            delegate?.session(self, videoStarted: Int(width), height: Int(height))
            report("Mirroring \(displayName) at \(width)×\(height)")

            if let audio = audioSocket {
                Thread.detachNewThread { [weak self] in self?.readAudio(audio) }
            }
            readVideo(video)
        } catch {
            if !stopped {
                Log.write("Session failed: \(error.localizedDescription)")
                for line in Log.lastServerLines() { Log.write("  server said: \(line)") }
            }
            teardown(error: stopped ? nil : error)
        }
    }

    private func serverCommand() -> String {
        var args = [
            "CLASSPATH=\(ScrcpySession.remoteServerPath)",
            "app_process", "/", "com.genymobile.scrcpy.Server", ScrcpySession.serverVersion,
            "scid=\(String(format: "%08x", scid))",
            "log_level=debug",
            "tunnel_forward=true",
            "control=true",
            "video_codec=h264",
            "max_size=\(config.maxSize)",
            "video_bit_rate=\(config.videoBitRate)",
            "max_fps=\(config.maxFps)",
            "lock_video_orientation=\(config.orientation.rawValue)",
            "stay_awake=\(config.stayAwake)",
            "cleanup=true",
            "send_frame_meta=true",
        ]
        if config.audio {
            // Raw PCM: nothing to decode on the Mac, which keeps audio latency minimal.
            args += ["audio=true", "audio_codec=raw", "audio_source=\(config.audioSource.rawValue)"]
        } else {
            args += ["audio=false"]
        }
        return args.joined(separator: " ")
    }

    /// In forward mode adb accepts the TCP connection before the server is listening and then closes it,
    /// so keep connecting until we actually receive the server's dummy byte.
    private func connectWithRetry(process: Process) throws -> TCPSocket {
        for _ in 0..<100 {
            if stopped { throw SocketError.closed }
            if !process.isRunning { throw SessionError.serverDidNotStart }
            if let socket = try? TCPSocket(port: config.localPort) {
                if let byte = try? socket.readUInt8(), byte == 0 {
                    return socket
                }
                socket.close()
            }
            Thread.sleep(forTimeInterval: 0.1)
        }
        throw SessionError.serverDidNotStart
    }

    // MARK: - Streams

    private func readVideo(_ socket: TCPSocket) {
        do {
            while !stopped {
                let ptsAndFlags = try socket.readUInt64BE()
                let size = Int(try socket.readUInt32BE())
                let packet = try socket.readExactly(size)
                if ptsAndFlags & ScrcpySession.flagConfig != 0 {
                    delegate?.session(self, videoConfig: packet)
                } else {
                    delegate?.session(self, videoFrame: packet, keyframe: ptsAndFlags & ScrcpySession.flagKeyframe != 0)
                }
            }
            teardown(error: nil)
        } catch {
            if !stopped { Log.write("Video stream failed: \(error.localizedDescription)") }
            teardown(error: stopped ? nil : error)
        }
    }

    private func readAudio(_ socket: TCPSocket) {
        do {
            let codecID = try socket.readUInt32BE()
            switch codecID {
            case ScrcpySession.codecRaw:
                break
            case ScrcpySession.audioDisabled:
                delegate?.session(self, audioUnavailable: "Audio is not supported by this device (needs Android 11+).")
                return
            case ScrcpySession.audioError:
                delegate?.session(self, audioUnavailable: "Audio capture failed on the device.")
                return
            default:
                delegate?.session(self, audioUnavailable: String(format: "Unexpected audio codec 0x%08x", codecID))
                return
            }
            while !stopped {
                _ = try socket.readUInt64BE()             // pts / flags — raw audio has no config packets
                let size = Int(try socket.readUInt32BE())
                let packet = try socket.readExactly(size)
                delegate?.session(self, audioPCM: packet)
            }
        } catch {
            if !stopped {
                delegate?.session(self, audioUnavailable: "Audio stream ended: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Teardown

    private let teardownLock = NSLock()

    private func teardown(error: Error?) {
        // May be called from the video thread, the control queue, the work queue or the main
        // thread; make it idempotent and serialised.
        teardownLock.lock()
        defer { teardownLock.unlock() }
        if stopped && endReported { return }
        stopped = true

        videoSocket?.close()
        audioSocket?.close()
        controlSocket?.close()
        videoSocket = nil
        audioSocket = nil
        controlSocket = nil

        if let process = serverProcess {
            if process.isRunning { process.terminate() }
            serverProcess = nil
        }
        if let serial = serial {
            adb.removeForward(localPort: config.localPort, serial: serial)
        }

        if !endReported {
            endReported = true
            delegate?.session(self, ended: error)
        }
    }

    private func report(_ status: String) {
        Log.write(status)
        delegate?.session(self, status: status)
    }
}
