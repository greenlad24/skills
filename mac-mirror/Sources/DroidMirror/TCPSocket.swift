import Foundation

enum SocketError: LocalizedError {
    case connectFailed(Int32)
    case closed
    case readFailed(Int32)
    case writeFailed(Int32)

    var errorDescription: String? {
        switch self {
        case .connectFailed(let e): return "connect failed: \(String(cString: strerror(e)))"
        case .closed: return "connection closed"
        case .readFailed(let e): return "read failed: \(String(cString: strerror(e)))"
        case .writeFailed(let e): return "write failed: \(String(cString: strerror(e)))"
        }
    }
}

/// Minimal blocking TCP client used for the scrcpy video/audio/control streams.
final class TCPSocket {
    private var fd: Int32 = -1
    private let lock = NSLock()

    var isOpen: Bool { fd >= 0 }

    init(connectTo host: String = "127.0.0.1", port: UInt16) throws {
        let sock = socket(AF_INET, SOCK_STREAM, 0)
        guard sock >= 0 else { throw SocketError.connectFailed(errno) }

        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = port.bigEndian
        addr.sin_addr.s_addr = inet_addr(host)

        let result = withUnsafePointer(to: &addr) { ptr -> Int32 in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                connect(sock, sa, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard result == 0 else {
            let err = errno
            Darwin.close(sock)
            throw SocketError.connectFailed(err)
        }

        var one: Int32 = 1
        setsockopt(sock, IPPROTO_TCP, TCP_NODELAY, &one, socklen_t(MemoryLayout<Int32>.size))
        setsockopt(sock, SOL_SOCKET, SO_NOSIGPIPE, &one, socklen_t(MemoryLayout<Int32>.size))
        fd = sock
    }

    deinit { close() }

    /// Read exactly `count` bytes, blocking until they arrive.
    func readExactly(_ count: Int) throws -> Data {
        var buffer = Data(count: count)
        var offset = 0
        while offset < count {
            let n = buffer.withUnsafeMutableBytes { raw -> Int in
                guard let base = raw.baseAddress else { return -1 }
                return Darwin.read(fd, base.advanced(by: offset), count - offset)
            }
            if n == 0 { throw SocketError.closed }
            if n < 0 {
                if errno == EINTR { continue }
                throw SocketError.readFailed(errno)
            }
            offset += n
        }
        return buffer
    }

    func readUInt8() throws -> UInt8 { try readExactly(1)[0] }

    func readUInt32BE() throws -> UInt32 {
        let d = try readExactly(4)
        return d.withUnsafeBytes { $0.load(as: UInt32.self).bigEndian }
    }

    func readUInt64BE() throws -> UInt64 {
        let d = try readExactly(8)
        return d.withUnsafeBytes { $0.load(as: UInt64.self).bigEndian }
    }

    func write(_ data: Data) throws {
        lock.lock(); defer { lock.unlock() }
        var offset = 0
        while offset < data.count {
            let n = data.withUnsafeBytes { raw -> Int in
                guard let base = raw.baseAddress else { return -1 }
                return Darwin.write(fd, base.advanced(by: offset), data.count - offset)
            }
            if n < 0 {
                if errno == EINTR { continue }
                throw SocketError.writeFailed(errno)
            }
            offset += n
        }
    }

    func close() {
        if fd >= 0 {
            shutdown(fd, SHUT_RDWR)
            Darwin.close(fd)
            fd = -1
        }
    }
}
