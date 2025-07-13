import base64
from io import BytesIO

from PIL import Image


def compress_image_from_file(
    file_path: str,
    max_jpg_size: int = 700 * 1024,
    quality_step: int = 5,
    max_dimensions: tuple = (1024, 1024),
) -> bytes:
    """Compress an image file, resize if necessary, convert to JPEG, and return compressed bytes."""
    try:
        with Image.open(file_path) as img:
            # 如果是动图，只取第一帧
            if getattr(img, "is_animated", False):
                img = img.convert("RGBA")
            else:
                img = img.copy()

            # 如果尺寸超过 max_dimensions，等比缩放
            img.thumbnail(max_dimensions, Image.LANCZOS)

            # 转换模式：确保是 RGB
            if img.mode in ("RGBA", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            buffer = BytesIO()
            quality = 85

            # 循环压缩直到达到目标大小
            while True:
                buffer.seek(0)
                buffer.truncate()
                img.save(buffer, format="JPEG", optimize=True, quality=quality)
                size = buffer.tell()
                if size <= max_jpg_size or quality <= 10:  # noqa: PLR2004
                    break
                quality -= quality_step

            return buffer.getvalue()

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None


def image_file_to_base64_jpg(file_path: str) -> str:
    """Compress image and return Base64-encoded JPEG."""
    compressed_bytes = compress_image_from_file(file_path)
    if compressed_bytes:
        return base64.b64encode(compressed_bytes).decode("utf-8")
    return ""


if __name__ == "__main__":
    import time

    t = time.time()
    img = image_file_to_base64_jpg("C:/Users/86137/Downloads/GnEBHefbUAAsUmF.jpg")
    print(time.time() - t)
    padding = img.count("=")
    print(((len(img) * 3) // 4 - padding) / 1024)
