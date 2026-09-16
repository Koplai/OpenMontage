"""Legacy diagnostics run explicitly via make test-qa, never during collection."""

collect_ignore = [
    "test_04_audio_mix.py",
    "test_05_video_compose.py",
    "test_06_video_stitch.py",
    "test_07_playbook_intelligence.py",
    "test_08_end_to_end.py",
]
