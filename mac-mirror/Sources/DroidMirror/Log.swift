import Foundation

/// Appends diagnostic lines to ~/Library/Logs/DroidMirror.log and keeps the most recent
/// server output in memory so errors can be explained to the user.
enum Log {
    static let fileURL: URL = {
        let logs = FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask)[0].appendingPathComponent("Logs")
        try? FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
        return logs.appendingPathComponent("DroidMirror.log")
    }()

    private static let queue = DispatchQueue(label: "droidmirror.log")
    private static var recentServerLines: [String] = []
    private static let formatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss.SSS"
        return f
    }()

    static func write(_ message: String) {
        let line = "\(formatter.string(from: Date())) \(message)\n"
        NSLog("%@", message)
        queue.async {
            if let handle = try? FileHandle(forWritingTo: fileURL) {
                handle.seekToEndOfFile()
                handle.write(line.data(using: .utf8)!)
                handle.closeFile()
            } else {
                try? line.write(to: fileURL, atomically: true, encoding: .utf8)
            }
        }
    }

    static func server(_ line: String) {
        write("[server] \(line)")
        queue.async {
            recentServerLines.append(line)
            if recentServerLines.count > 30 { recentServerLines.removeFirst() }
        }
    }

    static func clearServerLines() {
        queue.async { recentServerLines.removeAll() }
    }

    /// Most recent server output, newest last.
    static func lastServerLines(_ count: Int = 5) -> [String] {
        queue.sync { Array(recentServerLines.suffix(count)) }
    }

    static func contents() -> String {
        (try? String(contentsOf: fileURL, encoding: .utf8)) ?? ""
    }
}
