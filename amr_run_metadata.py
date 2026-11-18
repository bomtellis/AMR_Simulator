"""Editable run annotations and chronological presentation, separate from evidence."""
from datetime import datetime, timezone
import re


def normalise_metadata(user_name, note):
    if not isinstance(user_name, str) or not isinstance(note, str):
        raise ValueError('Run name and note must be text.')
    user_name = user_name.strip()
    if '\x00' in user_name + note or '\n' in user_name or '\r' in user_name:
        raise ValueError('Use a single line for the run name and valid text for the note.')
    if len(user_name) > 200 or len(note) > 10000:
        raise ValueError('Use up to 200 characters for the name and 10,000 for the note.')
    return user_name, note


def run_datetime(created_at, folder_name=''):
    """Use recorded UTC creation time; recover older missing runs from their ID."""
    try:
        value = datetime.fromisoformat(created_at)
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    except (TypeError, ValueError):
        match = re.match(r'^run_(\d{8}_\d{6})_', folder_name)
        if match:
            try:
                return datetime.strptime(match[1], '%Y%m%d_%H%M%S').replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return None


def display_name(user_name, folder_name):
    if user_name:
        return user_name
    match = re.match(r'^run_\d{8}_\d{6}_[^-]+(?:-(.+))?$', folder_name)
    if match:
        return match[1].replace('-', ' ') if match[1] else 'Simulation run'
    return folder_name or 'Simulation run'
