import Foundation

public let wireProtocolVersion: UInt16 = 4

public enum WireMessageKind: UInt8, Sendable {
  case play = 1
  case stopPlayback = 2
  case shutdown = 3
  case reservedDuck = 4
  case reservedRestore = 5
  case checkDuplex = 7
  case startAudio = 8
  case stopAudio = 9
  case startRoomVoice = 10
  case stopRoomVoice = 11
  case setPlaybackGain = 12
  case getStatus = 13

  case ready = 128
  case capture = 129
  case playbackFinished = 130
  case playbackStopped = 131
  case playbackGainChanged = 132
  case diagnostic = 133
  case duplexChecked = 135
  case audioStarted = 136
  case audioStopped = 137
  case roomVoiceStartResult = 138
  case roomVoiceStopResult = 139
  case status = 140
  case error = 255
}

public enum PlaybackStatus: UInt8, Sendable {
  case played = 0
  case interrupted = 1
}

public enum AudioMode: String, Codable, CaseIterable, Sendable {
  case input
  case output
  case duplex

  public var hasInput: Bool { self == .input || self == .duplex }
  public var hasOutput: Bool { self == .output || self == .duplex }
}

public enum AudioStatusMode: String, Codable, Sendable {
  case stopped
  case input
  case output
  case duplex

  init(_ mode: AudioMode?) {
    switch mode {
    case .none: self = .stopped
    case .input: self = .input
    case .output: self = .output
    case .duplex: self = .duplex
    }
  }
}

public struct StartAudioRequest: Codable, Equatable, Sendable {
  public let mode: AudioMode
  public let voiceProcessing: Bool?

  public init(
    mode: AudioMode,
    voiceProcessing: Bool? = nil
  ) {
    self.mode = mode
    self.voiceProcessing = voiceProcessing
  }

  public func validate() throws {}
}

public struct StartRoomVoiceRequest: Codable, Equatable, Sendable {
  public let path: String

  public init(path: String) {
    self.path = path
  }

  public func validate() throws {
    if path.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      throw WireProtocolError.invalidPayload("room voice path must not be empty")
    }
  }
}

public struct DuplexCheckRequest: Codable, Equatable, Sendable {
  public init() {}
  public func validate() throws {}
}

public struct PlaybackGainRequest: Codable, Equatable, Sendable {
  public let gain: Float

  public init(gain: Float) {
    self.gain = gain
  }

  public func validate() throws {
    guard gain.isFinite, (0...1).contains(gain) else {
      throw WireProtocolError.invalidPayload(
        "playback gain must be finite and between 0 and 1; got \(gain)"
      )
    }
  }
}

public struct PlaybackGainPacket: Codable, Equatable, Sendable {
  public let gain: Float

  public init(gain: Float) {
    self.gain = gain
  }
}

public struct AudioStartedPacket: Codable, Equatable, Sendable {
  public let mode: AudioMode
  public let duplexInterruptionAvailable: Bool

  public init(
    mode: AudioMode,
    duplexInterruptionAvailable: Bool
  ) {
    self.mode = mode
    self.duplexInterruptionAvailable = duplexInterruptionAvailable
  }
}

public struct DuplexCheckedPacket: Codable, Equatable, Sendable {
  public let available: Bool
  public let reason: String?

  public init(
    available: Bool,
    reason: String? = nil
  ) {
    self.available = available
    self.reason = reason
  }
}

public struct AudioStatusPacket: Codable, Equatable, Sendable {
  public let audioMode: AudioStatusMode
  public let roomVoiceConfigured: Bool
  public let roomVoiceActive: Bool
  public let playbackGain: Float
  public let pendingPlaybackCount: Int
  public let duplexInterruptionAvailable: Bool

  public init(
    audioMode: AudioStatusMode,
    roomVoiceConfigured: Bool,
    roomVoiceActive: Bool,
    playbackGain: Float,
    pendingPlaybackCount: Int,
    duplexInterruptionAvailable: Bool
  ) {
    self.audioMode = audioMode
    self.roomVoiceConfigured = roomVoiceConfigured
    self.roomVoiceActive = roomVoiceActive
    self.playbackGain = playbackGain
    self.pendingPlaybackCount = pendingPlaybackCount
    self.duplexInterruptionAvailable = duplexInterruptionAvailable
  }
}

public enum WireErrorCode: String, Codable, Sendable {
  case invalidCommand = "invalid_command"
  case invalidPayload = "invalid_payload"
  case invalidState = "invalid_state"
  case deviceUnavailable = "device_unavailable"
  case audioConfigurationFailed = "audio_configuration_failed"
  case audioConversionFailed = "audio_conversion_failed"
  case roomVoiceFailed = "room_voice_failed"
  case protocolFailure = "protocol_failure"
}

public struct ErrorPacket: Codable, Equatable, Sendable {
  public let code: WireErrorCode
  public let message: String
  public let fatal: Bool

  public init(code: WireErrorCode, message: String, fatal: Bool) {
    self.code = code
    self.message = message
    self.fatal = fatal
  }
}

public protocol WireCodedError: Error {
  var wireErrorCode: WireErrorCode { get }
}

/// Binary envelope: message kind, request identifier, payload length, payload.
public struct WireFrame: Equatable, Sendable {
  public let kind: WireMessageKind
  public let requestID: UInt32
  public let payload: Data

  public init(kind: WireMessageKind, requestID: UInt32 = 0, payload: Data = Data()) {
    self.kind = kind
    self.requestID = requestID
    self.payload = payload
  }

