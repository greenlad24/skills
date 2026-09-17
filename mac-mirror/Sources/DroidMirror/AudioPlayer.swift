import Foundation
import AVFoundation

/// Plays the raw 48 kHz stereo 16-bit PCM stream from the scrcpy audio socket.
/// Buffers that fall too far behind real time are dropped so audio stays in step with video.
final class AudioPlayer {
    static let sampleRate: Double = 48_000
    static let channels: AVAudioChannelCount = 2

    /// Maximum amount of queued-but-unplayed audio before we start dropping packets.
    var maxQueuedSeconds: Double = 0.12

    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private let format: AVAudioFormat
    private let queue = DispatchQueue(label: "droidmirror.audio")
    private var scheduledFrames: AVAudioFramePosition = 0
    private var started = false

    init() {
        format = AVAudioFormat(standardFormatWithSampleRate: AudioPlayer.sampleRate, channels: AudioPlayer.channels)!
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: format)
    }

    func start() {
        queue.async {
            guard !self.started else { return }
            do {
                try self.engine.start()
                self.player.play()
                self.started = true
            } catch {
                NSLog("AudioPlayer: engine failed to start: \(error)")
            }
        }
    }

    func stop() {
        queue.async {
            guard self.started else { return }
            self.player.stop()
            self.engine.stop()
            self.started = false
            self.scheduledFrames = 0
        }
    }

    /// Enqueue interleaved signed 16-bit little-endian stereo samples.
    func enqueue(pcm: Data) {
        queue.async { self.schedule(pcm) }
    }

    private func schedule(_ pcm: Data) {
        guard started else { return }
        let bytesPerFrame = Int(AudioPlayer.channels) * 2
        let frameCount = pcm.count / bytesPerFrame
        guard frameCount > 0 else { return }

        // Drop packets when we are buffering more than maxQueuedSeconds ahead of the playhead.
        if let nodeTime = player.lastRenderTime, let playerTime = player.playerTime(forNodeTime: nodeTime) {
            let queued = scheduledFrames - playerTime.sampleTime
            if Double(queued) / AudioPlayer.sampleRate > maxQueuedSeconds {
                return
            }
        }

        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frameCount)),
              let channelData = buffer.floatChannelData else { return }
        buffer.frameLength = AVAudioFrameCount(frameCount)

        pcm.withUnsafeBytes { raw in
            let samples = raw.bindMemory(to: Int16.self)
            let left = channelData[0]
            let right = channelData[1]
            for i in 0..<frameCount {
                left[i] = Float(Int16(littleEndian: samples[i * 2])) / 32768.0
                right[i] = Float(Int16(littleEndian: samples[i * 2 + 1])) / 32768.0
            }
        }

        scheduledFrames += AVAudioFramePosition(frameCount)
        player.scheduleBuffer(buffer, completionHandler: nil)
    }
}
