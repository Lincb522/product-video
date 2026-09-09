import AppKit
import ApplicationServices
import Foundation

struct CaptureFailure: Error {}
let args = CommandLine.arguments
func fail() throws -> Never { throw CaptureFailure() }
func attr(_ node: AXUIElement, _ key: CFString) -> CFTypeRef? {
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(node, key, &value) == .success else { return nil }
    return value
}
func string(_ node: AXUIElement, _ key: CFString) -> String { attr(node, key) as? String ?? "" }
func named(_ node: AXUIElement) -> String {
    let title = string(node, kAXTitleAttribute as CFString)
    return title.isEmpty ? string(node, kAXDescriptionAttribute as CFString) : title
}
func window(_ app: NSRunningApplication, _ title: String) throws -> AXUIElement {
    let root = AXUIElementCreateApplication(app.processIdentifier)
    let windows = attr(root, kAXWindowsAttribute as CFString) as? [AXUIElement] ?? []
    let matches = windows.filter { title.isEmpty || named($0) == title }
    guard matches.count == 1, let result = matches.first else { try fail() }
    return result
}
func descendants(_ root: AXUIElement) throws -> [AXUIElement] {
    var queue = [root], index = 0
    while index < queue.count {
        guard queue.count <= 3000 else { try fail() }
        queue += attr(queue[index], kAXChildrenAttribute as CFString) as? [AXUIElement] ?? []
        index += 1
    }
    return queue
}
func emit(_ value: Any) throws {
    let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
}
func run() throws {
    guard args.count >= 4 else { try fail() }
    let command = args[1], bundle = args[2], title = args[3]
    let foregroundPID = NSWorkspace.shared.frontmostApplication?.processIdentifier
    if command == "permissions" {
        try emit(["accessibility": AXIsProcessTrusted(), "screen_recording": CGPreflightScreenCaptureAccess()]); return
    }
    guard AXIsProcessTrusted() else { try fail() }
    let deadline = Date().addingTimeInterval(12)
    var application: NSRunningApplication?
    repeat {
        application = NSRunningApplication.runningApplications(withBundleIdentifier: bundle).first
        if application != nil { break }
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
    } while Date() < deadline
    guard let app = application else { try fail() }
    var found: AXUIElement?
    repeat {
        found = try? window(app, title)
        if found != nil { break }
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
    } while Date() < deadline
    guard let root = found, (attr(root, kAXMinimizedAttribute as CFString) as? Bool) != true else { try fail() }
    if command == "ready" { try emit(["ready": true]); return }
    if command == "inspect" {
        let rows = try descendants(root).map { ["role": string($0, kAXRoleAttribute as CFString), "name": named($0)] }
            .filter { !$0["name", default: ""].isEmpty }
        try emit(["controls": rows]); return
    }
    if command == "window" {
        guard CGPreflightScreenCaptureAccess() else { try fail() }
        let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
        let visible = list.filter {
            ($0[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == app.processIdentifier &&
            ($0[kCGWindowLayer as String] as? Int) == 0 &&
            (title.isEmpty || ($0[kCGWindowName as String] as? String) == title)
        }
        guard visible.count == 1, let id = visible.first?[kCGWindowNumber as String] as? UInt32 else { try fail() }
        try emit(["id": id]); return
    }
    guard args.count == 6, command == "press" || command == "wait" else { try fail() }
    repeat {
        let current = try window(app, title)
        let matches = try descendants(current).filter {
            string($0, kAXRoleAttribute as CFString) == args[4] && named($0) == args[5]
        }
        if matches.count > 1 { try fail() }
        if let node = matches.first {
            if command == "press" {
                guard AXUIElementPerformAction(node, kAXPressAction as CFString) == .success else { try fail() }
                guard NSWorkspace.shared.frontmostApplication?.processIdentifier == foregroundPID else { try fail() }
            }
            try emit(["done": true]); return
        }
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
    } while Date() < deadline
    try fail()
}
do { try run() } catch {
    FileHandle.standardError.write(Data("Native capture unavailable; check target window and macOS permissions.\n".utf8))
    exit(1)
}
