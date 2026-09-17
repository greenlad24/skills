import Foundation

struct ADBDevice {
    let serial: String
    let state: String      // "device", "unauthorized", "offline", ...
    let model: String
}

enum ADBError: LocalizedError {
    case adbNotFound
    case serverNotFound
    case noDevice
    case unauthorized(String)
    case commandFailed(String, String)

    var errorDescription: String? {
        switch self {
        case .adbNotFound:
            return "adb was not found. Run scripts/setup.sh or install Android platform-tools."
        case .serverNotFound:
            return "scrcpy-server was not found. Run scripts/setup.sh to download it."
        case .noDevice:
            return "No Android device detected over USB. Enable USB debugging and plug the phone in."
        case .unauthorized(let serial):
            return "Device \(serial) has not authorised this Mac. Tap “Allow” on the phone."
        case .commandFailed(let cmd, let output):
            return "adb \(cmd) failed: \(output)"
        }
    }
}

/// Thin wrapper around the adb binary.
final class ADB {
    let path: String

    init() throws {
        guard let found = ADB.locate() else { throw ADBError.adbNotFound }
        path = found
    }

    /// Locate a bundled or installed adb.
    static func locate() -> String? {
        var candidates: [String] = []
        let env = ProcessInfo.processInfo.environment
        if let override = env["DROIDMIRROR_ADB"] { candidates.append(override) }
        candidates.append(contentsOf: Tools.candidatePaths(for: "adb"))
        candidates += [
            "/usr/local/bin/adb",
            "/opt/homebrew/bin/adb",
            NSHomeDirectory() + "/Library/Android/sdk/platform-tools/adb",
        ]
        for key in ["ANDROID_HOME", "ANDROID_SDK_ROOT"] {
            if let sdk = env[key] { candidates.append(sdk + "/platform-tools/adb") }
        }
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    /// Run an adb command to completion and return combined stdout+stderr.
    @discardableResult
    func run(_ args: [String], serial: String? = nil) throws -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: path)
        var full = args
        if let serial = serial { full = ["-s", serial] + args }
        process.arguments = full
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        try process.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let output = String(decoding: data, as: UTF8.self)
        if process.terminationStatus != 0 {
            throw ADBError.commandFailed(full.joined(separator: " "), output.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return output
    }

    func devices() throws -> [ADBDevice] {
        let out = try run(["devices", "-l"])
        var result: [ADBDevice] = []
        for line in out.split(separator: "\n").dropFirst() {
            let parts = line.split(separator: " ", omittingEmptySubsequences: true).map(String.init)
            guard parts.count >= 2 else { continue }
            let model = parts.first { $0.hasPrefix("model:") }?.dropFirst(6).replacingOccurrences(of: "_", with: " ") ?? ""
            result.append(ADBDevice(serial: parts[0], state: parts[1], model: String(model)))
        }
        return result
    }

    /// Pick the first usable USB device, surfacing authorisation problems.
    func firstDevice() throws -> ADBDevice {
        let list = try devices()
        if let ready = list.first(where: { $0.state == "device" }) { return ready }
        if let pending = list.first(where: { $0.state == "unauthorized" }) { throw ADBError.unauthorized(pending.serial) }
        throw ADBError.noDevice
    }

    func push(local: String, remote: String, serial: String) throws {
        try run(["push", local, remote], serial: serial)
    }

    func forward(localPort: UInt16, abstractSocket: String, serial: String) throws {
        try run(["forward", "tcp:\(localPort)", "localabstract:\(abstractSocket)"], serial: serial)
    }

    func removeForward(localPort: UInt16, serial: String) {
        _ = try? run(["forward", "--remove", "tcp:\(localPort)"], serial: serial)
    }

    /// Start a long-running `adb shell` command. Output lines are reported as they arrive.
    func shell(_ command: String, serial: String, onOutput: @escaping (String) -> Void) throws -> Process {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: path)
        process.arguments = ["-s", serial, "shell", command]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
                return
            }
            let text = String(decoding: data, as: UTF8.self)
            for line in text.split(separator: "\n") where !line.isEmpty {
                onOutput(String(line))
            }
        }
        try process.run()
        return process
    }
}

/// Finds helper binaries either inside the .app bundle or in the repo's Tools/ folder during development.
enum Tools {
    static func candidatePaths(for name: String) -> [String] {
        var paths: [String] = []
        if let res = Bundle.main.resourceURL {
            paths.append(res.appendingPathComponent(name).path)
        }
        if let exe = Bundle.main.executableURL {
            // .build/<config>/DroidMirror  ->  <package>/Tools/<name>
            let packageRoot = exe.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            paths.append(packageRoot.appendingPathComponent("Tools").appendingPathComponent(name).path)
            // .build/<triple>/<config>/DroidMirror
            let deeper = packageRoot.deletingLastPathComponent()
            paths.append(deeper.appendingPathComponent("Tools").appendingPathComponent(name).path)
        }
        paths.append(FileManager.default.currentDirectoryPath + "/Tools/" + name)
        return paths
    }

    static func scrcpyServerPath() -> String? {
        var candidates: [String] = []
        if let override = ProcessInfo.processInfo.environment["DROIDMIRROR_SERVER"] { candidates.append(override) }
        candidates.append(contentsOf: candidatePaths(for: "scrcpy-server"))
        return candidates.first { FileManager.default.fileExists(atPath: $0) }
    }
}
