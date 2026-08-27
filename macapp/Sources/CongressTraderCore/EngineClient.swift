import Foundation

public actor EngineClient {
    private let environment: [String: String]
    private let workingDirectory: URL?

    public init(environment: [String: String] = ProcessInfo.processInfo.environment) {
        self.environment = environment
        self.workingDirectory = EngineRootLocator.find()
    }

    public init(environment: [String: String], workingDirectory: URL?) {
        self.environment = environment
        self.workingDirectory = workingDirectory
    }

    public func fetch(options: ReportOptions, pythonPath: String?) async throws -> Report {
        let executable = try InterpreterResolver.resolve(
            preferred: pythonPath,
            environment: environment
        )
        let configuration = RunConfiguration(
            executable: executable,
            arguments: options.arguments,
            environment: environment,
            workingDirectory: workingDirectory
        )

        return try await Task.detached(priority: .userInitiated) {
            try Self.execute(configuration)
        }.value
    }

    private nonisolated static func execute(_ configuration: RunConfiguration) throws -> Report {
        let fileManager = FileManager.default
        let scratch = fileManager.temporaryDirectory
            .appendingPathComponent("CongressTrader-\(UUID().uuidString)")
        let stdoutURL = scratch.appendingPathComponent("stdout.json")
        let stderrURL = scratch.appendingPathComponent("stderr.txt")
        try fileManager.createDirectory(at: scratch, withIntermediateDirectories: true)
        try Data().write(to: stdoutURL)
        try Data().write(to: stderrURL)
        defer { try? fileManager.removeItem(at: scratch) }

        let stdout = try FileHandle(forWritingTo: stdoutURL)
        let stderr = try FileHandle(forWritingTo: stderrURL)
        defer {
            try? stdout.close()
            try? stderr.close()
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: configuration.executable)
        process.arguments = configuration.arguments
        process.environment = configuration.environment
        process.currentDirectoryURL = configuration.workingDirectory
        process.standardOutput = stdout
        process.standardError = stderr

        do {
            try process.run()
        } catch {
            throw EngineClientError.couldNotLaunch(error.localizedDescription)
        }
        process.waitUntilExit()
        try stdout.close()
        try stderr.close()

        let stderrText = String(
            decoding: try Data(contentsOf: stderrURL),
            as: UTF8.self
        ).trimmingCharacters(in: .whitespacesAndNewlines)
        guard process.terminationStatus == 0 else {
            throw EngineClientError.processFailed(
                status: process.terminationStatus,
                message: stderrText.isEmpty ? "No error details were provided." : stderrText
            )
        }

        let output = try Data(contentsOf: stdoutURL)
        do {
            return try Report.decode(output)
        } catch let error as ReportSchemaError {
            throw error
        } catch {
            throw EngineClientError.invalidOutput(error.localizedDescription)
        }
    }
}

private struct RunConfiguration: Sendable {
    let executable: String
    let arguments: [String]
    let environment: [String: String]
    let workingDirectory: URL?
}

public enum EngineClientError: LocalizedError, Sendable {
    case couldNotLaunch(String)
    case processFailed(status: Int32, message: String)
    case invalidOutput(String)

    public var errorDescription: String? {
        switch self {
        case let .couldNotLaunch(message):
            return "Could not start the engine: \(message)"
        case let .processFailed(status, message):
            return "Engine failed (exit \(status)): \(message)"
        case let .invalidOutput(message):
            return "The engine returned unreadable data: \(message)"
        }
    }
}

public enum InterpreterResolver {
    public static func resolve(
        preferred: String?,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) throws -> String {
        if let preferred, !preferred.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return try requireExecutable(expandHome(preferred))
        }
        if let configured = environment["CONGRESS_TRADER_PYTHON"], !configured.isEmpty {
            return try requireExecutable(expandHome(configured))
        }

        let directories = environment["PATH", default: ""]
            .split(separator: ":")
            .map(String.init)
        for name in ["python3", "python"] {
            for directory in directories {
                let candidate = URL(fileURLWithPath: directory)
                    .appendingPathComponent(name).path
                if FileManager.default.isExecutableFile(atPath: candidate) {
                    return candidate
                }
            }
        }
        throw InterpreterError.notFound
    }

    private static func requireExecutable(_ path: String) throws -> String {
        guard FileManager.default.isExecutableFile(atPath: path) else {
            throw InterpreterError.notExecutable(path)
        }
        return path
    }

    private static func expandHome(_ path: String) -> String {
        NSString(string: path).expandingTildeInPath
    }
}

public enum InterpreterError: LocalizedError, Sendable {
    case notFound
    case notExecutable(String)

    public var errorDescription: String? {
        switch self {
        case .notFound:
            return "No Python interpreter was found. Set one in Congress Trader settings."
        case let .notExecutable(path):
            return "The configured Python interpreter is not executable: \(path)"
        }
    }
}

enum EngineRootLocator {
    static func find(from start: URL? = nil) -> URL? {
        var candidate = start ?? URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        while candidate.path != "/" {
            let module = candidate.appendingPathComponent("congress_trader/__main__.py")
            if FileManager.default.fileExists(atPath: module.path) {
                return candidate
            }
            candidate.deleteLastPathComponent()
        }
        return nil
    }
}
