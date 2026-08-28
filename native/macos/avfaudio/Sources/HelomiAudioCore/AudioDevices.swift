import AudioToolbox
import CoreAudio
import Foundation

public struct AudioDeviceInfo: Codable, Equatable, Sendable {
  public let index: Int
  public let name: String
  public let uid: String?
  public let isDefault: Bool

  public init(index: Int, name: String, uid: String? = nil, isDefault: Bool) {
    self.index = index
    self.name = name
    self.uid = uid
    self.isDefault = isDefault
  }
}

public struct AudioDevicesPacket: Codable, Equatable, Sendable {
  public let input: [AudioDeviceInfo]
  public let output: [AudioDeviceInfo]

  public init(input: [AudioDeviceInfo], output: [AudioDeviceInfo]) {
    self.input = input
    self.output = output
  }
}

enum AudioDeviceDirection: Sendable {
  case input
  case output

  var scope: AudioObjectPropertyScope {
    switch self {
    case .input: kAudioDevicePropertyScopeInput
    case .output: kAudioDevicePropertyScopeOutput
    }
  }

  var defaultSelector: AudioObjectPropertySelector {
    switch self {
    case .input: kAudioHardwarePropertyDefaultInputDevice
    case .output: kAudioHardwarePropertyDefaultOutputDevice
    }
  }
}

enum AudioDeviceError: Error, LocalizedError, WireCodedError {
  case query(String, OSStatus)
  case unavailable(AudioDeviceDirection, Int?)
  case selection(String, OSStatus)

  var wireErrorCode: WireErrorCode { .deviceUnavailable }

  var errorDescription: String? {
    switch self {
    case .query(let operation, let status):
      "CoreAudio query \(operation) failed with status \(status)"
    case .unavailable(let direction, let index):
      "Audio \(direction == .input ? "input" : "output") device "
        + (index.map(String.init) ?? "default") + " is unavailable"
    case .selection(let name, let status):
      "Cannot select audio device \(name); CoreAudio status \(status)"
    }
  }
}

protocol AudioHardwareAccess {
  func allDeviceIDs() throws -> [AudioDeviceID]
  func defaultDeviceID(for direction: AudioDeviceDirection) throws -> AudioDeviceID?
  func hasStreams(_ deviceID: AudioDeviceID, direction: AudioDeviceDirection) -> Bool
  func name(of deviceID: AudioDeviceID) -> String?
  func uid(of deviceID: AudioDeviceID) -> String?
}

struct CoreAudioHardware: AudioHardwareAccess {
  func allDeviceIDs() throws -> [AudioDeviceID] {
    var address = AudioObjectPropertyAddress(
      mSelector: kAudioHardwarePropertyDevices,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain
    )
    var size: UInt32 = 0
    var status = AudioObjectGetPropertyDataSize(
      AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size
    )
    guard status == noErr else {
      throw AudioDeviceError.query("device list size", status)
    }
    var devices = [AudioDeviceID](
      repeating: kAudioObjectUnknown,
      count: Int(size) / MemoryLayout<AudioDeviceID>.size
    )
    status = AudioObjectGetPropertyData(
      AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &devices
    )
    guard status == noErr else {
      throw AudioDeviceError.query("device list", status)
    }
    return devices
  }

  func defaultDeviceID(for direction: AudioDeviceDirection) throws -> AudioDeviceID? {
    var address = AudioObjectPropertyAddress(
      mSelector: direction.defaultSelector,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain
    )
    var deviceID = AudioDeviceID(kAudioObjectUnknown)
    var size = UInt32(MemoryLayout<AudioDeviceID>.size)
    let status = AudioObjectGetPropertyData(
      AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &deviceID
    )
    guard status == noErr else {
      throw AudioDeviceError.query("default device", status)
    }
    return deviceID == kAudioObjectUnknown ? nil : deviceID
  }

  func hasStreams(_ deviceID: AudioDeviceID, direction: AudioDeviceDirection) -> Bool {
    var address = AudioObjectPropertyAddress(
      mSelector: kAudioDevicePropertyStreams,
      mScope: direction.scope,
      mElement: kAudioObjectPropertyElementMain
    )
    var size: UInt32 = 0
    let status = AudioObjectGetPropertyDataSize(deviceID, &address, 0, nil, &size)
    return status == noErr && size >= UInt32(MemoryLayout<AudioStreamID>.size)
  }

