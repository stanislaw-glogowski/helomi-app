@preconcurrency import AVFAudio
import Foundation
import Testing

@testable import HelomiAudioCore

@Test func protocolVersionAndMessageIdentifiersAreStable() {
  #expect(wireProtocolVersion == 4)
  #expect(WireMessageKind.play.rawValue == 1)
  #expect(WireMessageKind.stopPlayback.rawValue == 2)
  #expect(WireMessageKind.reservedDuck.rawValue == 4)
  #expect(WireMessageKind.reservedRestore.rawValue == 5)
  #expect(WireMessageKind.getStatus.rawValue == 13)
  #expect(WireMessageKind.ready.rawValue == 128)
  #expect(WireMessageKind.status.rawValue == 140)
  #expect(WireMessageKind.error.rawValue == 255)
}

@Test func wireFrameEncodesHeaderAndPayload() throws {
  let frame = WireFrame(kind: .play, requestID: 42, payload: Data([1, 2, 3]))
  let encoded = frame.encode()

  #expect(encoded.count == 12)
  #expect(encoded[0] == WireMessageKind.play.rawValue)
  #expect(encoded.readLittleEndian(UInt32.self, at: 1) == 42)
  #expect(encoded.readLittleEndian(UInt32.self, at: 5) == 3)
  #expect(encoded.suffix(3) == Data([1, 2, 3]))
}

@Test func audioPacketRoundTripsAndValidatesAlignment() throws {
  let samples: [Float] = [0.25, -0.5, 0.75, -1]
  let packet = try AudioPacket(
    sampleRate: 16_000,
    channels: 2,
    samples: samples.withUnsafeBytes { Data($0) }
  )
  let decoded = try AudioPacket(payload: packet.encode())

  #expect(decoded == packet)
  #expect(decoded.frameCount == 2)
  #expect(throws: WireProtocolError.self) {
    try AudioPacket(sampleRate: 16_000, channels: 2, samples: Data([0]))
  }
}

@Test func startAudioPayloadRoundTrips() throws {
  let request = StartAudioRequest(mode: .duplex, voiceProcessing: true)
  let decoded = try WireJSON.decode(
    StartAudioRequest.self,
    from: WireJSON.encode(request)
  )
  try decoded.validate()
  #expect(decoded == request)

  let requestWithVP = StartAudioRequest(mode: .duplex, voiceProcessing: false)
  let decodedWithVP = try WireJSON.decode(
    StartAudioRequest.self,
    from: WireJSON.encode(requestWithVP)
  )
  try decodedWithVP.validate()
  #expect(decodedWithVP == requestWithVP)
}

@Test func startRoomVoicePayloadRoundTripsAndValidatesPath() throws {
  let request = StartRoomVoiceRequest(path: "/path/to/room.wav")
  let decoded = try WireJSON.decode(
    StartRoomVoiceRequest.self,
    from: WireJSON.encode(request)
  )
  try decoded.validate()
  #expect(decoded == request)

  #expect(throws: WireProtocolError.self) {
    try StartRoomVoiceRequest(path: "").validate()
  }
  #expect(throws: WireProtocolError.self) {
    try StartRoomVoiceRequest(path: "   ").validate()
  }
}

@Test func playbackGainAcceptsOnlyFiniteUnitRange() throws {
  try PlaybackGainRequest(gain: 0).validate()
  try PlaybackGainRequest(gain: 0.5).validate()
  try PlaybackGainRequest(gain: 1).validate()
  #expect(throws: WireProtocolError.self) {
    try PlaybackGainRequest(gain: -0.01).validate()
  }
  #expect(throws: WireProtocolError.self) {
    try PlaybackGainRequest(gain: 1.01).validate()
  }
  #expect(throws: WireProtocolError.self) {
    try PlaybackGainRequest(gain: .nan).validate()
  }
}

@Test func idleControllerReportsStateAndRoomVoiceNoOps() throws {
  let controller = try AudioEngineController(
    writer: WireFrameWriter(handle: .nullDevice),
    roomVoicePath: nil
  )

  #expect(controller.status().audioMode == .stopped)
  #expect(!controller.status().roomVoiceConfigured)
  #expect(try !controller.startRoomVoice())
  #expect(!controller.stopRoomVoice())
  #expect(try controller.setPlaybackGain(PlaybackGainRequest(gain: 0.25)).gain == 0.25)
  #expect(controller.status().playbackGain == 0.25)
  controller.stopAudio()
  #expect(controller.status().audioMode == .stopped)
}

@Test func invalidRoomVoicePathFailsBeforeControllerIsReady() {
  #expect(throws: AudioEngineError.self) {
    try AudioEngineController(
      writer: WireFrameWriter(handle: .nullDevice),
      roomVoicePath: "/definitely/missing/helomi-room-voice.wav"
    )
  }
}

@Test func validRoomVoiceIsConfiguredButStartsOnlyWithOutput() throws {
  let url = FileManager.default.temporaryDirectory
    .appendingPathComponent("helomi-room-voice-\(UUID().uuidString).caf")
  defer { try? FileManager.default.removeItem(at: url) }
  let format = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 1)!
  do {
    let file = try AVAudioFile(forWriting: url, settings: format.settings)
    let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 16)!
    buffer.frameLength = 16
    try file.write(from: buffer)
  }

  let controller = try AudioEngineController(
    writer: WireFrameWriter(handle: .nullDevice),
    roomVoicePath: url.path
  )
  #expect(controller.status().roomVoiceConfigured)
  #expect(try !controller.startRoomVoice())
  #expect(!controller.status().roomVoiceActive)
}

@Test func errorsExposeStableWireCodes() {
  #expect(AudioEngineError.invalidState("stopped").wireErrorCode == .invalidState)
  #expect(WireProtocolError.invalidPayload("bad packet").wireErrorCode == .invalidPayload)
  let packet = ErrorPacket(code: .deviceUnavailable, message: "missing", fatal: false)
  #expect(packet.code.rawValue == "device_unavailable")
}

@Test func convertAudioBufferHandlesFormatConversionSuccessfully() throws {
  let sourceFormat = AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1)!
  let targetFormat = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 2)!

  let sourceBuffer = AVAudioPCMBuffer(pcmFormat: sourceFormat, frameCapacity: 160)!
  sourceBuffer.frameLength = 160
  if let channelData = sourceBuffer.floatChannelData {
    for i in 0..<160 {
      channelData[0][i] = Float(i) / 160.0
    }
  }

  let converted = try AudioEngineController.convert(sourceBuffer, to: targetFormat)
  #expect(converted.format == targetFormat)
  #expect(converted.frameLength > 0)
}
