import CongressTraderCore
import Foundation

@main
enum ContractTests {
    static func main() async {
        let checks: [(String, @Sendable () async throws -> Void)] = [
            ("decodes every schema section", decodeEverySection),
            ("rejects newer schemas", rejectNewerSchema),
            ("decodes nullable signal fields", decodeNullFields),
            ("runs the sample command with every control", runSampleCommand),
            ("loads the repository sample through Python", loadRepositorySample),
            ("surfaces stderr", surfaceStderr),
            ("rejects a non-executable interpreter", rejectNonExecutableInterpreter),
        ]
        var failures: [String] = []

        for (name, check) in checks {
            do {
                try await check()
                print("PASS  \(name)")
            } catch {
                failures.append("\(name): \(error)")
                print("FAIL  \(name): \(error)")
            }
        }

        guard failures.isEmpty else {
            print("\n\(failures.count) contract check(s) failed.")
            Foundation.exit(1)
        }
        print("\nAll \(checks.count) contract checks passed.")
    }

    private static func decodeEverySection() throws {
        let report = try Report.decode(fixtureData())
        try expect(report.schemaVersion == 1, "schema version")
        try expect(report.asof == "2026-08-26", "as-of date")
        try expect(report.signals.first?.ticker == "NVDA", "signal")
        try expect(report.signals.first?.raw["bipartisan"] == 4.0, "raw components")
        try expect(report.sectors.first?.momentum == 1.2, "sector")
        try expect(report.contested.first?.sellers == ["Victor Kaplan"], "contested")
        try expect(report.filers.first?.fastestLagDays == 12, "filer")
    }

    private static func rejectNewerSchema() throws {
        do {
            _ = try Report.decode(Data(#"{"schema_version":2}"#.utf8))
            throw ContractFailure("schema 2 was accepted")
        } catch let error as ReportSchemaError {
            try expect(
                error.localizedDescription
                    == "The engine is newer than this app (schema 2; supported 1). Update Congress Trader.",
                "newer-engine message"
            )
        }
    }

    private static func decodeNullFields() throws {
        let original = String(decoding: try fixtureData(), as: UTF8.self)
        let modified = original
            .replacingOccurrences(of: #""first_date": "2026-08-18""#, with: #""first_date": null"#)
            .replacingOccurrences(of: #""last_date": "2026-08-24""#, with: #""last_date": null"#)
            .replacingOccurrences(of: #""median_lag_days": 28.0"#, with: #""median_lag_days": null"#)
        let signal = try require(Report.decode(Data(modified.utf8)).signals.first, "signal")
        try expect(signal.firstDate == nil, "first date")
        try expect(signal.lastDate == nil, "last date")
        try expect(signal.medianLagDays == nil, "median lag")
    }

    private static func runSampleCommand() async throws {
        let sandbox = try Sandbox()
        let client = EngineClient(
            environment: [
                "CAPTURE_PATH": sandbox.capture.path,
                "FIXTURE_PATH": sandbox.fixture.path,
                "PATH": "/bin:/usr/bin",
            ],
            workingDirectory: sandbox.root
        )
        let options = ReportOptions(
            lookback: 45,
            minMembers: 4,
            midpoint: .arithmetic,
            source: .sample
        )

        let report = try await client.fetch(options: options, pythonPath: sandbox.executable.path)
        try expect(report.signals.first?.ticker == "NVDA", "subprocess report")
        let arguments = try String(contentsOf: sandbox.capture, encoding: .utf8)
            .split(separator: "\n")
            .map(String.init)
        try expect(arguments == [
            "-m", "congress_trader", "report", "--json", "--lookback", "45",
            "--min-members", "4", "--midpoint", "arithmetic", "--sample",
        ], "subprocess arguments: \(arguments)")
    }

    private static func surfaceStderr() async throws {
        let sandbox = try Sandbox(script: "#!/bin/sh\necho 'feed unavailable' >&2\nexit 7\n")
        let client = EngineClient(environment: ["PATH": "/bin:/usr/bin"], workingDirectory: sandbox.root)
        do {
            _ = try await client.fetch(options: .sample, pythonPath: sandbox.executable.path)
            throw ContractFailure("failing process was accepted")
        } catch let error as EngineClientError {
            try expect(
                error.localizedDescription == "Engine failed (exit 7): feed unavailable",
                "stderr message"
            )
        }
    }

    private static func loadRepositorySample() async throws {
        let report = try await EngineClient().fetch(options: .sample, pythonPath: nil)
        try expect(report.source == "sample", "sample source")
        try expect(!report.signals.isEmpty, "sample report signals")
        try expect(report.schemaVersion == 1, "sample report schema")
    }

    private static func rejectNonExecutableInterpreter() throws {
        let sandbox = try Sandbox()
        let notExecutable = sandbox.root.appendingPathComponent("not-python")
        try Data().write(to: notExecutable)
        do {
            _ = try InterpreterResolver.resolve(
                preferred: notExecutable.path,
                environment: ["PATH": "/missing"]
            )
            throw ContractFailure("non-executable interpreter was accepted")
        } catch let error as InterpreterError {
            try expect(error.localizedDescription.contains("not executable"), "interpreter message")
        }
    }

    private static func fixtureData() throws -> Data {
        let url = try require(
            Bundle.module.url(
                forResource: "report-v1",
                withExtension: "json",
                subdirectory: "Fixtures"
            ),
            "fixture URL"
        )
        return try Data(contentsOf: url)
    }

    private static func expect(_ condition: @autoclosure () -> Bool, _ message: String) throws {
        guard condition() else { throw ContractFailure(message) }
    }

    private static func require<T>(_ value: T?, _ message: String) throws -> T {
        guard let value else { throw ContractFailure(message) }
        return value
    }
}

private struct ContractFailure: Error, CustomStringConvertible {
    let description: String

    init(_ description: String) {
        self.description = description
    }
}

private struct Sandbox {
    let root: URL
    let executable: URL
    let fixture: URL
    let capture: URL

    init(script: String? = nil) throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("CongressTraderTests-\(UUID().uuidString)")
        executable = root.appendingPathComponent("fake-python")
        fixture = root.appendingPathComponent("report.json")
        capture = root.appendingPathComponent("arguments.txt")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)

        guard let fixtureURL = Bundle.module.url(
            forResource: "report-v1",
            withExtension: "json",
            subdirectory: "Fixtures"
        ) else {
            throw ContractFailure("fixture URL")
        }
        try FileManager.default.copyItem(at: fixtureURL, to: fixture)

        let body = script ?? """
        #!/bin/sh
        printf '%s\\n' "$@" > "$CAPTURE_PATH"
        cat "$FIXTURE_PATH"
        """
        try Data(body.utf8).write(to: executable)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o755],
            ofItemAtPath: executable.path
        )
    }
}
