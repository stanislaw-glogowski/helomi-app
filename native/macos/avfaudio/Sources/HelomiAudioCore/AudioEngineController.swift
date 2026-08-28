@preconcurrency import AVFAudio
import Foundation

private let captureChannels: UInt16 = 1
private let playbackSampleRate = 48_000.0
private let playbackChannels: AVAudioChannelCount = 1
private let playbackGainRampDuration: TimeInterval = 0.1
private let playbackGainRampSteps = 10
private let duplexProbeTimeout: TimeInterval = 1

public enum AudioEngineError: Error, LocalizedError, WireCodedError {
  case invalidState(String)
  case configuration(String)
  case conversion(String)
  case roomVoice(String)

  public var wireErrorCode: WireErrorCode {
    switch self {
    case .invalidState: .invalidState
    case .configuration: .audioConfigurationFailed
    case .conversion: .audioConversionFailed
    case .roomVoice: .roomVoiceFailed
    }
  }

  public var errorDescription: String? {
    switch self {
    case .invalidState(let message):
      "Invalid audio state: \(message)"
    case .configuration(let message):
      "Audio engine configuration failed: \(message)"
    case .conversion(let message):
      "Audio conversion failed: \(message)"
    case .roomVoice(let message):
      "Room voice failed: \(message)"
    }
  }
}

private final class AudioBufferBox: @unchecked Sendable {
  let buffer: AVAudioPCMBuffer

  init(_ buffer: AVAudioPCMBuffer) {
    self.buffer = buffer
  }
}

private final class AudioBufferSupplier: @unchecked Sendable {
  private var buffer: AVAudioPCMBuffer?
  private let exhaustedStatus: AVAudioConverterInputStatus

  init(buffer: AVAudioPCMBuffer, exhaustedStatus: AVAudioConverterInputStatus) {
    self.buffer = buffer
    self.exhaustedStatus = exhaustedStatus
  }

  func next(status: UnsafeMutablePointer<AVAudioConverterInputStatus>) -> AVAudioBuffer? {
    guard let buffer else {
      status.pointee = exhaustedStatus
      return nil
    }
    self.buffer = nil
    status.pointee = .haveData
    return buffer
  }
}

/// Owns one explicitly started AVAudioEngine session and its protocol-visible state.
public final class AudioEngineController: @unchecked Sendable {
  private let writer: WireFrameWriter
  private let deviceResolver: AudioDeviceResolver
  private let roomVoiceURL: URL?
  private let captureQueue = DispatchQueue(label: "helomi.audio.capture")
  private let volumeQueue = DispatchQueue(label: "helomi.audio.volume")
  private let playbackLock = NSLock()

  private var engine: AVAudioEngine?
  private var playbackPlayer: AVAudioPlayerNode?
  private var roomVoicePlayer: AVAudioPlayerNode?
  private var roomVoiceBuffer: AVAudioPCMBuffer?
  private var playbackFormat: AVAudioFormat?
  private var mode: AudioMode?
  private var selectedInput: ResolvedAudioDevice?
  private var selectedOutput: ResolvedAudioDevice?
  private var roomVoiceActive = false
  private var playbackGain: Float = 1
  private var pendingPlayback: Set<UInt32> = []
  private var captureDiagnosticSent = false
  private var captureDiagnosticSampleCount = 0
  private var captureDiagnosticSquaredSum = 0.0
  private var captureDiagnosticPeak = Float.zero

  public convenience init(
    writer: WireFrameWriter,
    roomVoicePath: String? = nil
  ) throws {
    try self.init(
      writer: writer,
      roomVoicePath: roomVoicePath,
      deviceResolver: AudioDeviceResolver()
    )
  }

  init(
    writer: WireFrameWriter,
    roomVoicePath: String?,
    deviceResolver: AudioDeviceResolver
  ) throws {
    self.writer = writer
    self.deviceResolver = deviceResolver
    self.roomVoiceURL = try Self.validateRoomVoice(path: roomVoicePath)
  }

  public func devices() throws -> AudioDevicesPacket {
    try deviceResolver.catalog().packet
  }

