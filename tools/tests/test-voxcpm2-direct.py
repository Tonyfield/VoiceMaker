#!/usr/bin/env python3
"""
Direct test of VoxCPM2 model loading
"""
import sys
import os

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

# Step 1: Check voxcpm package
print("Step 1: Checking voxcpm package...")
try:
    import voxcpm
    print("✅ voxcpm package is installed")
except ImportError:
    print("❌ voxcpm package is not installed")
    print("Please install: pip install voxcpm")
    sys.exit(1)

# Step 2: Check model files
print()
print("Step 2: Checking VoxCPM2 model files...")
model_path = 'D:\\llm-models'
possible_paths = [
    model_path,
    os.path.join(model_path, "OpenBMB", "VoxCPM2"),
    os.path.join(model_path, "VoxCPM2"),
]

actual_model_path = None
for path in possible_paths:
    config_file = os.path.join(path, "config.json")
    if os.path.exists(config_file):
        print(f"✅ Found model files at: {path}")
        actual_model_path = path
        break

if not actual_model_path:
    print(f"❌ Model files not found")
    print(f"Expected location: {model_path}")
    print(f"Or subdirectory: {os.path.join(model_path, 'OpenBMB', 'VoxCPM2')}")
    sys.exit(1)

# Step 3: Load model
print()
print("Step 3: Loading VoxCPM2 model...")
print(f"⏳ Loading model from: {actual_model_path}")
print("⏳ This may take 1-3 minutes on CPU, please wait...")
print()

try:
    from voxcpm import VoxCPM
    
    # Try to load the model
    print("⏳ Initializing VoxCPM model...")
    model = VoxCPM(actual_model_path)
    
    print()
    print("✅ Model loaded successfully!")
    print()
    print("Model details:")
    print(f"  Model type: {type(model).__name__}")
    print(f"  Model path: {actual_model_path}")
    print()
    print("=" * 60)
    print("✅ Test PASSED - VoxCPM2 model is working!")
    print("=" * 60)
    sys.exit(0)

except Exception as e:
    print()
    print(f"❌ Test FAILED - Error loading model: {e}")
    print()
    import traceback
    traceback.print_exc()
    print()
    print("=" * 60)
    print("❌ Test FAILED")
    print("=" * 60)
    sys.exit(1)