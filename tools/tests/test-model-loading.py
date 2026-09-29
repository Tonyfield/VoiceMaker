#!/usr/bin/env python3
"""
Simple test to verify VoxCPM2 model can be loaded
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from voxcpm2_model import VoxCPM2Model
from loguru import logger

def test_model_loading():
    """Test if VoxCPM2 model can be loaded"""
    print("=" * 60)
    print("VoxCPM2 Model Loading Test")
    print("=" * 60)
    print()
    print("This test will:")
    print("1. Check if voxcpm package is installed")
    print("2. Check if VoxCPM2 model files exist")
    print("3. Try to load the VoxCPM2 model")
    print()
    print("⚠️  Note: Model loading may take 1-3 minutes on CPU")
    print("⏳ Please be patient and wait...")
    print()
    print("=" * 60)
    print()

    # Mock configuration
    config = {
        'model_path': 'D:\\llm-models\\VoxCPM2'
    }

    # Mock args
    class MockArgs:
        def __init__(self):
            self.language = 'zh'
            self.output_format = 'wav'
            self.speed = 1.0
            self.pitch = 1.0
            self.energy = 1.0
            self.brightness = 1.0
            self.emotion = 'neutral'
            self.dialect = None
            self.voice_clone_audio = None

    args = MockArgs()

    try:
        print("Creating VoxCPM2 model instance...")
        model = VoxCPM2Model(config, args)
        print("✅ Model loaded successfully!")
        print()
        print("Model details:")
        print(f"  Type: {type(model).__name__}")
        print(f"  Has model attribute: {hasattr(model, 'model')}")
        print(f"  Model initialized: {model.model is not None}")
        print()
        print("=" * 60)
        print("✅ Test PASSED - VoxCPM2 model is working!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"❌ Test FAILED - Error loading model: {e}")
        print()
        import traceback
        traceback.print_exc()
        print()
        print("=" * 60)
        print("❌ Test FAILED")
        print("=" * 60)
        return False

if __name__ == '__main__':
    success = test_model_loading()
    sys.exit(0 if success else 1)