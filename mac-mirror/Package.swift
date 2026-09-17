// swift-tools-version:5.5
import PackageDescription

let package = Package(
    name: "DroidMirror",
    platforms: [
        .macOS(.v11)
    ],
    targets: [
        .executableTarget(
            name: "DroidMirror",
            path: "Sources/DroidMirror",
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("AVFoundation"),
                .linkedFramework("CoreMedia"),
                .linkedFramework("QuartzCore"),
            ]
        )
    ]
)