  func name(of deviceID: AudioDeviceID) -> String? {
    stringProperty(deviceID: deviceID, selector: kAudioObjectPropertyName)
  }

  func uid(of deviceID: AudioDeviceID) -> String? {
    stringProperty(deviceID: deviceID, selector: kAudioDevicePropertyDeviceUID)
  }

  private func stringProperty(
    deviceID: AudioDeviceID,
    selector: AudioObjectPropertySelector
  ) -> String? {
    var address = AudioObjectPropertyAddress(
      mSelector: selector,
      mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain
    )
    var value: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    let status = AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &value)
    guard status == noErr, let value else { return nil }
    return value.takeUnretainedValue() as String
  }
}

struct ResolvedAudioDevice: Sendable {
  let id: AudioDeviceID
  let info: AudioDeviceInfo
}

struct AudioDeviceCatalog: Sendable {
  let input: [ResolvedAudioDevice]
  let output: [ResolvedAudioDevice]

  var packet: AudioDevicesPacket {
    AudioDevicesPacket(input: input.map(\.info), output: output.map(\.info))
  }

  func resolve(_ index: Int?, direction: AudioDeviceDirection) throws -> ResolvedAudioDevice {
    let devices = direction == .input ? input : output
    if let index {
      guard devices.indices.contains(index) else {
        throw AudioDeviceError.unavailable(direction, index)
      }
      return devices[index]
    }
    guard let device = devices.first(where: { $0.info.isDefault }) else {
      throw AudioDeviceError.unavailable(direction, nil)
    }
    return device
  }
}

struct AudioDeviceResolver {
  private let hardware: any AudioHardwareAccess

  init(hardware: any AudioHardwareAccess = CoreAudioHardware()) {
    self.hardware = hardware
  }

  func catalog() throws -> AudioDeviceCatalog {
    let deviceIDs = try hardware.allDeviceIDs()
    let defaultInput = try hardware.defaultDeviceID(for: .input)
    let defaultOutput = try hardware.defaultDeviceID(for: .output)
    return AudioDeviceCatalog(
      input: devices(
        from: deviceIDs,
        direction: .input,
        defaultDeviceID: defaultInput
      ),
      output: devices(
        from: deviceIDs,
        direction: .output,
        defaultDeviceID: defaultOutput
      )
    )
  }

  private func devices(
    from deviceIDs: [AudioDeviceID],
    direction: AudioDeviceDirection,
    defaultDeviceID: AudioDeviceID?
  ) -> [ResolvedAudioDevice] {
    let capable = deviceIDs.filter { hardware.hasStreams($0, direction: direction) }
      .sorted {
        let left = hardware.name(of: $0) ?? "Unknown"
        let right = hardware.name(of: $1) ?? "Unknown"
        let comparison = left.localizedCaseInsensitiveCompare(right)
        return comparison == .orderedSame ? $0 < $1 : comparison == .orderedAscending
      }
    return capable.enumerated().map { index, deviceID in
      ResolvedAudioDevice(
        id: deviceID,
        info: AudioDeviceInfo(
          index: index,
          name: hardware.name(of: deviceID) ?? "Unknown",
          uid: hardware.uid(of: deviceID),
          isDefault: deviceID == defaultDeviceID
        )
      )
    }
  }

  static func select(_ device: ResolvedAudioDevice, on audioUnit: AudioUnit?) throws {
    guard let audioUnit else {
      throw AudioDeviceError.selection(device.info.name, -1)
    }
    var deviceID = device.id
    let status = AudioUnitSetProperty(
      audioUnit,
      kAudioOutputUnitProperty_CurrentDevice,
      kAudioUnitScope_Global,
      0,
      &deviceID,
      UInt32(MemoryLayout<AudioDeviceID>.size)
    )
    guard status == noErr else {
      throw AudioDeviceError.selection(device.info.name, status)
    }
  }
}
