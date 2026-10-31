"""Load local images into a size-limited display cache."""
from collections import OrderedDict
from markprompt_core.storage.local import PathPolicy, StorageError
try:
    from PIL import Image, ImageOps
except ImportError:
    Image = ImageOps = None
MAX_IMAGE_PIXELS = 24_000_000


class LocalImageStore:
    """Cache decoded local images at display size, within a fixed memory budget."""

    def __init__(self):
        self.cache = OrderedDict()

    def load(self, target, note, width):
        if Image is None:
            raise ValueError("Pillow unavailable")
        try:
            path = PathPolicy().image(target, note)
        except StorageError as error:
            raise ValueError(str(error)) from error
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            raise ValueError("unsupported image")
        stat = path.stat()
        if stat.st_size > 64 * 1024 * 1024:
            raise ValueError("large image file")
        key = (str(path), stat.st_mtime_ns, stat.st_size, width)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        with Image.open(path, formats=("PNG", "JPEG")) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("image dimensions too large")
            if source.format == "JPEG":
                source.draft("RGB", (max(width, 1000), max(width, 1000)))
            picture = ImageOps.exif_transpose(source)
            picture.thumbnail((width, 1000), Image.Resampling.LANCZOS)
            picture = picture.convert("RGBA").copy()
        picture._markprompt_key = key
        self.cache[key] = picture
        while len(self.cache) > 8 or sum(image.width * image.height * 4 for image in self.cache.values()) > 32 * 1024 * 1024:
            self.cache.popitem(last=False)
        return picture

