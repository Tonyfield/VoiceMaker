from indextts.infer_v2_5 import IndexTTS2

print("Loading IndexTTS v2.5 model...")

tts = IndexTTS2(
    cfg_path="/app/models/tts_models/IndexTeam/IndexTTS-2.5/config.yaml",
    model_dir="/app/models/tts_models/IndexTeam/IndexTTS-2.5",
)

print("Auxiliary models for IndexTTS-2.5 downloaded successfully.")
