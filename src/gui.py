"""
Web-based GUI interface for TTS Voice Cloning using Gradio.
"""
from pathlib import Path
from typing import Optional, Tuple
import tempfile
import os

import gradio as gr
from loguru import logger

from src import setup_logger, config
from src.voice import VoiceCloner, VoiceProfile
from src.models.loader import list_models
from src.exceptions import TTSBaseException


# Initialize voice cloner (lazy loaded)
_cloner: Optional[VoiceCloner] = None


def get_cloner() -> VoiceCloner:
    """Get or create the voice cloner instance."""
    global _cloner
    if _cloner is None:
        _cloner = VoiceCloner()
    return _cloner


def synthesize_speech(
    text: str,
    reference_audio: Optional[str],
    voice_profile: Optional[str],
    language: str,
    model: str,
    progress=gr.Progress()
) -> Tuple[str, str]:
    """
    Synthesize speech from text.
    
    Args:
        text: Text to synthesize
        reference_audio: Path to reference audio file
        voice_profile: Name of saved voice profile
        language: Language code
        model: TTS model to use
        progress: Gradio progress tracker
        
    Returns:
        Tuple of (output_audio_path, status_message)
    """
    if not text or not text.strip():
        return None, "❌ Error: Please enter text to synthesize."
    
    try:
        progress(0.1, desc="Loading model...")
        cloner = get_cloner()
        
        # Create output path
        output_dir = config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"output_{os.getpid()}.wav"
        
        progress(0.3, desc="Synthesizing speech...")
        
        result = cloner.synthesize(
            text=text,
            output_path=str(output_path),
            reference_audio=reference_audio,
            voice_profile=voice_profile if voice_profile else None,
            language=language if language != "auto" else None,
            model_name=model
        )
        
        progress(1.0, desc="Done!")
        
        return str(result), f"✅ Audio saved to: {result}"
        
    except TTSBaseException as e:
        logger.error(f"Synthesis error: {e}")
        return None, f"❌ Error: {e}"
    except Exception as e:
        logger.exception("Unexpected error during synthesis")
        return None, f"❌ Unexpected error: {e}"


def save_voice_profile(
    name: str,
    reference_audio: str,
    language: str,
    description: str
) -> Tuple[str, list]:
    """
    Save a voice profile.
    
    Args:
        name: Profile name
        reference_audio: Path to reference audio
        language: Language code
        description: Profile description
        
    Returns:
        Tuple of (status_message, updated_profile_list)
    """
    if not name or not name.strip():
        return "❌ Error: Please enter a profile name.", get_profile_choices()
    
    if not reference_audio:
        return "❌ Error: Please upload a reference audio file.", get_profile_choices()
    
    try:
        cloner = get_cloner()
        cloner.create_voice_profile(
            name=name.strip(),
            reference_audio=reference_audio,
            language=language,
            description=description
        )
        
        return f"✅ Voice profile saved: {name}", get_profile_choices()
        
    except TTSBaseException as e:
        logger.error(f"Profile save error: {e}")
        return f"❌ Error: {e}", get_profile_choices()
    except Exception as e:
        logger.exception("Unexpected error saving profile")
        return f"❌ Unexpected error: {e}", get_profile_choices()


def get_profile_choices() -> list:
    """Get list of voice profile names."""
    try:
        cloner = get_cloner()
        return cloner.list_voice_profiles()
    except Exception:
        return []


def get_model_choices() -> list:
    """Get list of available model names."""
    return list(list_models().keys())


