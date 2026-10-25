from setuptools import find_packages, setup

setup(
    name="ai-sales-assistant-bot",
    version="0.1.0",
    description="Standalone Telegram AI sales assistant bot with FastAPI + OpenAI",
    packages=find_packages(include=["app", "app.*"]),
    python_requires=">=3.10",
    install_requires=[
        "alembic>=1.14.0,<2.0.0",
        "aiogram>=3.7.0,<4.0.0",
        "fastapi>=0.115.0,<1.0.0",
        "httpx>=0.27.0,<1.0.0",
        "openai>=1.65.0,<2.0.0",
        "psycopg[binary]>=3.2.0,<4.0.0",
        "pydantic-settings>=2.6.1,<3.0.0",
        "sqlalchemy>=2.0.36,<3.0.0",
        "uvicorn[standard]>=0.30.0,<1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.2.0,<9.0.0",
            "pytest-asyncio>=0.23.7,<1.0.0",
            "ruff>=0.7.0,<1.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "api=app.api.main:run",
            "bot=app.bot.main:run",
        ]
    },
)
