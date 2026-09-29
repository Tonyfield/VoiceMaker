"""
Command-line interface for TTS Voice Cloning.

Provides commands for speech synthesis, voice profile management, and model operations.
"""
import os
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from loguru import logger

from src.config import config
from src.exceptions import ConfigurationError, TTSBaseException
from src.logger import setup_logger
from src.voice import VoiceCloner
from src.models.loader import list_models


console = Console()


def setup_logging(verbose: bool = False) -> None:
    """
    Setup logging configuration.
    
    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO.
    """
    level = "DEBUG" if verbose else "INFO"
    setup_logger(
        log_dir=str(config.log_dir),
        app_name="tts-vc",
        level=level
    )


def load_runtime_config(config_path: Optional[str] = None) -> None:
    """Load the CLI runtime configuration from the provided path or the default file."""
    resolved_path = config_path or "config.yaml"
    config.load(resolved_path)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--config", "-c", "config_path", type=click.Path(exists=True), 
              help="Path to config file")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, config_path: Optional[str]) -> None:
    """
    TTS Voice Cloning - Text-to-speech with voice cloning support.
    
    This CLI provides commands for synthesizing speech, managing voice profiles,
    and working with TTS models.
    """
    ctx.ensure_object(dict)

    try:
        load_runtime_config(config_path)
        setup_logging(verbose)
    except ConfigurationError as exc:
        console.print(f"[red]Configuration error: {exc}[/red]")
        raise SystemExit(1)

    ctx.obj["verbose"] = verbose


@cli.command()
@click.argument("text", required=False)
@click.option("--text-file", "-t", type=click.Path(exists=True), 
              help="Path to text file")
@click.option("--output", "-o", required=True, type=click.Path(), 
              help="Output audio file path")
@click.option("--reference-audio", "-r", type=click.Path(exists=True), 
              help="Reference audio for voice cloning")
@click.option("--voice-profile", "-p", help="Name of saved voice profile")
@click.option("--language", "-l", help="Language code (auto-detect if not specified)")
@click.option("--model", "-m", default="xtts", help="TTS model to use")
@click.pass_context
def synthesize(
    ctx: click.Context,
    text: Optional[str],
    text_file: Optional[str],
    output: str,
    reference_audio: Optional[str],
    voice_profile: Optional[str],
    language: Optional[str],
    model: str
) -> None:
    """
    Synthesize speech from text.
    
    TEXT is the text to synthesize. Can also be provided via --text-file.
    
    Examples:
        tts-vc synthesize "Hello world" -o output.wav
        tts-vc synthesize -t input.txt -r voice.wav -o output.wav
        tts-vc synthesize "你好世界" -p my_voice -o output.wav
    """
    # Get text from file if provided
    if text_file:
        with open(text_file, "r", encoding="utf-8") as f:
            text = f.read().strip()
    
    if not text:
        console.print("[red]Error: No text provided. Use TEXT argument or --text-file[/red]")
        raise SystemExit(1)
    
    # Check voice cloning requirements
    if not reference_audio and not voice_profile:
        console.print("[yellow]Warning: No reference audio or voice profile specified.[/yellow]")
        console.print("[yellow]Using default speaker voice.[/yellow]")
    
    try:
        cloner = VoiceCloner(model_name=model)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Synthesizing speech...", total=None)
            
            result = cloner.synthesize(
                text=text,
                output_path=output,
                reference_audio=reference_audio,
                voice_profile=voice_profile,
                language=language
            )
        
        console.print(f"[green]✓ Audio saved to: {result}[/green]")
        
    except TTSBaseException as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        logger.exception("Unexpected error during synthesis")
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise SystemExit(1)


@cli.group()
def voice() -> None:
    """Manage voice profiles."""
    pass


@voice.command("save")
@click.argument("name")
@click.argument("reference_audio", type=click.Path(exists=True))
@click.option("--language", "-l", default="auto", help="Language code")
@click.option("--description", "-d", default="", help="Profile description")
@click.pass_context
def voice_save(
    ctx: click.Context,
    name: str,
    reference_audio: str,
    language: str,
    description: str
) -> None:
    """
    Save a voice profile.
    
    NAME is the profile name.
    REFERENCE_AUDIO is the path to the reference audio file.
    
    Example:
        tts-vc voice save my_voice voice.wav -l zh-cn -d "My voice profile"
    """
    try:
        cloner = VoiceCloner()
        profile = cloner.create_voice_profile(
            name=name,
            reference_audio=reference_audio,
            language=language,
            description=description
        )
        
        console.print(f"[green]✓ Voice profile saved: {profile.name}[/green]")
        
    except TTSBaseException as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)