  public func startAudio(_ request: StartAudioRequest) throws -> AudioStartedPacket {
    try request.validate()
    guard mode == nil else {
      throw AudioEngineError.invalidState("audio is already started; stop it before reconfiguring")
    }

    let catalog = try deviceResolver.catalog()
    let input =
      request.mode.hasInput
      ? try catalog.resolve(request.inputIndex, direction: .input) : nil
    let output =
      request.mode.hasOutput
      ? try catalog.resolve(request.outputIndex, direction: .output) : nil
    let newEngine = AVAudioEngine()
    let newPlaybackPlayer = request.mode.hasOutput ? AVAudioPlayerNode() : nil
    let newRoomVoicePlayer = request.mode.hasOutput ? AVAudioPlayerNode() : nil
    let newPlaybackFormat = request.mode.hasOutput ? try Self.makePlaybackFormat() : nil
    var tapInstalled = false

    do {
      let inputNode = request.mode.hasInput ? newEngine.inputNode : nil
      let outputNode = request.mode.hasOutput ? newEngine.outputNode : nil

      if request.mode == .duplex, let inputNode {
        try inputNode.setVoiceProcessingEnabled(true)
        guard inputNode.isVoiceProcessingEnabled else {
          throw AudioEngineError.configuration("voice processing did not become active")
        }
      }

      if let input, let inputNode {
        try AudioDeviceResolver.select(input, on: inputNode.audioUnit)
      }
      if let output, let outputNode {
        try AudioDeviceResolver.select(output, on: outputNode.audioUnit)
      }

      if let newPlaybackPlayer, let newRoomVoicePlayer, let newPlaybackFormat {
        newEngine.attach(newPlaybackPlayer)
        newEngine.attach(newRoomVoicePlayer)
        newEngine.connect(
          newPlaybackPlayer,
          to: newEngine.mainMixerNode,
          format: newPlaybackFormat
        )
        newEngine.connect(
          newRoomVoicePlayer,
          to: newEngine.mainMixerNode,
          format: newPlaybackFormat
        )
        newPlaybackPlayer.volume = playbackGain
      }

      if let inputNode {
        inputNode.installTap(onBus: 0, bufferSize: 1_024, format: nil) {
          [weak self] buffer, _ in
          self?.receiveCapture(buffer)
        }
        tapInstalled = true
      }

      newEngine.prepare()
      try newEngine.start()
      if request.mode == .duplex, let inputNode {
        inputNode.isVoiceProcessingInputMuted = false
        inputNode.isVoiceProcessingBypassed = false
      }

      engine = newEngine
      playbackPlayer = newPlaybackPlayer
      roomVoicePlayer = newRoomVoicePlayer
      playbackFormat = newPlaybackFormat
      mode = request.mode
      selectedInput = input
      selectedOutput = output
      resetCaptureDiagnostic()

      sendDiagnostic(
        "audio_started mode=\(request.mode.rawValue), "
          + "voice_processing=\(request.mode == .duplex)"
      )
      return AudioStartedPacket(
        mode: request.mode,
        input: input?.info,
        output: output?.info,
        duplexInterruptionAvailable: request.mode == .duplex
      )
    } catch {
      if tapInstalled {
        newEngine.inputNode.removeTap(onBus: 0)
      }
      newPlaybackPlayer?.stop()
      newRoomVoicePlayer?.stop()
      newEngine.stop()
      throw error
    }
  }

  public func stopAudio() {
    guard let activeMode = mode else { return }
    stopRoomVoice()
    stopPlayback()
    if activeMode.hasInput {
      engine?.inputNode.removeTap(onBus: 0)
    }
    playbackPlayer?.stop()
    roomVoicePlayer?.stop()
    engine?.stop()
    engine = nil
    playbackPlayer = nil
    roomVoicePlayer = nil
    roomVoiceBuffer = nil
    playbackFormat = nil
    selectedInput = nil
    selectedOutput = nil
    mode = nil
  }

  public func play(requestID: UInt32, packet: AudioPacket) throws {
    guard mode?.hasOutput == true, let playbackPlayer, let playbackFormat else {
      throw AudioEngineError.invalidState("PLAY requires active output audio")
    }
    let input = try makeBuffer(packet: packet)
    let output = try convert(input, to: playbackFormat)

    playbackLock.withLock { _ = pendingPlayback.insert(requestID) }
    playbackPlayer.scheduleBuffer(output, completionCallbackType: .dataPlayedBack) {
      [weak self] _ in
      self?.finishPlayback(requestID: requestID)
    }
    if !playbackPlayer.isPlaying { playbackPlayer.play() }
  }

  public func stopPlayback() {
    let requestIDs = playbackLock.withLock {
      let values = pendingPlayback
      pendingPlayback.removeAll()
      return values
    }
    playbackPlayer?.stop()
    for requestID in requestIDs {
      writer.send(
        WireFrame(
          kind: .playbackFinished,
          requestID: requestID,
          payload: Data([PlaybackStatus.interrupted.rawValue])
        )
      )
    }
  }

