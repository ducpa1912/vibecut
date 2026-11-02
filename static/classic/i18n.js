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
    "checking engine…": "đang kiểm tra engine…",
    "ffmpeg · local analysis": "ffmpeg · phân tích cục bộ",
    "Save setup": "Lưu cài đặt",
    "Saving…": "Đang lưu…",
    "Cancel": "Hủy",
    "Save": "Lưu",
    "Done": "Xong",
    "Delete": "Xóa",
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
    [/^(\d+) voices$/, "$1 giọng"],
    [/^(\d+) moments?$/, "$1 khoảnh khắc"],
    [/^(\d+) beats?$/, "$1 nhịp"],
    [/^(\d+) attempts?$/, "$1 lần thử"],
    [/^(\d+) renders?$/, "$1 bản render"],
    [/^(\d+) events?$/, "$1 sự kiện"],
    [/^(\d+)%$/, "$1%"],
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
    if (!SUPPORTED.includes(lang)) return;
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

  window.VibeCutI18N = { current, setLanguage, apply, translateValue };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
