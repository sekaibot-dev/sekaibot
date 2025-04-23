import base64
import ssl
from io import BytesIO

import aiohttp
from PIL import Image, ImageSequence


def compress_image(
    image_bytes: bytes,
    max_jpg_size: int,
    gif_quality: int = 75,
    max_gif_size: int = 5 * 1024 * 1024,
) -> bytes:
    """Compress an image using Pillow, with support for static and animated images.

    Converts palette-based images (P mode) to RGB for JPEG compatibility.

    :param image_bytes: Original image in bytes
    :param max_jpg_size: Maximum allowed size for JPEG output in bytes
    :param gif_quality: Quality of the GIF compression (1-100, lower is more compression)
    :param max_gif_size: Maximum allowed size for GIF in bytes. Convert to static if exceeded.
    :return: Compressed image in bytes
    """
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            buffer = BytesIO()

            if img.format == "GIF" and getattr(img, "is_animated", False):
                # Handle animated GIF
                if len(image_bytes) > max_gif_size:
                    # Convert to a static frame if GIF exceeds size limit
                    static_frame = img.convert("RGB")
                    static_frame.save(
                        buffer, format="JPEG", optimize=True, quality=gif_quality
                    )
                    return buffer.getvalue()

                # Compress animated GIF
                frames = []
                for frame in ImageSequence.Iterator(img):
                    frame = frame.copy()
                    frames.append(frame)

                frames[0].save(
                    buffer,
                    format="GIF",
                    save_all=True,
                    append_images=frames[1:],
                    optimize=True,
                    loop=img.info.get("loop", 0),
                    duration=img.info.get("duration", 100),
                    quality=gif_quality,
                )
            else:
                # Handle static images (JPEG or PNG)
                if img.format == "PNG" or img.mode == "P":
                    # Convert palette-based images (P mode) or PNG to RGBA if needed
                    if img.mode == "P":
                        img = img.convert("RGBA")

                    if img.mode in ("RGBA", "LA"):
                        # Fill transparency with white for PNG or RGBA images
                        white_background = Image.new("RGB", img.size, (255, 255, 255))
                        white_background.paste(
                            img, mask=img.split()[-1]
                        )  # Use alpha channel as mask
                        img = white_background
                    elif img.mode != "RGB":
                        # Ensure image is in RGB mode for JPEG
                        img = img.convert("RGB")

                # Compress and adjust JPEG quality to meet size requirements
                quality = 85  # Start with a default quality
                while True:
                    buffer = BytesIO()
                    img.save(buffer, format="JPEG", optimize=True, quality=quality)
                    size = buffer.tell()
                    if size <= max_jpg_size or quality <= 10:
                        break  # Exit when size is within limit or quality is very low
                    quality -= 5  # Reduce quality incrementally

            return buffer.getvalue()
    except Exception as e:
        print(f"Error compressing image: {e}")
        return image_bytes


async def fetch_image_as_base64(
    url: str,
    max_jpg_size: int = 700 * 1024,
    gif_quality: int = 55,
    max_gif_size: int = 1024 * 1024,
) -> str:
    """Fetch an image from a URL, compress it if necessary, and return its Base64 encoding.

    :param url: URL of the image to fetch
    :param max_jpg_size: Maximum allowed size for JPEG in bytes
    :param gif_quality: Quality of the GIF compression (1-100, lower is more compression)
    :param max_gif_size: Maximum allowed size for GIF in bytes. Convert to static if exceeded.
    :return: Base64 encoded string of the image
    """
    ssl_context = ssl.create_default_context()
    ssl_context.set_ciphers(
        "DEFAULT:@SECLEVEL=1"
    )  # Lower security level to support broader certificates

    async with aiohttp.ClientSession() as session:
        async with session.get(url, ssl=ssl_context) as response:
            if response.status == 200:
                image_bytes = await response.read()

                # Compress the image
                compressed_image = compress_image(
                    image_bytes, max_jpg_size, gif_quality, max_gif_size
                )

                # Convert to Base64
                return base64.b64encode(compressed_image).decode("utf-8")
            raise Exception(
                f"Failed to fetch image. HTTP status code: {response.status}"
            )


# Example usage
# You can test the code using the following:
"""async def main():
    url = "https://multimedia.nt.qq.com.cn/download?appid=1406&fileid=EhT6gGIvtKDXjJP8Jwf8LlPvhiBY_xiqoQIg_googPbnlKTFigMyBHByb2RQgLsvWhDmXAfGgZE0mtPXWT32l23H&rkey=CAISKKSBekjVG1fM8nMXosknissfUmm5p_RjAChYcxYrAXKOuFG0Ov5BXPg"
    base64_image = await fetch_image_as_base64(url)
    print(base64_image)

asyncio.run(main())"""