  @discardableResult
  public func startRoomVoice() throws -> Bool {
    guard let roomVoiceURL, mode?.hasOutput == true,
      let roomVoicePlayer, let playbackFormat, !roomVoiceActive
    else {
      return false
    }

    let file: AVAudioFile
    do {
      file = try AVAudioFile(forReading: roomVoiceURL)
    } catch {
      throw AudioEngineError.roomVoice(error.localizedDescription)
    }
    guard file.length > 0, file.length <= Int64(UInt32.max) else {
      throw AudioEngineError.roomVoice("file must contain between 1 and \(UInt32.max) frames")
    }
    guard
      let source = AVAudioPCMBuffer(
        pcmFormat: file.processingFormat,
        frameCapacity: AVAudioFrameCount(file.length)
      )
    else {
      throw AudioEngineError.roomVoice("cannot allocate the source buffer")
    }
    do {
      try file.read(into: source)
      let loop = try convert(source, to: playbackFormat)
      roomVoiceBuffer = loop
      roomVoicePlayer.scheduleBuffer(loop, at: nil, options: .loops)
      roomVoicePlayer.play()
      roomVoiceActive = true
      return true
    } catch let error as AudioEngineError {
      throw error
    } catch {
      throw AudioEngineError.roomVoice(error.localizedDescription)
    }
  }

  @discardableResult
  public func stopRoomVoice() -> Bool {
    guard roomVoiceActive else { return false }
    roomVoicePlayer?.stop()
    roomVoiceBuffer = nil
    roomVoiceActive = false
    return true
  }

  public func setPlaybackGain(_ request: PlaybackGainRequest) throws -> PlaybackGainPacket {
    try request.validate()
    playbackGain = request.gain
    guard let playbackPlayer else { return PlaybackGainPacket(gain: request.gain) }

    volumeQueue.async { [weak playbackPlayer] in
      guard let playbackPlayer else { return }
      let start = playbackPlayer.volume
      let stepDuration = playbackGainRampDuration / Double(playbackGainRampSteps)
      for step in 1...playbackGainRampSteps {
        let progress = Float(step) / Float(playbackGainRampSteps)
        playbackPlayer.volume = start + (request.gain - start) * progress
        Thread.sleep(forTimeInterval: stepDuration)
      }
    }
    return PlaybackGainPacket(gain: request.gain)
  }

  public func status() -> AudioStatusPacket {
    AudioStatusPacket(
      audioMode: AudioStatusMode(mode),
      input: selectedInput?.info,
      output: selectedOutput?.info,
      roomVoiceConfigured: roomVoiceURL != nil,
      roomVoiceActive: roomVoiceActive,
      playbackGain: playbackGain,
      pendingPlaybackCount: playbackLock.withLock { pendingPlayback.count },
      duplexInterruptionAvailable: mode == .duplex
    )
  }

  public func checkDuplex(_ request: DuplexCheckRequest) throws -> DuplexCheckedPacket {
    try request.validate()
    guard mode == nil else {
      throw AudioEngineError.invalidState("CHECK_DUPLEX requires stopped audio")
    }

    var selectedInputInfo: AudioDeviceInfo?
    var selectedOutputInfo: AudioDeviceInfo?
    do {
      let catalog = try deviceResolver.catalog()
      let input = try catalog.resolve(request.inputIndex, direction: .input)
      let output = try catalog.resolve(request.outputIndex, direction: .output)
      selectedInputInfo = input.info
      selectedOutputInfo = output.info
      try probeDuplex(input: input, output: output)
      return DuplexCheckedPacket(
        available: true,
        input: input.info,
        output: output.info
      )
    } catch {
      return DuplexCheckedPacket(
        available: false,
        input: selectedInputInfo,
        output: selectedOutputInfo,
        reason: error.localizedDescription
      )
    }
  }

  public func shutdown() {
    stopAudio()
  }

