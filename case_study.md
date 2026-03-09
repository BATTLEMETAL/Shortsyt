# 🧠 Shortsyt: Autonomous AI Content Pipeline & Real-Time Adaptation Loop

## 📝 Overview
**Shortsyt** is a fully autonomous, production-ready AI pipeline designed to generate, narrate, edit, and publish YouTube Shorts. Built around the "Cash Cow" concept, it currently specializes in the **Dark Psychology** niche. 

What sets this project apart is its **Phase 4: Real-Time Engagement Feedback Loop** — an autonomous system that doesn't just create content, but actively monitors its initial performance on YouTube and dynamically mutates its own prompts for future videos to avoid algorithmic decay.

---

## 🏗️ Core Architecture

### 1. Script Generation (`agent_dark_psychology.py` & `synapsa_bridge.py`)
- Instructs the LLM (Synapsa / Qwen) to generate highly engaging 40-70 word scripts focusing on the "Hook-Trick-Warning" framework.
- Enforces strict storytelling loops (the last sentence seamlessly connects to the first sentence) and compels comments as the Call-to-Action.
- Maintains a deduplication memory (`topic_history.json`) to prevent identical concepts from recurring.

### 2. Audio Validation & TTS
- Strips any unwanted tags from the LLM output and generates hyper-realistic Text-to-Speech audio (using `edge-tts`).
- Calculates precise audio length (optimizing for the 20-45s retention sweet spot).
- Applies `FFmpeg silenceremove` to cut out dead air at the start and end of the audio, ensuring a perfect, endless loop on the YouTube Shorts player.

### 3. Visuals & Pacing (`cashcow_generator.py`)
- Automatically fetches relevant, royalty-free background videos (e.g., moody, dynamic visuals).
- Passes the audio through an **AI Whisper model** to generate precise `.vtt` / `.ass` subtitles.
- Injects Hormozi-style **Pop-Zoom animations** word-by-word.
- Uses semantic styling: Highlights core emotional keywords (e.g., FEAR, TRAP, EXPOSED) in red, and colors the loop-triggering closing sentences in yellow.
- Merges a low-volume (18%) atmospheric dark music track beneath the narration.

### 4. Diagnostic Pre-Flight (`analyze_video_features.py`)
- Before publishing, an internal auditor script intercepts the `.mp4`.
- Analyzes resolution (requires 9:16 vertical), duration, and audio levels.
- Parses the subtitle metadata (`.ass`) up to the `0:00:03.00` mark to calculate **Hook Density**. If the opening presents more than 12 words in 3 seconds, it halts the upload due to high "Swipe Away" risk.

### 5. Deployment (`upload_youtube.py`)
- Safely authenticates via OAuth2 and securely uploads the video via the official YouTube Data API.
- Generates an SEO block with niche-specific tags and schedules staggered releases (e.g., immediate, and +8 hours for peak evening traffic).
- Logs the official `video_id` into `publish_report.json`.

---

## 🚀 The "Secret Sauce": Real-Time Feedback Loop (Phase 4)

Standard AI generators suffer from "Mode Collapse"—they find one viral format and repeat it until the audience is bored. Shortsyt solves this through the **MicroEVS (Early Velocity Score)** architecture.

### How It Works:
1. **Live Scraping (`real_time_monitor_agent.py`):** 
   When it's time to generate the day's 2nd video, the system pauses and connects to the **YouTube Analytics API**. It fetches the exact performance metrics (Views, Average View Duration, Engagement) of the *previous* video published hours earlier.

2. **MicroEVS Calculation:**
   The system calculates the mathematical velocity:
   ```math
   MicroEVS = VPM_60 \times (Viewed\_Percentage / Swiped\_Percentage) \times Engagement\_Factor
   ```

3. **Dynamic Prompt Injection (`dynamic_pattern_agent.py`):**
   Based on the MicroEVS score, the agent selects an adaptation state and explicitly forces a prompt override (via `os.environ["SYNAPSA_ADAPTATION_DIRECTIVE"]`) onto the LLM:
   - 🟢 **State S (Hyper-Clone) [>150%]:** Viral hit. The prompt injection forces the AI to clone the exact grammatical syntax of the hook, only changing the subject.
   - 🟡 **State A (Soft-Mutate) [105%-150%]:** Good traction. Instructs the AI to keep the core topic but change the Hook type (e.g., transform a Question into a Shocking Statement).
   - 🟠 **State B (Explore) [<105%]:** Stagnation. The agent ditches the current hook and explores a previously successful style.
   - 🔴 **State F (Hard Pivot) [<80%]:** Total algorithmic rejection. The specific topic is banned and sent to `quarantine.json` (14-day timeout). The prompt forces a completely new educational tone and a sub-4-word hook length.

4. **Decay Logic:**
   To prevent audience fatigue, if the AI achieves "State S" three times consecutively, it triggers a forced "Hard Pivot" to discover new narrative patterns.

---

## 🛠️ Tech Stack
- **AI / LLM:** Qwen (DeepSeek) via ChatML
- **Audio:** `edge-tts`, `whisper`
- **Video:** `moviepy`, `ffmpeg`
- **Analytics:** `google-api-python-client` (YouTube Data & Analytics v2)
- **Automation:** Python, Windows Task Scheduler (`start_daily.bat`)

## 💡 Future Roadmap
- Expanding the niche from strictly Dark Psychology to "Brainrot" (high-stimulation, colloquial gaming content).
- Full automation of thumbnail generation using diffusion models based on the initial hook. 

*(This AI agent is currently active and fully autonomous).*
