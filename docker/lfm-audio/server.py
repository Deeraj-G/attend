"""Local HTTP wrapper around LFM2.5-Audio-1.5B (STT + TTS) for testing.

Uses the `liquid-audio` package's sequential-generation mode (plain ASR/TTS,
not the interleaved chat mode). See https://github.com/Liquid4All/liquid-audio
for the reference examples this mirrors.
"""

import os
import tempfile

import soundfile as sf
import torch
from fastapi import FastAPI, UploadFile
from fastapi.responses import Response
from liquid_audio import ChatState, LFM2AudioModel, LFM2AudioProcessor

MODEL_PATH = os.environ.get("LFM_AUDIO_MODEL_PATH", "LiquidAI/LFM2.5-Audio-1.5B")
# Both default to device="cuda" in liquid-audio; this container has no GPU.
DEVICE = os.environ.get("LFM_AUDIO_DEVICE", "cpu")
DTYPE = getattr(torch, os.environ.get("LFM_AUDIO_DTYPE", "float32"))

app = FastAPI(title="lfm-audio-local")

processor = LFM2AudioProcessor.from_pretrained(MODEL_PATH, device=DEVICE).eval()
model = LFM2AudioModel.from_pretrained(MODEL_PATH, dtype=DTYPE, device=DEVICE).eval()


@app.get("/health")
def health():
    return {"status": "ok", "model_path": MODEL_PATH}


@app.post("/transcribe")
async def transcribe(audio: UploadFile):
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(await audio.read())
        tmp.flush()
        wav, sampling_rate = sf.read(tmp.name, dtype="float32")

    chat = ChatState(processor)
    chat.new_turn("system")
    chat.add_text("Perform ASR.")
    chat.end_turn()
    chat.new_turn("user")
    chat.add_audio(torch.from_numpy(wav).unsqueeze(0), sampling_rate)
    chat.end_turn()
    chat.new_turn("assistant")

    text = ""
    with torch.no_grad():
        for t in model.generate_sequential(**chat, max_new_tokens=512):
            if t.numel() == 1:
                text += processor.text.decode(t)
    return {"text": text}


@app.post("/synthesize")
async def synthesize(text: str):
    chat = ChatState(processor)
    chat.new_turn("system")
    chat.add_text("Perform TTS.")
    chat.end_turn()
    chat.new_turn("user")
    chat.add_text(text)
    chat.end_turn()
    chat.new_turn("assistant")

    audio_out = []
    with torch.no_grad():
        for t in model.generate_sequential(
            **chat, max_new_tokens=512, audio_temperature=0.8, audio_top_k=64
        ):
            if t.numel() > 1:
                audio_out.append(t)

    # Drop the trailing end-of-audio code before decoding.
    audio_codes = torch.stack(audio_out[:-1], 1).unsqueeze(0)
    waveform = processor.decode(audio_codes)

    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, waveform.cpu()[0], 24_000)
        tmp.seek(0)
        return Response(content=tmp.read(), media_type="audio/wav")