  private static func validateRoomVoice(path: String?) throws -> URL? {
    guard let path else { return nil }
    let url = URL(fileURLWithPath: path).standardizedFileURL
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory),
      !isDirectory.boolValue
    else {
      throw AudioEngineError.roomVoice("file does not exist: \(url.path)")
    }
    do {
      let file = try AVAudioFile(forReading: url)
      guard file.length > 0 else {
        throw AudioEngineError.roomVoice("file is empty: \(url.path)")
      }
    } catch let error as AudioEngineError {
      throw error
    } catch {
      throw AudioEngineError.roomVoice("cannot read \(url.path): \(error.localizedDescription)")
    }
    return url
  }

  private static func makePlaybackFormat() throws -> AVAudioFormat {
    guard
      let format = AVAudioFormat(
        standardFormatWithSampleRate: playbackSampleRate,
        channels: playbackChannels
      )
    else {
      throw AudioEngineError.configuration("cannot create the 48 kHz mono playback format")
    }
    return format
  }

  private func probeDuplex(
    input: ResolvedAudioDevice,
    output: ResolvedAudioDevice
  ) throws {
    let probeEngine = AVAudioEngine()
    let probePlayer = AVAudioPlayerNode()
    let inputNode = probeEngine.inputNode
    let outputNode = probeEngine.outputNode
    let format = try Self.makePlaybackFormat()
    let captured = DispatchSemaphore(value: 0)

    try inputNode.setVoiceProcessingEnabled(true)
    guard inputNode.isVoiceProcessingEnabled else {
      throw AudioEngineError.configuration("voice processing did not become active")
    }
    try AudioDeviceResolver.select(input, on: inputNode.audioUnit)
    try AudioDeviceResolver.select(output, on: outputNode.audioUnit)
    probeEngine.attach(probePlayer)
    probeEngine.connect(probePlayer, to: probeEngine.mainMixerNode, format: format)
    inputNode.installTap(onBus: 0, bufferSize: 256, format: nil) { _, _ in
      captured.signal()
    }
    defer {
      probePlayer.stop()
      inputNode.removeTap(onBus: 0)
      probeEngine.stop()
    }

    guard
      let silence = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 480)
    else {
      throw AudioEngineError.configuration("cannot allocate duplex probe buffer")
    }
    silence.frameLength = 480
    if let channel = silence.floatChannelData?[0] {
      channel.initialize(repeating: 0, count: Int(silence.frameLength))
    }

    probeEngine.prepare()
    try probeEngine.start()
    inputNode.isVoiceProcessingInputMuted = false
    inputNode.isVoiceProcessingBypassed = false
    probePlayer.scheduleBuffer(silence)
    probePlayer.play()
    guard captured.wait(timeout: .now() + duplexProbeTimeout) == .success else {
      throw AudioEngineError.configuration("no capture arrived during the duplex probe")
    }
    probePlayer.stop()
  }

  private func receiveCapture(_ buffer: AVAudioPCMBuffer) {
    sendCaptureDiagnostic(buffer)
    guard let copy = copyBuffer(buffer) else { return }
    let box = AudioBufferBox(copy)
    captureQueue.async { [weak self, box] in
      self?.processCapture(box.buffer)
    }
  }

  private func processCapture(_ input: AVAudioPCMBuffer) {
    do {
      guard let channel = input.floatChannelData?[0] else {
        throw AudioEngineError.conversion(
          "capture format \(input.format) does not provide Float32 channel data"
        )
      }
      let sampleRate = input.format.sampleRate
      guard sampleRate > 0, sampleRate <= Double(UInt32.max) else {
        throw AudioEngineError.configuration("capture sample rate \(sampleRate) is invalid")
      }
      let sampleData = Data(
        bytes: channel,
        count: Int(input.frameLength) * MemoryLayout<Float>.size
      )
      let packet = try AudioPacket(
        sampleRate: UInt32(sampleRate.rounded()),
        channels: captureChannels,
        samples: sampleData
      )
      writer.send(WireFrame(kind: .capture, payload: packet.encode()))
    } catch {
      sendAsynchronousError(error)
    }
  }

  private func finishPlayback(requestID: UInt32) {
    let wasPending = playbackLock.withLock { pendingPlayback.remove(requestID) != nil }
    guard wasPending else { return }
    writer.send(
      WireFrame(
        kind: .playbackFinished,
        requestID: requestID,
        payload: Data([PlaybackStatus.played.rawValue])
      )
    )
  }

  private func makeBuffer(packet: AudioPacket) throws -> AVAudioPCMBuffer {
    guard
      let format = AVAudioFormat(
        commonFormat: .pcmFormatFloat32,
        sampleRate: Double(packet.sampleRate),
        channels: AVAudioChannelCount(packet.channels),
        interleaved: false
      ),
      let buffer = AVAudioPCMBuffer(
        pcmFormat: format,
        frameCapacity: AVAudioFrameCount(packet.frameCount)
      ), let channelData = buffer.floatChannelData
    else {
      throw AudioEngineError.configuration(
        "cannot allocate a playback buffer for \(packet.channels) channels at "
          + "\(packet.sampleRate) Hz"
      )
    }

    let samples = packet.samples.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
    let channelCount = Int(packet.channels)
    for channelIndex in 0..<channelCount {
      let destination = channelData[channelIndex]
      for frameIndex in 0..<packet.frameCount {
        destination[frameIndex] = samples[frameIndex * channelCount + channelIndex]
      }
    }
    buffer.frameLength = AVAudioFrameCount(packet.frameCount)
    return buffer
  }

  private func convert(
    _ input: AVAudioPCMBuffer,
    to outputFormat: AVAudioFormat
  ) throws -> AVAudioPCMBuffer {
    if input.format == outputFormat { return input }
    guard let converter = AVAudioConverter(from: input.format, to: outputFormat) else {
      throw AudioEngineError.conversion(
        "unsupported conversion from \(input.format) to \(outputFormat)"
      )
    }
    let ratio = outputFormat.sampleRate / input.format.sampleRate
    let capacity = AVAudioFrameCount(ceil(Double(input.frameLength) * ratio) + 16)
    guard let output = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
      throw AudioEngineError.conversion(
        "cannot allocate a converted buffer with capacity \(capacity)"
      )
    }

    let supplier = AudioBufferSupplier(buffer: input, exhaustedStatus: .endOfStream)
    var conversionError: NSError?
    let status = converter.convert(to: output, error: &conversionError) { _, inputStatus in
      supplier.next(status: inputStatus)
    }
    if let conversionError { throw conversionError }
    guard status != .error else {
      throw AudioEngineError.conversion(
        "audio converter returned status \(String(describing: status))"
      )
    }
    return output
  }

  private func copyBuffer(_ source: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
    guard
      let copy = AVAudioPCMBuffer(
        pcmFormat: source.format,
        frameCapacity: source.frameLength
      )
    else { return nil }
    copy.frameLength = source.frameLength

    let sourceBuffers = UnsafeMutableAudioBufferListPointer(
      UnsafeMutablePointer(mutating: source.audioBufferList)
    )
    let destinationBuffers = UnsafeMutableAudioBufferListPointer(copy.mutableAudioBufferList)
    guard sourceBuffers.count == destinationBuffers.count else { return nil }
    for index in sourceBuffers.indices {
      guard let sourceData = sourceBuffers[index].mData,
        let destinationData = destinationBuffers[index].mData
      else { return nil }
      let byteCount = Int(sourceBuffers[index].mDataByteSize)
      memcpy(destinationData, sourceData, byteCount)
      destinationBuffers[index].mDataByteSize = UInt32(byteCount)
    }
    return copy
  }

  private func resetCaptureDiagnostic() {
    captureDiagnosticSent = false
    captureDiagnosticSampleCount = 0
    captureDiagnosticSquaredSum = 0
    captureDiagnosticPeak = 0
  }

  private func sendCaptureDiagnostic(_ buffer: AVAudioPCMBuffer) {
    guard !captureDiagnosticSent else { return }
    guard let channels = buffer.floatChannelData else {
      captureDiagnosticSent = true
      sendDiagnostic(
        "raw_capture format=\(buffer.format), frames=\(buffer.frameLength), "
          + "float_samples=unavailable"
      )
      return
    }

    let frameCount = Int(buffer.frameLength)
    let channelCount = Int(buffer.format.channelCount)
    for channelIndex in 0..<channelCount {
      let channel = channels[channelIndex]
      for frameIndex in 0..<frameCount {
        let sample = channel[frameIndex]
        captureDiagnosticPeak = max(captureDiagnosticPeak, abs(sample))
        captureDiagnosticSquaredSum += Double(sample * sample)
      }
    }
    captureDiagnosticSampleCount += frameCount * channelCount
    guard captureDiagnosticSampleCount >= 4_800 else { return }

    captureDiagnosticSent = true
    let rms = sqrt(captureDiagnosticSquaredSum / Double(captureDiagnosticSampleCount))
    sendDiagnostic(
      "raw_capture format=\(buffer.format), frames=\(buffer.frameLength), "
        + "rms=\(rms), peak=\(captureDiagnosticPeak)"
    )
  }

  private func sendAsynchronousError(_ error: Error) {
    let code = (error as? any WireCodedError)?.wireErrorCode ?? .audioConfigurationFailed
    let packet = ErrorPacket(code: code, message: error.localizedDescription, fatal: false)
    if let payload = try? WireJSON.encode(packet) {
      writer.send(WireFrame(kind: .error, payload: payload))
    }
  }

  private func sendDiagnostic(_ message: String) {
    writer.send(WireFrame(kind: .diagnostic, payload: Data(message.utf8)))
  }
}
