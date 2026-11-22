# DIRECTIVE & IMPLEMENTATION PLAN: LEAGUE OF LEGENDS SHORTS QUALITY GATES & FALLBACK MONTAGE ENGINE

> **Target Model:** Claude 3.5 / 3.7 Sonnet or Claude Opus  
> **Channel:** Dwannellenga (League of Legends Gaming — Shorts / TikTok / Reels)  
> **Core Directive:** ZERO SYCOPHANCY (Sykofancja = 0)  
> **Repository:** `Shortsyt` (`lol_agent/` module)

---

## 1. EXECUTIVE SUMMARY & MISSION

The objective is to audit, harden, and optimize the automated **Quality Gates** in the `Shortsyt` League of Legends pipeline (`lol_agent/`). 

### Core Problems Being Solved:
1. **Gemini Sycophancy & Hallucinations:** Gemini routinely generates generic, outdated AI titles (e.g., *"Master Katarina Insane Pentakill Gameplay 2024"*), flatters mediocre plays, and hallucinates in-game context (e.g., claiming a "Tower Dive" when the fight occurred in the jungle river).
2. **False Approvals & The "Advisory" Anti-Pattern:** In `lol_agent/run_lol_agent.py`, the system currently logs:
   ```python
   log("Proceeding with upload anyway (score gate is advisory)")
   ```
   This fatal flaw must be eradicated. Substandard clips ruin channel authority and trigger YouTube algorithmic suppression.
3. **Binary Discard of Good Raw Clips:** Currently, if a montage fails (e.g., bad beat sync or awkward cuts), the entire play is either dumped or force-uploaded in a damaged state. 
4. **Missing Distinction:** The system lacks a clear demarcation between **inherently bad raw material** (which must be discarded immediately) and **good raw material suffering from a flawed montage style** (which must be re-edited using an alternative style).

---

## 2. TAXONOMY: DEFINING "GOOD MATERIAL" VS "TRASH MATERIAL"

The pipeline must establish a rigid **Pre-Montage Material Viability Gate** in `lol_agent/lol_quality_validator.py` before expensive rendering cycles begin.

```
                    [Raw Video Clip from Medal/Outplayed]
                                      │
                                      ▼
               ┌──────────────────────────────────────────────┐
               │  GATE 0: RAW MATERIAL VIABILITY CHECK        │
               │  (Computer Vision & Gameplay Analysis)       │
               └──────────────────────────────────────────────┘
                               /              \
                   [TRASH MATERIAL]        [GOOD MATERIAL]
                          │                       │
                          ▼                       ▼
                   [HARD DISCARD]          [PROCEED TO MONTAGE]
              (No rendering, log reason)   (Pass to Montage Director)
```

### A. Trash Material (Hard Discard — Zero Rendering):
A clip is immediately rejected and archived without rendering if it matches any of these criteria:
* **Passive Kill / Anti-Climax:** Single isolated kill with no skillshot dodges, no high-APM combos, or merely auto-attacking an escaping target with 5% HP.
* **Instant Death Payoff:** The player gets a kill but dies within ≤1.2s without securing a trade or multi-kill (creates a pathetic, anticlimactic feeling).
* **Walking Simulator (Dead Air):** >70% of the clip duration consists of traversing lanes/jungle without enemy engagement or threatening cooldown exchanges.
* **Extreme Chaos / Unframeable Action:** Key action occurs outside the 9:16 vertical crop window (tracking confidence <65%), or combatants leave the frame entirely during combat peaks.
* **Low Source Fidelity:** Source resolution <720p or framerate <30fps.

