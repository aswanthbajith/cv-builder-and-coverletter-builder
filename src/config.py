"""Configuration management for the Job Automation System."""

import os
import yaml
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Singleton configuration manager."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self) -> None:
        """Load configuration from YAML file with environment variable substitution."""
        config_path = os.getenv('CONFIG_PATH', 'config.yaml')
        
        with open(config_path, 'r', encoding='utf-8') as f:
            raw_config = f.read()
        
        # Substitute environment variables
        raw_config = os.path.expandvars(raw_config)
        self._config = yaml.safe_load(raw_config)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key."""
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        
        return value
    
    @property
    def all(self) -> Dict[str, Any]:
        """Return entire configuration dictionary."""
        return self._config


# Global config instance
config = Config()
