import os
import sys
import subprocess
import urllib.request
import zipfile
import tempfile
import shutil
import cv2
import numpy as np

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

    def __init__(self, data_handler, library_path=None):
        self.data_handler = data_handler
        if library_path is None:
            # Resolve absolute path for libraries/realesrgan
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.library_path = os.path.join(base_dir, "libraries", "realesrgan")
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
        if self.data_handler.image_matrix is None:
            return 0, 0
        height, width = self.data_handler.image_matrix.shape[:2]
        return width * scale, height * scale

    @staticmethod
    def scale2x(image: np.ndarray) -> np.ndarray:
        """
        Applies the Scale2x (AdvMAME2x / EPX) algorithm to double image resolution,
        smoothing/rounding edges while strictly preserving the exact palette colors.
        """
        h, w, c = image.shape
        padded = np.pad(image, ((1, 1), (1, 1), (0, 0)), mode='edge')

        # Orthogonal neighbors of center pixel E:
        #   B
        # D E F
        #   H
        E = padded[1:-1, 1:-1]
        B = padded[0:-2, 1:-1]  # Top
        D = padded[1:-1, 0:-2]  # Left
        F = padded[1:-1, 2:]    # Right
        H = padded[2:, 1:-1]    # Bottom

        # Equality tests across color channels
        eq_DB = np.all(D == B, axis=-1)
        eq_BF = np.all(B == F, axis=-1)
        eq_DH = np.all(D == H, axis=-1)
        eq_HF = np.all(H == F, axis=-1)

        # Scale2x rules:
        # E0 = D == B and D != H and B != F ? D : E
        m0 = eq_DB & (~eq_DH) & (~eq_BF)
        # E1 = B == F and B != D and F != H ? F : E
        m1 = eq_BF & (~eq_DB) & (~eq_HF)
        # E2 = D == H and D != B and H != F ? D : E
        m2 = eq_DH & (~eq_DB) & (~eq_HF)
        # E3 = H == F and H != D and F != B ? F : E
        m3 = eq_HF & (~eq_DH) & (~eq_BF)

        E0 = np.where(m0[..., None], D, E)
        E1 = np.where(m1[..., None], F, E)
        E2 = np.where(m2[..., None], D, E)
        E3 = np.where(m3[..., None], F, E)

        out = np.empty((h * 2, w * 2, c), dtype=image.dtype)
        out[0::2, 0::2] = E0
        out[0::2, 1::2] = E1
        out[1::2, 0::2] = E2
        out[1::2, 1::2] = E3
        return out

    def palette_preserving_upscale(self, scale: int = 2, status_callback=None) -> np.ndarray | None:
        """
        Upscales the image while rounding edges and strictly preserving the original color palette.
        Uses the Scale2x (AdvMAME2x) algorithm (iterated for powers of 2).
        """
        if self.data_handler.image_matrix is None:
            if status_callback:
                status_callback("Error: No image loaded.")
            return None

        image_matrix = np.asarray(self.data_handler.image_matrix)
        if image_matrix.ndim == 2:
            image_matrix = np.stack([image_matrix] * 3, axis=-1)
        elif image_matrix.shape[-1] == 4:
            image_matrix = image_matrix[..., :3]
        elif image_matrix.shape[-1] != 3:
            raise ValueError(f"Unsupported image shape for palette-preserving upscale: {image_matrix.shape}")

        if scale <= 0:
            raise ValueError("Scale must be a positive integer.")

        if scale == 1:
            return image_matrix.copy()

        if status_callback:
            status_callback(f"Applying palette-preserving {scale}x upscale (Scale2x / AdvMAME2x)...")

        is_power_of_two = (scale & (scale - 1)) == 0
        current = image_matrix

        if is_power_of_two:
            passes = int(np.round(np.log2(scale)))
            for i in range(passes):
                if status_callback and passes > 1:
                    status_callback(f"Applying Scale2x pass {i + 1}/{passes}...")
                current = self.scale2x(current)
            upscaled_rgb = current
        else:
            passes = int(np.floor(np.log2(scale)))
            for i in range(passes):
                if status_callback:
                    status_callback(f"Applying Scale2x pass {i + 1}...")
                current = self.scale2x(current)

            orig_h, orig_w = image_matrix.shape[:2]
            target_w, target_h = orig_w * scale, orig_h * scale
            if current.shape[1] != target_w or current.shape[0] != target_h:
                if status_callback:
                    status_callback("Adjusting to target dimensions (nearest-neighbor)...")
                upscaled_rgb = cv2.resize(current, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
            else:
                upscaled_rgb = current

        self.data_handler.image_matrix = upscaled_rgb

        if status_callback:
            status_callback("Palette-preserving upscaling completed.")

        return upscaled_rgb

    def upscale(self, scale: int = 4, model: str = "realesrgan-x4plus", use_gpu: bool = True, status_callback=None, preserve_palette: bool = False) -> np.ndarray | None:
        """
        Upscales the current image in data_handler.image_matrix using the portable AI engine.
        Saves output directly back to data_handler.image_matrix and returns it.
        If preserve_palette is True, a palette-safe Scale2x (AdvMAME2x) algorithm is used instead.
        """
        if preserve_palette:
            return self.palette_preserving_upscale(scale=scale, status_callback=status_callback)

        if self.data_handler.image_matrix is None:
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
            image_matrix = self.data_handler.image_matrix
            bgr_image = cv2.cvtColor(image_matrix, cv2.COLOR_RGB2BGR)
            cv2.imwrite(temp_in, bgr_image)

            if status_callback:
                status_callback(f"Running AI super-resolution upscaling ({scale}x)...")

            # Formulate subprocess arguments
            cmd = [
                exe_path,
                "-i", temp_in,
                "-o", temp_out,
                "-s", str(scale),
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

            # Update data handler state
            self.data_handler.image_matrix = upscaled_rgb

            if status_callback:
                status_callback("Upscaling completed successfully!")

            return upscaled_rgb

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
        if self.data_handler.image_matrix is None:
            return None

        image_matrix = self.data_handler.image_matrix
        new_w, new_h = self.calculate_dimensions(scale)

        # Apply OpenCV high-quality Lanczos4 interpolation
        upscaled_rgb = cv2.resize(image_matrix, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        # Update data handler state
        self.data_handler.image_matrix = upscaled_rgb
        return upscaled_rgb
