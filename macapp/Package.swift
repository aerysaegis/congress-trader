// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "CongressTrader",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(name: "CongressTrader", targets: ["CongressTraderApp"]),
        .executable(
            name: "CongressTraderCoreContractTests",
            targets: ["CongressTraderCoreContractTests"]
        ),
    ],
    targets: [
        .target(name: "CongressTraderCore"),
        .executableTarget(
            name: "CongressTraderApp",
            dependencies: ["CongressTraderCore"]
        ),
        .executableTarget(
            name: "CongressTraderCoreContractTests",
            dependencies: ["CongressTraderCore"],
            path: "Tests/CongressTraderCoreContractTests",
            resources: [.copy("Fixtures")]
        ),
    ]
)
