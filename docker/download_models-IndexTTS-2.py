from indextts.infer_v2 import IndexTTS2

print("Loading IndexTTS v2 model...")

tts = IndexTTS2(
    cfg_path="/app/models/tts_models/IndexTeam/IndexTTS-2/config.yaml",
    model_dir="/app/models/tts_models/IndexTeam/IndexTTS-2",
)

print("Auxiliary models for IndexTTS-2 downloaded successfully.")