@voice.command("list")
@click.pass_context
def voice_list(ctx: click.Context) -> None:
    """List all saved voice profiles."""
    try:
        cloner = VoiceCloner()
        profiles = cloner.list_voice_profiles()
        
        if not profiles:
            console.print("[yellow]No voice profiles found.[/yellow]")
            return
        
        table = Table(title="Voice Profiles")
        table.add_column("Name", style="cyan")
        table.add_column("Language", style="green")
        table.add_column("Description")
        
        for name in profiles:
            profile = cloner.get_voice_profile(name)
            table.add_row(
                profile.name,
                profile.language,
                profile.description or "-"
            )
        
        console.print(table)
        
    except TTSBaseException as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)


@voice.command("delete")
@click.argument("name")
@click.pass_context
def voice_delete(ctx: click.Context, name: str) -> None:
    """
    Delete a voice profile.
    
    NAME is the profile name to delete.
    """
    try:
        cloner = VoiceCloner()
        cloner.delete_voice_profile(name)
        console.print(f"[green]✓ Voice profile deleted: {name}[/green]")
        
    except TTSBaseException as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)


@cli.group()
def models() -> None:
    """Manage TTS models."""
    pass


@models.command("list")
@click.pass_context
def models_list(ctx: click.Context) -> None:
    """List available TTS models."""
    models_dict = list_models()
    
    table = Table(title="Available TTS Models")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    
    for name, description in models_dict.items():
        table.add_row(name, description)
    
    console.print(table)


@cli.command()
@click.option("--host", "-h", default=None, help="Server host")
@click.option("--port", "-p", default=None, type=int, help="Server port")
@click.option("--share", is_flag=True, help="Create public share link")
@click.pass_context
def gui(ctx: click.Context, host: Optional[str], port: Optional[int], share: bool) -> None:
    """
    Launch the GUI interface.
    
    Starts a web-based GUI using Gradio.
    """
    try:
        from src.gui import launch_gui
        
        host = host or config.gui_host
        port = port or config.gui_port
        
        console.print(f"[cyan]Starting GUI server on {host}:{port}...[/cyan]")
        launch_gui(host=host, port=port, share=share)
        
    except ImportError:
        console.print("[red]Error: GUI dependencies not installed.[/red]")
        console.print("[yellow]Install with: pip install gradio[/yellow]")
        raise SystemExit(1)
    except Exception as e:
        logger.exception("Failed to start GUI")
        console.print(f"[red]Error starting GUI: {e}[/red]")
        raise SystemExit(1)


@cli.command()
@click.option("--host", default=None, help="Service host")
@click.option("--port", default=None, type=int, help="Service port")
@click.pass_context
def serve(ctx: click.Context, host: Optional[str], port: Optional[int]) -> None:
    """
    Launch the API service and web dashboard.

    Starts the FastAPI application used by the Docker deployment.
    """
    try:
        import uvicorn

        host = host or config.service_host
        port = port or config.service_port

        console.print(f"[cyan]Starting API service on {host}:{port}...[/cyan]")
        uvicorn.run("src.web.app:app", host=host, port=port, reload=False)

    except ImportError as exc:
        console.print(f"[red]Error: Missing service dependency: {exc}[/red]")
        raise SystemExit(1)
    except Exception as exc:
        logger.exception("Failed to start API service")
        console.print(f"[red]Error starting service: {exc}[/red]")
        raise SystemExit(1)


@cli.command("serve-model")
@click.option("--model", "model_name", default=None, help="Canonical model name served by this process")
@click.option("--host", default="0.0.0.0", help="Model service host")
@click.option("--port", default=None, type=int, help="Model service port")
@click.option("--device", default=None, help="Inference device override")
@click.pass_context
def serve_model(
    ctx: click.Context,
    model_name: Optional[str],
    host: str,
    port: Optional[int],
    device: Optional[str],
) -> None:
    """Launch a dedicated TTS model API service."""
    try:
        import uvicorn

        resolved_model = model_name or os.getenv("VOICECLONER_MODEL_NAME") or config.model_default
        resolved_port = port or int(os.getenv("VOICECLONER_MODEL_SERVICE_PORT", "20200"))
        if device:
            os.environ["VOICECLONER_MODEL_DEVICE"] = device
        os.environ["VOICECLONER_MODEL_NAME"] = resolved_model

        console.print(
            f"[cyan]Starting model service for {resolved_model} on {host}:{resolved_port}...[/cyan]"
        )
        uvicorn.run("src.model_service.app:app", host=host, port=resolved_port, reload=False)

    except ImportError as exc:
        console.print(f"[red]Error: Missing model service dependency: {exc}[/red]")
        raise SystemExit(1)
    except Exception as exc:
        logger.exception("Failed to start model service")
        console.print(f"[red]Error starting model service: {exc}[/red]")
        raise SystemExit(1)


def main() -> None:
    """Main entry point for the CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
