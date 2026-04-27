from setuptools import setup, find_packages

setup(
    name="moodle-time-tracker",
    version="1.0.0",
    description="Moodle student time tracking engine based on site-level logs",
    author="phuquocchamp",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "moodle-tracker=moodle_tracker.engine:main",
        ],
    },
)
