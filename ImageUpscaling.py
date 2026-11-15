import os
import sys
import subprocess
import urllib.request
import zipfile
import tempfile
import shutil
import cv2
import numpy as np
from core import image_doc

class ImageUpscaler:
    """
    Handles AI/KI-based image upscaling using portable Real-ESRGAN-ncnn-vulkan.
    Provides instant fallback to high-quality OpenCV Lanczos4 interpolation.
    """

    DOWNLOAD_URL = "https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases/download/v0.2.0/realesrgan-ncnn-vulkan-v0.2.0-windows.zip"
    SUPPORTED_MODELS = [
        "realesrgan-x4plus",
        "realesrgan-x4plus-anime",
        "realesrnet-x4plus",
        "realesr-animevideov3"
    ]

    def __init__(self, image_matrix, library_path=None):
        self.image_matrix = image_matrix
        if library_path is None:
            # Downloaded on demand into a writable user folder (same place as the database)
            self.library_path = os.path.join(os.path.expanduser("~"), "Documents", "BildHatcher", "libraries", "realesrgan")
        else:
            self.library_path = os.path.abspath(library_path)

    def is_engine_available(self) -> bool:
        """Check if realesrgan-ncnn-vulkan.exe and models folder are present locally."""
        exe_path = os.path.join(self.library_path, "realesrgan-ncnn-vulkan.exe")
        models_dir = os.path.join(self.library_path, "models")
        return os.path.isfile(exe_path) and os.path.isdir(models_dir)

    def download_engine(self, status_callback=None) -> bool:
        """
        Synchronously downloads the portable Real-ESRGAN-ncnn-vulkan zip release 
        from GitHub and extracts it to the target library directory.
        """
        if self.is_engine_available():
            if status_callback:
                status_callback("Engine already available.")
            return True

        if status_callback:
            status_callback("Creating library directory...")
        os.makedirs(self.library_path, exist_ok=True)

        temp_zip = os.path.join(self.library_path, "realesrgan_release.zip")
        
        try:
            if status_callback:
                status_callback("Downloading Real-ESRGAN binaries (approx. 33MB)...")
            
            # Simple download wrapper
            def report_progress(block_num, block_size, total_size):
                if total_size > 0 and status_callback:
                    downloaded = block_num * block_size
                    percent = min(100, int(downloaded * 100 / total_size))
                    status_callback(f"Downloading Real-ESRGAN binaries... {percent}%")

            urllib.request.urlretrieve(self.DOWNLOAD_URL, temp_zip, reporthook=report_progress)
            
            if status_callback:
                status_callback("Extracting archive...")
            
            with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                # The official zip contains subfolders (e.g. realesrgan-ncnn-vulkan-v0.2.0-windows/)
                # Extract directly to library_path, resolving subfolder structure cleanly
                for member in zip_ref.infolist():
                    filename = member.filename
                    # Split path parts
                    parts = filename.split('/')
                    if len(parts) > 1:
                        # Skip the first folder wrapper to extract contents flatly into library_path
                        target_subpath = os.path.join(*parts[1:])
                        # If target_subpath is empty, it's just the top-level directory member itself
                        if not target_subpath:
                            continue
                        target_filepath = os.path.join(self.library_path, target_subpath)
                        if member.is_dir():
                            os.makedirs(target_filepath, exist_ok=True)
                        else:
                            os.makedirs(os.path.dirname(target_filepath), exist_ok=True)
                            with zip_ref.open(member) as source, open(target_filepath, "wb") as target:
                                shutil.copyfileobj(source, target)
                    else:
                        zip_ref.extract(member, self.library_path)

            if status_callback:
                status_callback("Ready! Cleaning up zip...")
            
            if os.path.exists(temp_zip):
                os.remove(temp_zip)
                
            return self.is_engine_available()

        except Exception as e:
            if status_callback:
                status_callback(f"Download failed: {str(e)}")
            if os.path.exists(temp_zip):
                try:
                    os.remove(temp_zip)
                except Exception:
                    pass
            return False

    def calculate_dimensions(self, scale: int) -> tuple[int, int]:
        """Calculate the resulting dimensions in pixels for a given upscale factor."""
        if self.image_matrix is None:
            return 0, 0
        height, width = self.image_matrix.shape[:2]
        return width * scale, height * scale

    def palette_preserving_upscale(self, scale: int = 2, status_callback=None) -> np.ndarray | None:
        """
        Preserves the original palette exactly by using nearest-neighbor pixel replication.
        This does not create any blended or interpolated colors.
        """
        if self.image_matrix is None:
            if status_callback:
                status_callback("Error: No image loaded.")
            return None

        image_matrix = image_doc.normalize(self.image_matrix)

        if scale <= 0:
            raise ValueError("Scale must be a positive integer.")

        if status_callback:
            status_callback(f"Applying palette-preserving {scale}x nearest-neighbor upscale...")

        # Replicate each pixel block exactly to keep every original RGB value unchanged.
        upscaled_rgb = np.repeat(np.repeat(image_matrix, scale, axis=0), scale, axis=1)
        
        if status_callback:
            status_callback("Palette-preserving upscaling completed.")

        return upscaled_rgb

    def upscale(self, scale: int = 4, model: str = "realesrgan-x4plus", use_gpu: bool = True, status_callback=None, preserve_palette: bool = False) -> np.ndarray | None:
        """
        Upscales self.image_matrix using the portable AI engine.
        Returns the upscaled image (the input is not modified).
        If preserve_palette is True, a palette-safe nearest-neighbor algorithm is used instead.
        """
        if preserve_palette:
            return self.palette_preserving_upscale(scale=scale, status_callback=status_callback)

        if self.image_matrix is None:
            if status_callback:
                status_callback("Error: No image loaded.")
            return None

        if model not in self.SUPPORTED_MODELS:
            if status_callback:
                status_callback(f"Warning: Model '{model}' is unsupported. Defaulting to 'realesrgan-x4plus'.")
            model = "realesrgan-x4plus"

        # Check if local engine binaries exist
        if not self.is_engine_available():
            if status_callback:
                status_callback("AI Engine missing. Auto-downloading...")
            success = self.download_engine(status_callback)
            if not success:
                if status_callback:
                    status_callback("AI Engine download failed. Performing high-quality Lanczos4 fallback...")
                return self.fallback_upscale(scale)

        if status_callback:
            status_callback("Preparing temporary files...")

        # Setup paths
        exe_path = os.path.join(self.library_path, "realesrgan-ncnn-vulkan.exe")
        temp_dir = tempfile.mkdtemp()
        temp_in = os.path.join(temp_dir, "input.png")
        temp_out = os.path.join(temp_dir, "output.png")

        try:
            # Convert RGB image matrix to BGR for OpenCV write
            image_matrix = self.image_matrix
            bgr_image = cv2.cvtColor(image_doc.rgb_filled(image_matrix), cv2.COLOR_RGB2BGR)  # engine needs RGB
            cv2.imwrite(temp_in, bgr_image)

            if status_callback:
                status_callback(f"Running AI super-resolution upscaling ({scale}x)...")

            # Formulate subprocess arguments
            cmd = [
                exe_path,
                "-i", temp_in,
                "-o", temp_out,
                "-s", "4",  # B22: realesrgan(-net)-x4plus models only support 4x; resized below
                "-n", model,
                "-g", "0" if use_gpu else "-1"
            ]

            # Block command window flash on Windows systems
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            result = subprocess.run(
                cmd,
                startupinfo=startupinfo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown engine error"
                raise RuntimeError(f"Engine failed (code {result.returncode}): {error_msg}")

            if not os.path.exists(temp_out) or os.path.getsize(temp_out) == 0:
                raise FileNotFoundError("Engine failed to generate the upscaled output file.")

            # Load the BGR result and convert back to RGB
            upscaled_bgr = cv2.imread(temp_out)
            if upscaled_bgr is None:
                raise ValueError("Failed to decode the upscaled image file.")

            upscaled_rgb = cv2.cvtColor(upscaled_bgr, cv2.COLOR_BGR2RGB)
            if scale != 4:
                upscaled_rgb = cv2.resize(upscaled_rgb, self.calculate_dimensions(scale), interpolation=cv2.INTER_AREA)

            
            if status_callback:
                status_callback("Upscaling completed successfully!")

            return self._with_scaled_alpha(upscaled_rgb, scale)

        except Exception as e:
            if status_callback:
                status_callback(f"AI Upscale Error: {str(e)}. Falling back to Lanczos4 upscaler...")
            return self.fallback_upscale(scale)

        finally:
            # Cleanup temp files cleanly
            if os.path.exists(temp_in):
                try:
                    os.remove(temp_in)
                except Exception:
                    pass
            if os.path.exists(temp_out):
                try:
                    os.remove(temp_out)
                except Exception:
                    pass
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass

    def fallback_upscale(self, scale: int = 4) -> np.ndarray:
        """
        Highest-quality traditional interpolation (Lanczos4)
        as an instant, robust, offline fallback.
        """
        if self.image_matrix is None:
            return None

        image_matrix = image_doc.rgb_filled(self.image_matrix)  # transparent -> white, so edges do not darken
        new_w, new_h = self.calculate_dimensions(scale)

        # Apply OpenCV high-quality Lanczos4 interpolation
        upscaled_rgb = cv2.resize(image_matrix, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        return self._with_scaled_alpha(upscaled_rgb, scale)

    def _with_scaled_alpha(self, upscaled_rgb, scale):
        """Attach the source alpha, scaled with nearest neighbour (stays binary)."""
        alpha = cv2.resize(image_doc.normalize(self.image_matrix)[..., 3], upscaled_rgb.shape[1::-1], interpolation=cv2.INTER_NEAREST)
        return image_doc.with_rgb(np.dstack([upscaled_rgb, alpha]), upscaled_rgb)
