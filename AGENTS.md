# AGENTS.md - Repository Guidelines for AI Coding Agents

Welcome! This document provides context, technology stack overviews, development workflows, testing commands, and security guardrails to help AI coding agents work efficiently and safely on this repository.

---

## 1. Project Overview & Architecture

Arbitrage Arena is a sports arbitrage analytics engine and decentralized monetization platform. It consists of:
* **Arbitrage Engine (`engine.py`, `main.py`)**: Fetches sports match data via RapidAPI, analyzes odds anomalies, and broadcasts signals to Telegram channels.
* **FastAPI Backend (`app.py`)**: Serves the user interface, tracks subscriptions in Listmonk, and manages local sqlite3 databases.
* **Web3 Integration (`watcher.py`, `contract/`, `pages/`)**: A Next.js frontend with RainbowKit/Wagmi and a Solidity contract (`ArbitrageArenaPass.sol`) that manages stablecoin-based (USDC/USDT) memberships. An asynchronous watcher daemon (`watcher.py`) monitors on-chain events and handles Listmonk state synchronization.
* **Self-Hosted Email Service (`listmonk/`)**: Dockerized Listmonk newsletter engine, PostgreSQL, and Mailpit SMTP server for transactional reminders.

---

## 2. Technology Stack

* **Backend**: Python 3.10+ (FastAPI, Web3.py, python-telegram-bot, pytest)
* **Frontend**: React, Next.js, TypeScript, Wagmi, RainbowKit
* **Smart Contracts**: Solidity (EVM)
* **Containers**: Docker Compose, PostgreSQL 17, Mailpit, Listmonk app

---

## 3. Dev Environment & Setup Tips

* **Environment Setup**: Copy `.env.example` to `.env` and configure credentials.
* **Dependencies**: Install Python packages via:
  ```bash
  pip install -r requirements.txt
  ```
* **Database & Services**: Start the local Listmonk mailing services via:
  ```bash
  docker compose up -d
  ```
* **Web backend**: Run the FastAPI application using:
  ```bash
  python app.py
  ```
* **Web3 Watcher Daemon**: Start the on-chain subscription listener using:
  ```bash
  python watcher.py
  ```

---

## 4. Testing Instructions

* **Pytest Suite**: Run all automated tests via:
  ```bash
  pytest
  ```
* **Test Isolation**: Seeding of realistic logs in the SQLite database (`agent_memory.db`) is automatically bypassed when unit test suites (`pytest` or `unittest`) are active. This prevents database state pollution. Do not change this check in `backtest_handler.py`.

---

## 5. Security & Safety Guardrails (MANDATORY)

To keep this project safe from security vulnerabilities:
* **No Hardcoded Secrets**: Under no circumstances should you write API keys, Telegram Bot Tokens, passwords, or credentials directly into code, Docker Compose, or static files.
* **Configuration Validation**: All critical configurations must load via `config.py`. The `Config.validate()` method executes at startup to check for missing keys, template placeholders, and known compromised credentials. Do not bypass this check.
* **Git Hygiene**: Keep `.env`, SQLite databases (`*.db`), and cached JSON state files in `.gitignore`. Do not track them.
* **Gitleaks Scan**: Every commit is audited locally via a pre-commit Gitleaks hook and in GitHub CI. Ensure all your changes are secret-free before submitting.
