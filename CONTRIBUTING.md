# Contributing to DorsalHub Open Validation Schemas

First off, thank you for considering contributing! This project thrives on community involvement, and we appreciate any contribution, from a small typo fix to a proposal for a brand-new schema.

This document provides a set of guidelines for contributing to the `dorsal/open-validation-schemas` repository.

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](./CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How Can I Contribute?

There are two main ways to contribute to this project:

### 1. Suggesting Improvements or Reporting Bugs

If you find a problem with an existing schema, see a way to improve a description, or have a suggestion, please **[open an issue](https://github.com/dorsalhub/open-valkidation-schemas/issues)**.
- For bugs, please use the "Bug Report" template.
- For improvements, feel free to use a blank issue and provide a clear description of your suggestion.

### 2. Proposing a New Schema

If you have an idea for a new, generic open validation schema that would be valuable to the community, we'd love to hear it! Please follow this process:

1.  **Check for existing proposals:** Make sure a similar idea hasn't already been discussed in the issues.
2.  **Open an issue:** Create a new issue using the "New Schema Proposal" template. This is the place to discuss the use case, the name, and the key fields of your proposed schema. The goal is to get community and maintainer feedback before starting on a full pull request.
3.  **Create a Pull Request:** Once the proposal has been discussed and has a clear direction, you can open a pull request to add the new schema.

## Pull Request Process

1.  **Fork the repository** and create your branch from `main`.
2.  **Add your new schema file** to the `/schemas` directory, following the `schema-name.json` naming convention.
3.  **Add Examples:**
    * Add at least one valid example to `/examples/positive/schema-name-1.json`.
    * Add at least one invalid example to `/examples/negative/schema-name-invalid.json` to demonstrate constraint enforcement.
4.  **Run Tests Locally:**
    * Install `uv` (if not installed): `curl -LsSf https://astral.sh/uv/install.sh | sh`
    * Run the test suite: `uv run pytest`
    * Ensure all tests pass before submitting.
5.  **Update the main `README.md`** to include a section for your new schema in the "Available Schemas" list.
6.  **Submit the Pull Request.**

### Style Guide for Schemas

Please refer to the internal [Style Guide](./STYLEGUIDE.md) for new contributions.

Thank you again for your interest in making DorsalHub a better platform for everyone!