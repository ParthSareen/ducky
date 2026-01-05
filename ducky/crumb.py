import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, Any, Optional


class CrumbManager:
    """Manages crumb storage for command shortcuts."""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path.home() / ".ducky"
        self.config_dir = config_dir
        self.crumbs_file = self.config_dir / "crumbs.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_crumbs(self) -> Dict[str, Any]:
        """Load crumbs from JSON file, returning empty dict if not found."""
        if not self.crumbs_file.exists():
            return {}

        try:
            with open(self.crumbs_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def save_crumbs(self, crumbs: Dict[str, Any]) -> None:
        """Save crumbs to JSON file."""
        try:
            with open(self.crumbs_file, "w") as f:
                json.dump(crumbs, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save crumbs: {e}")

    def save_crumb(
        self,
        name: str,
        prompt: str,
        response: str,
        command: str,
    ) -> None:
        """Add or update a crumb."""
        crumbs = self.load_crumbs()
        crumbs[name] = {
            "prompt": prompt,
            "response": response,
            "command": command,
            "explanation": "",
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.save_crumbs(crumbs)

    def get_crumb(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a crumb by name."""
        crumbs = self.load_crumbs()
        return crumbs.get(name)

    def list_crumbs(self) -> Dict[str, Any]:
        """Return all crumbs."""
        return self.load_crumbs()

    def delete_crumb(self, name: str) -> bool:
        """Remove a crumb. Returns True if deleted, False if not found."""
        crumbs = self.load_crumbs()
        if name in crumbs:
            del crumbs[name]
            self.save_crumbs(crumbs)
            return True
        return False

    def update_explanation(self, name: str, explanation: str) -> bool:
        """Update explanation for a crumb. Returns True if updated, False if not found."""
        crumbs = self.load_crumbs()
        if name in crumbs:
            crumbs[name]["explanation"] = explanation
            self.save_crumbs(crumbs)
            return True
        return False

    def has_crumb(self, name: str) -> bool:
        """Check if a crumb exists."""
        crumbs = self.load_crumbs()
        return name in crumbs