  public func encode() -> Data {
    var data = Data()
    data.append(kind.rawValue)
    data.appendLittleEndian(requestID)
    data.appendLittleEndian(UInt32(payload.count))
    data.append(payload)
    return data
  }
}

public enum WireProtocolError: Error, Equatable, LocalizedError, WireCodedError {
  case invalidMessageKind(UInt8)
  case invalidPayload(String)
  case unexpectedEndOfStream

  public var wireErrorCode: WireErrorCode {
    switch self {
    case .invalidPayload:
      .invalidPayload
    case .invalidMessageKind, .unexpectedEndOfStream:
      .protocolFailure
    }
  }

  public var errorDescription: String? {
    switch self {
    case .invalidMessageKind(let value):
      "Invalid wire message kind: \(value)"
    case .invalidPayload(let message):
      "Invalid wire payload: \(message)"
    case .unexpectedEndOfStream:
      "Unexpected end of wire stream"
    }
  }
}

public enum WireJSON {
  public static func encode<T: Encodable>(_ value: T) throws -> Data {
    try JSONEncoder().encode(value)
  }

  public static func decode<T: Decodable>(_ type: T.Type, from payload: Data) throws -> T {
    do {
      return try JSONDecoder().decode(type, from: payload)
    } catch {
      throw WireProtocolError.invalidPayload(error.localizedDescription)
    }
  }
}

public final class WireFrameReader {
  private let handle: FileHandle

  public init(handle: FileHandle) {
    self.handle = handle
  }

  public func read() throws -> WireFrame? {
    guard let header = try readExactly(9, allowCleanEOF: true) else {
      return nil
    }

    let rawKind = header[header.startIndex]
    guard let kind = WireMessageKind(rawValue: rawKind) else {
      throw WireProtocolError.invalidMessageKind(rawKind)
    }

    let requestID = header.readLittleEndian(UInt32.self, at: 1)
    let payloadSize = header.readLittleEndian(UInt32.self, at: 5)
    let payload = try readExactly(Int(payloadSize), allowCleanEOF: false) ?? Data()
    return WireFrame(kind: kind, requestID: requestID, payload: payload)
  }

  private func readExactly(_ count: Int, allowCleanEOF: Bool) throws -> Data? {
    if count == 0 { return Data() }

    var data = Data()
    while data.count < count {
      guard let chunk = try handle.read(upToCount: count - data.count), !chunk.isEmpty else {
        if allowCleanEOF && data.isEmpty { return nil }
        throw WireProtocolError.unexpectedEndOfStream
      }
      data.append(chunk)
    }
    return data
  }
}

public final class WireFrameWriter: @unchecked Sendable {
  private let handle: FileHandle
  private let queue = DispatchQueue(label: "helomi.audio.wire.output")

  public init(handle: FileHandle) {
    self.handle = handle
  }

  public func send(_ frame: WireFrame) {
    let encoded = frame.encode()
    queue.async { [handle] in
      do {
        try handle.write(contentsOf: encoded)
      } catch {
        // The peer owns process lifecycle; a closed pipe ends the helper.
      }
    }
  }

  public func flush() {
    queue.sync {}
  }
}

/// Interleaved Float32 audio carried by PLAY and CAPTURE messages.
public struct AudioPacket: Equatable, Sendable {
  public let sampleRate: UInt32
  public let channels: UInt16
  public let samples: Data

  public init(sampleRate: UInt32, channels: UInt16, samples: Data) throws {
    guard sampleRate > 0 else {
      throw WireProtocolError.invalidPayload("sample rate must be positive; got \(sampleRate)")
    }
    guard channels > 0 else {
      throw WireProtocolError.invalidPayload("channel count must be positive; got \(channels)")
    }
    guard samples.count.isMultiple(of: MemoryLayout<Float>.size * Int(channels)) else {
      throw WireProtocolError.invalidPayload(
        "sample data is not frame-aligned: \(samples.count) bytes for \(channels) channels"
      )
    }
    self.sampleRate = sampleRate
    self.channels = channels
    self.samples = samples
  }

  public init(payload: Data) throws {
    guard payload.count >= 6 else {
      throw WireProtocolError.invalidPayload(
        "audio header is truncated: expected at least 6 bytes, got \(payload.count)"
      )
    }
    try self.init(
      sampleRate: payload.readLittleEndian(UInt32.self, at: 0),
      channels: payload.readLittleEndian(UInt16.self, at: 4),
      samples: payload.subdata(in: 6..<payload.count)
    )
  }

  public var frameCount: Int {
    samples.count / (MemoryLayout<Float>.size * Int(channels))
  }

  public func encode() -> Data {
    var data = Data()
    data.appendLittleEndian(sampleRate)
    data.appendLittleEndian(channels)
    data.append(samples)
    return data
  }
}

extension Data {
  mutating func appendLittleEndian<T: FixedWidthInteger>(_ value: T) {
    var littleEndian = value.littleEndian
    Swift.withUnsafeBytes(of: &littleEndian) { append(contentsOf: $0) }
  }

  func readLittleEndian<T: FixedWidthInteger>(_ type: T.Type, at offset: Int) -> T {
    let size = MemoryLayout<T>.size
    return subdata(in: offset..<(offset + size)).withUnsafeBytes {
      T(littleEndian: $0.loadUnaligned(as: T.self))
    }
  }
}
