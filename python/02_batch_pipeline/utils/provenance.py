"""
provenance.py - Prompt versioning and model tracking for audit trail.

Computes SHA-256 hashes of prompt templates so that any change to a prompt
is detectable in the output records. Also records model version strings
for reproducibility.

Usage:
    from utils.provenance import hash_prompt, get_prompt_template
    template, version, phash = get_prompt_template(config, "triage_v1")
    filled = template.replace("{text}", doc_text)

Design Decisions:
    - Hash is computed on the raw template string (before variable substitution).
    - If the config hash field says "UPDATE_AFTER_FINALIZING", the hash is
      computed at runtime and a warning is printed. Once you finalize a prompt,
      paste the computed hash into the config to lock it.
"""

import hashlib


def hash_prompt(template: str) -> str:
    """Compute SHA-256 hash of a prompt template string."""
    return hashlib.sha256(template.encode("utf-8")).hexdigest()[:16]


def get_prompt_template(config: dict, prompt_name: str) -> tuple[str, str, str]:
    """
    Retrieve a prompt template from config and compute its hash.

    Searches every top-level config section that contains a 'prompts' key, so
    prompts defined under 'scoring', 'classification', or any other section are
    all found with the same call. Last-defined section wins on name collision.

    Returns:
        (template_string, version_string, hash_string)
    """
    prompts: dict = {}
    for section in config.values():
        if isinstance(section, dict) and "prompts" in section:
            prompts.update(section["prompts"])

    if prompt_name not in prompts:
        raise KeyError(f"Prompt '{prompt_name}' not found in config. "
                       f"Available: {list(prompts.keys())}")

    prompt_cfg = prompts[prompt_name]
    template = prompt_cfg["template"]
    version = prompt_cfg["version"]
    stored_hash = prompt_cfg.get("hash", "")

    computed_hash = hash_prompt(template)

    if stored_hash == "UPDATE_AFTER_FINALIZING":
        print(f"PROVENANCE WARNING: Prompt '{prompt_name}' hash not finalized. "
              f"Computed: {computed_hash}. Update config to lock this prompt.")
    elif stored_hash and stored_hash != computed_hash:
        print(f"PROVENANCE ERROR: Prompt '{prompt_name}' hash mismatch. "
              f"Config: {stored_hash}, Computed: {computed_hash}. "
              f"The prompt template has changed since the hash was recorded.")

    return template, version, computed_hash


def hash_file(filepath: str) -> str:
    """Compute SHA-256 hash of a file's content. Used for doc_id generation."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
