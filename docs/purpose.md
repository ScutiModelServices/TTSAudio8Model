# Purpose

**Kind:** text (+ optional reference clip) → audio

**Group:** Text-to-Speech

**Tags:** `gpu`, `streaming`, `voice-cloning`, `multilingual`

| | |
|---|---|
| Input | Text, voice name, seed, temperature. To add a cloned voice: a WAV clip (≤10 MB) plus its exact transcript (admin `PUT /admin/voices/{name}`). |
| Output | WAV file (16-bit mono). |
| Runs on | NVIDIA GPU (CUDA). 23 languages. |

**Use for:** realistic speech and voice cloning from a short clip.
**Not for:** machines without a GPU, low-latency bulk speech.
