"""Qwen2-VL model wrapper with graceful mock fallback."""
from __future__ import annotations
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class QwenVL:
    def __init__(self):
        self._model = None
        self._processor = None
        self._device = None

    async def load(self) -> None:
        if settings.MOCK_MODELS:
            logger.info("MOCK_MODELS=true — Qwen VL in mock mode")
            return
        try:
            import torch
            from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading {settings.VISION_MODEL} on {self._device}...")

            self._processor = AutoProcessor.from_pretrained(
                settings.VISION_MODEL,
                cache_dir=settings.MODEL_CACHE_PATH,
            )
            self._model = Qwen2VLForConditionalGeneration.from_pretrained(
                settings.VISION_MODEL,
                torch_dtype=torch.float16 if self._device == "cuda" else torch.float32,
                device_map=self._device,
                cache_dir=settings.MODEL_CACHE_PATH,
            )
            logger.info("Qwen VL model loaded")
        except Exception as e:
            logger.warning(f"Qwen VL load failed — mock mode: {e}")
            self._model = None

    async def analyze_image(self, image_path: str, prompt: str) -> str:
        """Run VL inference on an image with a text prompt."""
        if self._model is None:
            return self._mock_response(image_path, prompt)

        try:
            import torch
            from PIL import Image
            from qwen_vl_utils import process_vision_info

            image = Image.open(image_path).convert("RGB")
            max_size = settings.VISION_MAX_IMAGE_SIZE
            image.thumbnail((max_size, max_size))

            messages = [{
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }]

            text = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self._processor(
                text=[text],
                images=image_inputs,
                return_tensors="pt",
            ).to(self._device)

            with torch.no_grad():
                output_ids = self._model.generate(**inputs, max_new_tokens=1024)

            trimmed = [out[len(inp):] for inp, out in zip(inputs.input_ids, output_ids)]
            return self._processor.batch_decode(trimmed, skip_special_tokens=True)[0]

        except Exception as e:
            logger.error(f"VL inference failed: {e}")
            return self._mock_response(image_path, prompt)

    def _mock_response(self, image_path: str, prompt: str) -> str:
        from pathlib import Path
        name = Path(image_path).stem
        return (
            f'{{"diagram_type": "architecture_diagram", '
            f'"description": "Mock analysis of {name}. Configure GPU and set MOCK_MODELS=false for real VL inference.", '
            f'"entities": ["{name}"], '
            f'"text_overlay": "", '
            f'"relationships": []}}'
        )

    def get_clip_embedding(self, image_path: str) -> list[float]:
        """CLIP visual embedding for image similarity search."""
        import numpy as np
        if settings.MOCK_MODELS or self._model is None:
            return np.random.randn(512).tolist()

        try:
            import torch
            from PIL import Image
            from transformers import CLIPModel, CLIPProcessor

            if not hasattr(self, '_clip'):
                self._clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
                self._clip_proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

            img = Image.open(image_path).convert("RGB")
            inputs = self._clip_proc(images=img, return_tensors="pt")
            with torch.no_grad():
                feats = self._clip.get_image_features(**inputs)
            return feats.squeeze().numpy().tolist()
        except Exception as e:
            logger.warning(f"CLIP embedding failed: {e}")
            return np.random.randn(512).tolist()
