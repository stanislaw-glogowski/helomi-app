import Darwin
import Foundation
import HelomiAudioCore

private enum CommandLineError: Error, LocalizedError, WireCodedError {
  case invalidArguments(String)
  case invalidCommand(String)

  var wireErrorCode: WireErrorCode {
    switch self {
    case .invalidArguments: .invalidPayload
    case .invalidCommand: .invalidCommand
    }
  }

  var errorDescription: String? {
    switch self {
    case .invalidArguments(let message), .invalidCommand(let message): message
    }
  }
}

private func roomVoicePath(arguments: [String]) throws -> String? {
  let values = Array(arguments.dropFirst())
  guard !values.isEmpty else { return nil }
  guard values.count == 2, values[0] == "--room-voice", !values[1].isEmpty else {
    throw CommandLineError.invalidArguments("usage: avfaudio [--room-voice PATH]")
  }
  return values[1]
}

private func requireEmptyPayload(_ frame: WireFrame) throws {
  guard frame.payload.isEmpty else {
    throw WireProtocolError.invalidPayload(
      "\(frame.kind) does not accept a payload; got \(frame.payload.count) bytes"
    )
  }
}

private func errorPacket(for error: Error, fatal: Bool) -> ErrorPacket {
  let code =
    (error as? any WireCodedError)?.wireErrorCode
    ?? (fatal ? .protocolFailure : .audioConfigurationFailed)
  return ErrorPacket(code: code, message: error.localizedDescription, fatal: fatal)
}

private func sendJSON<T: Encodable>(
  _ value: T,
  kind: WireMessageKind,
  requestID: UInt32,
  writer: WireFrameWriter
) throws {
  writer.send(
    WireFrame(kind: kind, requestID: requestID, payload: try WireJSON.encode(value))
  )
}

let reader = WireFrameReader(handle: .standardInput)
let writer = WireFrameWriter(handle: .standardOutput)
var controller: AudioEngineController?

do {
  controller = try AudioEngineController(
    writer: writer,
    roomVoicePath: roomVoicePath(arguments: CommandLine.arguments)
  )

  var readyPayload = Data()
  withUnsafeBytes(of: wireProtocolVersion.littleEndian) {
    readyPayload.append(contentsOf: $0)
  }
  writer.send(WireFrame(kind: .ready, payload: readyPayload))

  commandLoop: while let frame = try reader.read() {
    guard let controller else { break }
    var shouldShutdown = false

    do {
      switch frame.kind {
      case .play:
        try controller.play(
          requestID: frame.requestID,
          packet: AudioPacket(payload: frame.payload)
        )
      case .stopPlayback:
        try requireEmptyPayload(frame)
        controller.stopPlayback()
        writer.send(WireFrame(kind: .playbackStopped, requestID: frame.requestID))
      case .getDevices:
        try requireEmptyPayload(frame)
        try sendJSON(
          controller.devices(),
          kind: .devices,
          requestID: frame.requestID,
          writer: writer
        )
      case .checkDuplex:
        let request =
          frame.payload.isEmpty
          ? DuplexCheckRequest()
          : try WireJSON.decode(DuplexCheckRequest.self, from: frame.payload)
        try sendJSON(
          controller.checkDuplex(request),
          kind: .duplexChecked,
          requestID: frame.requestID,
          writer: writer
        )
      case .startAudio:
        let request = try WireJSON.decode(StartAudioRequest.self, from: frame.payload)
        try sendJSON(
          controller.startAudio(request),
          kind: .audioStarted,
          requestID: frame.requestID,
          writer: writer
        )
      case .stopAudio:
        try requireEmptyPayload(frame)
        controller.stopAudio()
        writer.send(WireFrame(kind: .audioStopped, requestID: frame.requestID))
      case .startRoomVoice:
        try requireEmptyPayload(frame)
        let changed = try controller.startRoomVoice()
        writer.send(
          WireFrame(
            kind: .roomVoiceStartResult,
            requestID: frame.requestID,
            payload: Data([changed ? 1 : 0])
          )
        )
      case .stopRoomVoice:
        try requireEmptyPayload(frame)
        let changed = controller.stopRoomVoice()
        writer.send(
          WireFrame(
            kind: .roomVoiceStopResult,
            requestID: frame.requestID,
            payload: Data([changed ? 1 : 0])
          )
        )
      case .setPlaybackGain:
        let request = try WireJSON.decode(PlaybackGainRequest.self, from: frame.payload)
        try sendJSON(
          controller.setPlaybackGain(request),
          kind: .playbackGainChanged,
          requestID: frame.requestID,
          writer: writer
        )
      case .getStatus:
        try requireEmptyPayload(frame)
        try sendJSON(
          controller.status(),
          kind: .status,
          requestID: frame.requestID,
          writer: writer
        )
      case .shutdown:
        try requireEmptyPayload(frame)
        shouldShutdown = true
      case .reservedDuck, .reservedRestore:
        throw CommandLineError.invalidCommand(
          "message kind \(frame.kind.rawValue) is reserved in protocol v4"
        )
      case .ready, .capture, .playbackFinished, .playbackStopped,
        .playbackGainChanged, .diagnostic, .devices, .duplexChecked, .audioStarted,
        .audioStopped, .roomVoiceStartResult, .roomVoiceStopResult, .status, .error:
        throw CommandLineError.invalidCommand(
          "unexpected client command kind: \(frame.kind.rawValue)"
        )
      }
    } catch {
      try sendJSON(
        errorPacket(for: error, fatal: false),
        kind: .error,
        requestID: frame.requestID,
        writer: writer
      )
    }
    if shouldShutdown { break commandLoop }
  }

  controller?.shutdown()
  writer.flush()
} catch {
  if let payload = try? WireJSON.encode(errorPacket(for: error, fatal: true)) {
    writer.send(WireFrame(kind: .error, requestID: 0, payload: payload))
  }
  controller?.shutdown()
  writer.flush()
  exit(EXIT_FAILURE)
}
