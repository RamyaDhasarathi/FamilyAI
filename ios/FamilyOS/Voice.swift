import AVFoundation
import SwiftUI

/// Say it: record a short note, send it to the household's own server to be turned into words (the audio is not kept),
/// and hand the words back. Nothing is done from the words until the person sends them.
@MainActor
final class VoiceNote: ObservableObject {
    @Published var recording = false
    @Published var transcribing = false
    @Published var said: String?            // a one-line reason when it did not work

    private var recorder: AVAudioRecorder?
    private var file: URL?

    /// First tap starts recording, second tap stops it and returns the words.
    func toggle(onText: @escaping (String) -> Void) async {
        said = nil
        if recording { await finish(onText: onText); return }
        guard await AVAudioApplication.requestRecordPermission() else {
            said = "The microphone is off for FamilyOS in the iPhone's Settings."
            return
        }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
            try session.setActive(true)
            let url = FileManager.default.temporaryDirectory.appendingPathComponent("say-\(UUID().uuidString).m4a")
            let r = try AVAudioRecorder(url: url, settings: [AVFormatIDKey: Int(kAudioFormatMPEG4AAC), AVSampleRateKey: 16000, AVNumberOfChannelsKey: 1])
            guard r.record(forDuration: 60) else { said = "Could not start recording."; return }
            recorder = r; file = url; recording = true
        } catch { said = "Could not start recording: \(error.localizedDescription)" }
    }

    private func finish(onText: @escaping (String) -> Void) async {
        recorder?.stop(); recording = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        guard let url = file, let data = try? Data(contentsOf: url) else { said = "Nothing was recorded."; return }
        try? FileManager.default.removeItem(at: url)
        recorder = nil; file = nil
        transcribing = true
        defer { transcribing = false }
        do {
            let text = try await API.shared.transcribe(data, contentType: "audio/mp4")
            if text.isEmpty { said = "I could not make out any words. Try again closer to the phone." } else { onText(text) }
        } catch { said = "Could not turn that into words: \(error.localizedDescription)" }
    }
}
