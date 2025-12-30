import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigManager:
    """Manages Ducky configuration including model preferences."""
    
    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path.home() / ".ducky"
        self.config_dir = config_dir
        self.config_file = self.config_dir / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file, returning defaults if not found."""
        default_config = {
            "last_model": "glm-4.7:cloud",
            "last_host": "https://ollama.com"
        }
        
        if not self.config_file.exists():
            return default_config
            
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                # Ensure all required keys are present
                for key in default_config:
                    if key not in config:
                        config[key] = default_config[key]
                return config
        except (json.JSONDecodeError, IOError):
            return default_config
    
    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save config: {e}")
    
    def get_last_model(self) -> tuple[str, str]:
        """Get the last used model and host.

        Returns:
            Tuple of (model_name, host)
        """
        config = self.load_config()
        return config.get("last_model", "glm-4.7:cloud"), config.get("last_host", "https://ollama.com")
    
    def save_last_model(self, model_name: str, host: str) -> None:
        """Save the last used model and host."""
        config = self.load_config()
        config["last_model"] = model_name
        config["last_host"] = host
        self.save_config(config)
