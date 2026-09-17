import Foundation
import CoreMedia

enum H264Error: LocalizedError {
    case missingParameterSets
    case formatDescription(OSStatus)
    case blockBuffer(OSStatus)
    case sampleBuffer(OSStatus)

    var errorDescription: String? {
        switch self {
        case .missingParameterSets: return "H.264 config packet did not contain SPS/PPS"
        case .formatDescription(let s): return "CMVideoFormatDescription failed (\(s))"
        case .blockBuffer(let s): return "CMBlockBuffer failed (\(s))"
        case .sampleBuffer(let s): return "CMSampleBuffer failed (\(s))"
        }
    }
}

/// Converts the Annex-B H.264 stream produced by the scrcpy server into
/// CMSampleBuffers that AVSampleBufferDisplayLayer can decode with VideoToolbox.
final class H264Assembler {
    private(set) var formatDescription: CMVideoFormatDescription?
    private var sps: Data?
    private var pps: Data?

    /// Dimensions of the stream as declared by the current SPS (after cropping).
    var dimensions: CMVideoDimensions? {
        guard let fd = formatDescription else { return nil }
        return CMVideoFormatDescriptionGetDimensions(fd)
    }

    /// Split an Annex-B byte stream into NAL units (start codes removed).
    static func nalUnits(in data: Data) -> [Data] {
        var units: [Data] = []
        let bytes = [UInt8](data)
        let count = bytes.count
        var i = 0
        var start = -1

        while i + 2 < count {
            if bytes[i] == 0 && bytes[i + 1] == 0 && bytes[i + 2] == 1 {
                if start >= 0 {
                    // Trailing zero of a 4-byte start code belongs to the code, not the NALU.
                    var end = i
                    if end > start && bytes[end - 1] == 0 { end -= 1 }
                    if end > start { units.append(Data(bytes[start..<end])) }
                }
                i += 3
                start = i
                continue
            }
            i += 1
        }
        if start >= 0 && start < count {
            units.append(Data(bytes[start..<count]))
        }
        return units
    }

    /// Feed a config packet (SPS/PPS). Returns true if the format description changed.
    @discardableResult
    func handleConfig(_ data: Data) throws -> Bool {
        var changed = false
        for nalu in H264Assembler.nalUnits(in: data) {
            guard let first = nalu.first else { continue }
            switch first & 0x1F {
            case 7:
                if sps != nalu { sps = nalu; changed = true }
            case 8:
                if pps != nalu { pps = nalu; changed = true }
            default:
                break
            }
        }
        if changed || formatDescription == nil {
            try rebuildFormatDescription()
            return true
        }
        return false
    }

    private func rebuildFormatDescription() throws {
        guard let sps = sps, let pps = pps else { throw H264Error.missingParameterSets }
        var fd: CMVideoFormatDescription?
        let status: OSStatus = sps.withUnsafeBytes { spsRaw -> OSStatus in
            pps.withUnsafeBytes { ppsRaw -> OSStatus in
                let pointers: [UnsafePointer<UInt8>] = [
                    spsRaw.bindMemory(to: UInt8.self).baseAddress!,
                    ppsRaw.bindMemory(to: UInt8.self).baseAddress!,
                ]
                let sizes: [Int] = [sps.count, pps.count]
                return CMVideoFormatDescriptionCreateFromH264ParameterSets(
                    allocator: kCFAllocatorDefault,
                    parameterSetCount: 2,
                    parameterSetPointers: pointers,
                    parameterSetSizes: sizes,
                    nalUnitHeaderLength: 4,
                    formatDescriptionOut: &fd)
            }
        }
        guard status == noErr, let result = fd else { throw H264Error.formatDescription(status) }
        formatDescription = result
    }

    /// Build a sample buffer for one access unit. Returns nil when the frame carried no slice data.
    /// If the frame embeds a new SPS/PPS the format description is updated first and
    /// `formatChanged` is set.
    func makeSampleBuffer(frame: Data, pts: UInt64, formatChanged: inout Bool) throws -> CMSampleBuffer? {
        var avcc = Data()
        avcc.reserveCapacity(frame.count + 16)
        var paramChanged = false

        for nalu in H264Assembler.nalUnits(in: frame) {
            guard let first = nalu.first else { continue }
            let type = first & 0x1F
            switch type {
            case 7:
                if sps != nalu { sps = nalu; paramChanged = true }
                continue
            case 8:
                if pps != nalu { pps = nalu; paramChanged = true }
                continue
            case 9, 12:
                // Access unit delimiter / filler: not needed by VideoToolbox.
                continue
            default:
                break
            }
            var len = UInt32(nalu.count).bigEndian
            avcc.append(Data(bytes: &len, count: 4))
            avcc.append(nalu)
        }

        if paramChanged || formatDescription == nil {
            try rebuildFormatDescription()
            formatChanged = true
        }
        guard let fd = formatDescription, !avcc.isEmpty else { return nil }

        var blockBuffer: CMBlockBuffer?
        let length = avcc.count
        var status = CMBlockBufferCreateWithMemoryBlock(
            allocator: kCFAllocatorDefault,
            memoryBlock: nil,
            blockLength: length,
            blockAllocator: kCFAllocatorDefault,
            customBlockSource: nil,
            offsetToData: 0,
            dataLength: length,
            flags: 0,
            blockBufferOut: &blockBuffer)
        guard status == kCMBlockBufferNoErr, let bb = blockBuffer else { throw H264Error.blockBuffer(status) }

        status = avcc.withUnsafeBytes { raw in
            CMBlockBufferReplaceDataBytes(with: raw.baseAddress!, blockBuffer: bb, offsetIntoDestination: 0, dataLength: length)
        }
        guard status == kCMBlockBufferNoErr else { throw H264Error.blockBuffer(status) }

        // scrcpy timestamps are microseconds; the display layer still shows each frame immediately.
        let time = CMTime(value: CMTimeValue(pts & 0x3FFF_FFFF_FFFF_FFFF), timescale: 1_000_000)
        var timing = CMSampleTimingInfo(duration: .invalid, presentationTimeStamp: time, decodeTimeStamp: .invalid)
        var sampleSize = length
        var sampleBuffer: CMSampleBuffer?
        status = CMSampleBufferCreateReady(
            allocator: kCFAllocatorDefault,
            dataBuffer: bb,
            formatDescription: fd,
            sampleCount: 1,
            sampleTimingEntryCount: 1,
            sampleTimingArray: &timing,
            sampleSizeEntryCount: 1,
            sampleSizeArray: &sampleSize,
            sampleBufferOut: &sampleBuffer)
        guard status == noErr, let sb = sampleBuffer else { throw H264Error.sampleBuffer(status) }

        // Render as soon as it is decoded: we want the lowest possible latency, not smooth playback.
        if let attachments = CMSampleBufferGetSampleAttachmentsArray(sb, createIfNecessary: true),
           CFArrayGetCount(attachments) > 0 {
            let dict = unsafeBitCast(CFArrayGetValueAtIndex(attachments, 0), to: CFMutableDictionary.self)
            CFDictionarySetValue(dict,
                                 Unmanaged.passUnretained(kCMSampleAttachmentKey_DisplayImmediately).toOpaque(),
                                 Unmanaged.passUnretained(kCFBooleanTrue).toOpaque())
        }
        return sb
    }
}
