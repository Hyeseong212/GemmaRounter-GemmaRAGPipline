#!/usr/bin/env python3
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import torch
from PIL import Image
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModelForImageTextToText, AutoProcessor


MODEL_DIR = os.environ.get(
    "GEMMA4_BF16_MODEL_DIR",
    "/home/rbiotech-server/llama_Rest/models/gemma4-31b-bf16",
)
HOST = os.environ.get("GEMMA4_BF16_HOST", "0.0.0.0")
PORT = int(os.environ.get("GEMMA4_BF16_PORT", "18088"))
MAX_NEW_TOKENS = int(os.environ.get("GEMMA4_BF16_MAX_NEW_TOKENS", "256"))
VISION_BUDGET = int(os.environ.get("GEMMA4_BF16_VISION_BUDGET", "280"))
CHAT_TEMPLATE_PATH = os.environ.get(
    "GEMMA4_BF16_CHAT_TEMPLATE",
    "/home/rbiotech-server/llama_gemma4_latest/models/templates/google-gemma-4-31B-it.jinja",
)


tokenizer = None
model = None
chat_template = None


class InferRequest(BaseModel):
    prompt: str
    max_new_tokens: int | None = None
    temperature: float | None = None
    do_sample: bool | None = None
    image_path: str | None = None
    video_path: str | None = None


def target_device() -> str:
    first_device = next(iter(model.hf_device_map.values()))
    if isinstance(first_device, str) and first_device == "cpu":
        return "cpu"
    return f"cuda:{first_device}"


def apply_vision_budget(processor, budget: int) -> None:
    ip = getattr(processor, "image_processor", None)
    if ip is None:
        print("[gemma4-bf16] image_processor not found")
        return

    changed = {}

    if hasattr(ip, "max_soft_tokens"):
        ip.max_soft_tokens = budget
        changed["image_processor.max_soft_tokens"] = ip.max_soft_tokens

    if hasattr(ip, "image_seq_length"):
        ip.image_seq_length = budget
        changed["image_processor.image_seq_length"] = ip.image_seq_length

    if hasattr(processor, "image_seq_length"):
        processor.image_seq_length = budget
        changed["processor.image_seq_length"] = processor.image_seq_length

    print("[gemma4-bf16] vision budget applied:", changed)
    print("[gemma4-bf16] image_processor:", ip)


def build_inputs(prompt: str, image_path: str | None = None):
    content = []
    if image_path:
        image = Image.open(image_path).convert("RGB")
        content.append({"type": "image", "image": image})
    content.append({"type": "text", "text": prompt})
    messages = [{"role": "user", "content": content}]

    encoded = tokenizer.apply_chat_template(
        messages,
        chat_template=chat_template,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )

    device = target_device()
    if device == "cpu":
        return encoded
    return encoded.to(device)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global tokenizer, model, chat_template

    tokenizer = AutoProcessor.from_pretrained(MODEL_DIR)
    apply_vision_budget(tokenizer, VISION_BUDGET)

    chat_template = Path(CHAT_TEMPLATE_PATH).read_text(encoding="utf-8")
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_DIR,
        dtype=torch.bfloat16,
        device_map="auto",
        max_memory={0: "30GiB", 1: "30GiB", "cpu": "8GiB"},
    )

    yield


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
def healthz():
    ip = getattr(tokenizer, "image_processor", None) if tokenizer is not None else None
    return {
        "status": "ok",
        "model_dir": MODEL_DIR,
        "model_class": type(model).__name__ if model is not None else None,
        "vision_budget_env": VISION_BUDGET,
        "image_max_soft_tokens": getattr(ip, "max_soft_tokens", None),
        "image_seq_length": getattr(ip, "image_seq_length", None),
    }


@app.post("/infer")
def infer(req: InferRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    if req.video_path:
        raise HTTPException(
            status_code=501,
            detail="BF16 server currently supports text and image inference. video_path is not supported yet",
        )

    if req.image_path and not Path(req.image_path).exists():
        raise HTTPException(status_code=400, detail=f"image_path not found: {req.image_path}")

    encoded = build_inputs(req.prompt, req.image_path)
    prompt_len = encoded["input_ids"].shape[1]

    do_sample = bool(req.do_sample) if req.do_sample is not None else False
    temperature = req.temperature if req.temperature is not None else 0.0
    max_new_tokens = req.max_new_tokens or MAX_NEW_TOKENS

    gen_kwargs = {
        "max_new_tokens": max_new_tokens,
        "do_sample": do_sample,
        "pad_token_id": tokenizer.tokenizer.eos_token_id,
    }
    if do_sample:
        gen_kwargs["temperature"] = temperature if temperature > 0 else 0.7

    try:
        with torch.no_grad():
            output = model.generate(**encoded, **gen_kwargs)
    except torch.OutOfMemoryError as exc:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        raise HTTPException(
            status_code=507,
            detail=(
                "image inference ran out of GPU memory. "
                f"current vision budget={VISION_BUDGET}. "
                "Lower GEMMA4_BF16_VISION_BUDGET and retry."
            ),
        ) from exc
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise HTTPException(
                status_code=507,
                detail=(
                    "image inference ran out of GPU memory. "
                    f"current vision budget={VISION_BUDGET}. "
                    "Lower GEMMA4_BF16_VISION_BUDGET and retry."
                ),
            ) from exc
        raise

    text = tokenizer.decode(output[0][prompt_len:], skip_special_tokens=True).strip()
    return text


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