### B. Good Material (Worthy of Production & Fallback Protection):
A clip qualifies as high-value content if it contains:
* **Multi-Kill Sequences:** Verified Double, Triple, Quadra, or Pentakill.
* **Mechanical Outplay / Clutch:**
  * Reset chains on high-mobility champions (Katarina, Kha'Zix, Zed, Viego, Samira, Pyke).
  * 1vX turnaround with HP dropping below 15% (clutch factor).
  * Major objective steals (Baron / Elder Dragon).
  * Pixel-perfect skillshot dodge (e.g., Flash over Malphite R / Ahri charm).
* **High Combat Density:** Continuous combat engagement spanning at least 4.0–12.0 seconds.
* **Frame Centering:** The player champion and primary target remain trackable within the 9:16 vertical viewport.

---

## 3. ARCHITECTURE: 3-TIER QUALITY GATES

```
┌────────────────────────────────────────────────────────────────────────┐
│ BRAMKA 1: Pre-Flight CV & Pacing Guard (lol_quality_validator.py)       │
│ - Raw Material Viability (Outplay vs Trash check)                      │
│ - Action Hook Guard: First combat impact within ≤1.5s (cut dead intro) │
│ - Action Outro Guard: Hard trim max 1.8s after final elimination       │
│ - Authenticity Guard: Match OCR/Medal data to real kill peaks          │
└────────────────────────────────────────────────────────────────────────┘
                                   │ (PASS)
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ MONTAGE RENDER (lol_montage_director.py + lol_editor.py)               │
│ - Applies chosen visual style, smart camera tracking, and beat sync    │
└────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ BRAMKA 2: Post-Render Audio/Video QA (lol_quality_scorer.py)           │
│ - Kill Coverage: ≥75% of detected kill peaks present in montage        │
│ - Beat Sync Precision: Drop delta ≤0.50s (Warning at 1.0s, Fail >1.5s) │
│ - First Frame Saturation & Motion: HSV Sat >80, Motion delta >15       │
│ - Audio Guard: Zero silence on start (max allowable latency <0.8s)     │
│ - Camera Stability: Peak velocity ≤65 px/step (no nauseating snaps)    │
│ - Strict Score Threshold: COMPOSITE SCORE ≥ 70 / 100                   │
└────────────────────────────────────────────────────────────────────────┘
                     /                                  \
            (PASS: Score ≥ 70)                  (FAIL: Score < 70)
                    │                                    │
                    ▼                                    ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│ BRAMKA 3: Semantic & Metadata Judge  │  │ STYLE MUTATION ENGINE        │
│ (Claude Opus - Zero Sycophancy)      │  │ (Automatic Re-Montage Loop)  │
│ - Hook Punchiness & Curiosity Gap    │  │ - Diagnoses failure reason   │
│ - Anti-Cringe / Anti-Bot AI rules    │  │ - Selects Fallback Style     │
│ - Accuracy vs Real Context           │  │ - Re-renders & Re-audits     │
└──────────────────────────────────────┘  └──────────────────────────────┘
                    │                                    │
                    ▼                                    ▼
             [YOUTUBE UPLOAD]                    [MAX 2 RETRIES]
                                                 (If still <70 → HARD REJECT)
```

---

## 4. THE STYLE MUTATION ENGINE (ALTERNATIVE MONTAGE PROFILES)

When a **Good Raw Material** clip fails Bramka 2, the system must not discard it or bypass the gate. It initiates an automated fallback re-montage using specialized archetypes:

```
Failure Diagnosis               Fallback Editing Style
─────────────────────────────────────────────────────────────────────────
Awkward jump-cuts / pacing  ──► STYLE B: SPEED-RAMP FLOW (No Cuts)
Beat sync error >1.5s       ──► STYLE C: BEAT REALIGN (Music Track Swap)
Slow hook / low first frame ──► STYLE D: IN MEDIA RES (Combat First)
Violent camera shake in 1v1 ──► STYLE E: CINEMATIC DUEL (Stable Centroid)
```

### Style Specifications:

#### 1. Primary Style: Directorial Jump-Cut (`CHAOTIC_TEAMFIGHT` / `SPACED_RAMPAGE`)
* **Behavior:** Default baseline. Trims idle walking between kills (>3.5s gaps) using tight jump-cuts while keeping camera locked on player resets.
* **When It Fails:** If the jump-cut breaks visual continuity or skips crucial cooldown setup.

#### 2. Fallback Style A: Speed-Ramp Flow (`SPEED_RAMP_FLOW`)
* **Behavior:** **Zero cuts.** Instead of jump-cutting through dead air, the footage accelerates by 2.5x–3.5x between kills with motion-blur interpolation, slowing back to 1.0x right as abilities cast.
* **Target Fix:** Solves `kill_coverage` drops and disorienting jump-cuts. Maintains full spatial awareness of the map.

#### 3. Fallback Style B: In Media Res (`COMBAT_FIRST_HOOK`)
* **Behavior:** Hard cut directly into the initial strike. The clip begins 0.2s before the first crowd-control ability or high-damage burst lands. Zero buildup.
* **Target Fix:** Solves `first_frame_score` failures and `hook_latency > 1.5s`.

#### 4. Fallback Style C: Cinematic Duel (`SOLO_EGO_CINEMATIC`)
* **Behavior:** Wider framing using `duel_centroid` (keeps both combatants in view), smooth zoom-punch on impact (1.15x), followed by dramatic 0.5x slow-motion on the fatal blow.
* **Target Fix:** Solves camera jitter (`velocity > 70`) and tracking failures in 1v1 outplays.

#### 5. Fallback Style D: Audio Beat Re-Alignment
* **Behavior:** Scans `lol_music/` for an alternative track whose drop matches the primary kill timestamp, or calculates an intentional offset so the drop lands synchronously on the elimination frame.
* **Target Fix:** Solves `beat_sync_error > 1.5s`.

---

## 5. REPOSITORY CODE MAPPING & FILE RESPONSIBILITIES

| File | Current Implementation | Required Opus Refactoring |
| :--- | :--- | :--- |
| `lol_agent/run_lol_agent.py` | Line 350 contains advisory upload bypass (`Proceeding with upload anyway`). | Remove advisory mode. Implement two-pass loop: Try Primary Style -> If Fail -> Diagnose -> Apply Fallback Style -> If Still Fail -> Discard to `rejected_montages/`. |
| `lol_agent/lol_quality_validator.py` | Contains `validate_pre_flight` and `validate_montage_segments`. | Add explicit `is_raw_material_viable()` gate with thresholds for kill quality, movement ratio, and combat density. |
| `lol_agent/lol_quality_scorer.py` | Calculates composite score (0-100) with `QUALITY_THRESHOLD = 65`. | Raise threshold to **70**. Add diagnostic error codes (`ERR_BEAT_SYNC`, `ERR_PACING`, `ERR_HOOK`, `ERR_CAMERA`) mapped directly to fallback styles. |
| `lol_agent/lol_montage_director.py` | Contains 4 basic archetypes. | Add formal definitions for `SPEED_RAMP_FLOW`, `IN_MEDIA_RES`, and `SOLO_EGO_CINEMATIC`. |
| `lol_agent/lol_smart_titles.py` | Relies on Gemini with weak prompt constraints. | Replace with Claude Opus prompt template enforcing zero sycophancy, context accuracy (tower dive vs river), and proven channel archetypes. |
| `lol_agent/qa_after_render.py` | Standalone post-render script for OCR and velocity. | Integrate output directly into `lol_quality_scorer.py` feedback loop. |

---

## 6. MASTER PROMPT FOR CLAUDE OPUS (COPY & PASTE READY)

Copy the prompt block below and feed it directly into Claude Opus:

```markdown
You are an uncompromising Executive Creative Director for viral League of Legends Shorts/TikTok content and the Lead Video Pipeline Architect for the channel 'Dwannellenga'.

Your objective is to audit, harden, and refactor the automated QUALITY GATES and implement an ALTERNATIVE MONTAGE FALLBACK ENGINE in the 'Shortsyt' codebase (`lol_agent/` module).

### 1. CORE OPERATING PRINCIPLE: ZERO SYCOPHANCY (Sycophancy = 0)
- Zero flattery, zero generic approval, zero leniency.
- League of Legends players are among the most cynical, cringe-sensitive audiences online. If a title sounds like an outdated 2018 AI bot ("Insane Katarina Pentakill Outplay"), or a clip showcases a boring last-hit with 4 seconds of aimless walking, your mandate is to REJECT it immediately.
- In `lol_agent/run_lol_agent.py`, the pipeline currently contains this flaw:
  `log("Proceeding with upload anyway (score gate is advisory)")`
  You must ELIMINATE this behavior. Substandard clips must never reach YouTube. Either a short meets rigorous criteria (≥70/100), gets successfully repaired via an alternative montage style, or gets discarded.

### 2. SYSTEM CONTEXT & TARGET FILES
- Repository: `Shortsyt`
- Channel: `Dwannellenga` (Focus champions: Katarina, Kha'Zix, Zed, Yasuo, outplays, resets, multi-kills).
- Key files to refactor:
  1. `lol_agent/lol_quality_validator.py` (Pre-montage raw material validation).
  2. `lol_agent/lol_montage_director.py` (Montage styles & fallback profiles).
  3. `lol_agent/lol_quality_scorer.py` (Post-render scoring and failure diagnosis).
  4. `lol_agent/run_lol_agent.py` (Production pipeline execution loop).
  5. `lol_agent/lol_smart_titles.py` (High-CTR title generation & context guard).

### 3. ARCHITECTURAL REQUIREMENTS TO IMPLEMENT

#### A. Raw Material Viability Gate (Pre-Montage Filter)
Define clear algorithmic and heuristic rules to distinguish TRASH from GOOD raw material before calling `lol_editor.py`:
- Reject: passive kills, immediate post-kill deaths, >70% idle walking time, unframeable chaos (tracking confidence <65%).
- Accept: multi-kills, outplays with HP <20%, rapid reset chains, clutch objective steals.

#### B. Alternative Montage Styles (The Mutation Engine)
When good raw material fails the post-render score (<70), trigger an automatic re-montage using a diagnosed fallback style:
1. `SPEED_RAMP_FLOW`: Replaces choppy jump-cuts with continuous speed-ramping (2.5x–3.5x between action peaks).
2. `IN_MEDIA_RES`: Eliminates sluggish setups; starts 0.2s before first strike.
3. `CINEMATIC_DUEL`: Stabilizes jittery tracking in 1v1 fights with a smooth centroid anchor and slow-motion finish.
4. `BEAT_REALIGN`: Swaps the audio track or offsets timing when music drop error exceeds 1.5s.

#### C. Post-Render Quality Scoring (Harden Thresholds)
- Raise `QUALITY_THRESHOLD` from 65 to 70.
- Return structured diagnostic failure codes (`ERR_BEAT_SYNC`, `ERR_HOOK_LATENCY`, `ERR_PACING`, `ERR_CAMERA_SHAKE`).
- Integrate OCR kill detection and camera peak velocity directly into the score.

#### D. Semantic Title Gate (Zero AI Cringe)
- Replace generic Gemini patterns with punchy human-like archetypes:
  - DISRESPECT / EGO: "They Grouped For Free 💀", "Walking Up Like That Is Crazy 💀"
  - SPEED / STATEMENT: "Entire Team Disappeared in 2 Seconds ⚡"
  - STORY / TURNAROUND: "Duel Accepted. Duel Won. 💀"
  - MECHANICAL FLEX: "Pixel-Perfect Reaction 🔥", "Dodge Everything, Hit Everything 👑"
- Enforce strict contextual accuracy: forbid "Tower Dive" if the play was in the river; forbid "Early Game" for teamfights with Baron buff.
- 100% English only.

### 4. DELIVERABLES REQUIRED FROM YOU
1. **Critical Audit:** Point out specific flaws, edge cases, and exploit vectors in the existing files.
2. **Concrete Code Refactoring:**
   - Updated `lol_quality_validator.py` with the `is_raw_material_viable()` function.
   - Updated `lol_montage_director.py` featuring the fallback style profiles.
   - Refactored `run_lol_agent.py` showing the fallback re-montage loop (kill the advisory bypass).
   - High-CTR Title Generation Prompt with zero-sycophancy evaluation criteria.

Provide production-ready code and an uncompromising critique. Sycophancy = 0.
```

---

## 7. EXECUTION SUMMARY FOR LOCAL PIPELINE

Once Claude Opus reviews this directive and provides the refactored code modules:
1. Apply the updated `is_raw_material_viable()` logic in [lol_quality_validator.py](file:///c:/Users/mz100/OneDrive/Michal/Shortsyt/lol_agent/lol_quality_validator.py).
2. Replace the advisory upload bypass in [run_lol_agent.py](file:///c:/Users/mz100/OneDrive/Michal/Shortsyt/lol_agent/run_lol_agent.py) with the two-pass retry loop.
3. Update [lol_montage_director.py](file:///c:/Users/mz100/OneDrive/Michal/Shortsyt/lol_agent/lol_montage_director.py) to register the `SPEED_RAMP_FLOW` and `IN_MEDIA_RES` styles.
4. Verify the new threshold by running test benchmarks on real clips from `lol_agent/`.
