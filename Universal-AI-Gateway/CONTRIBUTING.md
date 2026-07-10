# Contributing to Universal LLM Gateway

First off, thank you for considering contributing to the Universal LLM Gateway! It's people like you that make this tool great for the whole community.

---

## 🚀 Getting Started

Testing and development are handled via Docker and Pytest.

### 1. Local Setup

```bash
# Fork and clone the repository
git clone https://github.com/your-username/universal-llm-gateway.git
cd universal-llm-gateway

# Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Environment Configuration

Copy `.env.example` to `.env` and add your API keys. For testing without spending credits, set `MOCK_LLM=true`.

---

## 🛠️ Development Workflow

### Branching Policy

- `feat/` for new features (e.g., `feat/google-gemini-provider`)
- `fix/` for bug fixes
- `docs/` for documentation updates

### Code Style

- We use **Black** for formatting and **Ruff** for linting.
- Ensure your code follows PEP 8 standards.

### Testing Requirements

- Every new feature must include unit tests in the `tests/` directory.
- Complex logic (like token counting or budgeting) should include **Property-Based Tests** using `Hypothesis`.
- Run the full suite before submitting:

  ```bash
  pytest
  ```

---

## 📬 Pull Request Process

1. Fork and create a branch.
2. Ensure `ruff check .` passes (Linting).
3. Ensure `pytest` passes (**350+ tests**).
4. Update relevant documentation in `docs/` if you've added new functionality.
5. Submit your PR against the `main` branch.
6. Reference any related issues (e.g., `Closes #123`).
7. One of the maintainers will review your code within 1-2 business days.

---

## ⚖️ Code of Conduct

By participating in this project, you agree to abide by the terms of our **[Code of Conduct](CODE_OF_CONDUCT.md)**.
