from setuptools import setup, find_packages
from pathlib import Path

requirements = [
    line.split("#", 1)[0].strip()
    for line in Path(__file__).with_name("requirements.txt").read_text(encoding="utf-8").splitlines()
    if line.split("#", 1)[0].strip()
]

setup(
    name="openmontage",
    version="0.1.0",
    description="AI-Orchestrated Video Production Platform",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.12",
    install_requires=requirements,
    package_data={
        "lib": ["env_policy.json"],
        "backlot": ["ui/*.html", "ui/*.js", "ui/*.css"],
        "schemas": ["artifacts/*.json", "checkpoints/*.json", "pipelines/*.json", "styles/*.json", "tools/*.json"],
        "styles": ["*.yaml"],
    },
)
