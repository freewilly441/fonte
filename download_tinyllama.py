#!/usr/bin/env python3
"""
Download TinyLlama GGML model for Fonte Android
Supports Hugging Face and direct downloads
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple

class TinyLlamaDownloader:
    """Download and verify TinyLlama model"""
    
    # Model information
    MODEL_NAME = "TinyLlama 1.1B Chat v1.0 (Q4_K_M)"
    MODEL_SIZE_MB = 690
    MODEL_FILENAME = "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
    
    # Download sources
    HF_REPO = "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGML"
    HF_MIRROR = "https://huggingface.co"
    HF_API = "https://huggingface-api.github.io"
    
    def __init__(self, output_dir: str = "."):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.output_dir / self.MODEL_FILENAME
    
    def print_header(self):
        """Print colored header"""
        print("\n" + "=" * 70)
        print(" " * 15 + "TinyLlama Model Download for Fonte Android")
        print("=" * 70)
        print(f"\nModel: {self.MODEL_NAME}")
        print(f"Size: ~{self.MODEL_SIZE_MB} MB")
        print(f"Output: {self.model_path}")
        print("\n" + "=" * 70 + "\n")
    
    def check_existing(self) -> bool:
        """Check if model already exists"""
        if self.model_path.exists():
            size_mb = self.model_path.stat().st_size / (1024 * 1024)
            print(f"✓ Model file already exists")
            print(f"  Path: {self.model_path}")
            print(f"  Size: {size_mb:.2f} MB")
            return True
        return False
    
    def progress_hook(self, block_num: int, block_size: int, total_size: int):
        """Print download progress"""
        if total_size <= 0:
            return
        
        downloaded = block_num * block_size
        percent = min(downloaded * 100.0 / total_size, 100.0)
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        
        bar_length = 40
        filled = int(bar_length * percent / 100)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        print(f"\r[{bar}] {percent:5.1f}% ({downloaded_mb:6.1f}/{total_mb:6.1f} MB)", end='')
        sys.stdout.flush()
    
    def build_download_url(self) -> str:
        """Build the download URL for the model"""
        # Direct HuggingFace CDN URL
        return (
            f"{self.HF_MIRROR}/{self.HF_REPO}/resolve/main/"
            f"{self.MODEL_FILENAME}?download=true"
        )
    
    def download_model(self, url: str) -> bool:
        """Download the model file"""
        print(f"Downloading TinyLlama GGML model...")
        print(f"From: {url}\n")
        
        try:
            urllib.request.urlretrieve(
                url,
                self.model_path,
                reporthook=self.progress_hook
            )
            print("\n✓ Download completed successfully!")
            return True
            
        except urllib.error.HTTPError as e:
            print(f"\n✗ HTTP Error {e.code}: {e.reason}")
            print(f"  This might be a rate limit or temporary issue")
            print(f"  Try downloading manually from: {url}")
            return False
            
        except urllib.error.URLError as e:
            print(f"\n✗ Network Error: {e.reason}")
            print(f"  Check your internet connection")
            return False
            
        except Exception as e:
            print(f"\n✗ Download failed: {e}")
            return False
    
    def verify_model(self) -> bool:
        """Verify downloaded model"""
        if not self.model_path.exists():
            print("✗ Model file not found after download")
            return False
        
        size_bytes = self.model_path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        
        # Check file size is reasonable (between 500-900 MB for Q4_K_M)
        if size_bytes < 500 * 1024 * 1024 or size_bytes > 900 * 1024 * 1024:
            print(f"✗ Model file size seems wrong: {size_mb:.2f} MB")
            print(f"  Expected: ~690 MB")
            return False
        
        # Check for GGML magic number
        try:
            with open(self.model_path, 'rb') as f:
                header = f.read(4)
                if header != b'GGUF':  # GGML files have GGUF header
                    print(f"⚠ Warning: File header doesn't look like GGML")
                    print(f"  Header: {header}")
                    return False
        except Exception as e:
            print(f"✗ Could not verify file: {e}")
            return False
        
        print(f"✓ Model file verified")
        print(f"  Size: {size_mb:.2f} MB")
        print(f"  Location: {self.model_path}")
        return True
    
    def copy_to_android_assets(self, android_path: Optional[str] = None) -> bool:
        """Copy model to Android assets directory"""
        if android_path is None:
            # Try to find the android project
            current = Path.cwd()
            if (current / "android").exists():
                android_path = current / "android"
            elif (current / "fonte" / "android").exists():
                android_path = current / "fonte" / "android"
            else:
                print("\n⚠ Could not find android project directory")
                print("  Manually copy the model to:")
                print("  android/app/src/main/assets/models/model.tflite")
                return False
        
        android_path = Path(android_path)
        assets_dir = android_path / "app" / "src" / "main" / "assets" / "models"
        assets_dir.mkdir(parents=True, exist_ok=True)
        
        target_path = assets_dir / "model.tflite"
        
        print(f"\nCopying model to Android assets...")
        try:
            import shutil
            shutil.copy(self.model_path, target_path)
            print(f"✓ Model copied to Android")
            print(f"  Location: {target_path}")
            print(f"  Size: {target_path.stat().st_size / (1024 * 1024):.2f} MB")
            return True
        except Exception as e:
            print(f"✗ Copy failed: {e}")
            return False
    
    def run(self, copy_to_assets: bool = True) -> bool:
        """Run the complete download process"""
        self.print_header()
        
        # Check if already exists
        if self.check_existing():
            print("\nModel is ready to use!")
            if copy_to_assets:
                return self.copy_to_android_assets()
            return True
        
        # Download
        url = self.build_download_url()
        if not self.download_model(url):
            print("\n" + "=" * 70)
            print("Download failed. Try these alternatives:")
            print("=" * 70)
            print("\n1. Manual Download:")
            print(f"   Visit: {url}")
            print(f"   Save to: {self.model_path}")
            print("\n2. Use a download manager (e.g., IDM, Aria2)")
            print("\n3. Use curl from command line:")
            print(f"   curl -L -o \"{self.model_path}\" \"{url}\"")
            return False
        
        # Verify
        print()
        if not self.verify_model():
            print("✗ Model verification failed")
            self.model_path.unlink(missing_ok=True)
            return False
        
        # Copy to Android assets
        if copy_to_assets:
            print()
            if not self.copy_to_android_assets():
                print("\n⚠ Model downloaded but not copied to Android assets")
                print(f"  Manual copy: {self.model_path}")
                print(f"  To: android/app/src/main/assets/models/model.tflite")
        
        print("\n" + "=" * 70)
        print("✓ Setup complete!")
        print("=" * 70)
        print("\nNext steps:")
        print("1. Build the Android project:")
        print("   cd android")
        print("   gradlew.bat clean build -x test")
        print("\n2. Deploy to emulator:")
        print("   adb install app/build/outputs/apk/debug/app-debug.apk")
        print("\n3. Launch the app and test!")
        print()
        
        return True


def main():
    """Main entry point"""
    downloader = TinyLlamaDownloader()
    
    try:
        success = downloader.run(copy_to_assets=True)
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n✗ Download cancelled by user")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
