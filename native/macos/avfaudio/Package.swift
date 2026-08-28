// swift-tools-version: 6.2

import PackageDescription

let package = Package(
  name: "avfaudio",
  platforms: [
    .macOS(.v14)
  ],
  products: [
    .executable(name: "avfaudio", targets: ["HelomiAudio"])
  ],
  targets: [
    .target(name: "HelomiAudioCore"),
    .executableTarget(
      name: "HelomiAudio",
      dependencies: ["HelomiAudioCore"]
    ),
    .testTarget(
      name: "HelomiAudioCoreTests",
      dependencies: ["HelomiAudioCore"]
    ),
  ]
)
