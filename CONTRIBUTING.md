# Contributing to ClubHub

Thank you for your interest in contributing to ClubHub! We welcome contributions from developers of all skill levels.

## Code of Conduct
Please review and adhere to our [Code of Conduct](CODE_OF_CONDUCT.md) in all project spaces and interactions.

## Development Workflow

### 1. Setting Up Your Development Environment
1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/clubhub.git
   cd clubhub
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Linux / macOS:
   source venv/bin/activate
   ```
3. Install dependencies in editable mode:
   ```bash
   pip install -e ".[dev,sheets]"
   ```
4. Copy the environment and configuration files:
   ```bash
   cp .env.example .env
   cp config.example.yaml config.yaml
   ```
   Add your test bot token to `.env` and configure your test Discord server in `config.yaml`.

### 2. Running Tests
Ensure all unit and integration tests pass before submitting code:
```bash
pytest
```

### 3. Coding Standards
- Follow PEP 8 style guidelines.
- Use explicit type annotations where appropriate.
- Ensure all Discord UI components have persistent `custom_id`s where state survival across restarts is required.
- Do not hardcode role names, channel IDs, or community identifiers in the bot core. Everything must be driven through the configuration and database layers.
- Maintain test coverage for newly introduced features, state changes, or database models.

### 4. Submitting Pull Requests
1. Fork the repo and create a topic branch from `main`.
2. Commit your changes with clear, descriptive commit messages.
3. Push to your fork and submit a Pull Request describing your changes, referencing any relevant issues or proposal sections.
