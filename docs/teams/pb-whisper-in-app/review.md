# P-B · On-device speech helper

**Verdict — dev-bundle acceptance passed.** The signed helper transcribed the 11-second JFK sample with networking unnecessary and only system directories on PATH. The frozen sidecar, running alone on port 8831 against the Codex scratch root, reported missing speech weights, then ready as soon as the verified pack appeared. Vietnamese accuracy, dubbing and the real Xcode app remain for founder testing.

## Build and pack

Built MIT-licensed whisper.cpp v1.8.2 at commit `4979e04f5dcaccb36057e059bbaed8a2f5288315`. The build checks the checkout, license, embedded shader symbol, Mach-O dependencies and absence of home-directory strings. The runtime log confirmed use of the embedded Metal library on Apple M1. The source configuration, link listing and CLI help are in `build/whisper-cpp/BUILD.txt`. [Pinned upstream release](https://github.com/ggml-org/whisper.cpp/tree/4979e04f5dcaccb36057e059bbaed8a2f5288315)

The signed helper is 2,764,608 bytes. Allocated dev-bundle size was 1,137,420 KiB before and 1,030,272 KiB after. This difference includes build-environment changes. The shared build venv was unavailable, so the normal build ran in a private venv. The optional Core ML fill package was also absent during this build, which reported PyTorch fallback. The helper check, GPL scan and individual helper signature verification passed.

The only speech-pack download is the unquantized GGML large-v3-turbo weights. Measured 1,624,555,275 bytes and SHA-256 `1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69`. The JFK test used separate tiny English weights, 77,704,715 bytes, SHA-256 `921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f`. Both measurements matched the publisher metadata at revision `5359861c739e955e79d9a303bcbc70fb988958b1`. [Pinned model files](https://huggingface.co/ggerganov/whisper.cpp/tree/5359861c739e955e79d9a303bcbc70fb988958b1)

## Runtime evidence

The signed helper returned 22 timed words in 8.15 seconds wall clock. The first word was “And” at 0.32–0.40 s and the last was “country.” at 10.02–10.76 s. A separate run through the Python adapter returned the same 22 words in 0.51 s after warm-up. These are sample measurements with the tiny English model.

> And so my fellow Americans ask not what your country can do for you ask what you can do for your country.

Dependency output from `otool -L`:

```text
build/DuckSuite.app/Contents/Helpers/whisper-cli:
	/System/Library/Frameworks/Accelerate.framework/Versions/A/Accelerate (compatibility version 1.0.0, current version 4.0.0)
	/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1359.0.0)
	/System/Library/Frameworks/Foundation.framework/Versions/C/Foundation (compatibility version 300.0.0, current version 5027.0.69)
	/System/Library/Frameworks/Metal.framework/Versions/A/Metal (compatibility version 1.0.0, current version 382.5.3)
	/System/Library/Frameworks/MetalKit.framework/Versions/A/MetalKit (compatibility version 1.0.0, current version 174.4.0)
	/usr/lib/libc++.1.dylib (compatibility version 1.0.0, current version 2200.27.0)
	/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation (compatibility version 150.0.0, current version 5027.0.69)
	/usr/lib/libobjc.A.dylib (compatibility version 1.0.0, current version 228.0.0)
```

The runner passes an explicit language or auto-detect, vocabulary via `--prompt`, and full JSON via `-ojf`. The adapter converts millisecond offsets and token probabilities to timed words and supplies the existing transcript filters. The CLI omits the old backend's segment no-speech and compression scores. Those particular thresholds therefore lack a direct equivalent. Chunk reads retain cancellation, heartbeat and timeout handling. The Whisper cache key includes the runner version, weights path, language and vocabulary.

The MLX runner fallback was removed. Existing safetensors packs display an update prompt and keep their files. The user speech slot accepts one GGML .bin file with a valid header. The Swift chooser and cleanup fixture were updated with founder approval. A frozen sidecar resolves the runner exclusively within its app. Development PATH lookup rejects candidates inside the data or pack root, including symlinks into those folders.

## Tests and founder check

433 tests passed with five warnings. One check skipped because the separate Xcode app was absent. Both helper layouts were exercised in fixture tests. JavaScript syntax passed. The dev app window stayed closed.

1. In the PO-built Xcode app, open Settings. If the older speech pack is installed, confirm its update message. Download the speech pack and check that Settings reports it installed.
2. Disconnect the network. On a founder-owned Vietnamese clip with a known phrase, choose Vietnamese and run Check using the local speech pack. Compare the transcript with the phrase and inspect word boundaries around pauses and accented words.
3. Dub a short section using that transcript and listen for alignment. Record the clip duration, elapsed Check time, mistranscriptions and timing errors before comparing any smaller model.

No founder media was used. Product-owned documentation should replace the former MLX pack and model-folder instructions with the GGML weights and update behavior.
