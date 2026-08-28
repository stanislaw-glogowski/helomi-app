@preconcurrency import AVFAudio
import CoreAudio
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

@Test func startAudioPayloadRoundTripsAndRejectsIrrelevantIndices() throws {
  let request = StartAudioRequest(mode: .duplex, inputIndex: 1, outputIndex: 2)
  let decoded = try WireJSON.decode(
    StartAudioRequest.self,
    from: WireJSON.encode(request)
  )
  try decoded.validate()
  #expect(decoded == request)

  #expect(throws: WireProtocolError.self) {
    try StartAudioRequest(mode: .input, outputIndex: 0).validate()
  }
  #expect(throws: WireProtocolError.self) {
    try StartAudioRequest(mode: .output, inputIndex: 0).validate()
  }
  #expect(throws: WireProtocolError.self) {
    try StartAudioRequest(mode: .duplex, inputIndex: -1).validate()
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

@Test func audioDevicesPacketEncodesListsAndDefaultFlags() throws {
  let packet = AudioDevicesPacket(
    input: [
      AudioDeviceInfo(index: 0, name: "MacBook Microphone", uid: "input-1", isDefault: true)
    ],
    output: [
      AudioDeviceInfo(index: 0, name: "Studio Display", uid: "output-1", isDefault: false)
    ]
  )

  let decoded = try WireJSON.decode(
    AudioDevicesPacket.self,
    from: WireJSON.encode(packet)
  )
  #expect(decoded == packet)
}

@Test func deviceResolverBuildsDirectionalSortedCatalog() throws {
  let resolver = AudioDeviceResolver(hardware: FakeAudioHardware())
  let catalog = try resolver.catalog()

  #expect(catalog.packet.input.map(\.name) == ["Alpha Microphone", "Combo Device"])
  #expect(catalog.packet.output.map(\.name) == ["Beta Speaker", "Combo Device"])
  #expect(catalog.packet.input[0].isDefault)
  #expect(catalog.packet.output[0].isDefault)
  #expect(try catalog.resolve(nil, direction: .input).id == 10)
  #expect(try catalog.resolve(1, direction: .output).id == 30)
  #expect(throws: AudioDeviceError.self) {
    try catalog.resolve(2, direction: .input)
  }
}

@Test func idleControllerReportsStateAndRoomVoiceNoOps() throws {
  let controller = try AudioEngineController(
    writer: WireFrameWriter(handle: .nullDevice),
    roomVoicePath: nil,
    deviceResolver: AudioDeviceResolver(hardware: FakeAudioHardware())
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
    roomVoicePath: url.path,
    deviceResolver: AudioDeviceResolver(hardware: FakeAudioHardware())
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

private struct FakeAudioHardware: AudioHardwareAccess {
  func allDeviceIDs() throws -> [AudioDeviceID] { [30, 20, 10] }

  func defaultDeviceID(for direction: AudioDeviceDirection) throws -> AudioDeviceID? {
    direction == .input ? 10 : 20
  }

  func hasStreams(_ deviceID: AudioDeviceID, direction: AudioDeviceDirection) -> Bool {
    switch direction {
    case .input: deviceID == 10 || deviceID == 30
    case .output: deviceID == 20 || deviceID == 30
    }
  }

  func name(of deviceID: AudioDeviceID) -> String? {
    switch deviceID {
    case 10: "Alpha Microphone"
    case 20: "Beta Speaker"
    case 30: "Combo Device"
    default: nil
    }
  }

  func uid(of deviceID: AudioDeviceID) -> String? { "device-\(deviceID)" }
}
