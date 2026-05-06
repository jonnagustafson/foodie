
# Project
This is an application visualize food habits by importing digital reciepts. The application analyzes your purchase patterns, favorite items, money spent, volume and nutritions.

# Tech stack
Python 3.11
Pytest for tests

# Code conventions
Format with Black (default settings).
Type hints on all public functions.
Google-style docstrings on modules and public functions.
Naming: snake_case for functions and variables, PascalCase for classes.

# Architecture
All I/O (API calls, file reads) lives in integrations/. Business logic in core/ must never call external services directly.
Functions do one thing. If a function needs a comment to explain what it does, split it.
No global variables or global state. Pass configuration as arguments.
All external calls must have explicit error handling. Never swallow exceptions.
Tests are written alongside implementation, not after.

# Rules
Do not add or swap dependencies without asking.
Do not change the CLI interface (command names, flags) — it affects existing users.
Do not create config files beyond .env.example. Configuration is done via environment variables.
Never commit directly to main. Work in feature branches.
Do not add logging beyond what exists in utils/logger.py.

# Project structure
/
├── CLAUDE.md
└── README.md