def create_interface() -> gr.Blocks:
    """Create the Gradio interface."""
    
    with gr.Blocks(
        title="TTS Voice Cloning",
        theme=gr.themes.Soft(),
        css="""
        .gradio-container {
            max-width: 1200px !important;
        }
        .output-audio {
            min-height: 100px;
        }
        """
    ) as interface:
        
        gr.Markdown(
            """
            # 🎙️ TTS Voice Cloning Studio
            
            Convert text to speech with voice cloning capabilities.
            Upload a reference audio to clone a voice, or use a saved voice profile.
            """
        )
        
        with gr.Row():
            # Left column - Input
            with gr.Column(scale=2):
                gr.Markdown("### 📝 Input")
                
                text_input = gr.Textbox(
                    label="Text to Synthesize",
                    placeholder="Enter the text you want to convert to speech...",
                    lines=5,
                    max_lines=10
                )
                
                with gr.Row():
                    text_file_btn = gr.UploadButton(
                        "Load from File",
                        file_types=[".txt"],
                        type="filepath"
                    )
                
                gr.Markdown("### 🎤 Voice Cloning")
                
                with gr.Tabs():
                    with gr.TabItem("Upload Reference"):
                        reference_audio = gr.Audio(
                            label="Reference Audio",
                            type="filepath",
                            sources=["upload", "microphone"]
                        )
                        gr.Markdown(
                            "_Upload an audio file (6+ seconds) containing the voice you want to clone._"
                        )
                    
                    with gr.TabItem("Use Profile"):
                        voice_profile = gr.Dropdown(
                            label="Voice Profile",
                            choices=get_profile_choices(),
                            interactive=True
                        )
                        refresh_profiles_btn = gr.Button("🔄 Refresh Profiles", size="sm")
                
                with gr.Row():
                    language = gr.Dropdown(
                        label="Language",
                        choices=[
                            ("Auto Detect", "auto"),
                            ("Chinese", "zh-cn"),
                            ("English", "en"),
                            ("Japanese", "ja"),
                            ("Korean", "ko"),
                            ("French", "fr"),
                            ("German", "de"),
                            ("Spanish", "es")
                        ],
                        value="auto"
                    )
                    
                    model = gr.Dropdown(
                        label="TTS Model",
                        choices=get_model_choices(),
                        value="xtts"
                    )
            
            # Right column - Output
            with gr.Column(scale=1):
                gr.Markdown("### 🔊 Output")
                
                output_audio = gr.Audio(
                    label="Generated Speech",
                    type="filepath",
                    interactive=False,
                    elem_classes=["output-audio"]
                )
                
                status_output = gr.Textbox(
                    label="Status",
                    interactive=False,
                    lines=2
                )
                
                synthesize_btn = gr.Button(
                    "🎵 Generate Speech",
                    variant="primary",
                    size="lg"
                )
        
        gr.Markdown("---")
        
        # Voice Profile Management Section
        with gr.Accordion("📁 Voice Profile Management", open=False):
            gr.Markdown("### Save New Voice Profile")
            
            with gr.Row():
                profile_name = gr.Textbox(
                    label="Profile Name",
                    placeholder="Enter a name for this voice profile..."
                )
                
                profile_language = gr.Dropdown(
                    label="Language",
                    choices=[
                        ("Auto", "auto"),
                        ("Chinese", "zh-cn"),
                        ("English", "en"),
                        ("Japanese", "ja"),
                        ("Korean", "ko")
                    ],
                    value="auto"
                )
            
            profile_description = gr.Textbox(
                label="Description (optional)",
                placeholder="Add a description for this profile...",
                lines=2
            )
            
            profile_audio = gr.Audio(
                label="Reference Audio for Profile",
                type="filepath",
                sources=["upload", "microphone"]
            )
            
            save_profile_btn = gr.Button("💾 Save Voice Profile")
            profile_status = gr.Textbox(label="Status", interactive=False)
        
        # Event handlers
        def load_text_file(file_path):
            """Load text from uploaded file."""
            if file_path:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception as e:
                    return f"Error loading file: {e}"
            return ""
        
        text_file_btn.upload(
            fn=load_text_file,
            inputs=[text_file_btn],
            outputs=[text_input]
        )
        
        synthesize_btn.click(
            fn=synthesize_speech,
            inputs=[text_input, reference_audio, voice_profile, language, model],
            outputs=[output_audio, status_output]
        )
        
        refresh_profiles_btn.click(
            fn=lambda: gr.Dropdown(choices=get_profile_choices()),
            outputs=[voice_profile]
        )
        
        save_profile_btn.click(
            fn=save_voice_profile,
            inputs=[profile_name, profile_audio, profile_language, profile_description],
            outputs=[profile_status, voice_profile]
        )
        
        # Footer
        gr.Markdown(
            """
            ---
            **TTS Voice Cloning** v0.5.2 | Powered by Coqui XTTS v2
            """
        )
    
    return interface


def launch_gui(
    host: str = "0.0.0.0",
    port: int = 7860,
    share: bool = False
):
    """
    Launch the Gradio GUI.
    
    Args:
        host: Server host address
        port: Server port
        share: Whether to create a public share link
    """
    if not config._config:
        config.load()

    # Setup logging
    setup_logger(
        log_dir=str(config.log_dir),
        app_name="tts-vc",
        level=config.log_level
    )
    
    logger.info(f"Starting GUI server on {host}:{port}")
    
    interface = create_interface()
    interface.launch(
        server_name=host,
        server_port=port,
        share=share,
        show_error=True
    )


if __name__ == "__main__":
    launch_gui()
