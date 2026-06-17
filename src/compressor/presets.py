"""
presets.py
----------
Maps human-friendly intentions ("Instagram", "Email", "High quality")
to the actual technical numbers our compressors need.

TEACHING NOTE — the levers that control compression:
  • QUALITY       : 1..100 for images. Higher = better looking, bigger file.
  • CRF           : 0..51 for video (FFmpeg's "Constant Rate Factor").
                    LOWER = better quality, bigger file. ~20 near-lossless,
                    ~24 default, ~28 small, ~32 very small/blocky.
  • MAX_DIM/HEIGHT: longest side / height in pixels. We shrink anything bigger.
                    Most file size comes from resolution, so capping it saves a lot.
  • AUDIO_BITRATE : kbps for audio/video sound track. 128k is transparent-ish.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)  # frozen=True -> read-only, can't be changed by accident
class Preset:
    name: str
    description: str
    image_quality: int      # 1..100
    image_max_dim: int      # px, longest side
    video_crf: int          # 0..51 (lower = better)
    video_max_height: int   # px, e.g. 1080 for Full HD
    pdf_dpi: int            # target DPI for images inside PDFs
    audio_bitrate: int      # kbps for audio (and video soundtracks)


PRESETS: dict[str, Preset] = {
    "high_quality": Preset(
        name="High Quality",
        description="Barely visible quality loss. Best for archiving / pro work.",
        image_quality=90, image_max_dim=3840,
        video_crf=20, video_max_height=2160, pdf_dpi=200, audio_bitrate=192,
    ),
    "balanced": Preset(
        name="Balanced (Recommended)",
        description="Great quality, much smaller. The safe everyday choice.",
        image_quality=80, image_max_dim=1920,
        video_crf=24, video_max_height=1080, pdf_dpi=150, audio_bitrate=128,
    ),
    "small": Preset(
        name="Small Size",
        description="Noticeably smaller files, slight quality loss. Good for web.",
        image_quality=65, image_max_dim=1280,
        video_crf=28, video_max_height=720, pdf_dpi=120, audio_bitrate=96,
    ),
    "instagram": Preset(
        name="Instagram / Social",
        description="Tuned for social feeds (1080p, looks crisp on phones).",
        image_quality=80, image_max_dim=1080,
        video_crf=23, video_max_height=1080, pdf_dpi=150, audio_bitrate=128,
    ),
    "email": Preset(
        name="Email / WhatsApp (tiny)",
        description="Smallest files so they fit attachment limits.",
        image_quality=55, image_max_dim=1024,
        video_crf=30, video_max_height=480, pdf_dpi=96, audio_bitrate=64,
    ),
}

DEFAULT_PRESET = "balanced"


def get_preset(key: str) -> Preset:
    """Look up a preset by its key, falling back to 'balanced' if unknown."""
    return PRESETS.get(key, PRESETS[DEFAULT_PRESET])


def make_custom_preset(image_quality: int, image_max_dim: int,
                       video_crf: int, video_max_height: int,
                       audio_bitrate: int = 128, pdf_dpi: int = 150) -> Preset:
    """
    Build a one-off preset from the GUI's 'Advanced' sliders.
    `replace` clones the balanced preset and overrides just the fields we set.
    """
    base = PRESETS[DEFAULT_PRESET]
    return replace(
        base, name="Custom", description="Your manual settings",
        image_quality=image_quality, image_max_dim=image_max_dim,
        video_crf=video_crf, video_max_height=video_max_height,
        audio_bitrate=audio_bitrate, pdf_dpi=pdf_dpi,
    )
