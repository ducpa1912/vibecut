/* VibeCut interface language: English + Vietnamese.
 *
 * The Classic and Voice Room pages are rendered by large JavaScript modules,
 * so this file translates the live DOM instead of every template call site.
 * Exact text is replaced; anything not in the dictionary stays in English.
 * The choice is per browser (`localStorage`) and is also accepted as ?lang=vi.
 */
(() => {
  "use strict";

  const KEY = "vibecut.ui_lang";
  const SUPPORTED = ["en", "vi"];

  const VI = {
    // Header and shared controls
    "VibeCut": "VibeCut",
    "Open Studio": "Mở Studio",
    "Voice Room": "Phòng giọng nói",
    "Back to VibeCut": "Quay lại VibeCut",
    "Creator": "Creator",
    "Setup": "Cài đặt",
    "On-device AI": "AI trên thiết bị",
    "Cloud AI": "AI trên đám mây",
    "Mixed AI": "AI hỗn hợp",
    "AI off": "AI đang tắt",
    "AI": "AI",
    "STT / transcript": "STT / bản chép lời",
    "TTS / voice": "TTS / giọng nói",
    "Vision / text": "Vision / chữ",
    "Translation / rewrite": "Dịch / viết lại",
    "Render": "Render",
    "Native": "Gốc",
    "Not native · check Setup": "Không có bản gốc · xem Cài đặt",
    "Not available · center crop": "Không khả dụng · cắt giữa",
    "See Setup routes": "Xem tuyến trong Cài đặt",
    "Local": "Cục bộ",
    "on-device": "trên thiết bị",
    "mixed": "hỗn hợp",
    "AI not configured": "AI chưa cấu hình",
    "apple vision": "apple vision",
    "center crop": "cắt giữa",
    "Switching language reloads the page and discards unsaved cut changes. Continue?": "Đổi ngôn ngữ sẽ tải lại trang và bỏ các thay đổi bản cắt chưa lưu. Tiếp tục?",
    "No render baseline on this browser. Render again to confirm this cut matches.": "Trình duyệt này chưa có mốc render. Hãy render lại để xác nhận bản cắt khớp.",
    "Voice preview ready · cached, no new call. Play ▶ or render to use this voice.": "Bản nghe thử giọng đã sẵn sàng · dùng bộ nhớ đệm, không gọi mới. Phát ▶ hoặc render để dùng giọng này.",
    "Voice preview ready. Play ▶ or render to use this voice.": "Bản nghe thử giọng đã sẵn sàng. Phát ▶ hoặc render để dùng giọng này.",
    "custom hook": "mở đầu tùy chỉnh",
    "checking engine…": "đang kiểm tra engine…",
    "ffmpeg · local analysis": "ffmpeg · phân tích cục bộ",
    "Save setup": "Lưu cài đặt",
    "Saving…": "Đang lưu…",
    "Cancel": "Hủy",
    "Save": "Lưu",
    "Done": "Xong",
    "Delete": "Xóa",
    "Clean work files?": "Dọn tệp làm việc?",
    "thumbnails, the transcript, extracted audio and deep-read scores": "ảnh thu nhỏ, bản chép lời, âm thanh đã trích xuất và điểm đọc sâu",
    "the source video, rendered reels and job details": "video gốc, reel đã render và thông tin job",
    "Analysis work files can be rebuilt by analyzing again.": "Có thể tạo lại tệp phân tích bằng cách phân tích lại.",
    "Clean rendered reels?": "Dọn reel đã render?",
    "rendered reels, render masters and legacy render files": "reel đã render, bản master và tệp render cũ",
    "the source video, transcript, thumbnails and job details": "video gốc, bản chép lời, ảnh thu nhỏ và thông tin job",
    "Review links and pinned artifacts are protected. If they cannot be protected, Clean stops.": "Liên kết xem lại và artifact đã ghim được bảo vệ. Nếu không thể bảo vệ, Clean sẽ dừng.",
    "Clean everything except the source?": "Dọn mọi thứ trừ video gốc?",
    "work files and rendered reels (thumbnails, transcript, extracted audio, deep-read scores, render masters)": "tệp làm việc và reel đã render (ảnh thu nhỏ, bản chép lời, âm thanh đã trích xuất, điểm đọc sâu, bản master)",
    "the source video and job details": "video gốc và thông tin job",
    "Download": "Tải xuống",
    "Refresh": "Làm mới",
    "Close": "Đóng",
    "Open Setup": "Mở cài đặt",
    "Optional: add keys and voices in Setup": "Tùy chọn: thêm khóa và giọng trong Cài đặt",
    "Language": "Ngôn ngữ",
    "Interface language": "Ngôn ngữ giao diện",
    "English": "English",
    "Tiếng Việt": "Tiếng Việt",

    // Ingest
    "ingest": "nhập video",
    "Long video in.": "Video dài vào.",
    "Reels that keep the vibe.": "Reels giữ đúng chất.",
    "Drop a video": "Thả video vào",
    "or click to choose · files stay on this machine": "hoặc bấm để chọn · tệp ở lại máy này",
    "Paste a video link": "Dán liên kết video",
    "Get video": "Lấy video",
    "yt-dlp for most sites · XHS / RedNote for share links.": "yt-dlp cho hầu hết trang · XHS / RedNote cho liên kết chia sẻ.",
    "Use a local path instead": "Dùng đường dẫn cục bộ",
    "no copy": "không sao chép",
    "Load": "Tải",
    "Smart crop": "Cắt thông minh",
    "follows the subject": "bám theo chủ thể",
    "Track crop": "Theo dõi cắt",
    "smoothed per beat": "làm mượt theo nhịp",
    "Read text & faces": "Đọc chữ và khuôn mặt",
    "Apple Vision · local": "Apple Vision · cục bộ",
    "Transcribe speech": "Chép lời nói",
    "local Whisper": "Whisper cục bộ",
    "Dissect video": "Phân tích video",
    "Clean video": "Làm sạch video",
    "Clean removes text from the whole video. Dissect cuts a reel.": "Làm sạch xóa chữ khỏi toàn bộ video. Phân tích sẽ cắt thành reel.",
    "Back to ingest": "Quay lại nhập video",
    "Find text & clean": "Tìm chữ & làm sạch",
    "Find text &amp; clean": "Tìm chữ & làm sạch",
    "Make a reel": "Tạo reel",
    "Clean again": "Làm sạch lại",
    "Whole video": "Toàn bộ video",
    "Finding text": "Đang tìm chữ",
    "Cleaning": "Đang làm sạch",
    "Encoding": "Đang mã hóa",
    "Estimating": "Đang ước lượng",
    "Estimating…": "Đang ước lượng…",
    "Scanning the whole video…": "Đang quét toàn bộ video…",
    "Analysis started": "Đã bắt đầu phân tích",
    "No baked-in text found. Nothing was rendered.": "Không tìm thấy chữ nằm sẵn trong video. Không có gì được render.",
    "Text was found but is not cleaned yet. Tick a row or use Find text & clean.": "Đã tìm thấy chữ nhưng chưa làm sạch. Tích một dòng hoặc dùng Tìm chữ & làm sạch.",
    "Analysis started. The cut opens here when it is ready.": "Đã bắt đầu phân tích. Bản cắt sẽ tự mở ở đây khi xong.",
    "Retry analysis": "Thử phân tích lại",
    "Source Clean layers added.": "Đã thêm các lớp Làm sạch nguồn.",
    "Analysis was cancelled.": "Phân tích đã bị hủy.",
    "Analysis was interrupted.": "Phân tích đã bị gián đoạn.",
    "Analysis stopped before it could build the cut.": "Phân tích đã dừng trước khi dựng được bản cắt.",
    "Analysis stopped before it could build the cut. Your clean video is still available.": "Phân tích đã dừng trước khi dựng được bản cắt. Video làm sạch của bạn vẫn còn.",
    "Analysis finished without a cut.": "Phân tích kết thúc nhưng không có bản cắt.",
    "Analysis status could not be checked.": "Không kiểm tra được trạng thái phân tích.",
    "Analysis did not start.": "Phân tích không bắt đầu.",
    "Download the source clean file, or retry.": "Tải tệp làm sạch nguồn, hoặc thử lại.",
    "Try again.": "Thử lại.",
    "Blur needs no fill estimate · render progress will show": "Blur không cần ước lượng AI fill · tiến độ render sẽ hiển thị",
    "Blur needs no fill estimate. Render progress will show.": "Blur không cần ước lượng AI fill. Tiến độ render sẽ hiển thị.",
    "The scan could not confirm on-screen text. Rescan to try again.": "Bản quét không xác nhận được chữ trên màn hình. Quét lại để thử.",
    "The scan failed. Retry the scan; nothing was rendered.": "Quét thất bại. Thử quét lại; không có gì được render.",
    "Scan cancelled. Scan again when ready.": "Đã hủy quét. Quét lại khi sẵn sàng.",
    "No text scan yet. Find text & clean scans the whole video and fills each text it finds.": "Chưa quét chữ. Tìm chữ & làm sạch sẽ quét toàn bộ video và lấp từng đoạn chữ tìm thấy.",
    "No clean boxes yet. Find text, or draw a box on the frame.": "Chưa có khung làm sạch. Tìm chữ, hoặc vẽ một khung trên hình.",
    "Remove text from the whole video. The frame is the real render.": "Xóa chữ khỏi toàn bộ video. Khung hình chính là bản render thật.",
    "Remove what should not be in the cut. The frame is the real render.": "Xóa những gì không nên nằm trong bản cắt. Khung hình chính là bản render thật.",
    "whole video": "toàn bộ video",
    "ffmpeg cuts first. Analysis follows.": "ffmpeg cắt trước. Phân tích theo sau.",
    "the cut": "bản cắt",
    "Hook first": "Mở đầu trước",
    "A strong visual, line or action opens the reel.": "Một hình ảnh, câu nói hoặc hành động mạnh mở đầu reel.",
    "Keep the story": "Giữ mạch truyện",
    "Beats stay in order. No random highlights.": "Các nhịp giữ đúng thứ tự. Không cắt ngẫu nhiên.",
    "Land the ending": "Chốt phần kết",
    "A payoff beat closes the cut.": "Một nhịp cao trào khép lại bản cắt.",
    "Follow the subject": "Bám theo chủ thể",
    "9:16 crop tracks faces and saliency.": "Khung 9:16 theo dõi khuôn mặt và điểm nổi bật.",
    "On-device AI on supported Macs; cloud AI where native engines are not available. No watermark.": "AI trên thiết bị với Mac được hỗ trợ; AI trên đám mây khi máy không có engine gốc. Không có watermark.",
    "recent": "gần đây",
    "Recent cuts": "Bản cắt gần đây",
    "View all cuts": "Xem tất cả bản cắt",
    "dissect": "phân tích",
    "Reading the video": "Đang đọc video",
    "Warming up": "Đang khởi động",
    "Scan cuts": "Quét cảnh cắt",
    "ffmpeg scene detection": "ffmpeg phát hiện cảnh",
    "Read frames": "Đọc khung hình",
    "stills, text, faces, audio": "ảnh tĩnh, chữ, khuôn mặt, âm thanh",
    "Choose hook": "Chọn mở đầu",
    "score beats · build three cuts": "chấm điểm nhịp · dựng ba bản cắt",
    "Ready": "Sẵn sàng",
    "15s · 30s · 60s": "15 giây · 30 giây · 60 giây",
    "Runs locally. Leave this tab open.": "Chạy cục bộ. Giữ tab này mở.",
    "Cancel download": "Hủy tải xuống",
    "Back to source clean": "Quay lại làm sạch nguồn",
    "Back to ingest": "Quay lại nhập video",
    "New video": "Video mới",
    "Work files": "Tệp làm việc",
    "Renders": "Bản render",
    "All but source": "Tất cả trừ nguồn",
    "Clean": "Dọn dẹp",
    "Changed since this render — render again to see it.": "Đã thay đổi từ lần render này — render lại để xem.",
    "Speech was on, but no transcript came back.": "Đã bật lời nói nhưng không nhận được bản chép lời.",
    "Retry speech": "Thử lại lời nói",
    "hook": "mở đầu",
    "Opening beat": "Nhịp mở đầu",
    "Pick another hook →": "Chọn mở đầu khác →",
    "Hook lab →": "Phòng thử mở đầu →",
    "CC · transcript": "CC · bản chép lời",
    "Review link": "Liên kết xem lại",
    "moments": "khoảnh khắc",
    "Moments": "Khoảnh khắc",
    "Best": "Tốt nhất",
    "Timeline": "Dòng thời gian",
    "Show all": "Hiện tất cả",
    "Show more": "Hiện thêm",
    "smart cut": "cắt thông minh",
    "Smart Cut": "Cắt thông minh",
    "auto hook": "mở đầu tự động",
    "Reset hook": "Đặt lại mở đầu",
    "Edit cut": "Sửa bản cắt",
    "Drop a moment here to add it · drag a clip here to remove it": "Thả một khoảnh khắc vào đây để thêm · kéo clip vào đây để xóa",
    "Why this cut": "Vì sao cắt như vậy",
    "Save variant": "Lưu biến thể",
    "Advanced": "Nâng cao",
    "Story arc order": "Thứ tự mạch truyện",
    "Custom": "Tùy chỉnh",
    "All 15/30/60": "Tất cả 15/30/60",
    "A/B hooks": "Mở đầu A/B",
    "Automation mixer": "Bộ trộn tự động",
    "Reset 100%": "Đặt lại 100%",
    "Flatten": "Làm phẳng",
    "original audio": "âm thanh gốc",
    "original music stem": "bản nhạc gốc",
    "voice line": "dòng giọng nói",
    "music line": "dòng nhạc",

    // Edit / copy / sound
    "edit": "sửa",
    "Edit": "Sửa",
    "Copy, sound and text are optional. Render and Draft stay at the end.": "Viết lại, âm thanh và chữ là tùy chọn. Render và Draft luôn ở cuối.",
    "Copy, sound, text": "Viết lại, âm thanh, chữ",
    "Find text on screen": "Tìm chữ trên màn hình",
    "Scan the cut for baked-in captions, watermarks and screen UI.": "Quét bản cắt để tìm phụ đề, watermark và giao diện đã nằm sẵn trong hình.",
    "Not scanned yet. Find text to look for captions, watermarks and screen UI baked into the cut.": "Chưa quét. Bấm tìm chữ để soi phụ đề, watermark và giao diện nằm sẵn trong hình.",
    "Scan again": "Quét lại",
    "Retry scan": "Thử quét lại",
    "Clean": "Làm sạch",
    "Cover what should not be in the cut. The frame on the left is the real render.": "Che những gì không nên nằm trong bản cắt. Khung bên trái chính là bản render thật.",
    "No boxes yet. Scan for text on screen, or draw a box on the frame.": "Chưa có khung nào. Quét chữ trên màn hình, hoặc vẽ một khung trên khung hình.",
    "Drag a box to move it, pull a corner to resize.": "Kéo khung để di chuyển, kéo góc để đổi kích thước.",
    "Draw a box (B)": "Vẽ khung (B)",
    "Undo": "Hoàn tác",
    "Redo": "Làm lại",
    "Refresh": "Tải lại",
    "frame": "khung hình",
    "Blur": "Làm mờ",
    "Cover": "Che kín",
    "Crop": "Cắt khung",
    "AI fill": "AI lấp",
    "Finish": "Hoàn tất",
    "Back to edit": "Quay lại sửa",
    "Keys": "Phím tắt",
    "I own this footage": "Tôi sở hữu video này",
    "or have the rights to it": "hoặc có quyền sử dụng",
    "Drawn box": "Khung tự vẽ",
    "whole cut": "cả bản cắt",
    "manual": "tự vẽ",
    "scan": "quét",
    "Mode": "Chế độ",
    "Original": "Bản gốc",
    "New voice-over": "Lồng tiếng mới",
    "Dub voice": "Lồng giọng",
    "Music only": "Chỉ nhạc",
    "New voice + music": "Giọng mới + nhạc",
    "Original audio and transcript. No new voice or music.": "Âm thanh và bản chép lời gốc. Không thêm giọng hoặc nhạc.",
    "Voice-over · new voice over original audio": "Lồng tiếng · giọng mới trên âm thanh gốc",
    "Dub · replace only the voice": "Lồng giọng · chỉ thay giọng",
    "Music · replace original audio": "Nhạc · thay âm thanh gốc",
    "Full Replace · new voice and new music": "Thay toàn bộ · giọng mới và nhạc mới",
    "Copy": "Viết lại",
    "Translate the full video once, then write this cut.": "Dịch toàn bộ video một lần, rồi viết cho bản cắt này.",
    "Script style": "Phong cách kịch bản",
    "Smooth · natural short script": "Mượt · kịch bản ngắn tự nhiên",
    "Viral · punchy hook": "Viral · mở đầu mạnh",
    "Fun · playful and warm": "Vui · hóm hỉnh và ấm áp",
    "Creative · vivid and surprising": "Sáng tạo · sống động và bất ngờ",
    "Sad · intimate and restrained": "Buồn · gần gũi và tiết chế",
    "Chill · calm and understated": "Chill · nhẹ nhàng và kín đáo",
    "Faithful · translation only": "Trung thành · chỉ dịch",
    "Story cut": "Cắt truyện",
    "Choose a mode, then copy the cut. The full transcript is reused.": "Chọn chế độ, rồi viết lại bản cắt. Bản chép lời đầy đủ được tái sử dụng.",
    "Original audio and transcript.": "Âm thanh và bản chép lời gốc.",
    "Rewrite this cut →": "Viết lại bản cắt này →",
    "Sound": "Âm thanh",
    "Voice or music for this cut.": "Giọng nói hoặc nhạc cho bản cắt này.",
    "Mixer": "Bộ trộn",
    "Voice": "Giọng nói",
    "Music": "Nhạc",
    "Generate": "Tạo",
    "Use my recording": "Dùng bản ghi của tôi",
    "Voice list": "Danh sách giọng",
    "Rate": "Tốc độ",
    "Generate voice sample": "Tạo mẫu giọng",
    "The render uses the voice and settings above; this sample is only a preview.": "Bản render dùng giọng và cài đặt ở trên; mẫu này chỉ để nghe thử.",
    "Generate a short voice preview.": "Tạo bản nghe thử giọng ngắn.",
    "Choose recording": "Chọn bản ghi",
    "Fit your recording to the cut length.": "Khớp bản ghi với độ dài bản cắt.",
    "None": "Không",
    "Use my BGM": "Dùng nhạc nền của tôi",
    "No music": "Không nhạc",
    "My own track": "Nhạc của tôi",
    "Track": "Bản nhạc",
    "Choose BGM": "Chọn nhạc nền",
    "Clear": "Xóa",
    "Use your own music file.": "Dùng tệp nhạc của bạn.",
    "Music prompt": "Mô tả nhạc",
    "Music dB": "dB nhạc",
    "Duck under voice": "Giảm nhạc dưới giọng",
    "Beat sync": "Đồng bộ nhịp",
    "Choose a music source before rendering.": "Chọn nguồn nhạc trước khi render.",
    "Generate music preview": "Tạo bản nghe thử nhạc",
    "The render generates its own music bed from this prompt.": "Bản render tự tạo nhạc nền từ mô tả này.",
    "Texts & Effects": "Chữ & hiệu ứng",
    "Subtitles, text overlays and motion on the cut.": "Phụ đề, lớp chữ và chuyển động trên bản cắt.",
    "Burn in subtitles": "Ghi cứng phụ đề",
    "Top": "Trên",
    "Center": "Giữa",
    "Bottom": "Dưới",
    "Start": "Bắt đầu",
    "End": "Kết thúc",
    "Add text": "Thêm chữ",
    "Punch in": "Phóng to",
    "Shake": "Rung",
    "Circle (centre)": "Vòng tròn (giữa)",
    "Seconds": "Giây",
    "Add effect": "Thêm hiệu ứng",
    "Text and effects burn into the reel on 9:16 and 4:5. Caption position, font and cue edits live in Creator → Captions.": "Chữ và hiệu ứng được ghi vào reel ở 9:16 và 4:5. Vị trí, phông và sửa cue nằm trong Creator → Captions.",
    "Script": "Kịch bản",
    "The lines this cut will say.": "Những câu bản cắt này sẽ nói.",
    "Draft": "Nháp",
    "Render 30s reel": "Render reel 30 giây",
    "Activity": "Hoạt động",

    // Setup
    "Cloud, optional": "Đám mây, tùy chọn",
    "Intelligence": "Trí tuệ",
    "Transcription": "Chép lời",
    "Voice over": "Lồng tiếng",
    "Voice fit": "Khớp giọng",
    "Optional packs": "Gói tùy chọn",
    "Rights lock": "Khóa bản quyền",
    "Video links · yt-dlp": "Liên kết video · yt-dlp",
    "Preserve voice pitch & tone": "Giữ nguyên cao độ & âm sắc",
    "Preserve voice pitch &amp; tone": "Giữ nguyên cao độ & âm sắc",
    "Keeps the original pitch. Speeds a line up to 1.25×; if it still does not fit, the script is shortened instead of pushing the voice.": "Giữ nguyên cao độ gốc. Tăng tốc tối đa 1.25×; nếu vẫn không vừa, kịch bản sẽ được rút gọn thay vì ép giọng.",
    "Maximum speed": "Tốc độ tối đa",
    "Stretch engine": "Bộ kéo giãn",
    "Allow extreme chipmunk speed above 1.8×": "Cho phép tốc độ chipmunk cực cao trên 1.8×",
    "Spoken language": "Ngôn ngữ nói",
    "yt-dlp can read some public notes, but many RedNote links need a signed-in xhs_get session. The cookie stays in xhs_get; VibeCut never stores or reads it.": "yt-dlp có thể đọc một số bài công khai, nhưng nhiều liên kết RedNote cần phiên xhs_get đã đăng nhập. Cookie ở lại xhs_get; VibeCut không lưu hoặc đọc cookie.",
    "Optional packs": "Gói tùy chọn",
    "Require the own-footage tick before import and Clean": "Yêu cầu xác nhận sở hữu cảnh trước khi nhập và Dọn dẹp",
    "Open admin console ↗": "Mở bảng quản trị ↗",
    "Test OpenCode": "Kiểm tra OpenCode",
    "Test OpenRouter": "Kiểm tra OpenRouter",
    "Check TTS": "Kiểm tra TTS",
    "Live TTS": "TTS trực tiếp",
    "Check local STT": "Kiểm tra STT cục bộ",
    "Live STT": "STT trực tiếp",
    "Refresh catalogs": "Làm mới danh mục",

    // Voice Room
    "Every voice here,": "Mọi giọng ở đây,",
    "and your own.": "và giọng của bạn.",
    "Listen to any voice, clone yours from a recording, or clone a speaker from the cleanest clips of one of your videos.": "Nghe thử mọi giọng, nhân bản giọng bạn từ bản ghi, hoặc nhân bản người nói từ những đoạn sạch nhất trong video.",
    "No cloned voices yet. Clone one below.": "Chưa có giọng nhân bản. Hãy nhân bản bên dưới.",
    "clone a voice": "nhân bản giọng",
    "Clone a voice": "Nhân bản giọng",
    "Give 30 s to 3 min of clear speech. Only clone your own voice, or a speaker who gave you permission.": "Cung cấp 30 giây đến 3 phút giọng nói rõ. Chỉ nhân bản giọng của bạn hoặc người đã cho phép.",
    "stock voices": "giọng có sẵn",
    "Voices on this machine": "Giọng trên máy này",
    "Test line · every Play button speaks it": "Câu thử · mọi nút Phát sẽ đọc câu này",
    "Advanced voice fit": "Khớp giọng nâng cao",
    "Preserve voice keeps pitch and tone; lines are capped at 1.25× and the script is shortened if needed.": "Giữ giọng bảo toàn cao độ và âm sắc; câu được giới hạn 1.25× và kịch bản được rút gọn nếu cần.",
    "Preserve voice is off. Faster lines raise pitch and may create a chipmunk sound.": "Đã tắt giữ giọng. Câu nhanh hơn sẽ tăng cao độ và có thể tạo tiếng chipmunk.",
    "Max speed": "Tốc độ tối đa",
    "Allow extreme chipmunk speed above 1.8×": "Cho phép tốc độ chipmunk cực cao trên 1.8×",
    "Auto · Signalsmith if installed, then FFmpeg": "Tự động · Signalsmith nếu đã cài, sau đó FFmpeg",
    "FFmpeg · atempo": "FFmpeg · atempo",
    "Signalsmith Stretch": "Signalsmith Stretch",
    "Signalsmith Stretch · not installed": "Signalsmith Stretch · chưa cài",
    "Play": "Phát",
    "Stop": "Dừng",
    "Search voices": "Tìm giọng",
    "All languages": "Tất cả ngôn ngữ",
    "Not set up on this machine": "Chưa thiết lập trên máy này",
    "From a recording or a file": "Từ bản ghi hoặc tệp",
    "From a video": "Từ video",
    "Your voices": "Giọng của bạn",
    "Rename": "Đổi tên",
    "Delete": "Xóa",
  };

  const PATTERNS = [
    [/^Render (\d+)s reel$/, "Render reel $1 giây"],
    [/^Render (\d+)s reel ↗$/, "Render reel $1 giây ↗"],
    [/^(\d+) scenes$/, "$1 cảnh"],
    [/^(\d+) texts?$/, "$1 chữ"],
    [/^Review (\d+) texts?$/, "Xem lại $1 chữ"],
    [/^Clean (\d+) texts?$/, "Làm sạch $1 chữ"],
    [/^Clean (\d+) texts? · estimating…$/, "Làm sạch $1 chữ · đang ước lượng…"],
    [/^Clean (\d+) texts? · estimate unavailable$/, "Làm sạch $1 chữ · không ước lượng được"],
    [/^Clean (\d+) texts? · ~(.+)$/, "Làm sạch $1 chữ · ~$2"],
    [/^Finding text · (\d+)%$/, "Đang tìm chữ · $1%"],
    [/^Cleaning · (\d+)%$/, "Đang làm sạch · $1%"],
    [/^Encoding · (\d+)%$/, "Đang mã hóa · $1%"],
    [/^(\d+) voices$/, "$1 giọng"],
    [/^(\d+) moments?$/, "$1 khoảnh khắc"],
    [/^(\d+) beats?$/, "$1 nhịp"],
    [/^(\d+) attempts?$/, "$1 lần thử"],
    [/^(\d+) renders?$/, "$1 bản render"],
    [/^(\d+) events?$/, "$1 sự kiện"],
    [/^(\d+)%$/, "$1%"],
    [/^(\d+(?:\.\d+)?)s cut · (\d+) beats$/, "$1 giây cắt · $2 nhịp"],
    [/^(\d+) cuts? · (\d+) sources?$/, "$1 bản cắt · $2 nguồn"],
    [/^(\d+) moments? · (.+)$/, "$1 khoảnh khắc · $2"],
    [/^(\d+) · (\d+) shown$/, "$1 · hiện $2"],
    [/^(.+) · (.+) source · (\d+) moments · (\d+) deep-read · ([\d.]+)s analysis · (.+)$/, "$1 · nguồn $2 · $3 khoảnh khắc · $4 đọc sâu · phân tích $5 giây · $6"],
    [/^Hook (.+) → payoff (.+) · (\d+) beats · ([\d.]+)s$/, "Mở đầu $1 → kết $2 · $3 nhịp · $4 giây"],
    [/^(\d+) beats · ([\d.]+)s$/, "$1 nhịp · $2 giây"],
    [/^(\d+) beats · (.+) · no watermark$/, "$1 nhịp · $2 · không watermark"],
    [/^(\d+) beats · (.+)$/, "$1 nhịp · $2"],
    [/^(.+) · sends (.+) · may cost credits\.$/, "$1 · gửi $2 · có thể tốn tín dụng."],
    [/^Render calls (.+) · may cost credits\.$/, "Render gọi $1 · có thể tốn tín dụng."],
    [/^Cached · no new call$/, "Đã lưu · không gọi mới"],
  ];

  const SKIP = [
    "script", "style", "textarea", "input", "code", "pre",
    "[contenteditable='true']", "[data-i18n-skip]",
    "#transcript-panel", ".transcript-list", ".recent-grid", ".recent-all-list",
    "#history-list", ".vr-voices", ".vr-mine", ".vr-missing-list",
  ].join(",");

  function current() {
    try {
      const param = new URLSearchParams(window.location.search).get("lang");
      if (param && SUPPORTED.includes(param)) {
        localStorage.setItem(KEY, param);
        return param;
      }
      const stored = localStorage.getItem(KEY);
      if (stored && SUPPORTED.includes(stored)) return stored;
    } catch (_) { /* storage may be unavailable */ }
    return "en";
  }

  function t(value) {
    return current() === "vi" ? translateValue(value) : value;
  }

  function tBlock(value) {
    if (current() !== "vi") return value;
    return String(value).split("\n").map((line) => {
      const trailing = line.endsWith(".") ? "." : "";
      if (line.startsWith("Deletes: ")) {
        return `Xóa: ${translateValue(line.slice(9).replace(/\.$/, ""))}${trailing}`;
      }
      if (line.startsWith("Keeps: ")) {
        return `Giữ: ${translateValue(line.slice(7).replace(/\.$/, ""))}${trailing}`;
      }
      return translateValue(line);
    }).join("\n");
  }

  function translateValue(value) {
    if (!value) return value;
    const trimmed = String(value).trim();
    if (!trimmed) return value;
    const direct = VI[trimmed];
    if (direct) return String(value).replace(trimmed, direct);
    for (const [pattern, replacement] of PATTERNS) {
      if (pattern.test(trimmed)) return String(value).replace(trimmed, trimmed.replace(pattern, replacement));
    }
    return value;
  }

  function shouldSkip(node) {
    const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    return !element || !element.closest || Boolean(element.closest(SKIP));
  }

  function translateAttributes(element) {
    for (const name of ["placeholder", "title", "aria-label", "alt"]) {
      const value = element.getAttribute && element.getAttribute(name);
      if (!value) continue;
      const next = translateValue(value);
      if (next !== value) element.setAttribute(name, next);
    }
  }

  function walk(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      if (shouldSkip(root)) return;
      const next = translateValue(root.nodeValue);
      if (next !== root.nodeValue) root.nodeValue = next;
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
    if (root.nodeType === Node.ELEMENT_NODE && shouldSkip(root)) return;
    if (root.nodeType === Node.ELEMENT_NODE) translateAttributes(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let node = walker.nextNode();
    while (node) {
      if (node.nodeType === Node.TEXT_NODE) {
        if (!shouldSkip(node)) {
          const next = translateValue(node.nodeValue);
          if (next !== node.nodeValue) node.nodeValue = next;
        }
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        translateAttributes(node);
      }
      node = walker.nextNode();
    }
  }

  function syncSelector(lang) {
    const selector = document.getElementById("ui-language");
    if (!selector) return;
    if (selector.matches("select")) {
      selector.value = lang;
      return;
    }
    for (const button of selector.querySelectorAll("[data-lang]")) {
      const active = button.dataset.lang === lang;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  function apply() {
    const lang = current();
    document.documentElement.lang = lang;
    syncSelector(lang);
    if (lang !== "vi") return;
    walk(document.body);
  }

  function setLanguage(lang) {
    if (!SUPPORTED.includes(lang) || lang === current()) return;
    if (window.VibeCutClassicHasUnsaved?.()) {
      const warning = t(
        "Switching language reloads the page and discards unsaved cut changes. Continue?",
      );
      if (!window.confirm(warning)) return;
    }
    try { localStorage.setItem(KEY, lang); } catch (_) { /* ignore */ }
    // The query string is a one-visit override. Remove it before reloading,
    // otherwise ?lang=vi keeps winning after the user picks English.
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete("lang");
      window.location.replace(url.toString());
    } catch (_) {
      window.location.reload();
    }
  }

  function installSelector() {
    const selector = document.getElementById("ui-language");
    if (!selector) return;
    if (selector.matches("select")) {
      selector.value = current();
      selector.addEventListener("change", () => setLanguage(selector.value));
      return;
    }
    for (const button of selector.querySelectorAll("[data-lang]")) {
      button.addEventListener("click", () => setLanguage(button.dataset.lang));
    }
  }

  function start() {
    installSelector();
    apply();
    // No live DOM observer: dynamic English copy is source copy. Translate
    // only explicit UI copy at load time. New dynamic strings can opt in with
    // data-i18n or a future t() call.
  }

  window.VibeCutI18N = { current, setLanguage, apply, t, tBlock, translateValue };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
