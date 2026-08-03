// swift-tools-version: 6.2

import PackageDescription

let package = Package(
  name: "audio",
  platforms: [
    .macOS(.v14)
  ],
  products: [
    .executable(name: "audio", targets: ["HelomiAudio"])
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
